"""Starlette routes for read-only content and browser-owned preferences."""
from contextlib import asynccontextmanager
from functools import wraps
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

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
for name in ('prediction', 'signature', 'rarity', 'examples', 'exclusions', 'browser-storage'):
    STATIC[f'/{name}.js'] = (f'{name}.js', 'text/javascript')

SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'self'; connect-src 'self'; object-src 'none'; "
                               "base-uri 'none'; frame-ancestors 'none'",
}


def respond(status, payload, content_type='application/json'):
    if not isinstance(payload, bytes):
        payload = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    charset = '' if content_type == 'image/png' else '; charset=utf-8'
    return Response(payload, status_code=status,
                    headers={**SECURITY_HEADERS, 'Content-Type': content_type + charset})


class ResponseHeaders:
    """Apply headers and HEAD semantics to framework errors as well as our routes."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def send_response(message):
            if message['type'] == 'http.response.start':
                headers = dict(message['headers'])
                headers.update((k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS.items())
                message['headers'] = list(headers.items())
            elif message['type'] == 'http.response.body' and scope['method'] == 'HEAD':
                message['body'] = b''
            await send(message)

        await self.app(scope, receive, send_response)


class CookingServices:
    def __init__(self, database, assets_root, settings_path, exclusions_path):
        self.catalog = Catalog(database)
        overview = self.catalog.overview()
        self.settings = CookingDefaults(settings_path, (i['ingredient_id'] for i in overview['ingredients']))
        self.exclusions = DefaultExclusions(exclusions_path or DEFAULT_EXCLUSIONS,
                                           {d['dish_id'] for d in overview['dishes']})
        self.media = LocalAssets(self.catalog.asset_records(), assets_root)
        self.predictor, self.signature, self.prediction_error = None, None, None
        try:
            snapshot = self.catalog.prediction_snapshot()
            self.predictor = ExactPotPredictor(snapshot)
            self.signature = RecipePlanner(self.predictor, snapshot['dishes'], self.settings)
        except PredictionDataError as error:
            self.prediction_error = str(error)


def read_errors(endpoint):
    @wraps(endpoint)
    def checked(request):
        try:
            return endpoint(request)
        except PredictionInputError as error:
            return respond(422, {'error': str(error)})
        except PredictionDataError as error:
            return respond(503, {'error': str(error)})
        except KeyError:
            return respond(404, {'error': '未找到该条目'})
        except (OSError, ValueError, sqlite3.Error):
            return respond(500, {'error': '无法读取内容快照。请检查数据库与迁移版本。'})
    return checked


@read_errors
def static_file(request):
    path, mime = request.app.state.static[request.url.path]
    return respond(200, path.read_bytes(), mime)


@read_errors
def catalog(request):
    service = request.app.state.cooking
    data = service.catalog.overview()
    preferences = service.settings.snapshot()
    data['settings'] = preferences
    for row in data['ingredients']:
        row['rarity'] = preferences['rarities'].get(row['ingredient_id'], 0)
    data['media'] = service.media.overview()
    data['media']['stat_provenance'] = service.media.stat_provenance()
    data['prediction'] = (service.predictor.capabilities() if service.predictor else
                          dict(enabled=False, error=service.prediction_error))
    data['signature'] = dict(enabled=service.signature is not None, error=service.prediction_error,
                             exclusions=service.exclusions.snapshot())
    return respond(200, data)


@read_errors
def predict(request):
    service = request.app.state.cooking
    if not service.predictor:
        return respond(503, {'error': service.prediction_error})
    try:
        query = parse_qs(request.url.query, keep_blank_values=True, max_num_fields=16)
    except ValueError as error:
        raise PredictionInputError('预测参数过多。') from error
    if set(query) - {'ingredient', 'cooker'} or len(query.get('cooker', [])) != 1:
        raise PredictionInputError('请提供四件食材及一个锅具。')
    return respond(200, service.predictor.predict(query.get('ingredient', []), query['cooker'][0]))


@read_errors
def suggestions(request):
    service = request.app.state.cooking
    if not service.signature:
        return respond(503, {'error': service.prediction_error})
    subject = 'ingredient' if request.url.path == '/api/signature' else 'dish'
    try:
        query = parse_qs(request.url.query, keep_blank_values=True, max_num_fields=4)
    except ValueError as error:
        raise PredictionInputError('计算参数过多。') from error
    allowed = {subject, 'cooker'} | ({'guaranteed_only'} if subject == 'dish' else set())
    if (not {subject, 'cooker'} <= set(query) or set(query) - allowed
            or any(len(values) != 1 for values in query.values())):
        raise PredictionInputError('请选择条目和一个锅具。')
    options = {}
    if 'guaranteed_only' in query:
        if query['guaranteed_only'][0] not in ('true', 'false'):
            raise PredictionInputError('确定配方筛选须为 true 或 false。')
        options['guaranteed_only'] = query['guaranteed_only'][0] == 'true'
    calculate = service.signature.recommend if subject == 'ingredient' else service.signature.examples
    return respond(200, calculate(query[subject][0], query['cooker'][0], **options))


@read_errors
def rarity(request):
    return respond(200, request.app.state.cooking.settings.snapshot())


@read_errors
def exclusions(request):
    return respond(200, request.app.state.cooking.exclusions.snapshot())


@read_errors
def detail(request):
    service = request.app.state.cooking
    try:
        query = parse_qs(request.url.query, max_num_fields=4)
    except ValueError as error:
        raise PredictionInputError('查询参数过多。') from error
    data = service.catalog.detail(query.get('kind', [''])[0], query.get('id', [''])[0])
    data['local_image'] = service.media.provenance(data['icon_asset_id'])
    if query.get('kind', [''])[0] == 'ingredient':
        preferences = service.settings.snapshot()
        data['rarity'] = preferences['rarities'].get(data['ingredient_id'], 0)
        data['rarity_version'] = preferences['version']
    return respond(200, data)


@read_errors
def asset(request):
    return respond(200, request.app.state.cooking.media.get(request.url.path), 'image/png')


def health(request):
    ready = request.app.state.cooking.predictor is not None
    return respond(200 if ready else 503, {'status': 'ok' if ready else 'degraded'})


class RequestError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


async def read_json(request: Request, max_size=16384):
    """Enforce the actual streamed size, including requests without Content-Length."""
    origin = request.headers.get('origin')
    try:
        allowed = not origin or (urlsplit(origin).scheme in ('http', 'https')
                                 and urlsplit(origin).netloc == request.headers.get('host'))
    except ValueError:
        allowed = False
    if not allowed or request.headers.get('sec-fetch-site') == 'cross-site':
        raise RequestError(403, '请从助手页面使用计算功能。')
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise PredictionInputError('请发送 JSON 计算请求。')
    length = request.headers.get('content-length')
    if length is not None and not 0 < int(length) <= max_size:
        raise PredictionInputError('请发送大小有效的 JSON 计算请求。')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_size:
            raise PredictionInputError('计算请求超过大小限制。')
        body.extend(chunk)
    value = json.loads(body.decode('utf-8'))
    if type(value) is not dict:
        raise PredictionInputError('计算请求须为 JSON 对象。')
    return value


async def calculate(request):
    try:
        payload = await read_json(request)
        subject = 'ingredient' if request.url.path == '/api/signature' else 'dish'
        required = {subject, 'cooker', 'rarities', 'rarity_version'}
        allowed = required | ({'guaranteed_only'} if subject == 'dish' else set())
        if not required <= set(payload) or set(payload) - allowed:
            raise PredictionInputError('请提供条目、锅具、稀有度和浏览器设置版本。')
        options = {}
        if 'guaranteed_only' in payload:
            if type(payload['guaranteed_only']) is not bool:
                raise PredictionInputError('确定配方筛选须为布尔值。')
            options['guaranteed_only'] = payload['guaranteed_only']
        if (type(payload[subject]) is not str or type(payload['cooker']) is not str
                or type(payload['rarity_version']) is not int
                or not 0 <= payload['rarity_version'] <= 9007199254740991):
            raise PredictionInputError('计算参数无效。')
        service = request.app.state.cooking
        rarities = validate_rarities(payload['rarities'], service.settings.ingredient_ids)
        if not service.signature:
            return respond(503, {'error': service.prediction_error})
        function = service.signature.recommend if subject == 'ingredient' else service.signature.examples
        result = await run_in_threadpool(function, payload[subject], payload['cooker'], rarities,
                                        payload['rarity_version'], **options)
        return respond(200, result)
    except RequestError as error:
        return respond(error.status, {'error': str(error)})
    except KeyError:
        return respond(404, {'error': '未找到该条目'})
    except PredictionDataError as error:
        return respond(503, {'error': str(error)})
    except (ValueError, UnicodeError, RecursionError) as error:
        return respond(422, {'error': str(error)})


async def suggestion_route(request):
    if request.method == 'POST':
        return await calculate(request)
    return await run_in_threadpool(suggestions, request)


def http_error(request, error):
    status = error.status_code
    if status == 404 and request.method not in ('GET', 'HEAD'):
        status = 405
    message = '此操作不受支持' if status == 405 else '未找到内容'
    response = respond(status, {'error': message})
    response.headers.update(error.headers or {})
    return response


def server_error(request, error):
    return respond(500, {'error': '无法处理请求。'})


def create_app(database=DEFAULT_DATABASE, assets_root=DEFAULT_ASSET_ROOT,
               settings_path=DEFAULT_SETTINGS, exclusions_path=None, *,
               static=None, extra_routes=(), initialize=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.cooking = await run_in_threadpool(CookingServices, database, assets_root,
                                                    settings_path, exclusions_path)
        if initialize:
            await run_in_threadpool(initialize, app)
        yield

    files = {path: (WEB / filename, mime) for path, (filename, mime) in STATIC.items()}
    files.update(static or {})
    routes = [Route(path, static_file) for path in files]
    routes.extend([
        Route('/healthz', health), Route('/api/catalog', catalog), Route('/api/predict', predict),
        Route('/api/signature', suggestion_route, methods=['GET', 'POST']),
        Route('/api/examples', suggestion_route, methods=['GET', 'POST']),
        Route('/api/rarity', rarity), Route('/api/signature-exclusions', exclusions),
        Route('/api/detail', detail), Route('/assets/{filename:path}', asset),
        *extra_routes,
    ])
    app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(ResponseHeaders)],
                    exception_handlers={HTTPException: http_error, Exception: server_error})
    app.router.redirect_slashes = False
    app.state.static = files
    return app


def create_server(port=8765, database=DEFAULT_DATABASE, assets_root=DEFAULT_ASSET_ROOT,
                  host='127.0.0.1', settings_path=DEFAULT_SETTINGS, exclusions_path=None):
    """Embedded Uvicorn runner retained for local HTTP acceptance tests."""
    from .serving import EmbeddedServer
    return EmbeddedServer(create_app(database, assets_root, settings_path, exclusions_path), host, port)


def main():
    # The historical Cooking command now starts the same combined production app.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dst_helper.server import main as run
    run()


if __name__ == '__main__':
    main()
