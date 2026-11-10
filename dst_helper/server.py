"""Shared local home and farming routes, delegating cooking to the existing app."""
import argparse
from functools import partial
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'DST_Cooking_Data_v0_1'))
from handbook import server as cooking
from .farming import FarmingPlanner, PlanConflict, PlanStore

WEB = Path(__file__).with_name('web')
STATIC = {'/': ('home.html', 'text/html'), '/farming': ('farming.html', 'text/html'),
          '/helper.css': ('helper.css', 'text/css'), '/farming.js': ('farming.js', 'text/javascript')}


class Handler(cooking.Handler):
    def __init__(self, *args, farming, plans, **kwargs):
        self.farming, self.plans = farming, plans
        super().__init__(*args, **kwargs)

    def do_GET(self, head=False):
        path = urlsplit(self.path).path
        if path in STATIC:
            filename, mime = STATIC[path]
            self.respond(200, (WEB / filename).read_bytes(), mime, head)
        elif path == '/api/farming':
            try:
                self.respond(200, dict(self.farming.overview(), preferences=self.plans.snapshot()), head=head)
            except (ValueError, OSError, sqlite3.Error):
                self.respond(503, {'error': '无法读取种植规划，请检查规划文件。'}, head=head)
        elif path in ('/cooking', '/cooking/'):
            self.respond(200, (cooking.WEB / 'index.html').read_bytes(), 'text/html', head)
        else:
            super().do_GET(head=head)

    def do_POST(self):
        if self.path not in ('/api/farming/analyze', '/api/farming/preferences'):
            return super().do_POST()
        origin = self.headers.get('Origin')
        try:
            allowed = not origin or (urlsplit(origin).scheme in ('http', 'https') and urlsplit(origin).netloc == self.headers.get('Host'))
        except ValueError:
            allowed = False
        if not allowed or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.respond(403, {'error': '请从本机助手页面使用种植规划。'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get_content_type() != 'application/json' or not 0 < length <= 65536 or self.headers.get('Transfer-Encoding'):
                raise ValueError('请发送不超过 64KB 的 JSON 规划。')
            value = json.loads(self.rfile.read(length).decode('utf-8'))
            if self.path.endswith('/analyze'):
                result = self.farming.analyze(value)
            else:
                if type(value) is not dict or set(value) != {'state', 'expected_version'}:
                    raise ValueError('请提供规划和保存版本。')
                result = self.plans.update(**value)
            self.respond(200, result)
        except PlanConflict as error:
            self.respond(409, {'error': str(error)})
        except (ValueError, UnicodeError, RecursionError) as error:
            self.respond(422, {'error': str(error)})
        except (OSError, sqlite3.Error):
            self.respond(500, {'error': '无法保存规划，请检查规划文件是否可写。'})


def create_server(port=8765, database=cooking.DEFAULT_DATABASE, assets_root=cooking.DEFAULT_ASSET_ROOT,
                  host='127.0.0.1', settings_path=cooking.DEFAULT_SETTINGS, exclusions_path=None, farming_settings=None):
    planner = FarmingPlanner()
    plan_path = Path(farming_settings).resolve() if farming_settings else Path(settings_path).resolve().with_name('farming_plans.sqlite')
    protected = [Path(database).resolve(), Path(settings_path).resolve(),
                 Path(exclusions_path).resolve() if exclusions_path else Path(settings_path).resolve().with_name('signature_exclusions.json')]
    protected.extend((ROOT / 'DST_Farming_v0_1').rglob('*.sqlite'))
    protected.append(ROOT / 'DST_Farming_v0_1/data/farming.json')
    if any(plan_path == p or (plan_path.exists() and p.exists() and plan_path.samefile(p)) for p in protected):
        raise ValueError('Farming plans must be separate from cooking settings and curated snapshots.')
    plans = PlanStore(plan_path, planner)
    return cooking.create_server(port, database, assets_root, host, settings_path, exclusions_path,
                                 handler_class=partial(Handler, farming=planner, plans=plans))


def main():
    parser = argparse.ArgumentParser(description='Local DST Helper: Cooking and Farming Planner')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1', help='localhost or a private LAN IPv4 address')
    parser.add_argument('--database', type=Path, default=cooking.DEFAULT_DATABASE)
    parser.add_argument('--assets', type=Path, default=cooking.DEFAULT_ASSET_ROOT)
    parser.add_argument('--settings', type=Path, default=cooking.DEFAULT_SETTINGS)
    parser.add_argument('--farming-settings', type=Path, help='Separate farming plan SQLite file; defaults beside --settings')
    args = parser.parse_args()
    with create_server(args.port, args.database, args.assets, args.host, args.settings,
                       farming_settings=args.farming_settings) as server:
        print(f'DST Helper: http://{args.host}:{server.server_port}', flush=True)
        print('Cooking /cooking | Farming /farming. Preferences shared by server users. Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
