"""Copy only verified runtime PNGs from a saved archive into assets/images."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handbook.assets import DEFAULT_ASSET_ROOT, LocalAssets
from handbook.catalog import Catalog


def package(source, output=DEFAULT_ASSET_ROOT):
    media = LocalAssets(Catalog().asset_records(), source)
    overview = media.overview()
    if overview['unavailable_count']:
        raise ValueError('Source has missing or invalid images; no files were copied')
    images = [*overview['catalog_images'].values(), *overview['stat_icons'].values()]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for image in images:
        (output / image['url'].rsplit('/', 1)[-1]).write_bytes(media.get(image['url']))
    return len(images)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=DEFAULT_ASSET_ROOT)
    args = parser.parse_args()
    print(f'Packaged {package(args.archive, args.output)} verified images into {args.output}')
