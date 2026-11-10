import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from planner_core import crop_index,eligible_crops,ratios,nutrient_net,scaled_requirements,analyze_layout,stress_bounds,grid_position,load_data
from build_database import ROOT,build

def layout(tile0,counts):
 items=[k for k,n in counts.items() for _ in range(n)]
 return [{'plant_id':id,'tile_x':tile0,'tile_y':0,'row':i//3,'col':i%3} for i,id in enumerate(items)]
class PlannerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=crop_index()
 def test_01_counts(self):
  d=load_data();self.assertEqual(len(self.c),14);self.assertEqual(sum(p['kind']=='weed' for p in d['plants']),4)
 def test_02_green_season_not_probability(self):
  self.assertFalse(self.c['carrot']['preferred_seasons']['summer']);self.assertGreater(self.c['carrot']['random_seed_percent']['summer'],0)
 def test_03_empty_seasons_no_filter(self):self.assertEqual(len(eligible_crops(self.c)),14)
 def test_04_all_seasons_intersection(self):self.assertEqual(set(eligible_crops(self.c,['spring','summer','autumn','winter'])),{'garlic'})
 def test_05_winter(self):self.assertEqual(set(eligible_crops(self.c,['winter'])),{'carrot','potato','asparagus','pumpkin','garlic'})
 def test_06_empty_available(self):self.assertEqual(ratios(self.c,available=[]),[])
 def test_07_potato_tomato(self):self.assertEqual(nutrient_net({'potato':1,'tomato':1},self.c),[0,0,0])
 def test_08_dragonfruit_tomato(self):self.assertEqual(nutrient_net({'dragonfruit':1,'tomato':2},self.c),[0,0,0])
 def test_09_wrong_ratio(self):self.assertNotEqual(nutrient_net({'dragonfruit':2,'tomato':1},self.c),[0,0,0])
 def test_10_coefficient_dedup(self):
  r=ratios(self.c,available=['potato','tomato']);self.assertEqual(len(r),1);self.assertEqual(r[0]['counts'],{'potato':1,'tomato':1})
 def test_11_offseason_pair_excluded(self):self.assertEqual(ratios(self.c,['winter'],['tomato','dragonfruit']),[])
 def test_12_inventory(self):
  r=ratios(self.c,available=['potato','tomato'],seed_inventory={'potato':4,'tomato':7});self.assertEqual(r[0]['max_inventory_scale'],4)
 def test_13_zero_inventory(self):self.assertEqual(ratios(self.c,available=['potato','tomato'],seed_inventory={'potato':4,'tomato':0}),[])
 def test_14_scale(self):
  s=scaled_requirements({'dragonfruit':1,'tomato':2},4);self.assertEqual(s['total_plants'],12);self.assertTrue(s['all_global_counts_at_least_four']);self.assertTrue(s['layout_required'])
 def test_15_no_fractional_counts(self):
  with self.assertRaises(ValueError):nutrient_net({'potato':1.5},self.c)
 def test_16_single_tile_eight(self):
  a=analyze_layout(layout(0,{'potato':4,'tomato':4}),self.c,['autumn']);self.assertTrue(a['all_tiles_nutrient_balanced']);self.assertTrue(a['all_crop_family_checks_pass']);self.assertFalse(a['guaranteed_giant'])
 def test_17_six_plus_three_family_fails(self):
  a=analyze_layout(layout(0,{'tomato':6,'dragonfruit':3}),self.c,['summer']);self.assertTrue(a['all_tiles_nutrient_balanced']);self.assertFalse(a['all_crop_family_checks_pass'])
 def test_18_adjacent_tiles_family_passes(self):
  p=[]
  for tile in [0,1]:
   for row in range(3):
    for col in range(3):
     minority=(col==2 if tile==0 else col==0)
     p.append(dict(plant_id='dragonfruit' if minority else 'tomato',tile_x=tile,tile_y=0,row=row,col=col))
  a=analyze_layout(p,self.c,['summer']);self.assertTrue(a['all_tiles_nutrient_balanced']);self.assertTrue(a['all_crop_family_checks_pass'])
 def test_19_no_cross_tile_fertilizer_sharing(self):
  p=layout(0,{'tomato':4})+layout(1,{'potato':4});a=analyze_layout(p,self.c)
  self.assertEqual(nutrient_net({'tomato':4,'potato':4},self.c),[0,0,0]);self.assertFalse(a['all_tiles_nutrient_balanced'])
 def test_20_empty_layout_not_valid(self):self.assertFalse(analyze_layout([],self.c)['all_tiles_nutrient_balanced'])
 def test_21_duplicate_slot_rejected(self):
  p=layout(0,{'tomato':4})
  with self.assertRaises(ValueError):analyze_layout(p+[p[0]],self.c)
 def test_22_weed_hazard(self):
  p=layout(0,{'tomato':4,'huiji:必忘我':1});a=analyze_layout(p,self.c);self.assertTrue(all(x['known_weed_debris_status']=='fail' for x in a['plants']))
 def test_23_unknown_history(self):self.assertEqual(stress_bounds([])['stress_max'],28);self.assertEqual(stress_bounds([])['giant_eligibility'],'unknown')
 def test_24_known_stages(self):
  keys=load_data()['mechanics'][0]['value'];stages=[dict.fromkeys(keys,False) for _ in range(4)]
  self.assertEqual(stress_bounds(stages,True,True,True)['giant_eligibility'],'eligible_under_wiki_rules')
  stages[0]['tending']=True;self.assertEqual(stress_bounds(stages,True,True,True)['giant_eligibility'],'eligible_under_wiki_rules')
  stages[1]['tending']=True;self.assertEqual(stress_bounds(stages,True,True,True)['giant_eligibility'],'ineligible')
 def test_25_specific_seed_required(self):self.assertEqual(stress_bounds([],False,True,True)['giant_eligibility'],'ineligible')
 def test_26_all_ratios_exact_and_primitive(self):
  import math
  r=ratios(self.c);self.assertGreater(len(r),0)
  for a in r:
   self.assertEqual(nutrient_net(a['counts'],self.c),[0,0,0]);self.assertEqual(math.gcd(*a['counts'].values()),1)
 def test_27_database_rebuild(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=build(Path(tmp)/'test.sqlite');db=sqlite3.connect(path)
   self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('pragma foreign_key_check').fetchall(),[])
   self.assertEqual(db.execute('select count(*) from farming_plants').fetchone()[0],18)
   self.assertEqual(db.execute('select count(*) from farming_seasons').fetchone()[0],72)
   self.assertTrue(json.loads(db.execute("select value_json from farming_metadata where key='planner_enabled'").fetchone()[0]));db.close()
 def test_28_data_contract(self):
  d=load_data()
  for p in d['plants']:
   self.assertTrue(p['name_zh']);self.assertEqual(len(p['source_cells']),12)
   self.assertIsNone(p['plant_prefab_id']);self.assertIsNone(p['seed_prefab_id'])
   if p['kind']=='crop':self.assertEqual(sum(p['nutrient_delta_per_stage']),0)
 def test_29_positions(self):self.assertAlmostEqual(grid_position(0,0,0,0)[0],2/3)
 def test_30_invalid_season(self):
  with self.assertRaises(ValueError):eligible_crops(self.c,['monsoon'])
if __name__=='__main__':unittest.main()
