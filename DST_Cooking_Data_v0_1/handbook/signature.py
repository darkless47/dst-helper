"""Complete one-ingredient completion search under the exact-pot model.

All possible remaining triples (with repetition) are considered. States may share a
search representative ONLY if every recipe tag/item-group contribution is identical.
Integer bit masks evaluate the last slot in parallel; priority groups exclude strictly
higher matches while preserving equal-priority ties. No sampling or heuristic cutoff.
Every possible prefix is compared for minimum additional rarity, using the cheapest
state for each mechanical profile. Every witness is replayed through ExactPotPredictor.
"""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from fractions import Fraction
from math import lcm
from threading import Lock

from .prediction import PredictionDataError, PredictionInputError
from .preparation import PREPARED_IDS

# Ordering changes witness choice only, never the allowed ingredient universe.
COMMON_INGREDIENTS = ('berries', 'carrot', 'ice', 'twigs', 'smallmeat', 'meat',
                      'monstermeat', 'honey', 'corn', 'bird_egg', 'potato', 'tomato',
                      'fishmeat_small', 'kelp', 'froglegs', 'onion', 'garlic')


def named_requirement(node, prefab):
    """Explicit positive named requirement, including listed OR alternatives."""
    if node[0] in ('all', 'any'):
        return any(named_requirement(child, prefab) for child in node[1])
    kind, subject, comparison, threshold = node
    return (kind == 'items' and prefab in subject
            and ((comparison == '>' and threshold >= 0)
                 or (comparison in ('>=', '==') and threshold > 0)))


class SignatureRecipes:
    def __init__(self, predictor, dishes, rarities=None, *, merge_profiles=True, prepared_ids=PREPARED_IDS):
        self.predictor = predictor
        self.rarities = dict(rarities or {})
        self.dishes = {row['dish_id']: dict(row) for row in dishes}
        self._subjects = {}
        denominators = []

        def collect(node):
            if node[0] in ('all', 'any'):
                for child in node[1]:
                    collect(child)
            else:
                self._subjects.setdefault((node[0], node[1]), len(self._subjects))
                denominators.append(node[3].denominator)

        for recipe, ast in predictor.recipes:
            collect(ast)
            if recipe['dish_id'] not in self.dishes:
                raise PredictionDataError('优选料理缺少料理资料。')
        for tags in predictor.tags.values():
            denominators.extend(value.denominator for value in tags.values())
        self.scale = lcm(*denominators) if denominators else 1
        self._representatives, self._vectors, self._state_profile = [], [], {}
        profile_by_vector = {}
        preferred = {ingredient_id: index for index, ingredient_id in enumerate(COMMON_INGREDIENTS)}
        ordered_ingredients = sorted(predictor.ingredients.items(), key=lambda item:
                                     (self.rarities.get(item[0], 0), item[0] in prepared_ids,
                                      preferred.get(item[0], len(preferred))))
        for ingredient_id, row in ordered_ingredients:
            vector = tuple(int(self.scale * (predictor.tags[ingredient_id].get(subject, Fraction(0))
                           if kind == 'tag' else int(row['prefab_id'] in subject)))
                           for kind, subject in self._subjects)
            if not merge_profiles or vector not in profile_by_vector:
                profile_by_vector[vector] = len(self._vectors)
                self._vectors.append(vector)
                self._representatives.append(ingredient_id)
            self._state_profile[ingredient_id] = profile_by_vector[vector]
        self.profile_count = len(self._vectors)
        self._costs = [self.rarities.get(item, 0) for item in self._representatives]
        self._all = (1 << self.profile_count) - 1
        self._values, self._equals, self._prefix_masks = [], [], []
        for dimension in range(len(self._subjects)):
            masks = defaultdict(int)
            for index, vector in enumerate(self._vectors):
                masks[vector[dimension]] |= 1 << index
            values = sorted(masks)
            prefix, running = [0], 0
            for value in values:
                running |= masks[value]
                prefix.append(running)
            self._values.append(values)
            self._equals.append(dict(masks))
            self._prefix_masks.append(prefix)

        def compile_mask(node):
            if node[0] in ('all', 'any'):
                return node[0], tuple(compile_mask(child) for child in node[1])
            return 'atom', self._subjects[(node[0], node[1])], node[2], int(node[3] * self.scale)

        self._recipes = [(recipe, ast, compile_mask(ast)) for recipe, ast in predictor.recipes]
        self._atom_masks, self._witness_cache, self._result_cache = {}, {}, {}
        self._lock = Lock()

    def _mask(self, node, totals):
        if node[0] == 'all':
            mask = self._all
            for child in node[1]:
                mask &= self._mask(child, totals)
                if not mask:
                    break
            return mask
        if node[0] == 'any':
            mask = 0
            for child in node[1]:
                mask |= self._mask(child, totals)
                if mask == self._all:
                    break
            return mask
        _, dimension, comparison, threshold = node
        remainder = threshold - totals[dimension]
        key = dimension, comparison, remainder
        mask = self._atom_masks.get(key)
        if mask is None:
            values, prefix = self._values[dimension], self._prefix_masks[dimension]
            if comparison == '==':
                mask = self._equals[dimension].get(remainder, 0)
            elif comparison == '<':
                mask = prefix[bisect_left(values, remainder)]
            elif comparison == '<=':
                mask = prefix[bisect_right(values, remainder)]
            elif comparison == '>':
                mask = self._all ^ prefix[bisect_right(values, remainder)]
            elif comparison == '>=':
                mask = self._all ^ prefix[bisect_left(values, remainder)]
            else:
                raise PredictionDataError('优选料理含不支持的比较。')
            self._atom_masks[key] = mask
        return mask

    def _search(self, profile, cooker):
        key = profile, cooker
        if key in self._witness_cache:
            return self._witness_cache[key]
        groups = defaultdict(list)
        for recipe, ast, mask in self._recipes:
            if self.predictor.available_in(recipe, cooker):
                groups[recipe['priority']].append((recipe, mask))
        ranked = [groups[priority] for priority in sorted(groups, reverse=True)]
        selected = self._vectors[profile]
        witnesses, best = {}, {}
        for first, first_vector in enumerate(self._vectors):
            pair = tuple(a + b for a, b in zip(selected, first_vector))
            for second in range(first, self.profile_count):
                totals = tuple(a + b for a, b in zip(pair, self._vectors[second]))
                candidates = self._all ^ ((1 << second) - 1)
                higher = 0
                for group in ranked:
                    group_matches = 0
                    for recipe, expression in group:
                        matches = self._mask(expression, totals) & candidates
                        group_matches |= matches
                        wins = matches & ~higher
                        if wins:
                            # Profiles are ordered by their cheapest state's rarity. Thus the
                            # first surviving last-slot bit is optimal for this fixed prefix.
                            third = (wins & -wins).bit_length() - 1
                            candidate = (self._costs[first] + self._costs[second] + self._costs[third],
                                         (first, second, third))
                            if recipe['dish_id'] not in best or candidate < best[recipe['dish_id']]:
                                best[recipe['dish_id']] = candidate
                                witnesses[recipe['dish_id']] = (first, second, third)
                    # Equal priorities compete only with earlier, strictly higher groups.
                    higher |= group_matches
                    if higher == candidates:
                        break
        self._witness_cache[key] = witnesses
        return witnesses

    def recommend(self, ingredient_id, cooker):
        self.predictor.validate_cooker(cooker)
        if not isinstance(ingredient_id, str) or ingredient_id not in self.predictor.ingredients:
            raise PredictionInputError('请选择已收录的食材状态。')
        key = ingredient_id, cooker
        # Bound cache to the finite snapshot universe and serialize CPU work across LAN clients.
        with self._lock:
            if key in self._result_cache:
                return self._result_cache[key]
            witnesses = self._search(self._state_profile[ingredient_id], cooker)
            selected = self.predictor.ingredients[ingredient_id]
            special, other = [], []
            for recipe, ast, _ in self._recipes:
                if recipe['dish_id'] not in witnesses:
                    continue
                pot = [ingredient_id, *(self._representatives[i] for i in witnesses[recipe['dish_id']])]
                checked = self.predictor.predict(pot, cooker)
                outcome = next((row for row in checked['outcomes'] if row['dish_id'] == recipe['dish_id']), None)
                if outcome is None:
                    raise PredictionDataError('优选配方未通过四格预测复核。')
                is_special = named_requirement(ast, selected['prefab_id'])
                additional = sum(self.rarities.get(item, 0) for item in pot[1:])
                row = dict(self.dishes[recipe['dish_id']], special=is_special, additional_rarity=additional,
                           example=dict(ingredients=pot, probability=outcome['probability'],
                                        total_rarity=additional + self.rarities.get(ingredient_id, 0)))
                (special if is_special else other).append(row)
            result = dict(ingredient_id=ingredient_id, cooker=cooker, special=special, other=other,
                          complete=True, mode=self.predictor.policy['mode'],
                          source_revision=self.predictor.metadata['source_revision'],
                          eligibility_verified=self.predictor.policy['eligibility_verified'])
            self._result_cache[key] = result
            return result
