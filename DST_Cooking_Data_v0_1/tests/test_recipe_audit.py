"""Independent source-parser and stored-predicate boundary fixtures, not pot outcomes."""
import json
import operator
from pathlib import Path
import unittest

from handbook.catalog import Catalog
from scripts.audit_recipe_capture import Expression, audit, canonical

SOURCE_ARCHIVE = Path(__file__).resolve().parents[2] / 'wiki-webpage-save'
COMPARE = {'==': operator.eq, '>': operator.gt, '<': operator.lt,
           '>=': operator.ge, '<=': operator.le}


def predicate_only(node, tags, counts=None):
    """Fixture helper. Deliberately does not choose outcomes or check pot legality."""
    counts = counts or {}
    if 'all' in node:
        return all(predicate_only(child, tags, counts) for child in node['all'])
    if 'any' in node:
        return any(predicate_only(child, tags, counts) for child in node['any'])
    value = (tags.get(node['tag'], 0) if 'tag' in node
             else sum(counts.get(prefab, 0) for prefab in node['item_sum']))
    return COMPARE[node['op']](value, node['value'])


class SourceGrammarTests(unittest.TestCase):
    def test_chained_bounds_and_or_precedence(self):
        parsed = Expression('0 < 肉度 ≤ 1.5，水果度 > 0 / 蔬菜度 ≥ 0.5').parse()
        expected = {'all': [
            {'tag': 'meat', 'op': '>', 'value': 0},
            {'tag': 'meat', 'op': '<=', 'value': 1.5},
            {'any': [{'tag': 'fruit', 'op': '>', 'value': 0},
                     {'tag': 'veggie', 'op': '>=', 'value': 0.5}]}]}
        self.assertEqual(canonical(parsed), canonical(expected))
        self.assertFalse(predicate_only(parsed, {'meat': 0, 'veggie': 1}))
        self.assertTrue(predicate_only(parsed, {'meat': 0.25, 'veggie': 0.5}))

    def test_icon_groups_and_separate_or_branches(self):
        ast = Expression('[A.png]/[B.png] ≥ 2 / [C.png] ≥ 1',
                         {'A.png': 'a', 'B.png': 'b', 'C.png': 'c'}).parse()
        self.assertEqual(canonical(ast), canonical({'any': [
            {'item_sum': ['a', 'b'], 'op': '>=', 'value': 2},
            {'item_sum': ['c'], 'op': '>=', 'value': 1}]}))

    def test_unsupported_source_is_not_ignored(self):
        for source in ['肉度 != 1', '肉度 > 0 或 蔬菜度 > 0', '未知度 > 0', '肉度 > 0 /']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                Expression(source).parse()


class StoredPredicateBoundaryTests(unittest.TestCase):
    def rule(self, dish):
        return Catalog().detail('dish', 'huiji:' + dish)['rule']['conditions']

    def test_fractional_meat_is_not_an_integer_item_count(self):
        ast = self.rule('肉丸')
        for meat, expected in [(0, False), (0.25, True), (0.5, True), (1, True)]:
            with self.subTest(meat=meat):
                self.assertEqual(predicate_only(ast, {'meat': meat}), expected)
        for meat in (0.25, 0.5):
            self.assertTrue(meat > 0)
            self.assertFalse(meat >= 1)

    def test_strict_and_inclusive_thresholds(self):
        for meat in (0, 0.25, 1, 1.5, 1.75, 2):
            with self.subTest(meat=meat):
                self.assertEqual(predicate_only(self.rule('蜜汁火腿'), {'meat': meat}, {'honey': 1}), meat > 1.5)
                self.assertEqual(predicate_only(self.rule('蜜汁卤肉'), {'meat': meat}, {'honey': 1}), 0 < meat <= 1.5)
        for meat in (0, 0.25, 0.5, 1):
            self.assertEqual(predicate_only(self.rule('炖兔子'), {'meat': meat, 'frozen': 2}), 0 < meat < 1)

    def test_and_or_are_not_flattened_into_the_same_operation(self):
        turkey = self.rule('火鸡正餐')
        for tags, expected in [({'meat': 1.5}, False),
                               ({'meat': 1.5, 'fruit': 0.25}, True),
                               ({'meat': 1.5, 'veggie': 0.5}, True),
                               ({'meat': 1, 'veggie': 1}, False)]:
            with self.subTest(tags=tags):
                self.assertEqual(predicate_only(turkey, tags, {'drumstick': 2}), expected)
        mousse = self.rule('发光浆果慕斯')
        for counts, expected in [({'wormlight': 1}, True), ({'wormlight_lesser': 1}, False),
                                 ({'wormlight_lesser': 2}, True)]:
            with self.subTest(counts=counts):
                self.assertEqual(predicate_only(mousse, {'fruit': 2}, counts), expected)

    def test_user_confirmed_shared_quantity_counting(self):
        # These fixtures implement the user's confirmation, not an independent game test.
        roll = self.rule('加州卷')
        self.assertTrue(predicate_only(roll, {'fish': 1}, {'kelp': 1, 'kelp_cooked': 1}))
        self.assertFalse(predicate_only(roll, {'fish': 1}, {'kelp': 2, 'kelp_cooked': 1}))


@unittest.skipUnless(SOURCE_ARCHIVE.is_dir(), 'Saved wiki archive is optional')
class SourceAuditTests(unittest.TestCase):
    def test_every_recipe_priority_and_tag_cell_matches_saved_html(self):
        report = audit(next(SOURCE_ARCHIVE.glob('*.html')))
        self.assertEqual(report['discrepancies'], [])
        self.assertEqual(report['recipe_conditions_checked'], 81)
        self.assertEqual(report['priorities_checked'], 81)
        self.assertEqual(report['ingredient_tag_cells_checked'], 2175)
        self.assertEqual(report['priority_range'], [-10, 100])
        self.assertEqual(report['per_recipe_weight_null_count'], 81)
        self.assertFalse(report['solver_ready_flags_changed'])
        self.assertEqual(report['grouped_quantity_review_count'], 0)
        self.assertEqual(report['grouped_quantity_recipes_count'], 10)
        self.assertTrue(report['user_confirmation']['mixed_listed_forms_share_count'])


if __name__ == '__main__':
    unittest.main()
