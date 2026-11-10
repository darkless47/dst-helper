"""Index three meter icons from the matching saved HTML; never run page scripts."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handbook.catalog import Catalog

FILENAMES = {f'28px-{name}_Meter.png': key for key, name in
             [('health', 'Health'), ('hunger', 'Hunger'), ('sanity', 'Sanity')]}


def index(source):
    raw = source.read_bytes()
    metadata = Catalog().overview()['metadata']
    digest = hashlib.sha256(raw).hexdigest()
    if digest != metadata['source_sha256']:
        raise ValueError('Saved HTML does not match the content snapshot')
    icons = {}

    class Images(HTMLParser):
        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            filename = unquote(attrs.get('src', '')).rsplit('/', 1)[-1]
            if tag != 'img' or filename not in FILENAMES:
                return
            stat = FILENAMES[filename]
            path = (source.parent / unquote(attrs['src'])).resolve()
            if not path.is_relative_to(source.parent.resolve()):
                raise ValueError('Image reference leaves source archive')
            data = path.read_bytes()
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Expected a PNG meter icon')
            icons[stat] = dict(asset_id='stat:' + stat, source_local_reference=attrs['src'],
                               source_alt=attrs.get('alt'),
                               original_candidates=attrs.get('srcset', '').split(', '),
                               sha256=hashlib.sha256(data).hexdigest(),
                               rights_status='unconfirmed', redistributable=False)

    Images().feed(raw.decode('utf-8'))
    if set(icons) != {'health', 'hunger', 'sanity'}:
        raise ValueError('Expected all three meter icons')
    return dict(source_html_sha256=digest, source_url=metadata['source_url'],
                source_revision=metadata['source_revision'], icons=icons)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/stat_icons.json')
    args = parser.parse_args()
    args.output.write_text(json.dumps(index(args.html), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(args.output)
