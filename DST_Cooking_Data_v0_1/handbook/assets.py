"""Serve only hash-matched PNGs from packaged images or a saved-page archive.

No images are downloaded or marked redistributable by this loader.
Verified bytes are held in memory until restart so the served file cannot drift
from its provenance record while the server is running.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import unquote

DEFAULT_ASSET_ROOT = Path(__file__).resolve().parents[2] / 'assets/images'
STAT_MANIFEST = Path(__file__).resolve().parents[1] / 'data/stat_icons.json'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class LocalAssets:
    def __init__(self, records, root=DEFAULT_ASSET_ROOT, stat_manifest=STAT_MANIFEST):
        self.root = Path(root).resolve()
        self._routes = {}
        self._catalog = {}
        self._stats = {}
        self._unavailable = {}
        self._records = {}
        self._catalog_count = len(records)
        for record in records:
            self._load(dict(record), self._catalog)
        manifest = json.loads(Path(stat_manifest).read_text(encoding='utf-8'))
        self._stat_source = manifest['source_html_sha256']
        for stat, record in manifest['icons'].items():
            image = self._load(record, self._stats)
            if image:
                self._stats[stat] = self._stats.pop(record['asset_id'])

    def _load(self, record, destination):
        asset_id = record['asset_id']
        if not re.fullmatch(r'(?:asset:[0-9a-f]{20}|stat:(?:health|hunger|sanity))', asset_id):
            raise ValueError('Unsupported asset ID')
        self._records[asset_id] = record
        source_path = (self.root / unquote(record['source_local_reference'])).resolve()
        packaged_path = (self.root / (asset_id.replace(':', '-') + '.png')).resolve()
        # Packaged names are independent of the saved webpage's directory layout.
        # Preserve support for --assets pointing at an original archive.
        path = packaged_path if packaged_path.is_file() else source_path
        reason = None
        if not source_path.is_relative_to(self.root) or not path.is_relative_to(self.root):
            reason = 'outside_archive'
        elif not record.get('sha256'):
            reason = 'missing_hash'
        else:
            try:
                if path.stat().st_size > 2_000_000:
                    reason = 'oversized_file'
                else:
                    data = path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != record['sha256']:
                        reason = 'hash_mismatch'
                    elif (len(data) < 24 or not data.startswith(PNG_SIGNATURE)
                          or data[12:16] != b'IHDR'):
                        reason = 'unsupported_image'
                    else:
                        width, height = struct.unpack('!II', data[16:24])
                        if not (0 < width <= 1024 and 0 < height <= 1024):
                            reason = 'unsupported_dimensions'
            except OSError:
                reason = 'missing_or_unreadable'
        if reason:
            self._unavailable[asset_id] = reason
            return None
        url = '/assets/' + asset_id.replace(':', '-') + '.png'
        self._routes[url] = data
        image = dict(url=url, width=width, height=height)
        destination[asset_id] = image
        return image

    def get(self, route):
        """Exact allowlist lookup; never interpret a request URL as a file path."""
        return self._routes[route]

    def overview(self):
        return dict(catalog_images=self._catalog, stat_icons=self._stats,
                    indexed_catalog_count=self._catalog_count,
                    available_catalog_count=len(self._catalog),
                    unavailable_count=len(self._unavailable),
                    stat_source_html_sha256=self._stat_source)

    def provenance(self, asset_id):
        record = self._records.get(asset_id)
        if record is None:
            return None
        return dict(record, available=asset_id not in self._unavailable,
                    unavailable_reason=self._unavailable.get(asset_id))

    def stat_provenance(self):
        return {stat: self.provenance('stat:' + stat) for stat in ('health', 'hunger', 'sanity')}
