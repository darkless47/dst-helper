"""Host adapter for the supplied wiki planner; curated JSON remains authoritative."""
from copy import deepcopy
import json
from pathlib import Path

from DST_Farming_v0_1.scripts import planner_core as core

DATA_ROOT = Path(__file__).resolve().parents[1] / 'DST_Farming_v0_1'
STRESS_KEYS = ('nutrients', 'moisture', 'debris', 'season', 'family', 'overcrowding', 'tending')
CARE_KEYS = ('water', 'tending', 'soil', 'debris', 'seeds', 'history')
FLAGS = ('specific_seed', 'never_rotted', 'not_forced_ripened')


class FarmingPlanner:
    def __init__(self):
        self.data = core.load_data()
        self.crops = core.crop_index(self.data)
        self.plants = {p['plant_id']: p for p in self.data['plants']}
        self.examples = json.loads((DATA_ROOT / 'data/example_layouts.json').read_text(encoding='utf-8'))
        # Calculate the bounded family once; filtering and scaling never broaden it.
        self.candidates = core.ratios(self.crops)

    def defaults(self):
        return dict(schema_version=1, dataset_version=self.data['metadata']['dataset_version'],
                    seasons=[], available=list(self.crops), inventory={}, scale=1,
                    selected_counts=None, tile_count=2, placements=[], care={}, stages=[{} for _ in range(4)],
                    specific_seed=None, never_rotted=None, not_forced_ripened=None)

    def validate(self, value):
        if type(value) is not dict or set(value) != set(self.defaults()):
            raise ValueError('规划字段不完整，请重置当前浏览器的规划。')
        if type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise ValueError('不支持此规划格式版本。')
        if value['dataset_version'] != self.data['metadata']['dataset_version']:
            raise ValueError('规划的数据版本与当前数据不同，请重新规划。')
        for key, allowed in (('seasons', core.SEASONS), ('available', self.crops)):
            rows = value[key]
            if type(rows) is not list or any(type(x) is not str or x not in allowed for x in rows) or len(set(rows)) != len(rows):
                raise ValueError('季节或可用种子选择无效。')
        inventory = value['inventory']
        if type(inventory) is not dict or any(k not in self.crops or type(n) is not int or not 0 <= n <= 1000000 for k, n in inventory.items()):
            raise ValueError('种子库存须为 0–1000000 的整数；留空表示不限制。')
        if type(value['scale']) is not int or not 1 <= value['scale'] <= 1000000:
            raise ValueError('倍数须为 1–1000000 的整数。')
        counts = value['selected_counts']
        if counts is not None and (type(counts) is not dict or any(type(n) is not int for n in counts.values()) or counts not in [r['counts'] for r in self.candidates]):
            raise ValueError('请选择一个已收录的最简配比。')
        if type(value['tile_count']) is not int or value['tile_count'] not in (1, 2, 4):
            raise ValueError('布局支持一块、两块或 2×2 四块田。')
        width = 1 if value['tile_count'] == 1 else 2
        height = 2 if value['tile_count'] == 4 else 1
        placements = value['placements']
        if type(placements) is not list or len(placements) > value['tile_count'] * 9:
            raise ValueError('种植数量超过当前田地的位置数（每块田 9 格）。')
        occupied = set()
        for p in placements:
            if type(p) is not dict or set(p) != {'plant_id', 'tile_x', 'tile_y', 'row', 'col'}:
                raise ValueError('种植位置字段无效。')
            if type(p['plant_id']) is not str or p['plant_id'] not in self.plants:
                raise ValueError('未知植物。')
            slot = tuple(p[k] for k in ('tile_x', 'tile_y', 'row', 'col'))
            if any(type(n) is not int for n in slot) or not (0 <= slot[0] < width and 0 <= slot[1] < height and 0 <= slot[2] < 3 and 0 <= slot[3] < 3):
                raise ValueError('种植位置超出当前田地。')
            if slot in occupied:
                raise ValueError('种植位置重复。')
            occupied.add(slot)
        care = value['care']
        if type(care) is not dict or set(care) - set(CARE_KEYS) or any(v is not None and type(v) is not bool for v in care.values()):
            raise ValueError('养护记录须为已满足、未满足或未知。')
        if type(value['stages']) is not list:
            raise ValueError('阶段记录无效。')
        core.stress_bounds(value['stages'], **{k: value[k] for k in FLAGS})
        normalized = deepcopy(value)
        normalized['stages'].extend({} for _ in range(4 - len(normalized['stages'])))
        return normalized

    def overview(self):
        keys = ('plant_id', 'kind', 'product_ingredient_id', 'name_zh', 'name_en_hint',
                'preferred_seasons', 'nutrient_delta_per_stage', 'water_source_text', 'random_seed_percent')
        return dict(metadata=self.data['metadata'], plants=[{k: p[k] for k in keys} for p in self.data['plants']],
                    examples=[{k: ex[k] for k in ('id', 'label_zh', 'seasons', 'ratio', 'placements')} for ex in self.examples],
                    defaults=self.defaults())

    def analyze(self, value):
        state = self.validate(value)
        eligible = core.eligible_crops(self.crops, state['seasons'], state['available'])
        inventory, scale = state['inventory'], state['scale']
        answers = []
        for r in self.candidates:
            counts = r['counts']
            if not set(counts) <= set(eligible):
                continue
            # Blank is unconstrained, unlike the handoff engine's complete-inventory API.
            caps = [inventory[k] // n for k, n in counts.items() if k in inventory]
            cap = min(caps) if caps else None
            if cap is not None and cap < scale:
                continue
            answers.append(dict(r, max_inventory_scale=cap, scaled=core.scaled_requirements(counts, scale),
                                matching_seasons=[s for s in self.data['metadata']['season_order']
                                                  if all(self.crops[k]['preferred_seasons'][s] for k in counts)]))
        layout = core.analyze_layout(state['placements'], self.crops, state['seasons'])
        for tile in layout['tiles']:
            tile['counts'] = {k: sum(p['plant_id'] == k and [p['tile_x'], p['tile_y']] == tile['tile'] for p in state['placements'])
                              for k in dict.fromkeys(p['plant_id'] for p in state['placements'] if [p['tile_x'], p['tile_y']] == tile['tile'])}
        selected = next((r for r in answers if r['counts'] == state['selected_counts']), None)
        required = selected['scaled']['seed_counts'] if selected else None
        actual = {k: sum(p['plant_id'] == k for p in state['placements']) for k in self.plants}
        matches = required is not None and all(actual[k] == required.get(k, 0) for k in self.plants)
        return dict(eligible=list(eligible), ratios=answers, layout=layout, layout_matches_selected=matches,
                    stress=core.stress_bounds(state['stages'], **{k: state[k] for k in FLAGS}))
