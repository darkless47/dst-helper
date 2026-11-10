"""Acceptance checks against the real combined HTTP app and isolated user stores."""
import hashlib
from contextlib import closing
import http.client
from itertools import combinations
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from dst_helper.farming import FarmingPlanner, PlanConflict, PlanStore, STRESS_KEYS
from dst_helper.server import create_server, cooking

ROOT = Path(__file__).resolve().parents[1]


class PlannerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = FarmingPlanner()

    def test_all_sixteen_season_subsets_match_handoff(self):
        expected = json.loads((ROOT / 'DST_Farming_v0_1/REFERENCE_COMPARISON.json').read_text(encoding='utf-8'))['ratio_counts_by_filter']
        for size in range(5):
            for seasons in combinations(sorted(('autumn', 'winter', 'spring', 'summer')), size):
                plan = self.planner.defaults()
                plan['seasons'] = list(seasons)
                answer = self.planner.analyze(plan)
                key = '+'.join(seasons) or 'no_filter'
                self.assertEqual(len(answer['ratios']), expected[key], key)
                if seasons == ('winter',):
                    self.assertEqual(len(answer['eligible']), 5)
                if size == 4:
                    self.assertEqual(answer['eligible'], ['garlic'])

    def test_stock_is_optional_but_zero_excludes_and_scale_respects_caps(self):
        p = self.planner.defaults()
        p.update(seasons=['spring'], available=['potato', 'tomato'], inventory={'potato': 4}, scale=4)
        r = self.planner.analyze(p)['ratios']
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['counts'], {'potato': 1, 'tomato': 1})
        self.assertEqual(r[0]['max_inventory_scale'], 4)
        self.assertEqual(r[0]['scaled']['seed_counts'], {'potato': 4, 'tomato': 4})
        self.assertEqual(r[0]['scaled']['area_lower_bound_9_slots'], 1)
        self.assertFalse(r[0]['spatially_validated'])
        p['scale'] = 5
        self.assertEqual(self.planner.analyze(p)['ratios'], [])
        p['scale'] = 1
        p['inventory']['tomato'] = 0
        self.assertEqual(self.planner.analyze(p)['ratios'], [])
        p['inventory'] = {}
        p['available'] = []
        self.assertEqual(self.planner.analyze(p)['ratios'], [])

    def test_examples_and_minority_family_failure(self):
        for ex in self.planner.examples:
            p = self.planner.defaults()
            p.update(placements=ex['placements'], selected_counts=ex['ratio'], seasons=ex['seasons'], scale=4 if len(ex['placements']) == 8 else 6)
            answer = self.planner.analyze(p)
            self.assertTrue(answer['layout']['all_tiles_nutrient_balanced'])
            self.assertTrue(answer['layout']['all_crop_family_checks_pass'])
            self.assertTrue(answer['layout_matches_selected'])
            self.assertEqual(answer['stress']['giant_eligibility'], 'unknown')
        p = self.planner.defaults()
        p['placements'] = [dict(plant_id='tomato' if i < 6 else 'dragonfruit', tile_x=0, tile_y=0, row=i // 3, col=i % 3) for i in range(9)]
        a = self.planner.analyze(p)['layout']
        self.assertTrue(a['all_tiles_nutrient_balanced'])
        self.assertFalse(a['all_crop_family_checks_pass'])
        self.assertEqual([r['family_status'] for r in a['plants'] if r['plant_id'] == 'dragonfruit'], ['fail'] * 3)

    def test_global_balance_cannot_cancel_tile_deficits(self):
        p = self.planner.defaults()
        p['placements'] = [dict(plant_id=id, tile_x=tile, tile_y=0, row=i // 3, col=i % 3) for tile, id in enumerate(('potato', 'tomato')) for i in range(4)]
        a = self.planner.analyze(p)['layout']
        self.assertFalse(a['all_tiles_nutrient_balanced'])
        self.assertEqual([t['external_nutrient_deficit_per_stage'] for t in a['tiles']], [[0, 0, 16], [8, 8, 0]])

    @staticmethod
    def grid_plants(cells):
        return [dict(plant_id='potato', tile_x=col // 3, tile_y=row // 3, row=row % 3, col=col % 3) for row, col in cells]

    def test_four_consecutive_crops_across_any_field_boundary_pass_family(self):
        # These runs span exactly four game units end to end, including the
        # user's F1R1C1/C2/C3 + F2R1C1 example and its rotations/translations.
        for count in (2, 4):
            runs = [[(row, col) for col in range(start, start + 4)]
                    for row in range(3 if count == 2 else 6) for start in range(3)]
            if count == 4:
                runs += [[(row, col) for row in range(start, start + 4)] for col in range(6) for start in range(3)]
            for cells in runs:
                with self.subTest(fields=count, cells=cells):
                    p = self.planner.defaults()
                    p.update(tile_count=count, placements=self.grid_plants(cells))
                    answer = self.planner.analyze(p)['layout']
                    self.assertTrue(answer['all_crop_family_checks_pass'])
                    self.assertEqual([r['same_kind_within_radius'] for r in answer['plants']], [4] * 4)
                    self.assertEqual(answer['plants'][0]['same_kind_on_boundary'], 1)
                    self.assertEqual(answer['plants'][-1]['same_kind_on_boundary'], 1)

    def test_family_checks_diagonals_and_excludes_plants_beyond_radius(self):
        p = self.planner.defaults()
        p.update(tile_count=4, placements=self.grid_plants([(2, 2), (2, 3), (3, 2), (3, 3)]))
        self.assertTrue(self.planner.analyze(p)['layout']['all_crop_family_checks_pass'])
        p['placements'] = self.grid_plants([(0, 0), (0, 1), (0, 2), (1, 3)])
        answer = self.planner.analyze(p)['layout']
        self.assertFalse(answer['all_crop_family_checks_pass'])
        self.assertEqual(answer['plants'][0]['family_status'], 'fail')
        self.assertEqual(answer['plants'][0]['same_kind_within_radius'], 3)

    def test_four_fields_support_36_positions_and_round_trip_without_changing_old_plans(self):
        p = self.planner.defaults()
        p.update(tile_count=4, placements=self.grid_plants([(row, col) for row in range(6) for col in range(6)]))
        answer = self.planner.analyze(p)['layout']
        self.assertEqual([t['tile'] for t in answer['tiles']], [[0, 0], [1, 0], [0, 1], [1, 1]])
        self.assertEqual({tuple(t['tile']): t['plant_count'] for t in answer['tiles']}, {(0, 0): 9, (1, 0): 9, (0, 1): 9, (1, 1): 9})
        self.assertTrue(answer['all_crop_family_checks_pass'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'four_fields.sqlite'
            store = PlanStore(path, self.planner)
            store.update(p, 0)
            self.assertEqual(PlanStore(path, self.planner).snapshot()['state'], p)
        for count in (1, 2):
            old = self.planner.defaults()
            old['tile_count'] = count
            self.assertEqual(self.planner.validate(old), old)

    def test_unknown_care_and_history_are_never_assumed_passed(self):
        p = self.planner.defaults()
        p['care'] = dict.fromkeys(('water', 'tending', 'soil', 'debris', 'seeds', 'history'), True)
        a = self.planner.analyze(p)['stress']
        self.assertEqual((a['stress_min'], a['stress_max'], a['giant_eligibility']), (0, 28, 'unknown'))
        p.update(stages=[dict.fromkeys(STRESS_KEYS, False) for _ in range(4)], specific_seed=True, never_rotted=True, not_forced_ripened=True)
        self.assertEqual(self.planner.analyze(p)['stress']['giant_eligibility'], 'eligible_under_wiki_rules')
        p['stages'][0]['family'] = None
        self.assertEqual(self.planner.analyze(p)['stress']['giant_eligibility'], 'unknown')
        p['stages'][0]['family'] = True
        p['stages'][1]['family'] = True
        self.assertEqual(self.planner.analyze(p)['stress']['giant_eligibility'], 'ineligible')
        p['stages'] = []
        self.assertEqual(self.planner.validate(p)['stages'], [{}, {}, {}, {}])

    def test_invalid_imports_and_positions_are_rejected(self):
        for field, value in [('schema_version', 2), ('dataset_version', 'future'), ('scale', True),
                             ('tile_count', 3),
                             ('inventory', {'tomato': -1}), ('available', ['unknown']), ('seasons', ['monsoon']),
                             ('stages', [None]), ('selected_counts', {'potato': True, 'tomato': 1}),
                             ('placements', [dict(plant_id='tomato', tile_x=-1, tile_y=0, row=0, col=0)])]:
            with self.subTest(field=field):
                p = self.planner.defaults()
                p[field] = value
                with self.assertRaises(ValueError):
                    self.planner.validate(p)
        for count, x, y in ((1, 1, 0), (2, 0, 1), (4, 2, 0), (4, 0, 2)):
            with self.subTest(fields=count, x=x, y=y):
                p = self.planner.defaults()
                p.update(tile_count=count, placements=[dict(plant_id='potato', tile_x=x, tile_y=y, row=0, col=0)])
                with self.assertRaises(ValueError):
                    self.planner.validate(p)

    def test_plan_round_trip_separate_storage_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plans.sqlite'
            store = PlanStore(path, self.planner)
            p = self.planner.defaults()
            p.update(available=['tomato'], inventory={'tomato': 7}, seasons=['winter'])
            self.assertEqual(store.update(p, 0)['version'], 1)
            other = PlanStore(path, self.planner)
            with self.assertRaises(PlanConflict):
                other.update(self.planner.defaults(), 0)
            self.assertEqual(other.snapshot()['state'], p)
            p['seasons'] = []
            other.update(p, 1)
            self.assertEqual(other.snapshot()['state']['available'], ['tomato'])
            self.assertEqual(other.snapshot()['state']['inventory'], {'tomato': 7})


class CombinedHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.snapshots = [cooking.DEFAULT_DATABASE, ROOT / 'DST_Farming_v0_1/data/farming.json', ROOT / 'DST_Farming_v0_1/farming.sqlite']
        cls.hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.snapshots]
        cls.settings = Path(cls.temp.name) / 'user_settings.sqlite'
        cls.server = create_server(port=0, settings_path=cls.settings)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)
        cls.temp.cleanup()
        if cls.hashes != [hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.snapshots]:
            raise AssertionError('Integration mutated curated data')

    def request(self, path, payload=None, headers=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
            connection.request(method or ('POST' if body else 'GET'), path, body, headers or ({'Content-Type': 'application/json'} if body else {}))
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_routes_assets_and_deep_links(self):
        for path in ['/', '/cooking', '/cooking?ingredient=tomato', '/farming', '/helper.css', '/farming.js', '/app.js']:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn('charset=utf-8', headers['Content-Type'])
                self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
                self.assertTrue(body)
        self.assertIn('/cooking', self.request('/')[2].decode())
        self.assertIn('Farming', self.request('/cooking')[2].decode())
        status, _, body = self.request('/farming', method='HEAD')
        self.assertEqual((status, body), (200, b''))

    def test_farming_and_cooking_navigation_preserves_rarity(self):
        before = json.loads(self.request('/api/rarity')[2])
        self.assertEqual(self.request('/api/rarity', dict(ingredient_id='tomato', rarity=23, expected_version=before['version']))[0], 200)
        overview = json.loads(self.request('/api/farming')[2])
        self.assertTrue(overview['metadata']['planner_enabled'])
        self.assertEqual(len(overview['plants']), 18)
        self.assertTrue(all(p['product_ingredient_id'] == p['plant_id'] for p in overview['plants'] if p['kind'] == 'crop'))
        status, _, raw = self.request('/api/farming/analyze', overview['defaults'])
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(raw)['ratios']), 74)
        state = overview['preferences']['state']
        self.assertEqual(self.request('/api/farming/preferences', dict(state=state, expected_version=overview['preferences']['version']))[0], 200)
        self.request('/cooking')
        self.assertEqual(json.loads(self.request('/api/rarity')[2])['rarities']['tomato'], 23)
        catalog = json.loads(self.request('/api/catalog')[2])
        self.assertEqual(len(catalog['dishes']), 81)
        self.assertTrue(catalog['prediction']['enabled'])
        self.assertTrue(catalog['signature']['enabled'])
        with closing(sqlite3.connect(self.settings)) as db:
            self.assertNotIn('farming_working_plan', {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_request_validation_origin_and_private_files(self):
        state = FarmingPlanner().defaults()
        for path in ('/api/farming/analyze', '/api/farming/preferences'):
            self.assertEqual(self.request(path, state, {'Content-Type': 'application/json', 'Origin': 'https://elsewhere.invalid'})[0], 403)
            self.assertEqual(self.request(path, [1, 2])[0], 422)
        state['placements'] = [{'plant_id': []}]
        self.assertEqual(self.request('/api/farming/analyze', state)[0], 422)
        for path in ('/farming_plans.sqlite', '/dst_helper/farming.py', '/data/farming.json'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/api/farming/preferences', method='PUT')[0], 405)

    def test_protect_content_and_cooking_settings_from_plan_path(self):
        for path in (self.settings, *self.snapshots):
            with self.subTest(path=path), self.assertRaises(ValueError):
                create_server(port=0, settings_path=self.settings, farming_settings=path)


if __name__ == '__main__':
    unittest.main()
