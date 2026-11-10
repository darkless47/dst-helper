"""Tracked defaults and unfiltered stateless calculations; browsers apply exclusions."""
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.exclusions import DEFAULTS, DefaultExclusions
from handbook.server import create_server

DEFAULT_IDS = {'huiji:蒸树枝', 'huiji:潮湿黏糊', 'huiji:怪物千层饼'}


class ExclusionDefaultsTests(unittest.TestCase):
    def test_read_only_defaults_and_independent_snapshots(self):
        before = DEFAULTS.read_bytes()
        ids = {r['dish_id'] for r in Catalog().overview()['dishes']}
        store = DefaultExclusions(DEFAULTS, ids)
        snapshot = store.snapshot()
        self.assertEqual(set(snapshot['dish_ids']), DEFAULT_IDS)
        snapshot['dish_ids'].clear()
        self.assertEqual(set(store.snapshot()['dish_ids']), DEFAULT_IDS)
        self.assertEqual(DEFAULTS.read_bytes(), before)

    def test_malformed_defaults_fail_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'defaults.json'
            for data in [dict(schema_version=True, dish_ids=[]), dict(schema_version=1, dish_ids=['unknown']),
                         dict(schema_version=1, dish_ids=['one', 'one']), dict(schema_version=1, dish_ids=[[]])]:
                path.write_text(json.dumps(data), encoding='utf-8')
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    DefaultExclusions(path, {'one'})
                self.assertEqual(path.read_bytes(), before)


class ExclusionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        cls.server = create_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
        assert hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() == cls.before

    def request(self, path, payload=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            connection.request('POST' if payload is not None else 'GET', path,
                               body=json.dumps(payload) if payload is not None else None,
                               headers=headers or {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_defaults_do_not_remove_winners_from_calculations_or_catalog(self):
        catalog = self.request('/api/catalog')[1]
        self.assertEqual(set(catalog['signature']['exclusions']['dish_ids']), DEFAULT_IDS)
        self.assertEqual(set(self.request('/api/signature-exclusions')[1]['dish_ids']), DEFAULT_IDS)
        fixtures = [('huiji:蒸树枝', ['twigs'] * 4), ('huiji:潮湿黏糊', ['nightmarefuel'] * 4),
                    ('huiji:怪物千层饼', ['monstermeat', 'monstermeat', 'ice', 'ice'])]
        for dish, ingredients in fixtures:
            with self.subTest(dish=dish):
                query = '/api/predict?' + urlencode([('cooker', 'crock_pot'), *[('ingredient', item) for item in ingredients]])
                predicted = self.request(query)[1]
                self.assertIn(dish, {row['dish_id'] for row in predicted['outcomes']})
                payload = dict(ingredient=ingredients[0], cooker='crock_pot', rarities={}, rarity_version=1)
                status, result = self.request('/api/signature', payload)
                self.assertEqual(status, 200)
                self.assertIn(dish, {row['dish_id'] for row in result['special'] + result['other']})
        self.assertEqual(self.request('/api/catalog')[1], catalog)
        self.assertEqual(self.request('/api/signature-exclusions', {})[0], 405)
        self.assertEqual(self.request('/.local/signature_exclusions.json')[0], 404)


if __name__ == '__main__':
    unittest.main()
