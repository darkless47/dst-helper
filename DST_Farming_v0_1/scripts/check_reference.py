"""Compare numeric facts and bounded ratio results with the requested reference.
Optional network tool; not required by tests or app. Never executes reference JS.
Use --html path for an already downloaded page.
No third-party code or artwork is copied into the handoff.
"""
import argparse,hashlib,json,re,urllib.request
from pathlib import Path
from itertools import combinations,product
from planner_core import crop_index,ratios,eligible_crops
URL='https://hzhangxyz.github.io/dst-farming/'
def check(raw):
 s=raw.decode();m=re.search(r'const co=(\[\{名称:.*?\}\]),uo=',s)
 if not m:raise ValueError('Reference bundle structure changed; manual review needed')
 # Strictly turn one observed array of literal facts into JSON, no JS execution.
 literal=re.sub(r'([{,])(\w+):',r'\1"\2":',m[1]).replace('!0','true').replace('!1','false');ref=json.loads(literal)
 own=crop_index();byname={p['name_zh']:id for id,p in own.items()};season_map={'春季':'spring','夏季':'summer','秋季':'autumn','冬季':'winter'}
 assert len(ref)==14
 for p in ref:
  q=own[byname[p['名称']]]
  assert [p['催长剂'],p['堆肥'],p['粪肥']]==q['nutrient_delta_per_stage']
  assert all(p[cn]==q['preferred_seasons'][en] for cn,en in season_map.items())
 counts={};all_seasons=sorted(season_map.values())
 for mask in range(16):
  seasons=[v for i,v in enumerate(all_seasons) if mask&(1<<i)]
  selected=[p for p in ref if all(p[cn] for cn,en in season_map.items() if en in seasons)]
  expected=set()
  # Independent enumeration of every 0/1/2 count vector for selected crops.
  # Match the observed site's bounded candidate family: two or three types,
  # each positive coefficient <=2, with at least one coefficient 1.
  for k in [2,3]:
   for plants in combinations(selected,k):
    for ns in product([1,2],repeat=k):
     if min(ns)!=1:continue
     if all(sum(p[nutrient]*n for p,n in zip(plants,ns))==0 for nutrient in ['催长剂','堆肥','粪肥']):
      expected.add(tuple(sorted((byname[p['名称']],n) for p,n in zip(plants,ns))))
  actual={tuple(sorted(r['counts'].items())) for r in ratios(own,seasons)}
  assert expected==actual,('Ratio mismatch',seasons)
  counts['+'.join(seasons) or 'no_filter']=len(actual)
 return {'reference_url':URL,'retrieved_date':'2026-11-09','reference_html_sha256':hashlib.sha256(raw).hexdigest(),'inspection':'HTTP HTML and embedded app behavior inspected; no screenshot/browser-render verification claimed','matched_crop_nutrient_and_season_records':14,'matched_season_filter_combinations':16,'ratio_counts_by_filter':counts,'reference_scope':'two or three crop types; primitive coefficients 1 or 2; exact zero net of all three nutrients','interpretation':'Agreement between two wiki-based tools, not independent game-build verification'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--html',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 raw=a.html.read_bytes() if a.html else urllib.request.urlopen(URL,timeout=30).read();result=check(raw)
 if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
