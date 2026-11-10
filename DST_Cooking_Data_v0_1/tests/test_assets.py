"""Independent local-media checks, including archive containment and missing assets."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from handbook.assets import DEFAULT_ASSET_ROOT, LocalAssets, STAT_MANIFEST
from handbook.catalog import Catalog
from scripts.index_stat_icons import index

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYioAAAAASUVORK5CYII=')
ASSET_ID = 'asset:' + 'a' * 20
SOURCE_ARCHIVE = Path(__file__).resolve().parents[2] / 'wiki-webpage-save'


class LocalAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.manifest = self.root / 'stat_icons.json'
        self.manifest.write_text(json.dumps({'source_html_sha256': 'fixture', 'icons': {}}), encoding='utf-8')

    def record(self, reference='food.png', data=PNG):
        return dict(asset_id=ASSET_ID, source_local_reference=reference,
                    sha256=hashlib.sha256(data).hexdigest(), redistributable=False)

    def test_serves_only_original_verified_bytes(self):
        path = self.archive / 'food.png'
        path.write_bytes(PNG)
        assets = LocalAssets([self.record()], self.archive, self.manifest)
        image = assets.overview()['catalog_images'][ASSET_ID]
        self.assertEqual((image['width'], image['height']), (1, 1))
        self.assertEqual(assets.get(image['url']), PNG)
        path.write_bytes(b'replaced after startup')
        self.assertEqual(assets.get(image['url']), PNG)
        self.assertFalse(assets.provenance(ASSET_ID)['redistributable'])
        for route in ['/assets/food.png', '/assets/../food.png', '/assets/asset-unknown.png']:
            with self.assertRaises(KeyError):
                assets.get(route)

    def test_missing_or_modified_files_are_unavailable(self):
        for contents, reason in [(None, 'missing_or_unreadable'), (b'modified', 'hash_mismatch')]:
            with self.subTest(reason=reason):
                if contents is not None:
                    (self.archive / 'food.png').write_bytes(contents)
                assets = LocalAssets([self.record()], self.archive, self.manifest)
                self.assertEqual(assets.overview()['catalog_images'], {})
                self.assertEqual(assets.provenance(ASSET_ID)['unavailable_reason'], reason)

    def test_packaged_filename_works_without_original_archive_layout(self):
        packaged = self.archive / (ASSET_ID.replace(':', '-') + '.png')
        packaged.write_bytes(PNG)
        assets = LocalAssets([self.record('missing_saved_page_files/food.png')], self.archive, self.manifest)
        self.assertEqual(assets.get('/assets/' + packaged.name), PNG)
        self.assertEqual(assets.overview()['unavailable_count'], 0)
        # A modified packaged file must not be hidden by a valid archive copy.
        packaged.write_bytes(b'corrupted')
        (self.archive / 'food.png').write_bytes(PNG)
        assets = LocalAssets([self.record()], self.archive, self.manifest)
        self.assertEqual(assets.provenance(ASSET_ID)['unavailable_reason'], 'hash_mismatch')

    def test_rejects_outside_paths_missing_hashes_and_non_pngs(self):
        (self.root / 'outside.png').write_bytes(PNG)
        (self.archive / 'not-an-image.png').write_bytes(b'not an image')
        for record, reason in [
            (self.record('../outside.png'), 'outside_archive'),
            (dict(self.record(), sha256=None), 'missing_hash'),
            (self.record('not-an-image.png', b'not an image'), 'unsupported_image'),
        ]:
            with self.subTest(reason=reason):
                assets = LocalAssets([record], self.archive, self.manifest)
                self.assertEqual(assets.provenance(ASSET_ID)['unavailable_reason'], reason)


class PackagedAssetsTests(unittest.TestCase):
    def test_all_indexed_images_match_and_brick_states_have_distinct_art(self):
        catalog = Catalog()
        assets = LocalAssets(catalog.asset_records())
        self.assertEqual(DEFAULT_ASSET_ROOT.name, 'images')
        overview = assets.overview()
        self.assertEqual(overview['available_catalog_count'], 226)
        self.assertEqual(overview['unavailable_count'], 0)
        self.assertEqual(set(overview['stat_icons']), {'health', 'hunger', 'sanity'})
        expected = {image['url'].rsplit('/', 1)[-1] for image in
                    [*overview['catalog_images'].values(), *overview['stat_icons'].values()]}
        self.assertEqual({path.name for path in DEFAULT_ASSET_ROOT.glob('*.png')}, expected)
        self.assertEqual(len(expected), 229)
        for image in [*overview['catalog_images'].values(), *overview['stat_icons'].values()]:
            self.assertTrue(assets.get(image['url']).startswith(b'\x89PNG\r\n\x1a\n'))
        bricks = [i for i in catalog.overview()['ingredients'] if i['prefab_id'] == 'wx78_foodbrick']
        self.assertNotEqual(bricks[0]['icon_asset_id'], bricks[1]['icon_asset_id'])
        images = [overview['catalog_images'][i['icon_asset_id']] for i in bricks]
        self.assertNotEqual(assets.get(images[0]['url']), assets.get(images[1]['url']))


@unittest.skipUnless(SOURCE_ARCHIVE.is_dir(), 'Optional source archive is not present')
class ArchiveTests(unittest.TestCase):
    def test_legacy_archive_images_are_still_supported(self):
        overview = LocalAssets(Catalog().asset_records(), SOURCE_ARCHIVE).overview()
        self.assertEqual(overview['available_catalog_count'], 226)
        self.assertEqual(overview['unavailable_count'], 0)
        self.assertEqual(len(overview['stat_icons']), 3)

    def test_stat_icon_manifest_is_reproducible_from_original_html(self):
        actual = index(next(SOURCE_ARCHIVE.glob('*.html')))
        self.assertEqual(actual, json.loads(STAT_MANIFEST.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
