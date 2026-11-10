"""Production transport contracts against real Uvicorn sockets."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from dst_helper.server import create_app, create_server


class ProductionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, method='GET', body=None, headers=None, chunked=False, timeout=5):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=timeout)
        try:
            client.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
            response = client.getresponse()
            return response.status, response.headers, response.read()
        finally:
            client.close()

    def test_health_head_and_error_response_headers(self):
        status, headers, body = self.request('/healthz')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'status': 'ok'})
        self.assertEqual(headers['server'], 'uvicorn')
        status, head_headers, body = self.request('/healthz', 'HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(head_headers['content-length'], headers['content-length'])
        for route, method, expected in [('/missing', 'GET', 404), ('/healthz', 'PUT', 405),
                                         ('/api/farming/preferences', 'POST', 405)]:
            status, headers, body = self.request(route, method)
            self.assertEqual(status, expected)
            self.assertIn('error', json.loads(body))
            self.assertEqual(headers['cache-control'], 'no-store')
            self.assertEqual(headers['x-content-type-options'], 'nosniff')
            self.assertIn("frame-ancestors 'none'", headers['content-security-policy'])

    def test_chunked_farming_request_and_public_origin(self):
        plan = json.loads(self.request('/api/farming')[2])['defaults']
        body = json.dumps(plan).encode()
        headers = {'Content-Type': 'application/json; charset=utf-8',
                   'Host': 'helper.example.com', 'Origin': 'https://helper.example.com'}
        status, _, result = self.request('/api/farming/analyze', 'POST',
                                         iter([body[:50], body[50:]]), headers, chunked=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(result)['ratios']), 74)
        for origin in ('https://elsewhere.example', 'http://['):
            status, _, _ = self.request('/api/farming/analyze', 'POST', body,
                                        dict(headers, Origin=origin))
            self.assertEqual(status, 403)

    def test_body_limits_cover_declared_and_streamed_sizes(self):
        headers = {'Content-Type': 'application/json'}
        for route, size in [('/api/signature', 16384), ('/api/farming/analyze', 65536)]:
            with self.subTest(route=route):
                status, _, _ = self.request(route, 'POST', b' ' * (size + 1), headers)
                self.assertEqual(status, 422)
                status, _, body = self.request(route, 'POST', iter([b' ' * size, b'x']),
                                               headers, chunked=True)
                self.assertEqual(status, 422)
                self.assertIn('大小限制', json.loads(body)['error'])
        for invalid in (b'{', b'[]', b'\xff'):
            self.assertEqual(self.request('/api/farming/analyze', 'POST', invalid, headers)[0], 422)

    def test_blank_query_values_cannot_hide_duplicates_or_unknown_fields(self):
        for route in [
            '/api/predict?cooker=crock_pot&cooker=&' + '&'.join(['ingredient=berries'] * 4),
            '/api/signature?ingredient=meat&cooker=crock_pot&extra=',
            '/api/examples?dish=unknown&cooker=crock_pot&extra=',
            '/api/detail?' + '&'.join(['kind=dish'] * 5),
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.request(route)[0], 422)

    def test_synchronous_calculation_does_not_block_other_requests(self):
        planner = self.server.server.config.app.state.farming
        entered, release = threading.Event(), threading.Event()
        original = planner.analyze

        def slow_calculation(plan):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release calculation')
            return original(plan)

        plan = json.dumps(planner.defaults()).encode()
        with patch.object(planner, 'analyze', slow_calculation), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, '/api/farming/analyze', 'POST', plan,
                                 {'Content-Type': 'application/json'})
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.request('/healthz', timeout=1)[0], 200)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=5)[0], 200)


class StartupTests(unittest.TestCase):
    def test_missing_content_database_fails_lifespan_before_serving(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(database=Path(temporary) / 'missing.sqlite')

            async def startup():
                async with app.router.lifespan_context(app):
                    self.fail('Missing content must not be served as a ready application')

            with self.assertRaises(sqlite3.OperationalError):
                asyncio.run(startup())


if __name__ == '__main__':
    unittest.main()
