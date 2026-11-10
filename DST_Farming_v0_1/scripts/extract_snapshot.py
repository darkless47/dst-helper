"""Extract user-saved Huiji farming overview without executing page scripts.
Usage: python scripts/extract_snapshot.py saved.html [--output data/farming.json]
Extraction requires lxml; normal use/rebuild does not.
"""
import argparse,hashlib,json,re
from pathlib import Path
from urllib.parse import unquote
from lxml import html
ROOT=Path(__file__).resolve().parents[1]
ORDER=['autumn','winter','spring','summer']
# Curated product mapping to wiki-reported ingredient IDs in the existing cooking dataset.
PRODUCTS={'Carrot':'carrot','Corn':'corn','Potato':'potato','Toma Root':'tomato','Asparagus':'asparagus','Eggplant':'eggplant','Pumpkin':'pumpkin','Watermelon':'watermelon','Dragon Fruit':'dragonfruit','Durian':'durian','Garlic':'garlic','Onion':'onion','Pepper':'pepper','Pomegranate':'pomegranate'}
def text(e):return ' '.join(e.text_content().split())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('html',type=Path);ap.add_argument('--output',type=Path,default=ROOT/'data/farming.json');a=ap.parse_args()
 raw=a.html.read_bytes();s=raw.decode();d=html.fromstring(raw)
 revision=re.search(r'"wgRevisionId":(\d+)',s)[1]
 url=re.search(r'saved from url=\(\d+\)(https://[^\s]+)',s)[1]
 out={'metadata':{'dataset_version':'0.1.0','game':'DST','target_build':'762172','target_build_evidence':'Previously reported installed build; not reconfirmed November 9','game_build_verified':None,'received_date':'2026-11-09','original_retrieval_timestamp':None,'source_url':url,'source_revision':revision,'source_sha256':hashlib.sha256(raw).hexdigest(),'evidence_level':'user_saved_wiki_snapshot','planner_enabled':True,'planner_mode':'wiki_based_static_balance','nutrient_order':['growth_formula','compost','manure'],'nutrient_sign':'positive adds to soil; negative consumes; per growth stage','season_order':ORDER,'random_seed_percent_note':'Rounded seasonal appearance percentages, not preferred-season flags and not giant-yield probabilities.','giant_outcome_status':'conditional; no guarantee from ratios alone','art_status':'references only; permission unconfirmed; images not bundled'},'plants':[],'assets':{},'mechanics':[],'source_sections':[],'issues':[]}
 def image(im):
  src=im.get('src','');id='asset:'+hashlib.sha256(src.encode()).hexdigest()[:20];p=a.html.parent/unquote(src)
  out['assets'][id]={'alt':im.get('alt'),'source_local_reference':src,'srcset':im.get('srcset'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,'redistributable':False,'rights_status':'unconfirmed'}
  return id
 table=d.xpath('//table')[3]
 rows=[r for r in table.xpath('./tbody/tr') if len(r.xpath('./td'))==12]
 assert len(rows)==18
 for row_no,r in enumerate(rows,1):
  c=r.xpath('./td');name=text(c[1]);im=c[0].xpath('.//img')[0]
  product_imgs=c[3].xpath('.//img');pname=product_imgs[0].get('alt').removesuffix('.png') if product_imgs else None
  crop=row_no<=14
  pid=PRODUCTS[pname] if crop else 'huiji:'+name
  seasons={};prob={}
  for season,cell in zip(ORDER,c[4:8]):
   style=(cell.get('style') or '').replace(' ','').lower();assert style in ['color:#7fffaa','color:#d1e8ef']
   seasons[season]=style=='color:#7fffaa';prob[season]=float(text(cell).removesuffix('%'))
  seed_imgs=c[2].xpath('.//img')
  out['plants'].append({'plant_id':pid,'kind':'crop' if crop else 'weed','product_ingredient_id':pid if crop else None,'plant_prefab_id':None,'seed_prefab_id':None,'name_zh':c[3].xpath('.//a/@title')[0] if crop else name,'plant_name_zh':name,'name_en_hint':pname if crop else im.get('alt').removesuffix('.png'),'source_url':c[1].xpath('.//a/@href')[0],'source_row':row_no,'preferred_seasons':seasons,'random_seed_percent':prob,'nutrient_delta_per_stage':[int(text(x)) for x in c[8:11]],'water_percent_points_per_stage':float(text(c[11]).removesuffix('%')),'water_source_text':text(c[11]),'seed_name_en_hint':seed_imgs[0].get('alt').removesuffix('.png') if seed_imgs else None,'plant_asset_id':image(im),'seed_asset_id':image(seed_imgs[0]) if seed_imgs else None,'product_asset_id':image(product_imgs[0]) if product_imgs else None,'source_cells':[{'text':text(x),'style':x.get('style'),'images':[{'alt':q.get('alt'),'asset_id':image(q)} for q in x.xpath('.//img')],'links':[{'title':q.get('title'),'url':q.get('href')} for q in x.xpath('.//a[@href]')]} for x in c]})
 content=d.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," mw-parser-output ")]')[0]
 heading='intro';sections={}
 for el in content:
  if el.tag in ['h2','h3','h4']:heading=text(el)
  if el.tag in ['p','ul','ol','dl']:
   for node in el.xpath('.//script|.//style'):node.drop_tree()
   t=text(el)
   if t:sections.setdefault(heading,[]).append(t)
 out['source_sections']=[{'heading':k,'paragraphs':v} for k,v in sections.items()]
 def rule(id,v,section,note):out['mechanics'].append({'rule_id':id,'value':v,'source_section':section,'note':note,'verification_status':'wiki_snapshot_only'})
 rule('stress_sources',['nutrients','moisture','debris','season','family','overcrowding','tending'],'压力','Up to one stress point per category per stage, over four growth transitions; maximum 28.')
 rule('checked_growth_transitions',4,'生长阶段与收获','Track actual stages, not four arbitrary watering actions.')
 rule('giant_max_stress',1,'生长阶段与收获','Also requires crop-specific seeds, no rot/regrowth history and no forced ripening.')
 rule('family',{'radius_game_units':4,'minimum_same_kind_including_self':4},'家庭','Count actual positions, across tile boundaries; boundary equality needs game check.')
 rule('tile_width_game_units',4,'家庭','Footnote defines one distance unit as one quarter of a tile side.')
 rule('recommended_planner_slots_per_tile',9,'拥挤','Design default, not the exact game threshold. Use a 3x3 grid.')
 rule('overcrowding',{'safe_count_max':9,'ambiguous_count':10,'definite_overcrowded_min':11,'source_phrase':'10 株以上'},'拥挤','Wiki wording leaves the exact ten-plant boundary ambiguous; plants AND weeds count.')
 rule('debris_radius_game_units',6,'杂物','Includes weeds, rotten plants, farm debris and rotten giant produce.')
 rule('moisture_min_positive_fraction_per_stage',0.10,'土壤水分','Stress if fraction of stage with soil moisture >0 is below 10%; not a moisture threshold of 10 units.')
 rule('soil_nutrient_bounds',{'min':0,'max':100,'initial_min':25,'initial_max':50},'土壤营养','Three separate stores per TILE. Nutrient output is coupled to actual consumption; capped surplus is wasted.')
 rule('soil_moisture_bounds',{'min':0,'max':100},'土壤水分','Water demand column is percent per stage, not a per-second rate.')
 rule('preferred_season_growth_time_multiplier',0.5,'生长时间','Night/darkness may pause growth; no exact clock simulation in v0.1.')
 rule('harvest_stress_bands',[{'min':0,'max':6,'produce':1,'specific_seeds':2},{'min':7,'max':11,'produce':1,'specific_seeds':1},{'min':12,'max':28,'produce':1,'specific_seeds':0}],'生长阶段与收获','For ordinary mature plants. Giant eligibility is evaluated separately, not inferred from the first band.')
 rule('harvest_rot_delay_game_days',{'ordinary':4,'giant':6,'wormwood_planted_multiplier':1.5},'生长时间','Wiki-based. Exact growing-time and regrowth simulation deferred.')
 rule('tending',{'required_each_stage':True,'can_be_reset_by':['burning','fruit_fly_harassment']},'幸福','Talking, applicable music or friendly fruit fly; no instrument range dataset in v0.1.')
 rule('generic_seeds',{'default_preferred_seasons':['autumn','spring'],'giant_eligible':False},'生长时间','Later season preference follows the resulting plant. Use identified crop-specific seeds for giant plans.')
 out['issues']=[{'code':code,'details':details} for code,details in [
 ('build_unconfirmed','No confirmation the saved wiki reflects build 762172; target build is last user report.'),
 ('static_not_growth_simulation','Exact nutrient balance does not prove sufficient starting stock or synchronized consumption; no daily moisture/growth forecast.'),
 ('position_required','Total crop counts do not prove family proximity; balancing across different tiles does not share soil nutrients.'),
 ('ten_plant_boundary','Source says 10株以上; default nine, report exactly ten as unknown.'),
 ('provisional_plant_ids','Crop keys are raw-product ingredient IDs cross-linked to prior wiki data. Actual plant/seed prefabs remain NULL; image names are localization hints.'),
 ('unverified_art_rights','Image references/hashes only. No game artwork bundled.'),
 ('scope','No fertilizer-item database, skill tree effects, exact growth clocks, automatic optimal layout solver or season-transition forecast in v0.1.')]]
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print('Extracted',len(rows),'plants,',len(out['assets']),'assets,',len(out['mechanics']),'mechanics; revision',revision)
if __name__=='__main__':main()
