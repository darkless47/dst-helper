"""Catalog/HTTP contracts and independent grammar fixtures; no game outcome claims."""
import hashlib
import http.client
import json
import sqlite3
import threading
import unittest
from urllib.parse import urlencode

from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.rules import describe_ast, validate_ast
from handbook.server import create_server


class RulesTests(unittest.TestCase):
    def test_independent_nested_example(self):
        ast = {'all': [
            {'tag': 'veggie', 'op': '>=', 'value': 0.5},
            {'any': [{'item_sum': ['a', 'b'], 'op': '>=', 'value': 2},
                     {'tag': 'meat', 'op': '==', 'value': 0}]},
        ]}
        validate_ast(ast, known_prefabs={'a', 'b'})
        self.assertEqual(describe_ast(ast, {'a': '甲', 'b': '乙'}),
                         '（蔬菜度 ≥ 0.5 且 （甲 + 乙 的合计数量 ≥ 2 或 肉度 = 0））')

    def test_empty_boolean_branches(self):
        self.assertIn('无额外条件', describe_ast({'all': []}))
        self.assertEqual(describe_ast({'any': []}), '无可满足的分支')

    def test_rejects_unsupported_or_ambiguous_rules(self):
        invalid = [None, [], {'all': [], 'any': []}, {'all': {}},
                   {'tag': 'preprocessed', 'op': '==', 'value': 0},
                   {'tag': 'meat', 'op': '!=', 'value': 1},
                   {'tag': 'meat', 'op': '==', 'value': True},
                   {'tag': 'meat', 'op': '==', 'value': float('nan')},
                   {'tag': 'meat', 'op': '==', 'value': 0, 'extra': 1},
                   {'item_sum': ['a', 'a'], 'op': '>=', 'value': 1},
                   {'item_sum': [], 'op': '>=', 'value': 1}]
        for ast in invalid:
            with self.subTest(ast=ast), self.assertRaises(ValueError):
                validate_ast(ast)
        with self.assertRaises(ValueError):
            validate_ast({'item_sum': ['missing'], 'op': '==', 'value': 1}, known_prefabs={'a'})

    def test_limits_nesting(self):
        ast = {'all': []}
        for _ in range(34):
            ast = {'all': [ast]}
        with self.assertRaises(ValueError):
            validate_ast(ast)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()

    def test_read_only_connection_cannot_mutate_content(self):
        before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        with self.catalog.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM dishes')
            db.execute('PRAGMA query_only=OFF')
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE dataset_metadata SET value_json='true' WHERE key='solver_ready'")
        self.assertEqual(hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest(), before)

    def test_preserves_nulls_and_separate_evidence_levels(self):
        data = self.catalog.overview()
        self.assertEqual(data['metadata']['target_build'], '762172')
        self.assertEqual(data['metadata']['verification'], 'single_wiki_snapshot')
        self.assertFalse(data['metadata']['solver_ready'])
        self.assertTrue(all(not d['solver_ready'] and d['weight'] is None for d in data['dishes']))
        jelly = self.catalog.detail('dish', 'huiji:彩虹糖豆')
        self.assertIsNone(jelly['base_health'])
        self.assertEqual(jelly['health_source_text'], '122(2+120)')
        self.assertIsNone(jelly['perish_game_days'])
        self.assertEqual(jelly['perish_source_text'], '无')
        self.assertIsNone(self.catalog.detail('dish', 'huiji:舒缓茶')['base_sanity'])

    def test_state_identity_is_preserved(self):
        data = self.catalog.overview()
        bricks = [i for i in data['ingredients'] if i['prefab_id'] == 'wx78_foodbrick']
        self.assertEqual(len(bricks), 2)
        self.assertNotEqual(bricks[0]['ingredient_id'], bricks[1]['ingredient_id'])
        self.assertNotEqual(bricks[0]['source_row'], bricks[1]['source_row'])
        # This snapshot reports equal tags for these states; identity must still survive.
        self.assertEqual(bricks[0]['tags'], bricks[1]['tags'])
        self.assertEqual(len(self.catalog.detail('ingredient', bricks[1]['ingredient_id'])['states']), 2)

    def test_every_record_has_evidence_and_draft_rule_can_be_described(self):
        data = self.catalog.overview()
        self.assertEqual((len(data['dishes']), len(data['ingredients'])), (81, 145))
        for kind, rows, key in [('dish', data['dishes'], 'dish_id'),
                                ('ingredient', data['ingredients'], 'ingredient_id')]:
            for row in rows:
                d = self.catalog.detail(kind, row[key])
                self.assertEqual(d['source_row'], d['evidence']['row_index'])
                self.assertEqual(len(d['evidence']['cells']), 10 if kind == 'dish' else 17)
                self.assertFalse(d['asset']['redistributable'])
                self.assertIsNone(d['source']['game_build_verified'])
                if kind == 'dish':
                    self.assertIsNone(d['rule']['display_error'])
                    self.assertTrue(d['rule']['description'])
        with self.assertRaises(KeyError):
            self.catalog.detail('dish', "' OR 1=1 --")
        with self.assertRaises(KeyError):
            self.catalog.detail('assets', 'anything')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
        cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        if hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() != cls.before:
            raise AssertionError('HTTP access mutated content database')

    def request(self, path, method='GET'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_pages_and_unicode_api(self):
        for path in ['/', '/app.js', '/prediction.js', '/signature.js', '/app.css', '/favicon.svg']:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn('charset=utf-8', headers['Content-Type'])
                self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
                self.assertTrue(body)
        status, _, body = self.request('/api/catalog')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['dishes']), 81)
        status, _, body = self.request('/api/detail?' + urlencode({'kind': 'dish', 'id': 'huiji:彩虹糖豆'}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['name_zh'], '彩虹糖豆')

    def test_does_not_serve_private_files_or_accept_writes(self):
        for path in ['/dst_cooking.sqlite', '/data/snapshot.json', '/../README.md', '/%2e%2e/README.md',
                     '/api/detail?kind=dish&id=missing', '/api/detail?kind=dataset_metadata&id=x',
                     '/assets/../README.md', '/assets/%2e%2e/README.md', '/assets/source.html',
                     '/wiki-webpage-save/', '/assets/stat-unknown.png']:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)
        for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            self.assertEqual(self.request('/api/catalog', method)[0], 405)
        status, _, body = self.request('/', 'HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')

    def test_available_images_are_png_responses(self):
        _, _, body = self.request('/api/catalog')
        media = json.loads(body)['media']
        for image in [*list(media['catalog_images'].values())[:2], *media['stat_icons'].values()]:
            status, headers, body = self.request(image['url'])
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'image/png')
            self.assertTrue(body.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(int(headers['Content-Length']), len(body))


if __name__ == '__main__':
    unittest.main()
