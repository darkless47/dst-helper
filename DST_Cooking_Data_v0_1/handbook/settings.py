"""Read-only, source-controlled Cooking defaults and request validation."""
import json
from pathlib import Path

from .prediction import PredictionInputError

DEFAULT_SETTINGS = Path(__file__).resolve().parents[1] / 'data/ingredient_rarities.default.json'
MIN_RARITY, MAX_RARITY = -2147483648, 2147483647


def validate_rarities(value, ingredient_ids):
    if (type(value) is not dict or len(value) > len(ingredient_ids)
            or any(key not in ingredient_ids or type(n) is not int
                   or not MIN_RARITY <= n <= MAX_RARITY for key, n in value.items())):
        raise PredictionInputError('稀有度须使用已收录食材及 -2147483648 到 2147483647 的整数。')
    return dict(value)


class CookingDefaults:
    def __init__(self, path, ingredient_ids):
        self.ingredient_ids = frozenset(ingredient_ids)
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if (type(data) is not dict or set(data) != {'schema_version', 'rarities'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1):
            raise ValueError('Invalid ingredient rarity defaults.')
        self.rarities = validate_rarities(data['rarities'], self.ingredient_ids)

    def snapshot(self):
        return dict(version=0, rarities=dict(self.rarities))
