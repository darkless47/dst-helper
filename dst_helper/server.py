"""Home and stateless Farming routes, delegating Cooking to its read-only app."""
import argparse
from functools import partial
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'DST_Cooking_Data_v0_1'))
from handbook import server as cooking
from .farming import FarmingPlanner

WEB = Path(__file__).with_name('web')
STATIC = {'/': ('home.html', 'text/html'), '/farming': ('farming.html', 'text/html'),
          '/helper.css': ('helper.css', 'text/css'), '/farming.js': ('farming.js', 'text/javascript')}


class Handler(cooking.Handler):
    def __init__(self, *args, farming, **kwargs):
        self.farming = farming
        super().__init__(*args, **kwargs)

    def do_GET(self, head=False):
        path = urlsplit(self.path).path
        if path in STATIC:
            filename, mime = STATIC[path]
            self.respond(200, (WEB / filename).read_bytes(), mime, head)
        elif path == '/api/farming':
            try:
                self.respond(200, self.farming.overview(), head=head)
            except (ValueError, OSError, sqlite3.Error):
                self.respond(503, {'error': '无法读取种植规划，请检查规划文件。'}, head=head)
        elif path in ('/cooking', '/cooking/'):
            self.respond(200, (cooking.WEB / 'index.html').read_bytes(), 'text/html', head)
        else:
            super().do_GET(head=head)

    def do_POST(self):
        if self.path != '/api/farming/analyze':
            return super().do_POST()
        try:
            value = self.read_json(max_size=65536)
            if value is None:
                return
            self.respond(200, self.farming.analyze(value))
        except (ValueError, UnicodeError, RecursionError) as error:
            self.respond(422, {'error': str(error)})
        except (OSError, sqlite3.Error):
            self.respond(500, {'error': '无法计算规划，请检查数据快照。'})


def create_server(port=8765, database=cooking.DEFAULT_DATABASE, assets_root=cooking.DEFAULT_ASSET_ROOT,
                  host='127.0.0.1', settings_path=cooking.DEFAULT_SETTINGS, exclusions_path=None):
    planner = FarmingPlanner()
    return cooking.create_server(port, database, assets_root, host, settings_path, exclusions_path,
                                 handler_class=partial(Handler, farming=planner))


def main():
    parser = argparse.ArgumentParser(description='Local DST Helper: Cooking and Farming Planner')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1', help='localhost or a private LAN IPv4 address')
    parser.add_argument('--database', type=Path, default=cooking.DEFAULT_DATABASE)
    parser.add_argument('--assets', type=Path, default=cooking.DEFAULT_ASSET_ROOT)
    parser.add_argument('--settings', type=Path, default=cooking.DEFAULT_SETTINGS, help='Read-only ingredient rarity defaults JSON')
    parser.add_argument('--exclusions', type=Path, default=cooking.DEFAULT_EXCLUSIONS, help='Read-only excluded-dish defaults JSON')
    args = parser.parse_args()
    with create_server(args.port, args.database, args.assets, args.host, args.settings,
                       exclusions_path=args.exclusions) as server:
        print(f'DST Helper: http://{args.host}:{server.server_port}', flush=True)
        print('Cooking /cooking | Farming /farming. Preferences stored in each browser. Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
