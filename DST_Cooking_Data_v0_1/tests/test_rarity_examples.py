"""Independent exhaustive cost references, stateless preference isolation, and HTTP calculations."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
from itertools import combinations_with_replacement
import json
from pathlib import Path
import tempfile
import threading
import unittest

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.examples import DishExamples, RecipePlanner
from handbook.prediction import ExactPotPredictor, PredictionInputError
from handbook.preparation import PREPARED_IDS, PREPARATION_POLICY, required_prepared_prefabs
from handbook.server import create_server
from handbook.settings import DEFAULT_SETTINGS, CookingDefaults, validate_rarities
from handbook.signature import SignatureRecipes
from test_signature import synthetic_snapshot


class SettingsTests(unittest.TestCase):
    def test_defaults_are_read_only_and_signed_values_are_supported(self):
        before = DEFAULT_SETTINGS.read_bytes()
        store = CookingDefaults(DEFAULT_SETTINGS, {r['ingredient_id'] for r in Catalog().overview()['ingredients']})
        values = store.snapshot()['rarities']
        self.assertEqual(values['twigs'], -1)
        self.assertEqual(values['butter'], 80)
        values.clear()
        self.assertTrue(store.snapshot()['rarities'])
        self.assertEqual(DEFAULT_SETTINGS.read_bytes(), before)

    def test_invalid_request_rarities(self):
        for value in [True, False, 1.5, '3', [], {}, 2147483648, -2147483649]:
            with self.subTest(value=value), self.assertRaises(PredictionInputError):
                validate_rarities({'raw': value}, {'raw'})
        for value in [None, [], {'missing': 1}]:
            with self.assertRaises(PredictionInputError):
                validate_rarities(value, {'raw'})
        self.assertEqual(validate_rarities({'raw': -7}, {'raw'}), {'raw': -7})
        self.assertEqual(validate_rarities({}, {'raw'}), {})


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

    def test_guaranteed_examples_match_brute_force_and_do_not_reuse_unfiltered_cache(self):
        snapshot = synthetic_snapshot()
        duplicate = dict(snapshot['recipes'][0], dish_id='named_twin')
        snapshot['recipes'].append(duplicate)
        snapshot['dishes'].append(dict(dish_id='named_twin'))
        predictor = ExactPotPredictor(snapshot)
        universe = list(predictor.ingredients)
        for rarities in [{}, {'raw': -7, 'fruit': 10, 'sweet': -2, 'filler': 4}]:
            search = DishExamples(predictor, snapshot['dishes'], rarities, prepared_ids=set())
            for cooker in predictor.policy['cookers']:
                expected = {row['dish_id']: [] for row in snapshot['dishes']}
                for pot in combinations_with_replacement(universe, 4):
                    outcomes = predictor.predict(list(pot), cooker)['outcomes']
                    if len(outcomes) == 1:
                        expected[outcomes[0]['dish_id']].append(sum(rarities.get(item, 0) for item in pot))
                for dish, costs in expected.items():
                    with self.subTest(rarities=rarities, cooker=cooker, dish=dish):
                        unfiltered = search.examples(dish, cooker)
                        actual = search.examples(dish, cooker, guaranteed_only=True)
                        self.assertTrue(actual['guaranteed_only'])
                        self.assertEqual([r['total_rarity'] for r in actual['examples']], sorted(costs)[:3])
                        self.assertEqual(actual['fewer_than_requested'], len(costs) < 3)
                        self.assertEqual(search.examples(dish, cooker), unfiltered)
                        pots = [tuple(sorted(r['ingredients'])) for r in actual['examples']]
                        self.assertEqual(len(pots), len(set(pots)))
                        for row in actual['examples']:
                            self.assertEqual(row['probability']['value'], 1)
                            self.assertEqual(len(predictor.predict(row['ingredients'], cooker)['outcomes']), 1)
                self.assertTrue(search.examples('named', cooker)['examples'])
                self.assertEqual(search.examples('named', cooker, True)['examples'], [])

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

    def test_request_preferences_isolate_cached_examples_and_signature_witnesses(self):
        snapshot = synthetic_snapshot()
        predictor = ExactPotPredictor(snapshot)
        class Defaults:
            def snapshot(self):
                return dict(rarities={})
        planner = RecipePlanner(predictor, snapshot['dishes'], Defaults(), cache_limit=2)
        before = planner.examples('fallback', 'crock_pot', {}, 1)
        old_signature = planner.recommend('raw', 'crock_pot', {}, 1)
        after = planner.examples('fallback', 'crock_pot', {'filler': -20}, 1)
        new_signature = planner.recommend('raw', 'crock_pot', {'filler': -20}, 1)
        self.assertEqual(before['rarity_version'], after['rarity_version'])
        self.assertLess(after['examples'][0]['total_rarity'], before['examples'][0]['total_rarity'])
        self.assertEqual(after['examples'][0]['ingredients'], ['filler'] * 4)
        self.assertNotEqual(old_signature['other'], new_signature['other'])
        self.assertEqual(planner.examples('fallback', 'crock_pot', {}, 1), before)
        def calculate(n):
            return planner.examples('fallback', 'crock_pot', {'filler': -n}, 1)['examples'][0]['total_rarity']
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(calculate, [10, 20, 30])), [-40, -80, -120])
        self.assertLessEqual(len(planner._cache), 2)



class RarityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        self.folder = tempfile.TemporaryDirectory()
        self.server = create_server(0)
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

    def test_request_preferences_do_not_change_defaults_or_other_clients(self):
        before = self.request('/api/rarity')[1]
        payload = dict(dish='huiji:华夫饼', cooker='crock_pot', rarities={'butter': 30}, rarity_version=1)
        status, examples = self.request('/api/examples', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual(examples['rarity_version'], 1)
        self.assertEqual(len(examples['examples']), 3)
        self.assertTrue(all(e['total_rarity'] == 30 for e in examples['examples']))
        other = self.request('/api/examples', 'POST', dict(payload, rarities={}))[1]
        self.assertTrue(all(e['total_rarity'] == 0 for e in other['examples']))
        self.assertEqual(self.request('/api/examples', 'POST', payload)[1], examples)
        self.assertEqual(self.request('/api/rarity')[1], before)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])
        _, result = self.request('/api/signature', 'POST', dict(ingredient='meat', cooker='crock_pot', rarities={'butter': 30}, rarity_version=1))
        waffles = next(r for r in result['other'] if r['dish_id'] == 'huiji:华夫饼')
        self.assertEqual(waffles['additional_rarity'], 30)

    def test_guaranteed_filter_contract_and_spicy_chili(self):
        defaults = self.request('/api/rarity')[1]['rarities']
        payload = dict(dish='huiji:辣椒炖肉', cooker='crock_pot', rarities=defaults, rarity_version=7)
        status, unfiltered = self.request('/api/examples', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertTrue(any(e['probability']['value'] < 1 for e in unfiltered['examples']))
        status, filtered = self.request('/api/examples', 'POST', dict(payload, guaranteed_only=True))
        self.assertEqual(status, 200)
        self.assertTrue(filtered['guaranteed_only'])
        self.assertEqual(filtered['rarity_version'], 7)
        self.assertEqual(len(filtered['examples']), 3)
        self.assertTrue(all(e['probability']['value'] == 1 for e in filtered['examples']))
        self.assertEqual(self.request('/api/examples', 'POST', dict(payload, guaranteed_only=False))[1], unfiltered)
        for value in [0, 1, 'true', None, []]:
            self.assertEqual(self.request('/api/examples', 'POST', dict(payload, guaranteed_only=value))[0], 422)
        from urllib.parse import urlencode
        query = urlencode(dict(dish=payload['dish'], cooker=payload['cooker'], guaranteed_only='true'))
        status, result = self.request('/api/examples?' + query)
        self.assertEqual(status, 200)
        self.assertTrue(result['guaranteed_only'])
        self.assertTrue(all(e['probability']['value'] == 1 for e in result['examples']))
        for suffix in ['&guaranteed_only=false', '&extra=']:
            self.assertEqual(self.request('/api/examples?' + query + suffix)[0], 422)
        self.assertEqual(self.request('/api/examples?' + query.replace('true', '1'))[0], 422)
        signature = dict(ingredient='meat', cooker='crock_pot', rarities={}, rarity_version=1, guaranteed_only=True)
        self.assertEqual(self.request('/api/signature', 'POST', signature)[0], 422)

    def test_validation_origin_guards_and_removed_write_endpoints(self):
        payload = dict(ingredient='meat', cooker='crock_pot', rarities={}, rarity_version=1)
        for origin in ['https://unrelated.example', 'http://[']:
            self.assertEqual(self.request('/api/signature', 'POST', payload, {'Content-Type': 'application/json', 'Origin': origin})[0], 403)
        for bad in [dict(payload, rarities={'meat': True}), dict(payload, rarities={'missing': 2}),
                    dict(payload, rarity_version=True), dict(payload, rarity_version=-1), dict(payload, extra=True),
                    dict(payload, ingredient=[]), dict(payload, cooker=[]), [], {}]:
            self.assertEqual(self.request('/api/signature', 'POST', bad)[0], 422)
        self.assertEqual(self.request('/api/signature', 'POST', payload, {'Content-Type': 'text/plain'})[0], 422)
        for path in ['/api/rarity', '/api/signature-exclusions', '/api/catalog']:
            self.assertEqual(self.request(path, 'POST', payload)[0], 405)
        self.assertEqual(self.request('/.local/user_settings.sqlite')[0], 404)
        self.assertEqual(self.request('/api/examples?dish=missing&cooker=crock_pot')[0], 404)
        for query in ['', 'dish=x', 'dish=x&cooker=bad', 'dish=x&dish=y&cooker=crock_pot', 'dish=x&cooker=crock_pot&extra=y']:
            self.assertEqual(self.request('/api/examples?' + query)[0], 422)



if __name__ == '__main__':
    unittest.main()
