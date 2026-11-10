"""Exact four-item wiki prediction, independent of HTTP/UI and ingestion helpers.

Tags use state IDs; named counts use prefab IDs. Arithmetic and probabilities use
fractions, preserving strict boundaries. Recipe readiness is never promoted here.
"""
from collections import Counter
from fractions import Fraction
import json
import operator
from pathlib import Path

from .rules import TAG_LABELS, validate_ast

POLICY = Path(__file__).resolve().parents[1] / 'data/prediction_policy.json'
COMPARE = {'==': operator.eq, '>': operator.gt, '<': operator.lt,
           '>=': operator.ge, '<=': operator.le}
ORDINARY = 'ordinary_recipe_cooker_matrix_unconfirmed'
PORTABLE = 'portable_only_wiki_claim'


class PredictionInputError(ValueError):
    pass


class PredictionDataError(ValueError):
    pass


def numeric(value):
    if type(value) not in (int, float):
        raise PredictionDataError('配方数据含不支持的数值。')
    try:
        return Fraction(str(value))
    except (ValueError, OverflowError) as error:
        raise PredictionDataError('配方数据含非有限数值。') from error


def compile_rule(node):
    for group in ('all', 'any'):
        if group in node:
            return group, tuple(compile_rule(child) for child in node[group])
    subject = node['tag'] if 'tag' in node else tuple(node['item_sum'])
    return ('tag' if 'tag' in node else 'items'), subject, node['op'], numeric(node['value'])


def rule_matches(node, tags, counts):
    if node[0] == 'all':
        return all(rule_matches(child, tags, counts) for child in node[1])
    if node[0] == 'any':
        return any(rule_matches(child, tags, counts) for child in node[1])
    kind, subject, comparison, threshold = node
    # Direct lookup for known tags: unknown vocabulary is rejected at load time.
    value = tags[subject] if kind == 'tag' else sum(counts.get(prefab, 0) for prefab in subject)
    return COMPARE[comparison](value, threshold)


class ExactPotPredictor:
    def __init__(self, snapshot, policy=None):
        self.policy = policy if policy is not None else json.loads(POLICY.read_text(encoding='utf-8'))
        self.metadata = snapshot['metadata']
        if (self.policy['selection'] != 'maximum_priority' or self.policy['ties'] != 'uniform'
                or self.policy['named_groups'] != 'sum_explicitly_listed_prefabs'
                or self.policy['ingredient_universe'] != 'all_snapshot_ingredient_states'):
            raise PredictionDataError('当前预测器不支持此选择策略。')
        if self.metadata.get('source_sha256') != self.policy['source_html_sha256']:
            raise PredictionDataError('内容快照与已审阅的预测策略不一致。')
        self.ingredients = {row['ingredient_id']: row for row in snapshot['ingredients']}
        if len(self.ingredients) != len(snapshot['ingredients']):
            raise PredictionDataError('食材状态 ID 重复。')
        self.tags = {}
        for ingredient_id, row in self.ingredients.items():
            if set(row['tags']) - TAG_LABELS.keys():
                raise PredictionDataError('食材含未建模的标签。')
            self.tags[ingredient_id] = {tag: numeric(value) for tag, value in row['tags'].items()}
        prefabs = {row['prefab_id'] for row in self.ingredients.values()}
        self.recipes = []
        for row in snapshot['recipes']:
            if row['cooker_scope_hint'] not in (ORDINARY, PORTABLE):
                raise PredictionDataError('配方锅具范围不支持。')
            if type(row['priority']) is not int:
                raise PredictionDataError('配方优先级必须为整数。')
            if row['weight'] is not None:
                raise PredictionDataError('内容含额外概率权重，需要先复核选择策略。')
            try:
                validate_ast(row['conditions'], known_prefabs=prefabs)
            except ValueError as error:
                raise PredictionDataError('配方含缺失或不支持的条件。') from error
            self.recipes.append((dict(row), compile_rule(row['conditions'])))
        if not self.recipes:
            raise PredictionDataError('没有可用配方。')

    def capabilities(self):
        return dict(enabled=True, mode=self.policy['mode'],
                    cookers=self.policy['cookers'], assumptions_zh=self.policy['assumptions_zh'],
                    source_revision=self.metadata['source_revision'],
                    eligibility_verified=self.policy['eligibility_verified'],
                    confirmations=self.policy['user_confirmation'])

    def validate_cooker(self, cooker):
        if not isinstance(cooker, str) or cooker not in self.policy['cookers']:
            raise PredictionInputError('请选择支持的锅具。')

    def available_in(self, recipe, cooker):
        return recipe['cooker_scope_hint'] == ORDINARY or self.policy['cookers'][cooker]['include_portable_only']

    def predict(self, ingredient_ids, cooker):
        self.validate_cooker(cooker)
        if not isinstance(ingredient_ids, list) or len(ingredient_ids) != 4:
            raise PredictionInputError('需要恰好四件食材；重复食材也分别占一格。')
        if any(not isinstance(item, str) or item not in self.ingredients for item in ingredient_ids):
            raise PredictionInputError('存在未收录的食材状态，请从食材列表选择。')
        counts = Counter(self.ingredients[item]['prefab_id'] for item in ingredient_ids)
        tags = dict.fromkeys(TAG_LABELS, Fraction(0))
        for item in ingredient_ids:
            for tag, value in self.tags[item].items():
                tags[tag] += value
        matches, unavailable = [], []
        for recipe, ast in self.recipes:
            if not rule_matches(ast, tags, counts):
                continue
            allowed = self.available_in(recipe, cooker)
            (matches if allowed else unavailable).append(recipe)
        if not matches:
            raise PredictionDataError('没有可用匹配；内容快照可能缺少兜底配方。')
        best = max(recipe['priority'] for recipe in matches)
        winners = [recipe for recipe in matches if recipe['priority'] == best]
        chance = Fraction(1, len(winners))

        def summary(recipe):
            return {key: recipe[key] for key in ('dish_id', 'name_zh', 'icon_asset_id', 'priority', 'cook_seconds')}

        outcomes = [dict(summary(recipe), probability=dict(numerator=chance.numerator,
                    denominator=chance.denominator, value=float(chance))) for recipe in winners]
        return dict(mode=self.policy['mode'], cooker=cooker, ingredients=ingredient_ids,
                    tag_totals={tag: float(value) for tag, value in tags.items()},
                    prefab_counts=dict(counts), highest_priority=best, outcomes=outcomes,
                    suppressed_matches=[summary(recipe) for recipe in matches if recipe['priority'] < best],
                    unavailable_matches=[summary(recipe) for recipe in unavailable],
                    source_revision=self.metadata['source_revision'],
                    target_build=self.metadata['target_build'],
                    eligibility_verified=self.policy['eligibility_verified'])
