"""Independent exhaustive cost references, preference persistence, and HTTP writes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
from itertools import combinations_with_replacement
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.examples import DishExamples, RecipePlanner
from handbook.prediction import ExactPotPredictor, PredictionInputError
from handbook.preparation import PREPARED_IDS, PREPARATION_POLICY, required_prepared_prefabs
from handbook.server import create_server
from handbook.settings import SettingsConflict, UserSettings
from handbook.signature import SignatureRecipes
from test_signature import synthetic_snapshot


class SettingsTests(unittest.TestCase):
    def test_content_copies_cannot_be_opened_as_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'content-copy.sqlite'
            shutil.copyfile(DEFAULT_DATABASE, path)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                UserSettings(path, ['raw'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_persistence_defaults_signed_values_and_state_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.sqlite'
            store = UserSettings(path, ['raw', 'cooked'])
            self.assertEqual(store.snapshot(), dict(version=0, rarities={}))
            self.assertEqual(store.update('raw', -7, 0)['rarities'], {'raw': -7})
            restored = UserSettings(path, ['raw', 'cooked'])
            result = restored.update('cooked', 12, 1)
            self.assertEqual(result['rarities'], {'raw': -7, 'cooked': 12})
            self.assertEqual(restored.update('raw', None, 2)['rarities'], {'cooked': 12})
            self.assertEqual(restored.update('raw', None, 3)['version'], 3)
            self.assertEqual(restored.update('raw', 0, 3)['rarities']['raw'], 0)
            # Replacing the content universe does not delete unknown stored preferences.
            UserSettings(path, ['cooked']).snapshot()
            self.assertIn('raw', UserSettings(path, ['raw', 'cooked']).snapshot()['rarities'])

    def test_invalid_values_and_concurrent_edit_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UserSettings(Path(folder) / 'settings.sqlite', ['raw'])
            for value in [True, False, 1.5, '3', [], {}, 2147483648, -2147483649]:
                with self.subTest(value=value), self.assertRaises(PredictionInputError):
                    store.update('raw', value, 0)
            with self.assertRaises(PredictionInputError):
                store.update('missing', 1, 0)
            with self.assertRaises(PredictionInputError):
                store.update('raw', 1, True)
            def edit(value):
                try:
                    store.update('raw', value, 0)
                    return True
                except SettingsConflict:
                    return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(edit, [3, -3])), [False, True])
            self.assertEqual(store.snapshot()['version'], 1)


class CostOptimalityTests(unittest.TestCase):
    def test_minimum_additional_rarity_matches_brute_force_for_every_state_and_cooker(self):
        snapshot = synthetic_snapshot()
        predictor = ExactPotPredictor(snapshot)
        universe = list(predictor.ingredients)
        for rarities in [{}, {'raw': 8, 'copy1': -4, 'copy2': 6, 'filler': 3},
                         {'raw': -10, 'cooked': 9, 'fruit': -2, 'sweet': 7}]:
            discovery = SignatureRecipes(predictor, snapshot['dishes'], rarities)
            for selected in universe:
                for cooker in predictor.policy['cookers']:
                    expected = {}
                    for rest in combinations_with_replacement(universe, 3):
                        cost = sum(rarities.get(item, 0) for item in rest)
                        for outcome in predictor.predict([selected, *rest], cooker)['outcomes']:
                            dish = outcome['dish_id']
                            expected[dish] = min(expected.get(dish, cost), cost)
                    actual = discovery.recommend(selected, cooker)
                    rows = actual['special'] + actual['other']
                    with self.subTest(rarities=rarities, selected=selected, cooker=cooker):
                        self.assertEqual({r['dish_id']: r['additional_rarity'] for r in rows}, expected)
                        for row in rows:
                            self.assertEqual(row['example']['ingredients'][0], selected)
                            self.assertEqual(row['example']['total_rarity'], row['additional_rarity'] + rarities.get(selected, 0))

    def test_top_three_distinct_examples_match_brute_force_even_for_negative_costs_and_equivalent_states(self):
        snapshot = synthetic_snapshot()
        # Add a recipe that explicitly requires the prepared form, and one allowing raw OR cooked.
        for dish, forms in [('cooked_only', ['cooked_a']), ('raw_or_cooked', ['a', 'cooked_a'])]:
            snapshot['recipes'].append(dict(dish_id=dish, name_zh=dish, icon_asset_id=None, priority=40,
                cook_seconds=10, weight=None, cooker_scope_hint='ordinary_recipe_cooker_matrix_unconfirmed',
                conditions={'item_sum': forms, 'op': '>=', 'value': 1}))
            snapshot['dishes'].append(dict(dish_id=dish))
        snapshot['ingredients'][1]['prefab_id'] = 'cooked_a'
        predictor = ExactPotPredictor(snapshot)
        for rarities in [{}, {'raw': 5, 'cooked': -100, 'fruit': -3, 'copy1': -4, 'copy2': 9},
                         {'raw': -2147483648, 'cooked': 2147483647, 'sweet': 10}]:
            search = DishExamples(predictor, snapshot['dishes'], rarities, prepared_ids={'cooked'})
            for cooker in predictor.policy['cookers']:
                for recipe, _ in predictor.recipes:
                    dish = recipe['dish_id']
                    # Independent fixture policy: only the cooked-only recipe may use cooked.
                    allowed = [item for item in predictor.ingredients if item != 'cooked' or dish == 'cooked_only']
                    expected = []
                    for pot in combinations_with_replacement(allowed, 4):
                        if dish in {r['dish_id'] for r in predictor.predict(list(pot), cooker)['outcomes']}:
                            expected.append(sum(rarities.get(item, 0) for item in pot))
                    expected.sort()
                    actual = search.examples(dish, cooker)
                    with self.subTest(rarities=rarities, cooker=cooker, dish=dish):
                        self.assertTrue(actual['complete'])
                        self.assertEqual([r['total_rarity'] for r in actual['examples']], expected[:3])
                        pots = [tuple(sorted(r['ingredients'])) for r in actual['examples']]
                        self.assertEqual(len(pots), len(set(pots)))
                        for row in actual['examples']:
                            self.assertEqual(len(row['ingredients']), 4)
                            self.assertTrue(set(row['ingredients']) <= set(allowed))
                            winner = next(r for r in predictor.predict(row['ingredients'], cooker)['outcomes'] if r['dish_id'] == dish)
                            self.assertEqual(row['probability'], winner['probability'])

    def test_prepared_policy_excludes_mixed_alternatives_and_nonpositive_requirements(self):
        snapshot = synthetic_snapshot()
        ast = ExactPotPredictor(snapshot).recipes[0][1]
        self.assertEqual(required_prepared_prefabs(ast, {'a'}), {'a'})
        self.assertEqual(required_prepared_prefabs(ast, {'other'}), set())
        self.assertEqual(required_prepared_prefabs(('items', ('cooked', 'raw'), '>=', 1), {'cooked'}), set())
        self.assertEqual(required_prepared_prefabs(('items', ('cooked',), '==', 0), {'cooked'}), set())
        rows = {row['ingredient_id']: row for row in Catalog().overview()['ingredients']}
        self.assertEqual(len(PREPARED_IDS), 57)
        for row in PREPARATION_POLICY['states']:
            self.assertEqual(row['name_zh'], rows[row['ingredient_id']]['name_zh'])
            self.assertEqual(row['source_row'], rows[row['ingredient_id']]['source_row'])

    def test_settings_changes_invalidate_cached_minimum_examples_and_signature_witnesses(self):
        snapshot = synthetic_snapshot()
        predictor = ExactPotPredictor(snapshot)
        with tempfile.TemporaryDirectory() as folder:
            store = UserSettings(Path(folder) / 'settings.sqlite', predictor.ingredients)
            planner = RecipePlanner(predictor, snapshot['dishes'], store)
            before = planner.examples('fallback', 'crock_pot')
            old_signature = planner.recommend('raw', 'crock_pot')
            store.update('filler', -20, 0)
            after = planner.examples('fallback', 'crock_pot')
            new_signature = planner.recommend('raw', 'crock_pot')
            self.assertEqual(before['rarity_version'], 0)
            self.assertEqual(after['rarity_version'], 1)
            self.assertLess(after['examples'][0]['total_rarity'], before['examples'][0]['total_rarity'])
            self.assertEqual(after['examples'][0]['ingredients'], ['filler'] * 4)
            self.assertNotEqual(old_signature['rarity_version'], new_signature['rarity_version'])


class RarityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        self.folder = tempfile.TemporaryDirectory()
        self.server = create_server(0, settings_path=Path(self.folder.name) / 'preferences.sqlite')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.folder.cleanup()
        self.assertEqual(hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest(), self.before)

    def request(self, path, method='GET', payload=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        try:
            conn.request(method, path, body=json.dumps(payload) if payload is not None else None,
                         headers=headers if headers is not None else {'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_rarity_writes_are_separate_persistent_and_exposed_in_catalog_detail_and_examples(self):
        self.assertEqual(self.request('/api/rarity')[1], dict(version=0, rarities={}))
        status, result = self.request('/api/rarity', 'POST', dict(ingredient_id='butter', rarity=30, expected_version=0))
        self.assertEqual(status, 200)
        self.assertEqual(result['rarities'], {'butter': 30})
        _, catalog = self.request('/api/catalog')
        self.assertEqual(next(r['rarity'] for r in catalog['ingredients'] if r['ingredient_id'] == 'butter'), 30)
        _, detail = self.request('/api/detail?kind=ingredient&id=butter')
        self.assertEqual(detail['rarity'], 30)
        status, examples = self.request('/api/examples?' + urlencode(dict(dish='huiji:华夫饼', cooker='crock_pot')))
        self.assertEqual(status, 200)
        self.assertEqual(examples['rarity_version'], 1)
        self.assertEqual(len(examples['examples']), 3)
        self.assertTrue(all(e['total_rarity'] == 30 for e in examples['examples']))
        _, result = self.request('/api/signature?ingredient=meat&cooker=crock_pot')
        waffles = next(r for r in result['other'] if r['dish_id'] == 'huiji:华夫饼')
        self.assertEqual(waffles['additional_rarity'], 30)
        self.assertEqual(self.request('/api/rarity', 'POST', dict(ingredient_id='butter', rarity=None, expected_version=1))[1]['rarities'], {})

    def test_validation_conflicts_cross_origin_writes_and_content_paths(self):
        payload = dict(ingredient_id='meat', rarity=1, expected_version=0)
        self.assertEqual(self.request('/api/rarity', 'POST', payload, {'Content-Type': 'application/json', 'Origin': 'https://unrelated.example'})[0], 403)
        self.assertEqual(self.request('/api/rarity', 'POST', payload, {'Content-Type': 'application/json', 'Origin': 'http://['})[0], 403)
        for bad in [dict(payload, rarity=1.5), dict(payload, rarity=True), dict(payload, rarity='2'),
                    dict(payload, ingredient_id='missing'), dict(payload, extra=True), {}]:
            self.assertEqual(self.request('/api/rarity', 'POST', bad)[0], 422)
        self.assertEqual(self.request('/api/rarity', 'POST', payload, {'Content-Type': 'text/plain'})[0], 422)
        self.assertEqual(self.request('/api/rarity', 'POST', payload)[0], 200)
        status, conflict = self.request('/api/rarity', 'POST', payload)
        self.assertEqual(status, 409)
        self.assertEqual(conflict['settings']['version'], 1)
        self.assertEqual(self.request('/api/catalog', 'POST', payload)[0], 405)
        self.assertEqual(self.request('/.local/user_settings.sqlite')[0], 404)
        self.assertEqual(self.request('/api/examples?dish=missing&cooker=crock_pot')[0], 404)
        for query in ['', 'dish=x', 'dish=x&cooker=bad', 'dish=x&dish=y&cooker=crock_pot', 'dish=x&cooker=crock_pot&extra=y']:
            self.assertEqual(self.request('/api/examples?' + query)[0], 422)
        with self.assertRaises(ValueError):
            create_server(0, settings_path=DEFAULT_DATABASE)


if __name__ == '__main__':
    unittest.main()
