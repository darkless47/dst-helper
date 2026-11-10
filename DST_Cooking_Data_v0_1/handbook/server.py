"""Read-only wiki content and separate editable preferences; opt-in LAN binding."""
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
from .settings import DEFAULT_SETTINGS, SettingsConflict, UserSettings
from .exclusions import ExclusionConflict, SignatureExclusions

WEB = Path(__file__).with_name('web')
STATIC = {'/': ('index.html', 'text/html'),
          '/app.css': ('app.css', 'text/css'), '/app.js': ('app.js', 'text/javascript'),
          '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
STATIC['/prediction.js'] = ('prediction.js', 'text/javascript')
STATIC['/signature.js'] = ('signature.js', 'text/javascript')
STATIC['/rarity.js'] = ('rarity.js', 'text/javascript')
STATIC['/examples.js'] = ('examples.js', 'text/javascript')
STATIC['/exclusions.js'] = ('exclusions.js', 'text/javascript')


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
                self.respond(200, self.exclusions.filter(result), head=head)
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

    def do_POST(self):
        if self.path not in ('/api/rarity', '/api/signature-exclusions'):
            self.respond(405, {'error': '维基目录只提供只读访问'})
            return
        origin = self.headers.get('Origin')
        try:
            allowed_origin = not origin or (urlsplit(origin).scheme in ('http', 'https') and urlsplit(origin).netloc == self.headers.get('Host'))
        except ValueError:
            allowed_origin = False
        if not allowed_origin or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.respond(403, {'error': '请从本手册页面保存设置。'})
            return
        try:
            if self.headers.get_content_type() != 'application/json':
                raise PredictionInputError('请使用 JSON 保存设置。')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096 or self.headers.get('Transfer-Encoding'):
                raise PredictionInputError('设置请求大小无效。')
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if self.path == '/api/rarity':
                if not isinstance(payload, dict) or set(payload) != {'ingredient_id', 'rarity', 'expected_version'}:
                    raise PredictionInputError('请提供食材、整数稀有度和设置版本。')
                self.respond(200, self.settings.update(**payload))
            else:
                if not isinstance(payload, dict) or set(payload) != {'dish_id', 'excluded', 'expected_version'}:
                    raise PredictionInputError('请提供料理、排除状态和名单版本。')
                self.respond(200, self.exclusions.update(**payload))
        except ExclusionConflict as error:
            self.respond(409, dict(error=str(error), exclusions=self.exclusions.snapshot()))
        except SettingsConflict as error:
            self.respond(409, dict(error=str(error), settings=self.settings.snapshot()))
        except (PredictionInputError, ValueError, UnicodeError) as error:
            self.respond(422, {'error': str(error)})
        except (OSError, sqlite3.Error):
            self.respond(500, {'error': '无法保存设置，请检查设置文件是否可写。'})

    def reject_write(self):
        self.respond(405, {'error': '此操作不受支持'})

    do_PUT = reject_write
    do_PATCH = reject_write
    do_DELETE = reject_write


def create_server(port=8765, database=DEFAULT_DATABASE, assets_root=DEFAULT_ASSET_ROOT, host='127.0.0.1', settings_path=DEFAULT_SETTINGS, exclusions_path=None, handler_class=Handler):
    bind_host = '127.0.0.1' if host.casefold() == 'localhost' else host
    catalog = Catalog(database)
    overview = catalog.overview()  # Fail before announcing a usable local URL.
    settings_path = Path(settings_path).resolve()
    if settings_path == catalog.database or (settings_path.exists() and settings_path.samefile(catalog.database)):
        raise ValueError('User settings must be separate from the content snapshot.')
    settings = UserSettings(settings_path, (row['ingredient_id'] for row in overview['ingredients']))
    exclusions_path = Path(exclusions_path).resolve() if exclusions_path is not None else settings_path.with_name('signature_exclusions.json')
    for protected in (catalog.database, settings_path):
        if exclusions_path == protected or (exclusions_path.exists() and exclusions_path.samefile(protected)):
            raise ValueError('Signature exclusions must use a separate JSON file.')
    exclusions = SignatureExclusions(exclusions_path, (row['dish_id'] for row in overview['dishes']))
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
                        help='Separate user-settings SQLite database (default: package .local/user_settings.sqlite)')
    parser.add_argument('--assets', type=Path, default=DEFAULT_ASSET_ROOT,
                        help='Image directory (default: assets/images); saved-page archive roots also supported')
    args = parser.parse_args()
    with create_server(args.port, args.database, args.assets, host=args.host, settings_path=args.settings) as server:
        print(f'Unofficial DST handbook: http://{args.host}:{server.server_port}', flush=True)
        print('Read-only wiki snapshot; rarity settings shared by server users. Press Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
