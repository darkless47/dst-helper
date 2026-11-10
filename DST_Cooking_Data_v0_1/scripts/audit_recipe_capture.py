"""Independent, read-only comparison of saved wiki HTML and SQLite recipe capture.

Uses stdlib HTMLParser and a separate token parser, not the ingestion extractor.
Checks transcription under the documented sum-of-prefabs interpretation of grouped
icon alternatives. It does not verify game behavior or implement outcome prediction.
"""
import argparse
from fractions import Fraction
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handbook.rules import TAG_LABELS


class SavedTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.prose = [], []
        self.depth = 0
        self.table = self.row = self.cell = None
        self.anchor = 0
        self.ignore = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in ('script', 'style'):
            self.ignore = tag
        if tag == 'table':
            if not self.depth:
                self.table = dict(rows=[], headers=[])
                self.tables.append(self.table)
            self.depth += 1
        if self.depth != 1:
            return
        if tag == 'tr':
            self.row = []
        elif tag in ('th', 'td'):
            self.cell = dict(kind=tag, attrs=attrs, parts=[], images=[])
        elif tag == 'a':
            self.anchor += 1
        elif self.cell is not None and tag == 'br':
            self.cell['parts'].append('\n')
        elif self.cell is not None and tag == 'img':
            self.cell['images'].append(dict(attrs, linked=bool(self.anchor)))
            self.cell['parts'].append('[' + attrs.get('alt', '') + ']')

    def handle_endtag(self, tag):
        if tag == self.ignore:
            self.ignore = None
        if self.depth == 1:
            if tag in ('td', 'th') and self.cell is not None:
                self.cell['text'] = ''.join(self.cell.pop('parts')).strip()
                self.row.append(self.cell)
                self.cell = None
            elif tag == 'tr' and self.row:
                group = 'rows' if all(c['kind'] == 'td' for c in self.row) else 'headers'
                self.table[group].append(self.row)
                self.row = None
            elif tag == 'a':
                self.anchor = max(0, self.anchor - 1)
        if tag == 'table':
            self.depth -= 1

    def handle_data(self, data):
        if not self.ignore:
            self.prose.append(data)
            if self.depth == 1 and self.cell is not None:
                self.cell['parts'].append(data)


OPS = {'=': '==', '==': '==', '>': '>', '<': '<', '≥': '>=', '≤': '<=', '>=': '>=', '<=': '<='}
REVERSE = {'==': '==', '>': '<', '<': '>', '>=': '<=', '<=': '>='}


class Expression:
    """Token-based AND/OR and chained-comparison parser, independent of extraction."""
    def __init__(self, source, prefabs=None):
        self.prefabs = prefabs
        names = '|'.join(re.escape(n) for n in sorted(TAG_LABELS.values(), key=len, reverse=True))
        pattern = re.compile(r'(?P<image>\[[^\]]+\])|(?P<tag>' + names + r')|'
                             r'(?P<op>>=|<=|==|[=<>≥≤])|(?P<number>-?\d+(?:\.\d+)?)|'
                             r'(?P<or>/)|(?P<and>[\n,，]+)|(?P<space>[ \t\r]+)')
        self.tokens = []
        position = 0
        source = source.strip()
        while position < len(source):
            match = pattern.match(source, position)
            if not match:
                raise ValueError('Unparsed source: ' + source[position:])
            if match.lastgroup != 'space':
                self.tokens.append((match.lastgroup, match.group()))
            position = match.end()
        self.position = 0

    def peek(self, kind):
        return self.position < len(self.tokens) and self.tokens[self.position][0] == kind

    def pop(self, kind):
        if not self.peek(kind):
            raise ValueError('Expected ' + kind + ' at ' + repr(self.tokens[self.position:]))
        value = self.tokens[self.position][1]
        self.position += 1
        return value

    def parse(self):
        if not self.tokens:
            return {'all': []}
        clauses = [self.disjunction()]
        while self.peek('and'):
            self.pop('and')
            clauses.append(self.disjunction())
        if self.position != len(self.tokens):
            raise ValueError('Trailing source tokens')
        return {'all': clauses}

    def disjunction(self):
        choices = [self.atom()]
        while self.peek('or'):
            self.pop('or')
            choices.append(self.atom())
        return choices[0] if len(choices) == 1 else {'any': choices}

    def atom(self):
        if self.prefabs is not None:
            labels = [self.pop('image')[1:-1]]
            while self.peek('or'):
                self.pop('or')
                labels.append(self.pop('image')[1:-1])
            op, value = OPS[self.pop('op')], float(self.pop('number'))
            return {'item_sum': sorted({self.prefabs[label] for label in labels}), 'op': op, 'value': value}
        names = {label: key for key, label in TAG_LABELS.items()}
        if self.peek('tag'):
            tag = names[self.pop('tag')]
            return {'tag': tag, 'op': OPS[self.pop('op')], 'value': float(self.pop('number'))}
        lower, op = float(self.pop('number')), OPS[self.pop('op')]
        tag = names[self.pop('tag')]
        lower_node = {'tag': tag, 'op': REVERSE[op], 'value': lower}
        if not self.peek('op'):
            return lower_node
        return {'all': [lower_node, {'tag': tag, 'op': OPS[self.pop('op')], 'value': float(self.pop('number'))}]}


def canonical(node):
    """Ignore ordering/associative nesting, preserving every comparison and OR group."""
    for operator in ('all', 'any'):
        if operator in node:
            children = []
            for child in node[operator]:
                normalized = canonical(child)
                if normalized[0] == operator:
                    children.extend(normalized[1])
                else:
                    children.append(normalized)
            if len(children) == 1:
                return children[0]
            return operator, tuple(sorted(children, key=repr))
    subject = ('tag', node['tag']) if 'tag' in node else ('item_sum', tuple(sorted(node['item_sum'])))
    return *subject, node['op'], str(Fraction(str(node['value'])))


def grouped_quantity_review(node):
    if 'all' in node or 'any' in node:
        return any(grouped_quantity_review(c) for c in node.get('all', node.get('any', [])))
    return ('item_sum' in node and len(node['item_sum']) > 1
            and (node['value'] > 1 or node['op'] == '=='))


def audit(html_path, database=ROOT / 'dst_cooking.sqlite'):
    policy = json.loads((ROOT / 'data/prediction_policy.json').read_text(encoding='utf-8'))
    groups_confirmed = policy['user_confirmation']['mixed_listed_forms_share_count']
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    page = SavedTables()
    raw = html_path.read_bytes()
    page.feed(raw.decode('utf-8'))
    db = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        metadata = {r['key']: json.loads(r['value_json']) for r in db.execute('SELECT * FROM dataset_metadata')}
        if hashlib.sha256(raw).hexdigest() != metadata['source_sha256']:
            raise ValueError('Saved page does not match snapshot hash')
        ingredients, recipes = page.tables[:2]
        if len(ingredients['rows']) != 145 or len(recipes['rows']) != 81:
            raise ValueError('Unexpected source table sizes')
        if recipes['headers'][0][7]['text'].strip() != '优先级':
            raise ValueError('Priority column header mismatch')
        discrepancies, results, alt_prefabs = [], [], {}
        tag_values_checked = 0
        labels = [c['text'].strip() for c in ingredients['headers'][0][1:]]
        if labels != list(TAG_LABELS.values()):
            raise ValueError('Ingredient tag column mismatch')
        db_ingredients = {r['source_row']: dict(r) for r in db.execute('SELECT * FROM ingredients')}
        for number, cells in enumerate(ingredients['rows'], 1):
            name = cells[1]['text'].strip()
            prefab = cells[0]['attrs']['data-sort-value'][len(name):]
            row = db_ingredients[number]
            if (row['name_zh'], row['prefab_id']) != (name, prefab):
                discrepancies.append(f'Ingredient identity mismatch at row {number}')
            for image in cells[0]['images']:
                if image['linked']:
                    alt_prefabs[image['alt']] = prefab
            expected = {tag: float(cells[i+2]['text']) for i, tag in enumerate(TAG_LABELS)
                        if cells[i+2]['text'].strip()}
            actual = {r['tag']: r['value'] for r in db.execute(
                'SELECT tag, value FROM ingredient_tags WHERE ingredient_id=?', (row['ingredient_id'],))}
            tag_values_checked += len(TAG_LABELS)
            if expected != actual:
                discrepancies.append(f'Ingredient tags differ at row {number}')
        rows = {r['source_row']: dict(r) for r in db.execute(
            'SELECT d.source_row,d.name_zh,r.* FROM dishes d JOIN recipe_rules r USING(dish_id)')}
        for number, cells in enumerate(recipes['rows'], 1):
            row = rows[number]
            tag_text, item_text = cells[8]['text'], cells[9]['text']
            named_only = item_text.split('只能由', 1)[0].strip()
            expected = {'all': [Expression(tag_text).parse(), Expression(named_only, alt_prefabs).parse()]}
            actual = json.loads(row['conditions_json'])
            conditions_match = canonical(expected) == canonical(actual)
            priority = int(cells[7]['text'].strip())
            portable = '只能由' in item_text
            expected_scope = 'portable_only_wiki_claim' if portable else 'ordinary_recipe_cooker_matrix_unconfirmed'
            checks = dict(name=row['name_zh'] == cells[1]['text'].strip(), conditions=conditions_match,
                          priority=row['priority'] == priority, cooker_hint=row['cooker_scope_hint'] == expected_scope)
            if not all(checks.values()):
                discrepancies.append(dict(row=number, name=row['name_zh'], checks=checks))
            results.append(dict(source_row=number, dish_id=row['dish_id'], name_zh=row['name_zh'],
                                source_tag_conditions=tag_text, source_named_conditions=item_text,
                                priority=priority, checks=checks,
                                has_quantity_sensitive_groups=grouped_quantity_review(expected),
                                grouped_quantity_semantics_needs_confirmation=grouped_quantity_review(expected) and not groups_confirmed))
        prose = ''.join(page.prose)
        selection = '从满足烹饪要求的食谱中选出优先级最高的食谱。'
        ties = '若有多个优先级最高的食谱，则在这些食谱中等概率地选中一个食谱。'
        if selection not in prose or ties not in prose:
            raise ValueError('Selection/tie prose not found')
        report = dict(audit_date='2026-11-08', source_revision=metadata['source_revision'],
                      source_html_sha256=hashlib.sha256(raw).hexdigest(),
                      content_database_sha256=original_hash,
                      ingredient_states_checked=145, ingredient_tag_cells_checked=tag_values_checked,
                      recipe_conditions_checked=len(results), priorities_checked=len(results),
                      discrepancies=discrepancies,
                      priority_range=[min(r['priority'] for r in results), max(r['priority'] for r in results)],
                      per_recipe_weight_null_count=db.execute('SELECT count(*) FROM recipe_rules WHERE weight IS NULL').fetchone()[0],
                      wiki_selection_prose=[selection, ties],
                      user_confirmation=dict(date='2026-11-08', policy='maximum priority; uniform among tied maxima',
                                             mixed_listed_forms_share_count=groups_confirmed),
                      abstract_selection_examples=[
                          dict(matching_priorities=[10, 10, 5], probabilities=['1/2', '1/2', '0']),
                          dict(matching_priorities=[30, 10, -1], probabilities=['1', '0', '0']),
                          dict(matching_priorities=[-1, -4, -10], probabilities=['1', '0', '0'])],
                      grouped_quantity_review_count=sum(r['grouped_quantity_semantics_needs_confirmation'] for r in results),
                      grouped_quantity_recipes_count=sum(r['has_quantity_sensitive_groups'] for r in results),
                      interpretation_limit='Shared icon groups are counted by summed explicitly listed prefabs, as confirmed by the user. The source transcription audit itself is not independent in-game verification.',
                      solver_ready_flags_changed=False, in_game_verification=False, recipes=results)
    finally:
        db.close()
    if hashlib.sha256(database.read_bytes()).hexdigest() != original_hash:
        raise AssertionError('Audit changed database bytes')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--database', type=Path, default=ROOT / 'dst_cooking.sqlite')
    parser.add_argument('--output', type=Path, default=ROOT / 'RECIPE_CAPTURE_AUDIT.json')
    args = parser.parse_args()
    source = args.html or next((ROOT.parent / 'wiki-webpage-save').glob('*.html'))
    report = audit(source, args.database)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('recipe_conditions_checked', 'priorities_checked',
                                          'ingredient_tag_cells_checked', 'discrepancies', 'priority_range')}))
    if report['discrepancies']:
        raise SystemExit(1)
