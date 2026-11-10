"""Signature-only display preferences must never change cooking competition."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.exclusions import ExclusionConflict, SignatureExclusions
from handbook.prediction import PredictionInputError
from handbook.server import create_server

DEFAULT_IDS = {'huiji:蒸树枝', 'huiji:潮湿黏糊', 'huiji:怪物千层饼'}


class ExclusionStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'exclusions.json'
        self.ids = DEFAULT_IDS | {'one', 'two'}
        self.store = SignatureExclusions(self.path, self.ids)

    def tearDown(self):
        self.folder.cleanup()

    def test_defaults_add_remove_clear_and_restart_persistence(self):
        current = self.store.snapshot()
        self.assertEqual(set(current['dish_ids']), DEFAULT_IDS)
        for dish in DEFAULT_IDS:
            current = self.store.update(dish, False, current['version'])
        self.assertEqual(current['dish_ids'], [])
        reopened = SignatureExclusions(self.path, self.ids)
        self.assertEqual(reopened.snapshot()['dish_ids'], [])
        current = reopened.update('one', True, current['version'])
        self.assertEqual(SignatureExclusions(self.path, self.ids).snapshot(), current)
        self.assertEqual(reopened.update('one', True, current['version']), current)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['dish_ids'], ['one'])

    def test_invalid_inputs_conflicts_and_external_json_edits(self):
        before = self.store.snapshot()
        for dish, excluded in [('unknown', True), ('one', 1), ('one', 'true'), (None, False)]:
            with self.subTest(dish=dish, excluded=excluded), self.assertRaises(PredictionInputError):
                self.store.update(dish, excluded, before['version'])
        self.path.write_text(json.dumps(dict(schema_version=1, dish_ids=['two', 'dormant-id'])), encoding='utf-8')
        with self.assertRaises(ExclusionConflict):
            self.store.update('one', True, before['version'])
        current = self.store.snapshot()
        self.assertEqual(current['dish_ids'], ['two'])
        self.store.update('one', True, current['version'])
        self.assertIn('dormant-id', json.loads(self.path.read_text(encoding='utf-8'))['dish_ids'])

    def test_atomic_failed_write_preserves_file_and_malformed_file_is_not_reset(self):
        before = self.path.read_bytes()
        with patch('handbook.exclusions.os.replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.store.update('one', True, self.store.snapshot()['version'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.signature-exclusions-*')), [])
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            SignatureExclusions(self.path, self.ids)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{broken')

    def test_concurrent_lan_edits_do_not_silently_replace_each_other(self):
        version = self.store.snapshot()['version']
        def edit(dish):
            try:
                self.store.update(dish, True, version)
                return True
            except ExclusionConflict:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(edit, ['one', 'two'])), [False, True])

    def test_filter_both_groups_without_mutating_underlying_witnesses_or_probability(self):
        example = dict(probability=dict(numerator=1, denominator=2, value=0.5))
        result = dict(special=[dict(dish_id='one', example=example), dict(dish_id='two', example=example)],
                      other=[dict(dish_id='huiji:潮湿黏糊', example=example)], complete=True)
        self.store.update('one', True, self.store.snapshot()['version'])
        filtered = self.store.filter(result)
        self.assertEqual([row['dish_id'] for row in filtered['special']], ['two'])
        self.assertEqual(filtered['other'], [])
        self.assertEqual(filtered['special'][0]['example']['probability']['value'], 0.5)
        self.assertEqual(len(result['special']), 2)
        self.assertEqual(len(result['other']), 1)


class ExclusionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        cls.server = create_server(0, settings_path=Path(cls.folder.name) / 'settings.sqlite')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
        cls.folder.cleanup()
        assert hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() == cls.before

    def request(self, path, payload=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        try:
            connection.request('POST' if payload is not None else 'GET', path,
                               body=json.dumps(payload) if payload is not None else None,
                               headers=headers or {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_signature_filter_is_reversible_and_all_other_modules_stay_identical(self):
        _, catalog_before = self.request('/api/catalog')
        _, rarity_before = self.request('/api/rarity')
        fixtures = [('huiji:蒸树枝', ['twigs'] * 4), ('huiji:潮湿黏糊', ['nightmarefuel'] * 4),
                    ('huiji:怪物千层饼', ['monstermeat', 'monstermeat', 'ice', 'ice'])]
        for dish, ingredients in fixtures:
            with self.subTest(dish=dish):
                prediction_query = '/api/predict?' + urlencode([('cooker', 'crock_pot'), *[('ingredient', item) for item in ingredients]])
                _, predicted = self.request(prediction_query)
                self.assertIn(dish, {row['dish_id'] for row in predicted['outcomes']})
                example_query = '/api/examples?' + urlencode(dict(dish=dish, cooker='crock_pot'))
                _, example_before = self.request(example_query)
                _, preferences = self.request('/api/signature-exclusions')
                self.assertIn(dish, preferences['dish_ids'])
                signature_query = '/api/signature?' + urlencode(dict(ingredient=ingredients[0], cooker='crock_pot'))
                _, hidden = self.request(signature_query)
                self.assertNotIn(dish, {row['dish_id'] for row in hidden['special'] + hidden['other']})
                status, restored = self.request('/api/signature-exclusions', dict(dish_id=dish, excluded=False, expected_version=preferences['version']))
                self.assertEqual(status, 200)
                _, visible = self.request(signature_query)
                self.assertIn(dish, {row['dish_id'] for row in visible['special'] + visible['other']})
                self.assertEqual(self.request(prediction_query)[1], predicted)
                self.assertEqual(self.request(example_query)[1], example_before)
                self.request('/api/signature-exclusions', dict(dish_id=dish, excluded=True, expected_version=restored['version']))
        _, catalog_after = self.request('/api/catalog')
        for key in ['dishes', 'ingredients', 'metadata', 'prediction']:
            self.assertEqual(catalog_before[key], catalog_after[key])
        self.assertEqual(len(catalog_after['dishes']), 81)
        self.assertEqual(self.request('/api/rarity')[1], rarity_before)
        # Lower-priority fallback is still suppressed by the hidden winning recipe.
        _, twigs = self.request('/api/signature?ingredient=twigs&cooker=crock_pot')
        raw = self.server.RequestHandlerClass.keywords['signature'].recommend('twigs', 'crock_pot')
        excluded = set(self.request('/api/signature-exclusions')[1]['dish_ids'])
        for group in ['special', 'other']:
            self.assertEqual(twigs[group], [row for row in raw[group] if row['dish_id'] not in excluded])

    def test_validation_conflicts_origin_guard_and_no_raw_file_access(self):
        _, preferences = self.request('/api/signature-exclusions')
        payload = dict(dish_id='huiji:华夫饼', excluded=True, expected_version=preferences['version'])
        for bad in [dict(payload, dish_id='unknown'), dict(payload, excluded=1), dict(payload, extra=1), {}]:
            self.assertEqual(self.request('/api/signature-exclusions', bad)[0], 422)
        self.assertEqual(self.request('/api/signature-exclusions', payload, {'Content-Type': 'application/json', 'Origin': 'http://unrelated.example'})[0], 403)
        self.assertEqual(self.request('/api/signature-exclusions', payload, {'Content-Type': 'text/plain'})[0], 422)
        self.assertEqual(self.request('/api/signature-exclusions', payload)[0], 200)
        status, conflict = self.request('/api/signature-exclusions', payload)
        self.assertEqual(status, 409)
        self.assertIn('exclusions', conflict)
        self.request('/api/signature-exclusions', dict(payload, excluded=False, expected_version=conflict['exclusions']['version']))
        self.assertEqual(self.request('/.local/signature_exclusions.json')[0], 404)
        with self.assertRaises(ValueError):
            create_server(0, settings_path=Path(self.folder.name) / 'settings.sqlite', exclusions_path=DEFAULT_DATABASE)


if __name__ == '__main__':
    unittest.main()
