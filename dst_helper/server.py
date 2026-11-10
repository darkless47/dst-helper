"""Combined Starlette application and Uvicorn command-line launcher."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys

from starlette.concurrency import run_in_threadpool
from starlette.routing import Route
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'DST_Cooking_Data_v0_1'))
from handbook import server as cooking
from .farming import FarmingPlanner

WEB = Path(__file__).with_name('web')
STATIC = {'/': ('home.html', 'text/html'), '/farming': ('farming.html', 'text/html'),
          '/home.js': ('home.js', 'text/javascript'),
          '/helper.css': ('helper.css', 'text/css'), '/farming.js': ('farming.js', 'text/javascript')}


@cooking.read_errors
def farming_overview(request):
    return cooking.respond(200, request.app.state.farming.overview())


async def farming_analyze(request):
    try:
        value = await cooking.read_json(request, max_size=65536)
        result = await run_in_threadpool(request.app.state.farming.analyze, value)
        return cooking.respond(200, result)
    except cooking.RequestError as error:
        return cooking.respond(error.status, {'error': str(error)})
    except (ValueError, UnicodeError, RecursionError) as error:
        return cooking.respond(422, {'error': str(error)})
    except (OSError, sqlite3.Error):
        return cooking.respond(500, {'error': '无法计算规划，请检查数据快照。'})


def create_app(database=cooking.DEFAULT_DATABASE, assets_root=cooking.DEFAULT_ASSET_ROOT,
               settings_path=cooking.DEFAULT_SETTINGS, exclusions_path=None):
    static = {path: (WEB / filename, mime) for path, (filename, mime) in STATIC.items()}
    static.update({path: (cooking.WEB / 'index.html', 'text/html')
                   for path in ('/cooking', '/cooking/')})

    def initialize(app):
        app.state.farming = FarmingPlanner()

    return cooking.create_app(database, assets_root, settings_path, exclusions_path,
                              static=static, initialize=initialize, extra_routes=[
                                  Route('/api/farming', farming_overview),
                                  Route('/api/farming/analyze', farming_analyze, methods=['POST']),
                              ])


def create_server(port=8765, database=cooking.DEFAULT_DATABASE, assets_root=cooking.DEFAULT_ASSET_ROOT,
                  host='127.0.0.1', settings_path=cooking.DEFAULT_SETTINGS, exclusions_path=None):
    from handbook.serving import EmbeddedServer
    return EmbeddedServer(create_app(database, assets_root, settings_path, exclusions_path), host, port)


def main():
    from handbook.serving import SERVER_LOOP
    parser = argparse.ArgumentParser(description='DST Helper: Starlette + Uvicorn')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1', help='Bind address; use 0.0.0.0 inside Docker')
    parser.add_argument('--database', type=Path, default=cooking.DEFAULT_DATABASE)
    parser.add_argument('--assets', type=Path, default=cooking.DEFAULT_ASSET_ROOT)
    parser.add_argument('--settings', type=Path, default=cooking.DEFAULT_SETTINGS, help='Read-only rarity defaults JSON')
    parser.add_argument('--exclusions', type=Path, default=cooking.DEFAULT_EXCLUSIONS, help='Read-only exclusion defaults JSON')
    parser.add_argument('--forwarded-allow-ips', default=os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1,::1'),
                        help='Trusted proxy addresses/networks; use the Nginx address as seen by this process')
    parser.add_argument('--limit-concurrency', type=int, default=64)
    parser.add_argument('--log-level', choices=['critical', 'error', 'warning', 'info', 'debug'], default='info')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.limit_concurrency < 2:
        parser.error('port must be 0–65535 and limit-concurrency must be at least 2')
    app = create_app(args.database, args.assets, args.settings, args.exclusions)
    uvicorn.run(app, host='127.0.0.1' if args.host.casefold() == 'localhost' else args.host,
                port=args.port, workers=1, loop=SERVER_LOOP, ws='none', lifespan='on', log_level=args.log_level,
                proxy_headers=True, forwarded_allow_ips=args.forwarded_allow_ips,
                limit_concurrency=args.limit_concurrency, timeout_keep_alive=5,
                timeout_graceful_shutdown=25)


if __name__ == '__main__':
    main()
