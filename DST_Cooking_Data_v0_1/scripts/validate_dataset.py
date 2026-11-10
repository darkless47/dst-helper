"""Offline structural checks and source-derived AST regression cases.
These tests check extraction fidelity; they are NOT in-game verification.
"""
import json,operator,sqlite3,tempfile
from pathlib import Path
from build_database import ROOT,build
OPS={'==':operator.eq,'>':operator.gt,'<':operator.lt,'>=':operator.ge,'<=':operator.le}
def matches(ast,counts,tags):
    if 'all' in ast:return all(matches(x,counts,tags) for x in ast['all'])
    if 'any' in ast:return any(matches(x,counts,tags) for x in ast['any'])
    if 'tag' in ast:v=tags.get(ast['tag'],0)
    elif 'item_sum' in ast:v=sum(counts.get(x,0) for x in ast['item_sum'])
    else:raise ValueError('Unknown AST node')
    return OPS[ast['op']](v,ast['value'])
def main():
    d=json.loads((ROOT/'data/snapshot.json').read_text(encoding='utf-8'))
    assert len(d['ingredients'])==145 and len({i['prefab_id'] for i in d['ingredients']})==144
    assert len(d['dishes'])==81
    assert len({i['dish_id'] for i in d['dishes']})==81
    ingredients={i['ingredient_id']:i for i in d['ingredients']}
    prefabs={i['prefab_id'] for i in d['ingredients']}
    def check_ast(a):
        if 'all' in a or 'any' in a:
            key='all' if 'all' in a else 'any'
            for x in a[key]:check_ast(x)
        else:
            assert a['op'] in OPS
            assert isinstance(a['value'],(int,float))
            if 'item_sum' in a:assert set(a['item_sum'])<=prefabs
    for dish in d['dishes']:
        assert not dish['solver_ready'] and dish['game_prefab_id'] is None and dish['weight'] is None
        assert dish['conditions'] is not None
        check_ast(dish['conditions'])
        assert len(dish['cells'])==10
    assert sum(x['cooker_scope_hint']=='portable_only_wiki_claim' for x in d['dishes'])==11
    assert ingredients['berries']['tags']['fruit']==0.5
    assert len([i for i in d['ingredients'] if i['prefab_id']=='wx78_foodbrick'])==2
    fixtures=json.loads((ROOT/'data/extraction_fixtures.json').read_text(encoding='utf-8'))
    byname={x['name_zh']:x for x in d['dishes']}
    for f in fixtures:
        got=matches(byname[f['dish_zh']]['conditions'],f['item_counts'],f['tag_totals'])
        assert got==f['matches'],f
    assert byname['彩虹糖豆']['base_health'] is None
    assert byname['舒缓茶']['base_sanity'] is None
    assert byname['彩虹糖豆']['perish_source_text']=='无'
    assert byname['肉丸']['base_hunger']==62.5
    assert byname['粉末蛋糕']['perish_game_days']==18750
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'rebuilt.sqlite';build(ROOT/'data/snapshot.json',p)
        c=sqlite3.connect(p)
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute('SELECT count(*) FROM source_rows').fetchone()[0]==226
        assert c.execute('SELECT count(*) FROM recipe_rules WHERE solver_ready=1').fetchone()[0]==0
        c.close()
    print(f'PASS: structural checks, complete offline rebuild, and {len(fixtures)} source-derived predicate cases. No in-game validation claimed.')
if __name__=='__main__':main()
