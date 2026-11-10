"""Read-only, source-controlled default exclusions; browsers own custom lists."""
import json
from pathlib import Path

DEFAULTS = Path(__file__).resolve().parents[1] / 'data/signature_exclusions.default.json'


class DefaultExclusions:
    def __init__(self, path, dish_ids):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if (type(data) is not dict or set(data) != {'schema_version', 'dish_ids'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1
                or type(data['dish_ids']) is not list
                or any(type(item) is not str or item not in dish_ids for item in data['dish_ids'])
                or len(data['dish_ids']) != len(set(data['dish_ids']))):
            raise ValueError('Invalid signature exclusion defaults.')
        self.dish_ids = list(data['dish_ids'])

    def snapshot(self):
        return dict(version=0, dish_ids=list(self.dish_ids))
