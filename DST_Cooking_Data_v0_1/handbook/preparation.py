"""Explicit prepared-state list for example selection, not cooker eligibility."""
import json
from pathlib import Path

PREPARATION_POLICY = json.loads((Path(__file__).resolve().parents[1] / 'data/prepared_ingredients.json').read_text(encoding='utf-8'))
PREPARED_IDS = frozenset(row['ingredient_id'] for row in PREPARATION_POLICY['states'])


def required_prepared_prefabs(node, prepared_prefabs):
    """Permit prepared forms only for positive named groups with no raw alternative."""
    if node[0] in ('all', 'any'):
        return set().union(*(required_prepared_prefabs(child, prepared_prefabs) for child in node[1]))
    kind, group, comparison, threshold = node
    positive = comparison == '>' and threshold >= 0 or comparison in ('>=', '==') and threshold > 0
    if kind == 'items' and positive and set(group) <= prepared_prefabs:
        return set(group)
    return set()
