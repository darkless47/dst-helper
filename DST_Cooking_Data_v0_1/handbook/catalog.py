"""Content queries only. User state must never be written to this snapshot."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from .rules import TAG_LABELS, describe_ast, validate_ast

DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / 'dst_cooking.sqlite'


class Catalog:
    def __init__(self, database=DEFAULT_DATABASE):
        self.database = Path(database).resolve()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        try:
            yield connection
        finally:
            connection.close()

    def overview(self):
        with self.connect() as db:
            metadata = {r['key']: json.loads(r['value_json'])
                        for r in db.execute('SELECT * FROM dataset_metadata')}
            dishes = [dict(r) for r in db.execute('''
                SELECT d.*, r.priority, r.cook_seconds, r.weight,
                       r.cooker_scope_hint, r.parse_status, r.solver_ready
                FROM dishes d JOIN recipe_rules r USING(dish_id) ORDER BY source_row
            ''')]
            ingredients = [dict(r) for r in db.execute(
                'SELECT * FROM ingredients ORDER BY source_row')]
            tags = {}
            for r in db.execute('SELECT * FROM ingredient_tags ORDER BY tag'):
                tags.setdefault(r['ingredient_id'], {})[r['tag']] = r['value']
            for ingredient in ingredients:
                ingredient['tags'] = tags.get(ingredient['ingredient_id'], {})
            return dict(metadata=metadata, dishes=dishes, ingredients=ingredients,
                        tag_labels=TAG_LABELS,
                        sources=[dict(r) for r in db.execute('SELECT * FROM sources')],
                        issues=[dict(r) for r in db.execute('SELECT * FROM review_issues ORDER BY issue_id')])

    def asset_records(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM assets ORDER BY asset_id')]

    def prediction_snapshot(self):
        data = self.overview()
        with self.connect() as db:
            recipes = []
            for row in db.execute('''SELECT d.dish_id,d.name_zh,d.icon_asset_id,r.*
                    FROM dishes d JOIN recipe_rules r USING(dish_id) ORDER BY d.source_row'''):
                recipe = dict(row)
                recipe['conditions'] = json.loads(recipe.pop('conditions_json') or 'null')
                recipes.append(recipe)
        return dict(metadata=data['metadata'], ingredients=data['ingredients'], recipes=recipes, dishes=data['dishes'])

    def detail(self, kind, entity_id):
        if kind not in ('dish', 'ingredient'):
            raise KeyError(kind)
        table, key = ('dishes', 'dish_id') if kind == 'dish' else ('ingredients', 'ingredient_id')
        with self.connect() as db:
            row = db.execute(f'SELECT * FROM {table} WHERE {key}=?', (entity_id,)).fetchone()
            if row is None:
                raise KeyError(entity_id)
            result = dict(row)
            evidence = db.execute('SELECT * FROM source_rows WHERE entity_kind=? AND entity_id=?',
                                  (kind, entity_id)).fetchone()
            result['evidence'] = dict(evidence) if evidence else None
            if evidence:
                result['evidence']['cells'] = json.loads(result['evidence'].pop('cells_json'))
            result['source'] = dict(db.execute('SELECT * FROM sources WHERE source_id=?',
                                              (row['source_id'],)).fetchone())
            result['issues'] = [dict(r) for r in db.execute(
                'SELECT * FROM review_issues WHERE entity_id=? ORDER BY issue_id', (entity_id,))]
            asset = db.execute('SELECT * FROM assets WHERE asset_id=?', (row['icon_asset_id'],)).fetchone()
            result['asset'] = dict(asset) if asset else None
            if kind == 'ingredient':
                result['tags'] = {r['tag']: r['value'] for r in db.execute(
                    'SELECT * FROM ingredient_tags WHERE ingredient_id=?', (entity_id,))}
                result['states'] = [dict(r) for r in db.execute(
                    'SELECT ingredient_id, name_zh, source_row FROM ingredients WHERE prefab_id=? ORDER BY source_row',
                    (row['prefab_id'],))]
            else:
                result['rule'] = dict(db.execute('SELECT * FROM recipe_rules WHERE dish_id=?',
                                                (entity_id,)).fetchone())
                ast = json.loads(result['rule'].pop('conditions_json') or 'null')
                result['rule']['conditions'] = ast
                result['rule']['description'] = None
                result['rule']['display_error'] = None
                if ast is not None:
                    names = {}
                    for r in db.execute('SELECT prefab_id, name_zh FROM ingredients ORDER BY source_row'):
                        names.setdefault(r['prefab_id'], r['name_zh'])
                    try:
                        validate_ast(ast, known_prefabs=names)
                        result['rule']['description'] = describe_ast(ast, names)
                    except ValueError:
                        result['rule']['display_error'] = '规则含不支持的结构；请查看原始证据，等待复核。'
            return result
