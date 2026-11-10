"""Completion-search correctness, exact witness checks, and HTTP contracts."""
import http.client
from itertools import combinations_with_replacement
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from handbook.catalog import Catalog
from handbook.prediction import ExactPotPredictor, PredictionInputError
from handbook.server import create_server
from handbook.signature import SignatureRecipes


def synthetic_snapshot():
    metadata = Catalog().prediction_snapshot()['metadata']
    ingredients = [
        dict(ingredient_id='raw', prefab_id='a', tags={'meat': 0.1}),
        dict(ingredient_id='cooked', prefab_id='a', tags={'meat': 0.2}),
        dict(ingredient_id='fruit', prefab_id='b', tags={'fruit': 0.5}),
        dict(ingredient_id='sweet', prefab_id='c', tags={'sweetener': 1}),
        dict(ingredient_id='copy1', prefab_id='c2', tags={'sweetener': 1}),
        dict(ingredient_id='copy2', prefab_id='c3', tags={'sweetener': 1}),
        dict(ingredient_id='filler', prefab_id='d', tags={})]
    definitions = [
        ('named', 5, {'all': [{'item_sum': ['a'], 'op': '>=', 'value': 2}, {'tag': 'meat', 'op': '>=', 'value': 0.3}]}, False),
        ('tie', 5, {'all': [{'tag': 'meat', 'op': '>', 'value': 0}, {'tag': 'sweetener', 'op': '>=', 'value': 1}]}, False),
        ('higher', 10, {'item_sum': ['b'], 'op': '>=', 'value': 2}, False),
        ('portable', 20, {'all': [{'item_sum': ['a'], 'op': '==', 'value': 1}, {'tag': 'fruit', 'op': '>=', 'value': 0.5}]}, True),
        ('or', 4, {'any': [{'tag': 'veggie', 'op': '>', 'value': 0}, {'item_sum': ['c'], 'op': '>=', 'value': 3}]}, False),
        ('lower', 3, {'all': [{'tag': 'meat', 'op': '>', 'value': 0}, {'tag': 'meat', 'op': '<', 'value': 0.3}]}, False),
        ('exact', 7, {'all': [{'item_sum': ['a'], 'op': '==', 'value': 2}, {'tag': 'meat', 'op': '<=', 'value': 0.3}]}, False),
        ('never', 99, {'any': []}, False),
        ('fallback', -10, {'all': []}, False),
        ('shadowed', -20, {'item_sum': ['a'], 'op': '>', 'value': 0}, False)]
    recipes, dishes = [], []
    for index, (dish, priority, condition, portable) in enumerate(definitions):
        recipes.append(dict(dish_id=dish, name_zh=dish, icon_asset_id=None, priority=priority, cook_seconds=10,
                            weight=None, conditions=condition, cooker_scope_hint='portable_only_wiki_claim' if portable
                            else 'ordinary_recipe_cooker_matrix_unconfirmed'))
        dishes.append(dict(dish_id=dish, name_zh=dish, source_row=index + 1, base_hunger=index,
                           base_health=None, base_sanity=0))
    return dict(metadata=metadata, ingredients=ingredients, recipes=recipes, dishes=dishes)


class SearchCorrectnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = synthetic_snapshot()
        cls.predictor = ExactPotPredictor(cls.snapshot)
        cls.discovery = SignatureRecipes(cls.predictor, cls.snapshot['dishes'])

    def test_every_result_set_equals_independent_brute_force_completions(self):
        universe = list(self.predictor.ingredients)
        self.assertLess(self.discovery.profile_count, len(universe))
        for selected in universe:
            for cooker in ('crock_pot', 'portable'):
                expected = set()
                for rest in combinations_with_replacement(universe, 3):
                    pot = [selected, *rest]
                    expected.update(row['dish_id'] for row in self.predictor.predict(pot, cooker)['outcomes'])
                found = self.discovery.recommend(selected, cooker)
                rows = found['special'] + found['other']
                with self.subTest(selected=selected, cooker=cooker):
                    self.assertTrue(found['complete'])
                    self.assertEqual({row['dish_id'] for row in rows}, expected)
                    self.assertEqual(len(rows), len(expected))
                    for row in rows:
                        self.assertEqual(row['example']['ingredients'][0], selected)
                        actual = self.predictor.predict(row['example']['ingredients'], cooker)
                        winner = next(r for r in actual['outcomes'] if r['dish_id'] == row['dish_id'])
                        self.assertEqual(row['example']['probability'], winner['probability'])

    def test_special_is_named_requirement_not_general_tag_or_shadowed_match(self):
        raw = self.discovery.recommend('raw', 'crock_pot')
        special = {row['dish_id'] for row in raw['special']}
        self.assertIn('named', special)
        self.assertNotIn('tie', special)
        self.assertNotIn('shadowed', {row['dish_id'] for row in raw['special'] + raw['other']})
        self.assertEqual(self.discovery.recommend('copy1', 'crock_pot')['special'], [])

    def test_invalid_state_or_cooker_is_rejected(self):
        for ingredient, cooker in [('missing', 'crock_pot'), ('a', 'crock_pot'),
                                   ('raw', 'ancient_kiln'), (None, 'crock_pot')]:
            with self.subTest(ingredient=ingredient, cooker=cooker), self.assertRaises(PredictionInputError):
                self.discovery.recommend(ingredient, cooker)


class SnapshotWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = Catalog().prediction_snapshot()
        cls.predictor = ExactPotPredictor(cls.snapshot)
        cls.discovery = SignatureRecipes(cls.predictor, cls.snapshot['dishes'])

    def test_real_state_witnesses_survive_exact_priority_competition(self):
        source = {row['dish_id']: row for row in self.snapshot['dishes']}
        for ingredient in ('ice', 'meat', 'honey', 'potato', 'potato_cooked', 'kelp', 'onion', 'wx78_foodbrick@wiki_state_104'):
            for cooker in ('crock_pot', 'portable'):
                result = self.discovery.recommend(ingredient, cooker)
                for row in result['special'] + result['other']:
                    with self.subTest(ingredient=ingredient, cooker=cooker, dish=row['dish_id']):
                        pot = row['example']['ingredients']
                        self.assertEqual(len(pot), 4)
                        self.assertIn(ingredient, pot)
                        actual = self.predictor.predict(pot, cooker)
                        self.assertIn(row['dish_id'], {r['dish_id'] for r in actual['outcomes']})
                        self.assertGreater(row['example']['probability']['value'], 0)
                        self.assertEqual(row['base_health'], source[row['dish_id']]['base_health'])

    def test_ice_is_general_and_honey_has_named_recipes(self):
        ice = self.discovery.recommend('ice', 'crock_pot')
        self.assertEqual(ice['special'], [])
        self.assertGreater(len(ice['other']), 5)
        honey = self.discovery.recommend('honey', 'crock_pot')
        self.assertEqual({row['dish_id'] for row in honey['special']},
                         {'huiji:蜜汁火腿', 'huiji:蜜汁卤肉', 'huiji:粉末蛋糕'})
        self.assertNotIn('huiji:怪物鞑靼', {r['dish_id'] for r in ice['special'] + ice['other']})


class SignatureHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.server = create_server(0, settings_path=Path(cls.folder.name) / 'settings.sqlite')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
        cls.folder.cleanup()

    def get(self, query):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            conn.request('GET', '/api/signature?' + query)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_success_returns_complete_groups_and_four_item_proofs(self):
        status, result = self.get(urlencode({'ingredient': 'honey', 'cooker': 'crock_pot'}))
        self.assertEqual(status, 200)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['special']), 3)
        self.assertGreater(len(result['other']), 5)
        self.assertFalse(result['eligibility_verified'])
        self.assertTrue(all(len(row['example']['ingredients']) == 4 for row in result['special'] + result['other']))

    def test_invalid_or_ambiguous_query_has_no_recommendations(self):
        for query in ['', 'ingredient=ice', 'ingredient=ice&cooker=bad',
                      'ingredient=bad&cooker=crock_pot', 'ingredient=ice&ingredient=meat&cooker=crock_pot',
                      'ingredient=ice&cooker=crock_pot&extra=x', 'x=1&x=2&x=3&x=4&x=5']:
            with self.subTest(query=query):
                status, result = self.get(query)
                self.assertEqual(status, 422)
                self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
