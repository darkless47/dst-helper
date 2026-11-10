"""Rebuild SQLite offline from snapshot.json. Standard library only.
Refuses to replace an existing file unless --overwrite is explicitly supplied.
"""
import argparse,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(snapshot, destination, overwrite=False):
    if destination.exists():
        if not overwrite:raise FileExistsError(destination)
        destination.unlink()
    d=json.loads(snapshot.read_text(encoding='utf-8'));m=d['metadata'];c=sqlite3.connect(destination)
    try:
        c.executescript((ROOT/'migrations/001_initial.sql').read_text(encoding='utf-8'))
        with c:
            c.executemany('INSERT INTO dataset_metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in m.items()])
            c.execute('INSERT INTO sources VALUES(1,?,?,?,?,?,?,?)',(m['source_url'],m['source_revision'],m['source_received_date'],'user_saved_wiki_html',m['source_sha256'],None,m['source_retrieval_note']))
            for id,a in d['assets'].items():
                c.execute('INSERT INTO assets VALUES(?,1,?,?,?,?,?)',(id,a['source_local_reference'],json.dumps(a['original_candidates']),a['sha256'],a['rights_status'],int(a['redistributable'])))
            for i in d['ingredients']:
                c.execute('INSERT INTO ingredients VALUES(?,?,?,?,?,?,1,?,?)',(i['ingredient_id'],i['prefab_id'],i['name_zh'],i['name_en_hint'],i['source_url'],i['source_row'],i['icon_asset_id'],'wiki_snapshot_only'))
                c.executemany('INSERT INTO ingredient_tags VALUES(?,?,?,1)',[(i['ingredient_id'],tag,v) for tag,v in i['tags'].items()])
                c.execute('INSERT INTO source_rows VALUES(?,?,1,?,?)',('ingredient',i['ingredient_id'],i['source_row'],json.dumps(i['cells'],ensure_ascii=False)))
            for i in d['dishes']:
                keys=['dish_id','game_prefab_id','name_zh','name_en_hint','base_health','base_hunger','base_sanity','health_source_text','hunger_source_text','sanity_source_text','perish_game_days','perish_source_text']
                vals=[i[k] for k in keys]+[None,i['source_url'],i['source_row'],1,i['icon_asset_id'],'wiki_snapshot_only']
                c.execute('INSERT INTO dishes VALUES('+','.join('?' for _ in vals)+')',vals)
                c.execute('INSERT INTO recipe_rules VALUES(?,?,?,?,?,?,?,0,1)',(i['dish_id'],i['priority'],i['cook_seconds'],i['weight'],i['cooker_scope_hint'],json.dumps(i['conditions'],ensure_ascii=False) if i['conditions'] is not None else None,i['parse_status']))
                c.execute('INSERT INTO source_rows VALUES(?,?,1,?,?)',('dish',i['dish_id'],i['source_row'],json.dumps(i['cells'],ensure_ascii=False)))
            for i in d['issues']:
                c.execute('INSERT INTO review_issues(entity_kind,entity_id,field_name,issue_code,details) VALUES(?,?,?,?,?)',[i[k] for k in ['entity_kind','entity_id','field_name','issue_code','details']])
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    finally:c.close()
    print(destination)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--snapshot',type=Path,default=ROOT/'data/snapshot.json');a.add_argument('--output',type=Path,default=ROOT/'dst_cooking.sqlite');a.add_argument('--overwrite',action='store_true');v=a.parse_args();build(v.snapshot,v.output,v.overwrite)
