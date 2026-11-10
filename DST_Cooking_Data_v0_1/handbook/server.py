"""Read-only wiki content and stateless calculations; preferences live in browsers."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .catalog import Catalog, DEFAULT_DATABASE
from .assets import DEFAULT_ASSET_ROOT, LocalAssets
from .prediction import ExactPotPredictor, PredictionDataError, PredictionInputError
from .examples import RecipePlanner
from .settings import DEFAULT_SETTINGS, CookingDefaults, validate_rarities
from .exclusions import DEFAULTS as DEFAULT_EXCLUSIONS, DefaultExclusions

WEB = Path(__file__).with_name('web')
STATIC = {'/': ('index.html', 'text/html'),
          '/app.css': ('app.css', 'text/css'), '/app.js': ('app.js', 'text/javascript'),
          '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
STATIC['/prediction.js'] = ('prediction.js', 'text/javascript')
STATIC['/signature.js'] = ('signature.js', 'text/javascript')
STATIC['/rarity.js'] = ('rarity.js', 'text/javascript')
STATIC['/examples.js'] = ('examples.js', 'text/javascript')
STATIC['/exclusions.js'] = ('exclusions.js', 'text/javascript')
STATIC['/browser-storage.js'] = ('browser-storage.js', 'text/javascript')


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, catalog, media, predictor, signature, settings, exclusions, prediction_error, **kwargs):
        self.catalog = catalog
        self.media = media
        self.predictor = predictor
        self.signature = signature
        self.settings = settings
        self.exclusions = exclusions
        self.prediction_error = prediction_error
        super().__init__(*args, **kwargs)

    def respond(self, status, payload, content_type='application/json', head=False):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        charset = '; charset=utf-8' if content_type != 'image/png' else ''
        self.send_header('Content-Type', content_type + charset)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if not head:
            try:
                self.wfile.write(payload)
            except ConnectionError:
                pass  # The user may switch ingredients and cancel an in-flight search.

    def do_GET(self, head=False):
        url = urlsplit(self.path)
        try:
            if url.path in STATIC:
                filename, content_type = STATIC[url.path]
                self.respond(200, (WEB / filename).read_bytes(), content_type, head)
            elif url.path == '/api/catalog':
                data = self.catalog.overview()
                preferences = self.settings.snapshot()
                data['settings'] = preferences
                for row in data['ingredients']:
                    row['rarity'] = preferences['rarities'].get(row['ingredient_id'], 0)
                data['media'] = self.media.overview()
                data['media']['stat_provenance'] = self.media.stat_provenance()
                data['prediction'] = (self.predictor.capabilities() if self.predictor else
                                      dict(enabled=False, error=self.prediction_error))
                data['signature'] = dict(enabled=self.signature is not None, error=self.prediction_error,
                                         exclusions=self.exclusions.snapshot())
                self.respond(200, data, head=head)
            elif url.path == '/api/predict':
                if not self.predictor:
                    self.respond(503, {'error': self.prediction_error}, head=head)
                    return
                try:
                    query = parse_qs(url.query, keep_blank_values=True, max_num_fields=16)
                except ValueError as error:
                    raise PredictionInputError('预测参数过多。') from error
                if set(query) - {'ingredient', 'cooker'} or len(query.get('cooker', [])) != 1:
                    raise PredictionInputError('请提供四件食材及一个锅具。')
                self.respond(200, self.predictor.predict(query.get('ingredient', []), query['cooker'][0]), head=head)
            elif url.path == '/api/signature':
                if not self.signature:
                    self.respond(503, {'error': self.prediction_error}, head=head)
                    return
                try:
                    query = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                except ValueError as error:
                    raise PredictionInputError('优选料理参数过多。') from error
                if set(query) != {'ingredient', 'cooker'} or any(len(values) != 1 for values in query.values()):
                    raise PredictionInputError('请选择一种食材和一个锅具。')
                result = self.signature.recommend(query['ingredient'][0], query['cooker'][0])
                self.respond(200, result, head=head)
            elif url.path == '/api/examples':
                if not self.signature:
                    self.respond(503, {'error': self.prediction_error}, head=head)
                    return
                try:
                    query = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                except ValueError as error:
                    raise PredictionInputError('料理示例参数过多。') from error
                if set(query) != {'dish', 'cooker'} or any(len(values) != 1 for values in query.values()):
                    raise PredictionInputError('请选择一道料理和一个锅具。')
                self.respond(200, self.signature.examples(query['dish'][0], query['cooker'][0]), head=head)
            elif url.path == '/api/rarity':
                self.respond(200, self.settings.snapshot(), head=head)
            elif url.path == '/api/signature-exclusions':
                self.respond(200, self.exclusions.snapshot(), head=head)
            elif url.path == '/api/detail':
                query = parse_qs(url.query)
                data = self.catalog.detail(query.get('kind', [''])[0], query.get('id', [''])[0])
                data['local_image'] = self.media.provenance(data['icon_asset_id'])
                if query.get('kind', [''])[0] == 'ingredient':
                    preferences = self.settings.snapshot()
                    data['rarity'] = preferences['rarities'].get(data['ingredient_id'], 0)
                    data['rarity_version'] = preferences['version']
                self.respond(200, data, head=head)
            elif url.path.startswith('/assets/'):
                self.respond(200, self.media.get(url.path), 'image/png', head=head)
            else:
                self.respond(404, {'error': '未找到内容'}, head=head)
        except PredictionInputError as error:
            self.respond(422, {'error': str(error)}, head=head)
        except PredictionDataError as error:
            self.respond(503, {'error': str(error)}, head=head)
        except KeyError:
            self.respond(404, {'error': '未找到该条目'}, head=head)
        except (OSError, ValueError, sqlite3.Error):
            self.respond(500, {'error': '无法读取内容快照。请检查数据库与迁移版本。'}, head=head)

    def do_HEAD(self):
        self.do_GET(head=True)

    def read_json(self, max_size=16384):
        origin = self.headers.get('Origin')
        try:
            allowed = not origin or (urlsplit(origin).scheme in ('http', 'https') and urlsplit(origin).netloc == self.headers.get('Host'))
        except ValueError:
            allowed = False
        if not allowed or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.respond(403, {'error': '请从助手页面使用计算功能。'})
            return None
        length = int(self.headers.get('Content-Length', '0'))
        if (self.headers.get_content_type() != 'application/json' or not 0 < length <= max_size
                or self.headers.get('Transfer-Encoding')):
            raise PredictionInputError('请发送大小有效的 JSON 计算请求。')
        value = json.loads(self.rfile.read(length).decode('utf-8'))
        if type(value) is not dict:
            raise PredictionInputError('计算请求须为 JSON 对象。')
        return value

    def do_POST(self):
        if self.path not in ('/api/signature', '/api/examples'):
            self.respond(405, {'error': '偏好仅保存在当前浏览器。'})
            return
        try:
            payload = self.read_json()
            if payload is None:
                return
            subject = 'ingredient' if self.path == '/api/signature' else 'dish'
            if set(payload) != {subject, 'cooker', 'rarities', 'rarity_version'}:
                raise PredictionInputError('请提供条目、锅具、稀有度和浏览器设置版本。')
            if (type(payload[subject]) is not str or type(payload['cooker']) is not str
                    or type(payload['rarity_version']) is not int or not 0 <= payload['rarity_version'] <= 9007199254740991):
                raise PredictionInputError('计算参数无效。')
            rarities = validate_rarities(payload['rarities'], self.settings.ingredient_ids)
            if not self.signature:
                self.respond(503, {'error': self.prediction_error})
                return
            calculate = self.signature.recommend if subject == 'ingredient' else self.signature.examples
            self.respond(200, calculate(payload[subject], payload['cooker'], rarities, payload['rarity_version']))
        except KeyError:
            self.respond(404, {'error': '未找到该条目'})
        except PredictionDataError as error:
            self.respond(503, {'error': str(error)})
        except (ValueError, UnicodeError, RecursionError) as error:
            self.respond(422, {'error': str(error)})

    def reject_write(self):
        self.respond(405, {'error': '此操作不受支持'})

    do_PUT = reject_write
    do_PATCH = reject_write
    do_DELETE = reject_write


def create_server(port=8765, database=DEFAULT_DATABASE, assets_root=DEFAULT_ASSET_ROOT, host='127.0.0.1', settings_path=DEFAULT_SETTINGS, exclusions_path=None, handler_class=Handler):
    bind_host = '127.0.0.1' if host.casefold() == 'localhost' else host
    catalog = Catalog(database)
    overview = catalog.overview()  # Fail before announcing a usable local URL.
    settings = CookingDefaults(settings_path, (row['ingredient_id'] for row in overview['ingredients']))
    exclusions = DefaultExclusions(exclusions_path or DEFAULT_EXCLUSIONS,
                                   {row['dish_id'] for row in overview['dishes']})
    media = LocalAssets(catalog.asset_records(), assets_root)
    predictor, signature, prediction_error = None, None, None
    try:
        snapshot = catalog.prediction_snapshot()
        predictor = ExactPotPredictor(snapshot)
        signature = RecipePlanner(predictor, snapshot['dishes'], settings)
    except PredictionDataError as error:
        prediction_error = str(error)
    return ThreadingHTTPServer((bind_host, port), partial(handler_class, catalog=catalog, media=media,
                               predictor=predictor, signature=signature, settings=settings, exclusions=exclusions, prediction_error=prediction_error))


def main():
    parser = argparse.ArgumentParser(description='Unofficial DST cooking handbook; local wiki content and editable rarity')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1',
                        help='localhost for local-only access, or your private IPv4 address for LAN sharing (default: 127.0.0.1)')
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    parser.add_argument('--settings', type=Path, default=DEFAULT_SETTINGS,
                        help='Read-only ingredient rarity defaults JSON')
    parser.add_argument('--exclusions', type=Path, default=DEFAULT_EXCLUSIONS, help='Read-only excluded-dish defaults JSON')
    parser.add_argument('--assets', type=Path, default=DEFAULT_ASSET_ROOT,
                        help='Image directory (default: assets/images); saved-page archive roots also supported')
    args = parser.parse_args()
    with create_server(args.port, args.database, args.assets, host=args.host, settings_path=args.settings, exclusions_path=args.exclusions) as server:
        print(f'Unofficial DST handbook: http://{args.host}:{server.server_port}', flush=True)
        print('Read-only wiki snapshot; preferences stored in each browser. Press Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
