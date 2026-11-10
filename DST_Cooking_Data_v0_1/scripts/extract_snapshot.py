"""Extract a user-saved Huiji cooking page; never execute its scripts.
Requires lxml. Usage: python scripts/extract_snapshot.py saved.html --output data/snapshot.json
"""
import argparse, hashlib, json, re
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote
from lxml import html

TAGS=dict(zip(['肉度','怪物度','鱼度','水果度','蔬菜度','蛋度','甜味剂度','乳制品度','冰度','不可食用度','魔法度','油脂度','种子度','装饰度','干货度'],['meat','monster','fish','fruit','veggie','egg','sweetener','dairy','frozen','inedible','magic','fat','seed','decoration','dried']))
OP={'=':'==','>':'>','<':'<','≥':'>=','≤':'<='}
def text(e): return ' '.join(e.text_content().split())
def cells(row): return row.xpath('./td')
def rich(e):
    q=deepcopy(e)
    for x in q.xpath('.//img'):
        x.tag='span';x.text='['+str(x.get('alt'))+']'
    for x in q.xpath('.//br'): x.tail='\n'+(x.tail or '')
    return q.text_content().strip()
def tag_atom(s):
    s=s.strip()
    for name,key in TAGS.items():
        if name not in s: continue
        pat=re.escape(name)
        m=re.fullmatch(pat+r'\s*([=<>≥≤])\s*(-?\d+(?:\.\d+)?)',s)
        if m:return {'tag':key,'op':OP[m[1]],'value':float(m[2])}
        m=re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*([<≤])\s*'+pat+r'\s*([<≤])\s*(-?\d+(?:\.\d+)?)',s)
        if m:return {'all':[{'tag':key,'op': '>' if m[2]=='<' else '>=','value':float(m[1])},{'tag':key,'op':OP[m[3]],'value':float(m[4])}]}
    raise ValueError('Unparsed tag clause: '+s)
def tag_tree(s):
    clauses=[]
    for line in re.split('[\n，,]',s):
        if not line.strip():continue
        a=[tag_atom(x) for x in line.split('/')]
        clauses.append(a[0] if len(a)==1 else {'any':a})
    return clauses

def main():
    ap=argparse.ArgumentParser();ap.add_argument('html',type=Path);ap.add_argument('--output',type=Path,default=Path('data/snapshot.json'));a=ap.parse_args()
    raw=a.html.read_bytes();doc=html.fromstring(raw);tables=doc.xpath('//table')
    assert len(tables)>=2
    rev=re.search(r'"wgRevisionId"\s*:\s*(\d+)',raw.decode('utf-8'))
    saved=re.search(r'saved from url=\(\d+\)(https://[^\s]+)',raw.decode('utf-8'))
    result={'metadata':{'dataset_version':'0.1.0','schema_version':1,'target_game':'DST','target_build':'762172','target_build_evidence':'User report; local version file modified 2026-11-05 23:32 America/New_York (UTC-05:00)','source_received_date':'2026-11-07','source_retrieved_at':None,'source_retrieval_note':'User-supplied saved page; exact save/retrieval timestamp unknown','source_url':saved[1], 'source_revision':rev[1], 'source_sha256':hashlib.sha256(raw).hexdigest(),'build_compatibility':'unconfirmed','verification':'single_wiki_snapshot','solver_ready':False,'tie_policy_source_claim':'equal probability among highest-priority matches; per-recipe weights unconfirmed','time_policy':'Perishability stays in game days; cooking time in seconds. No conversion to real seconds without a sourced day-length constant.','license_note':'Prior research reports Huiji text CC BY-NC-SA 3.0 unless otherwise specified; not reverified from this saved page. Game-art rights separate and unconfirmed. Unofficial fan dataset.'},'ingredients':[],'dishes':[],'assets':{},'issues':[]}
    def issue(kind,id,field,code,details):result['issues'].append(dict(entity_kind=kind,entity_id=id,field_name=field,issue_code=code,details=details))
    def asset(im):
        src=im.get('src'); aid='asset:'+hashlib.sha256(src.encode()).hexdigest()[:20]
        f=a.html.parent/unquote(src)
        result['assets'][aid]={'source_local_reference':src,'original_candidates':im.get('srcset','').split(', '),'sha256':hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None,'rights_status':'unconfirmed','redistributable':False}
        return aid
    def evidence(c):return [{'text':rich(x),'links':[{'title':y.get('title'),'url':y.get('href')} for y in x.xpath('.//a[@href]')], 'images':[{'alt':y.get('alt'),'src':y.get('src'),'srcset':y.get('srcset')} for y in x.xpath('.//img')]} for x in c]
    alt_ids={};seen=set()
    for n,r in enumerate(tables[0].xpath('./tbody/tr'),1):
        c=cells(r);assert len(c)==17
        name=text(c[1]); sort=c[0].get('data-sort-value'); assert sort.startswith(name)
        prefab=sort[len(name):];assert re.fullmatch('[a-z0-9_]+',prefab)
        iid=prefab if prefab not in seen else prefab+'@wiki_state_'+str(n)
        if prefab in seen:issue('ingredient',iid,'prefab_id','state_variant','Same wiki prefab as another ingredient row; preserve state identity and do not treat this suffix as a game prefab.')
        seen.add(prefab)
        im=c[0].xpath('.//a//img')[0]
        alt_ids[im.get('alt')]=prefab
        result['ingredients'].append(dict(ingredient_id=iid,prefab_id=prefab,name_zh=name,name_en_hint=im.get('alt').removesuffix('.png'),source_url=c[1].xpath('.//a/@href')[0],source_row=n,icon_asset_id=asset(im),tags={key:float(text(c[i+2])) for i,key in enumerate(TAGS.values()) if text(c[i+2])},cells=evidence(c)))
    def named_tree(s):
        q=s.split('只能由')[0].strip();clauses=[]
        for line in q.splitlines():
            line=line.strip()
            if not line:continue
            # Groups of icon alternatives followed by one shared comparison, or OR between comparisons.
            parts=re.split(r'(?<=[0-9])\s*/\s*(?=\[)',line)
            alternatives=[]
            for p in parts:
                m=re.fullmatch(r'((?:\[[^\]]+\]\s*/?\s*)+)\s*([=≥≤<>])\s*(\d+(?:\.\d+)?)',p)
                if not m:raise ValueError('Unparsed named clause: '+p)
                labels=re.findall(r'\[([^\]]+)\]',m[1]);ids=[]
                for label in labels:
                    if label not in alt_ids:raise ValueError('Unresolved item icon: '+label)
                    ids.append(alt_ids[label])
                alternatives.append({'item_sum':sorted(set(ids)),'op':OP[m[2]],'value':float(m[3])})
            clauses.append(alternatives[0] if len(alternatives)==1 else {'any':alternatives})
        return clauses
    for n,r in enumerate(tables[1].xpath('./tbody/tr'),1):
        c=cells(r);assert len(c)==10
        name=text(c[1]);url=c[1].xpath('.//a/@href')[0];id='huiji:'+unquote(url.split('/wiki/')[1])
        im=c[0].xpath('.//img')[0];stats=[]
        for field,x in zip(['health','hunger','sanity'],c[2:5]):
            s=text(x)
            if re.fullmatch(r'-?\d+(?:\.\d+)?',s):stats.append(float(s))
            else:
                stats.append(None);issue('dish',id,'base_'+field,'composite_stat','Source combines values: '+s+'. Do not display the total as immediate restoration; confirm timing and components on dish page.')
        raw_tags=rich(c[8]); raw_named=rich(c[9]); ast=None;status='needs_review'
        try:ast={'all':tag_tree(raw_tags)+named_tree(raw_named)};status='parsed_draft'
        except ValueError as e:issue('recipe',id,'conditions_json','parse_incomplete',str(e))
        perish=text(c[5]);days=None
        if perish.endswith('天'):days=float(perish[:-1])
        elif perish!='无':raise ValueError('Unknown perishability '+perish)
        result['dishes'].append(dict(dish_id=id,game_prefab_id=None,name_zh=name,name_en_hint=im.get('alt').removesuffix('.png'),base_health=stats[0],base_hunger=stats[1],base_sanity=stats[2],health_source_text=text(c[2]),hunger_source_text=text(c[3]),sanity_source_text=text(c[4]),perish_game_days=days,perish_source_text=perish,source_url=url,source_row=n,icon_asset_id=asset(im),priority=int(text(c[7])),cook_seconds=float(text(c[6]).removesuffix('秒')),weight=None,cooker_scope_hint='portable_only_wiki_claim' if '只能由' in raw_named else 'ordinary_recipe_cooker_matrix_unconfirmed',conditions=ast,parse_status=status,solver_ready=False,cells=evidence(c)))
    assert len(result['ingredients'])==145 and len(result['dishes'])==81,'Unexpected snapshot row counts: review input version'
    result['issues'].extend([dict(entity_kind='dataset',entity_id=None,field_name=None,issue_code=code,details=detail) for code,detail in [
    ('unconfirmed_build','Wiki revision 193291 is not verified against installed build 762172.'),('unconfirmed_weights','No per-recipe weight column; NULL means unknown, not weight=1.'),('dish_prefab_missing','Dish IDs are wiki-based placeholders. English names are filename-derived hints, not validated localization.'),('draft_predicates','AST conversion follows wiki shorthand and has not been checked against game scripts or in-game outcomes. All solver_ready flags are false.'),('cooker_matrix_missing','Page identifies portable-only recipes, but per-ingredient/per-recipe compatibility for all cookers is not established.'),('tag_coverage','Table has 15 tag columns; prose also mentions preprocessed. Absent columns are unknown, not an asserted complete tag vocabulary. Blank cells in these 15 columns are interpreted as zero.'),('mechanics_missing','Food types, character rules, special effects, generated example recipes, spices and output counts are not collected. Catalog values are wiki-reported, with wearable/animal foods needing interpretation.'),('asset_rights','Image references/hashes are indexed; art files are not bundled in this package and redistribution is not approved.')]])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ingredients':len(result['ingredients']),'distinct_prefabs':len(seen),'dishes':len(result['dishes']),'draft_ASTs':sum(x['conditions'] is not None for x in result['dishes']),'assets':len(result['assets']),'issues':len(result['issues'])}))
if __name__=='__main__':main()
