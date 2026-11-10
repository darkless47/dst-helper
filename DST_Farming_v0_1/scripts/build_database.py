"""Build separate farming.sqlite. Standard library only; no changes to cooking DB."""
import argparse,json,sqlite3,tempfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(destination,overwrite=False):
 destination=Path(destination)
 if destination.exists() and not overwrite:raise FileExistsError('Refusing to overwrite '+str(destination))
 destination.parent.mkdir(parents=True,exist_ok=True)
 d=json.loads((ROOT/'data/farming.json').read_text(encoding='utf-8'));m=d['metadata']
 fd,tmp=tempfile.mkstemp(dir=destination.parent,suffix='.sqlite');os.close(fd);c=sqlite3.connect(tmp)
 try:
  c.executescript((ROOT/'migrations/001_farming_tables.sql').read_text(encoding='utf-8'))
  with c:
   c.executemany('INSERT INTO farming_metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in m.items()])
   c.execute('INSERT INTO farming_sources VALUES(1,?,?,?,?,?,?)',(m['source_url'],m['source_revision'],m['received_date'],m['source_sha256'],None,m['evidence_level']))
   for id,a in d['assets'].items():c.execute('INSERT INTO farming_assets VALUES(?,1,?,0)',(id,json.dumps(a,ensure_ascii=False)))
   for p in d['plants']:
    vals=[p[k] for k in ['plant_id','kind','product_ingredient_id','plant_prefab_id','seed_prefab_id','name_zh','plant_name_zh','name_en_hint','seed_name_en_hint']]+p['nutrient_delta_per_stage']+[p[k] for k in ['water_percent_points_per_stage','water_source_text','plant_asset_id','seed_asset_id','product_asset_id','source_url','source_row']]+[1,'wiki_based_usable']
    c.execute('INSERT INTO farming_plants VALUES('+','.join('?' for _ in vals)+')',vals)
    for season,pref in p['preferred_seasons'].items():c.execute('INSERT INTO farming_seasons VALUES(?,?,?,?,1)',(p['plant_id'],season,int(pref),p['random_seed_percent'][season]))
    c.execute('INSERT INTO farming_row_evidence VALUES(?,?,1)',(p['plant_id'],json.dumps(p['source_cells'],ensure_ascii=False)))
   for r in d['mechanics']:c.execute('INSERT INTO farming_mechanics VALUES(?,?,?,?,1,?)',(r['rule_id'],json.dumps(r['value'],ensure_ascii=False),r['source_section'],r['note'],r['verification_status']))
   for s in d['source_sections']:c.execute('INSERT INTO farming_section_evidence(heading,paragraphs_json,source_id) VALUES(?,?,1)',(s['heading'],json.dumps(s['paragraphs'],ensure_ascii=False)))
   for i in d['issues']:c.execute('INSERT INTO farming_review_issues VALUES(?,?)',(i['code'],i['details']))
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
  c.close();os.replace(tmp,destination)
 except Exception:
  c.close();Path(tmp).unlink(missing_ok=True);raise
 return destination
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'farming.sqlite');ap.add_argument('--overwrite',action='store_true');a=ap.parse_args();print(build(a.output,a.overwrite))
