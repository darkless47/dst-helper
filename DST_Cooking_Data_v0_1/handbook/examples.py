"""Exact cheapest distinct four-state multisets and rarity-aware discovery.

The last slot is evaluated with the shared rule bit-mask index. Three prefix
slots enumerate actual states (not mechanical representatives), so substitutable
ingredients still produce distinct examples. Cost bounds remain valid for signed
rarities because states are ordered by cost and each pot has exactly four slots.
"""
from collections import OrderedDict
from threading import RLock

from .prediction import PredictionDataError
from .preparation import PREPARED_IDS, required_prepared_prefabs
from .signature import SignatureRecipes


class DishExamples(SignatureRecipes):
    def __init__(self, predictor, dishes, rarities=None, *, prepared_ids=PREPARED_IDS):
        super().__init__(predictor, dishes, rarities, merge_profiles=False, prepared_ids=prepared_ids)
        self.prepared_ids = frozenset(prepared_ids)
        self._examples_cache = {}

    def examples(self, dish_id, cooker):
        self.predictor.validate_cooker(cooker)
        if dish_id not in self.dishes:
            raise KeyError(dish_id)
        key = dish_id, cooker
        with self._lock:
            if key in self._examples_cache:
                return self._examples_cache[key]
            recipe, ast, expression = next(row for row in self._recipes if row[0]['dish_id'] == dish_id)
            available = self.predictor.available_in(recipe, cooker)
            best = []
            if available:
                prepared_prefabs = {self.predictor.ingredients[item]['prefab_id']
                                    for item in self.prepared_ids if item in self.predictor.ingredients}
                required = required_prepared_prefabs(ast, prepared_prefabs)
                allowed = [i for i, item in enumerate(self._representatives)
                           if item not in self.prepared_ids or self.predictor.ingredients[item]['prefab_id'] in required]
                allowed_mask = sum(1 << i for i in allowed)
                higher = [node for other, _, node in self._recipes if other['priority'] > recipe['priority']
                          and self.predictor.available_in(other, cooker)]
                costs, vectors = self._costs, self._vectors
                for position, first in enumerate(allowed):
                    if len(best) == 3 and (4 * costs[first], (first,) * 4) >= best[-1]:
                        break
                    for second_position in range(position, len(allowed)):
                        second = allowed[second_position]
                        if len(best) == 3 and (costs[first] + 3 * costs[second], (first, second, second, second)) >= best[-1]:
                            break
                        pair = tuple(a + b for a, b in zip(vectors[first], vectors[second]))
                        for third in allowed[second_position:]:
                            prefix_cost = costs[first] + costs[second] + costs[third]
                            if len(best) == 3 and (prefix_cost + costs[third], (first, second, third, third)) >= best[-1]:
                                break
                            totals = tuple(a + b for a, b in zip(pair, vectors[third]))
                            wins = self._mask(expression, totals) & allowed_mask & (self._all ^ ((1 << third) - 1))
                            if not wins:
                                continue
                            for node in higher:
                                wins &= ~self._mask(node, totals)
                                if not wins:
                                    break
                            # At most the three cheapest final states for this prefix can
                            # enter a global top three. Equality ties follow stable state order.
                            for _ in range(3):
                                if not wins:
                                    break
                                bit = wins & -wins
                                fourth = bit.bit_length() - 1
                                candidate = prefix_cost + costs[fourth], (first, second, third, fourth)
                                if len(best) == 3 and candidate >= best[-1]:
                                    break
                                best.append(candidate)
                                best.sort()
                                del best[3:]
                                wins ^= bit
            examples = []
            for cost, indices in best:
                pot = [self._representatives[i] for i in indices]
                checked = self.predictor.predict(pot, cooker)
                outcome = next((row for row in checked['outcomes'] if row['dish_id'] == dish_id), None)
                if outcome is None:
                    raise PredictionDataError('料理示例未通过四格预测复核。')
                examples.append(dict(ingredients=pot, total_rarity=cost, probability=outcome['probability']))
            result = dict(dish_id=dish_id, cooker=cooker, examples=examples, complete=True,
                          available=available, requested_count=3, fewer_than_requested=len(examples) < 3,
                          mode=self.predictor.policy['mode'], source_revision=self.predictor.metadata['source_revision'],
                          eligibility_verified=self.predictor.policy['eligibility_verified'])
            self._examples_cache[key] = result
            return result


class RecipePlanner:
    """Bounded cache keyed by actual request preferences, never a user revision."""
    def __init__(self, predictor, dishes, settings, cache_limit=8):
        self.predictor, self.dishes, self.settings = predictor, dishes, settings
        self.cache_limit = cache_limit
        self._cache = OrderedDict()
        self._lock = RLock()

    def _planners(self, rarities):
        values = self.settings.snapshot()['rarities'] if rarities is None else rarities
        key = tuple(sorted((k, v) for k, v in values.items() if v != 0))
        with self._lock:
            if key not in self._cache:
                self._cache[key] = (SignatureRecipes(self.predictor, self.dishes, values),
                                    DishExamples(self.predictor, self.dishes, values))
                if len(self._cache) > self.cache_limit:
                    self._cache.popitem(last=False)
            self._cache.move_to_end(key)
            return self._cache[key]

    def recommend(self, ingredient_id, cooker, rarities=None, rarity_version=0):
        signature, _ = self._planners(rarities)
        return dict(signature.recommend(ingredient_id, cooker), rarity_version=rarity_version)

    def examples(self, dish_id, cooker, rarities=None, rarity_version=0):
        _, examples = self._planners(rarities)
        return dict(examples.examples(dish_id, cooker), rarity_version=rarity_version)
