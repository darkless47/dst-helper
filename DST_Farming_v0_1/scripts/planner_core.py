"""Original reference implementation of static wiki-based planning.
No third-party app source copied. No exact temporal growth simulation.
All nutrient vectors are ordered growth_formula, compost, manure, per stage.
"""
import json,math
from collections import Counter,defaultdict
from itertools import combinations,product
from pathlib import Path
SEASONS={'autumn','winter','spring','summer'}
def load_data():return json.loads((Path(__file__).resolve().parents[1]/'data/farming.json').read_text(encoding='utf-8'))
def crop_index(data=None):return {p['plant_id']:p for p in (data or load_data())['plants'] if p['kind']=='crop'}
def eligible_crops(crops,seasons=(),available=None):
 seasons=set(seasons)
 if not seasons<=SEASONS:raise ValueError('Unknown season')
 if available is not None:
  available=set(available)
  if not available<=set(crops):raise ValueError('Unknown available crop')
 return {id:c for id,c in crops.items() if (available is None or id in available) and all(c['preferred_seasons'][s] for s in seasons)}
def nutrient_net(counts,crops):
 if not counts:raise ValueError('Empty plan')
 for id,n in counts.items():
  if id not in crops or type(n) is not int or n<0:raise ValueError('Invalid crop/count')
 return [sum(n*crops[id]['nutrient_delta_per_stage'][j] for id,n in counts.items()) for j in range(3)]
def ratios(crops,seasons=(),available=None,max_species=3,max_coefficient=2,seed_inventory=None):
 if not 2<=max_species<=4 or not 1<=max_coefficient<=8:raise ValueError('Unsupported search bounds')
 selected=eligible_crops(crops,seasons,available);answers=[]
 if seed_inventory is not None:
  for id,n in seed_inventory.items():
   if id not in crops or type(n)is not int or n<0:raise ValueError('Invalid seed inventory')
 for k in range(2,max_species+1):
  for ids in combinations(sorted(selected),k):
   for coeff in product(range(1,max_coefficient+1),repeat=k):
    if math.gcd(*coeff)!=1:continue
    counts=dict(zip(ids,coeff));net=nutrient_net(counts,crops)
    if any(net):continue
    max_scale=None if seed_inventory is None else min(seed_inventory.get(id,0)//n for id,n in counts.items())
    if max_scale==0:continue
    answers.append({'counts':counts,'net_per_stage':net,'ratio_total':sum(coeff),'max_inventory_scale':max_scale,'status':'nutrient_balanced_only','spatially_validated':False})
 return sorted(answers,key=lambda x:(len(x['counts']),x['ratio_total'],tuple(x['counts'].items())))
def scaled_requirements(counts,scale):
 if type(scale)is not int or scale<1:raise ValueError('Scale must be a positive integer')
 if not counts or any(type(v)is not int or v<1 for v in counts.values()):raise ValueError('Positive ratio counts required')
 need={k:v*scale for k,v in counts.items()}
 return {'seed_counts':need,'total_plants':sum(need.values()),'area_lower_bound_9_slots':math.ceil(sum(need.values())/9),'all_global_counts_at_least_four':all(n>=4 for n in need.values()),'layout_required':True}
def grid_position(tile_x,tile_y,row,col):
 if any(type(x)is not int for x in [tile_x,tile_y,row,col]) or not(0<=row<3 and 0<=col<3):raise ValueError('Invalid grid slot')
 # Actual game-distance units; a tile side is 4. Nine slots are a UI convention.
 return 4*tile_x+(col+.5)*4/3,4*tile_y+(row+.5)*4/3

def analyze_layout(plants,crops,seasons=()):
 """plants: {plant_id,tile_x,tile_y,row,col}. Include weeds; empty slots omitted.
 Unknown hazards, water, tending and starting soil are not inferred as satisfied.
 """
 all_plants={p['plant_id']:p for p in load_data()['plants']};all_plants.update(crops)
 if not set(seasons)<=SEASONS:raise ValueError('Unknown season')
 occupied=set();tiles=defaultdict(list);positions=[]
 for p in plants:
  if p['plant_id'] not in all_plants:raise ValueError('Unknown plant')
  slot=tuple(p[k] for k in ['tile_x','tile_y','row','col'])
  if slot in occupied:raise ValueError('Duplicate occupied slot')
  occupied.add(slot);xy=grid_position(*slot);positions.append(xy);tiles[slot[:2]].append(p)
 tile_results=[]
 for tile,items in sorted(tiles.items(),key=lambda item:(item[0][1],item[0][0])):
  counts=Counter(p['plant_id'] for p in items)
  net=nutrient_net(counts,all_plants)
  tile_results.append({'tile':list(tile),'plant_count':len(items),'net_per_stage':net,'nutrient_balanced':not any(net),'external_nutrient_deficit_per_stage':[max(0,-n) for n in net],'overcrowding_status':'pass' if len(items)<=9 else 'unknown' if len(items)==10 else 'fail'})
 per_plant=[]
 for i,p in enumerate(plants):
  c=all_plants[p['plant_id']]
  if c['kind']!='crop':continue
  inside=0;boundary=0;debris=False;debris_boundary=False
  for j,q in enumerate(plants):
   dist=math.dist(positions[i],positions[j]);same=q['plant_id']==p['plant_id']
   if same:
    # Grid coordinates in thirds of a game unit are exact integers. Include
    # the radius boundary, as confirmed for contiguous fields by the user.
    dx=12*(p['tile_x']-q['tile_x'])+4*(p['col']-q['col'])
    dy=12*(p['tile_y']-q['tile_y'])+4*(p['row']-q['row'])
    distance_squared=dx*dx+dy*dy
    if distance_squared==144:boundary+=1
    elif distance_squared<144:inside+=1
   if all_plants[q['plant_id']]['kind']=='weed':
    if math.isclose(dist,6,abs_tol=1e-9):debris_boundary=True
    elif dist<6:debris=True
  family='pass' if inside+boundary>=4 else 'fail'
  per_plant.append({'index':i,'plant_id':p['plant_id'],'same_kind_strictly_inside_radius':inside,'same_kind_on_boundary':boundary,'same_kind_within_radius':inside+boundary,'family_status':family,'season_status':'not_selected' if not seasons else 'pass' if all(c['preferred_seasons'][s] for s in seasons) else 'fail','known_weed_debris_status':'fail' if debris else 'unknown' if debris_boundary else 'no_known_weed_in_plan'})
 return {'tiles':tile_results,'plants':per_plant,'all_tiles_nutrient_balanced':bool(tiles) and all(t['nutrient_balanced'] for t in tile_results),'all_crop_family_checks_pass':bool(per_plant) and all(p['family_status']=='pass' for p in per_plant),'guaranteed_giant':False,'other_conditions':'Water/tending, initial soil, outside-plan debris, crop-specific seeds, actual seasons during growth and plant history still require management.'}

def stress_bounds(stages,specific_seed=None,never_rotted=None,not_forced_ripened=None):
 """Per stage/category input is True=stress occurred, False=no stress, None=unknown.
 Missing stages/categories remain unknown. Not a predictor from ratio counts.
 """
 keys=['nutrients','moisture','debris','season','family','overcrowding','tending']
 if len(stages)>4:raise ValueError('At most four checked transitions')
 if any(type(x)is not dict for x in stages):raise ValueError('Stage must be a mapping')
 low=high=0
 for i in range(4):
  stage=stages[i] if i<len(stages) else {}
  if not set(stage)<=set(keys):raise ValueError('Unknown stress source')
  for k in keys:
   v=stage.get(k)
   if v is not None and type(v)is not bool:raise ValueError('Stress state must be bool or None')
   if v is True:low+=1;high+=1
   elif v is None:high+=1
 flags=[specific_seed,never_rotted,not_forced_ripened]
 if any(v is not None and type(v)is not bool for v in flags):raise ValueError('Eligibility flags must be bool or None')
 status='ineligible' if any(v is False for v in flags) or low>1 else 'eligible_under_wiki_rules' if all(v is True for v in flags) and low==high and high<=1 else 'unknown'
 return {'stress_min':low,'stress_max':high,'giant_eligibility':status,'basis':'supplied stage records and saved wiki rules; not game-build verification'}
if __name__=='__main__':
 c=crop_index();r=ratios(c,seasons=['autumn']);print(json.dumps(r,ensure_ascii=False,indent=2))
