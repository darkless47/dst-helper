"""Validate and describe draft predicate ASTs. This module is NOT a solver.

No code execution, pot evaluation, priority selection, or readiness promotion occurs.
Only the 15 columns captured by this snapshot belong to the known vocabulary.
"""
import math

TAG_LABELS = dict(zip(
    ('meat', 'monster', 'fish', 'fruit', 'veggie', 'egg', 'sweetener',
     'dairy', 'frozen', 'inedible', 'magic', 'fat', 'seed', 'decoration', 'dried'),
    ('肉度', '怪物度', '鱼度', '水果度', '蔬菜度', '蛋度', '甜味剂度',
     '乳制品度', '冰度', '不可食用度', '魔法度', '油脂度', '种子度', '装饰度', '干货度'),
))
OPERATORS = {'==': '=', '>': '>', '<': '<', '>=': '≥', '<=': '≤'}


def validate_ast(node, *, known_prefabs=None, _depth=0):
    """Reject ambiguous, malformed, or unsupported grammar; never default new tags to 0."""
    if _depth > 32 or not isinstance(node, dict):
        raise ValueError('Invalid AST structure or excessive nesting')
    if set(node) in ({'all'}, {'any'}):
        children = next(iter(node.values()))
        if not isinstance(children, list) or len(children) > 1000:
            raise ValueError('AST branches must be bounded lists')
        for child in children:
            validate_ast(child, known_prefabs=known_prefabs, _depth=_depth + 1)
        return
    if set(node) not in ({'tag', 'op', 'value'}, {'item_sum', 'op', 'value'}):
        raise ValueError('Unknown or ambiguous AST node')
    if not isinstance(node['op'], str) or node['op'] not in OPERATORS:
        raise ValueError('Unsupported comparison')
    value = node['value']
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Comparison value must be a finite number')
    if 'tag' in node:
        if not isinstance(node['tag'], str) or node['tag'] not in TAG_LABELS:
            raise ValueError('Tag outside captured vocabulary')
    else:
        prefabs = node['item_sum']
        if (not isinstance(prefabs, list) or not prefabs
                or not all(isinstance(p, str) and p for p in prefabs)
                or len(set(prefabs)) != len(prefabs)):
            raise ValueError('item_sum requires distinct prefab IDs')
        if known_prefabs is not None and not set(prefabs) <= set(known_prefabs):
            raise ValueError('Unknown prefab reference')


def describe_ast(node, names=None):
    """Render reviewed grammar as text, without asserting the rule is correct."""
    validate_ast(node)
    names = names or {}

    def render(part):
        if 'all' in part:
            return ('（' + ' 且 '.join(render(c) for c in part['all']) + '）'
                    if part['all'] else '无额外条件（仍需考虑优先级及锅具）')
        if 'any' in part:
            return ('（' + ' 或 '.join(render(c) for c in part['any']) + '）'
                    if part['any'] else '无可满足的分支')
        subject = TAG_LABELS[part['tag']] if 'tag' in part else (
            ' + '.join(names.get(p, p) for p in part['item_sum']) + ' 的合计数量')
        return f"{subject} {OPERATORS[part['op']]} {part['value']:g}"

    return render(node)
