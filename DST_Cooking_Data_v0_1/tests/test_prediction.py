"""Exact-pot logic, fixture outcomes, and read-only HTTP prediction contracts."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.prediction import ExactPotPredictor, PredictionDataError, PredictionInputError
from handbook.server import create_server

ROOT = Path(__file__).resolve().parents[1]


class PredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = Catalog().prediction_snapshot()
        cls.predictor = ExactPotPredictor(cls.snapshot)

    def test_manually_derived_wiki_policy_fixtures(self):
        fixtures = json.loads((ROOT / 'data/prediction_fixtures.json').read_text(encoding='utf-8'))
        before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        for case in fixtures['cases']:
            with self.subTest(case=case['name']):
                result = self.predictor.predict(case['ingredients'], case['cooker'])
                self.assertEqual(result['highest_priority'], case['priority'])
                self.assertEqual({r['dish_id'] for r in result['outcomes']}, set(case['outcomes']))
                total = sum(Fraction(r['probability']['numerator'], r['probability']['denominator'])
                            for r in result['outcomes'])
                self.assertEqual(total, 1)
                self.assertTrue(all(r['probability']['denominator'] == len(case['outcomes']) for r in result['outcomes']))
                self.assertEqual(result['mode'], 'experimental_wiki')
                self.assertFalse(result['eligibility_verified'])
        self.assertEqual(hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest(), before)

    def test_lower_matches_and_unavailable_matches_are_explanations_only(self):
        result = self.predictor.predict(['corn', 'honey', 'twigs', 'fishmeat_small'], 'crock_pot')
        self.assertIn('huiji:肉串', {r['dish_id'] for r in result['suppressed_matches']})
        self.assertNotIn('huiji:肉串', {r['dish_id'] for r in result['outcomes']})
        ordinary = self.predictor.predict(['asparagus', 'asparagus_cooked', 'ice', 'ice'], 'crock_pot')
        self.assertIn('huiji:芦笋冷汤', {r['dish_id'] for r in ordinary['unavailable_matches']})

    def test_four_slots_known_state_ids_and_supported_cooker_are_required(self):
        for items in [None, 'berries', [], ['berries'] * 3, ['berries'] * 5,
                      ['berries'] * 3 + ['unknown'], ['berries'] * 3 + [None],
                      ['berries'] * 3 + ['wx78_foodbrick@wiki_state_fake']]:
            with self.subTest(items=items), self.assertRaises(PredictionInputError):
                self.predictor.predict(items, 'crock_pot')
        for cooker in [None, '', 'ancient_kiln', [], 'UNKNOWN']:
            with self.subTest(cooker=cooker), self.assertRaises(PredictionInputError):
                self.predictor.predict(['berries'] * 4, cooker)

    def test_duplicates_and_tag_aggregation_are_not_deduplicated(self):
        result = self.predictor.predict(['smallmeat', 'berries', 'berries', 'berries'], 'crock_pot')
        self.assertEqual(result['prefab_counts'], {'smallmeat': 1, 'berries': 3})
        self.assertEqual(result['tag_totals']['meat'], 0.5)
        self.assertEqual(result['tag_totals']['fruit'], 1.5)

    def synthetic(self):
        result = dict(metadata=deepcopy(self.snapshot['metadata']), ingredients=[
            dict(ingredient_id='raw', prefab_id='shared', tags={'meat': 0.1}),
            dict(ingredient_id='cooked', prefab_id='shared', tags={'meat': 0.2}),
            dict(ingredient_id='filler', prefab_id='filler', tags={})], recipes=[])
        for dish, priority, condition in [('winner', -1, {'all': [
            {'tag': 'meat', 'op': '==', 'value': 0.3},
            {'item_sum': ['shared'], 'op': '==', 'value': 2}]}), ('fallback', -10, {'all': []})]:
            result['recipes'].append(dict(dish_id=dish, name_zh=dish, icon_asset_id=None, priority=priority,
                cook_seconds=10, weight=None, cooker_scope_hint='ordinary_recipe_cooker_matrix_unconfirmed', conditions=condition))
        return result

    def test_state_tags_prefab_counts_exact_decimal_math_and_negative_priority(self):
        result = ExactPotPredictor(self.synthetic()).predict(['raw', 'cooked', 'filler', 'filler'], 'crock_pot')
        self.assertEqual(result['tag_totals']['meat'], 0.3)
        self.assertEqual(result['prefab_counts']['shared'], 2)
        self.assertEqual([r['dish_id'] for r in result['outcomes']], ['winner'])

    def test_unsupported_rules_and_extra_probability_weights_fail_closed(self):
        for field, value in [('weight', 2), ('priority', 1.5), ('cooker_scope_hint', 'unknown'),
                             ('conditions', None), ('conditions', {'tag': 'new_tag', 'op': '>', 'value': 0})]:
            data = self.synthetic(); data['recipes'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(PredictionDataError):
                ExactPotPredictor(data)
        data = self.synthetic(); data['metadata']['source_sha256'] = 'unreviewed snapshot'
        with self.assertRaises(PredictionDataError):
            ExactPotPredictor(data)


class PredictionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        cls.server = create_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
        if hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() != cls.before:
            raise AssertionError('Prediction requests modified the content database')

    def get(self, params):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request('GET', '/api/predict?' + params)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_successful_unicode_outcome(self):
        status, result = self.get(urlencode({'cooker': 'crock_pot', 'ingredient': ['smallmeat', 'berries', 'berries', 'berries']}, doseq=True))
        self.assertEqual(status, 200)
        self.assertEqual(result['outcomes'][0]['name_zh'], '肉丸')
        self.assertEqual(result['outcomes'][0]['probability']['value'], 1)

    def test_invalid_input_returns_422_not_an_outcome(self):
        for params in ['', 'cooker=crock_pot&ingredient=berries',
                       'cooker=crock_pot&cooker=portable&ingredient=berries',
                       'cooker=unknown&' + '&'.join(['ingredient=berries'] * 4),
                       'cooker=crock_pot&' + '&'.join(['ingredient=not-in-dataset'] * 4),
                       'cooker=crock_pot&extra=value', '&'.join(['ingredient=berries'] * 17)]:
            with self.subTest(params=params):
                status, result = self.get(params)
                self.assertEqual(status, 422)
                self.assertIn('error', result)
                self.assertNotIn('outcomes', result)

    def test_unsupported_dataset_disables_prediction_but_preserves_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'content.sqlite'
            source = sqlite3.connect(DEFAULT_DATABASE)
            destination = sqlite3.connect(database)
            try:
                source.backup(destination)
                destination.execute('UPDATE recipe_rules SET weight=2 WHERE dish_id=(SELECT dish_id FROM recipe_rules LIMIT 1)')
                destination.commit()
            finally:
                destination.close(); source.close()
            with create_server(0, database) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    conn.request('GET', '/api/catalog')
                    response = conn.getresponse(); data = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertFalse(data['prediction']['enabled'])
                    self.assertEqual(len(data['dishes']), 81)
                    conn.request('GET', '/api/predict?cooker=crock_pot&' + '&'.join(['ingredient=berries'] * 4))
                    response = conn.getresponse(); data = json.loads(response.read())
                    self.assertEqual(response.status, 503)
                    self.assertIn('error', data)
                finally:
                    conn.close(); server.shutdown(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
