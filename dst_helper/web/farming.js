'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const seasons = { autumn: '秋', winter: '冬', spring: '春', summer: '夏' };
  const stressNames = { nutrients: '养分', moisture: '水分', debris: '杂物', season: '季节', family: '家族', overcrowding: '拥挤', tending: '照料' };
  const flags = { specific_seed: '使用作物专属种子', never_rotted: '没有腐烂 / 再生长历史', not_forced_ripened: '没有被强制催熟' };
  const careItems = {
    water: ['水分', '每阶段至少 10% 的时间，土壤湿度 >0；不是湿度保持在 10 以上。'],
    tending: ['照料', '每个生长阶段都需要照料。'],
    soil: ['起始养分', '每块田分别管理三种养分；零净变化不保证生长时有足够存量。'],
    debris: ['周围杂物', '检查 6 单位内的杂草、腐烂作物及农田杂物；布局看不到外部危害。'],
    seeds: ['作物专属种子', '巨大作物需要对应作物的种子。'],
    history: ['生长历史', '无腐烂后再生长，且没有被强制催熟。']
  };
  let data, plan, version, result, timer, pending = false, busy = false, blocked = false, seq = 0, limit = 12;
  let resetting = false, loading = false, importing = false;
  const resetDialog = $('reset-plan-dialog');
  const RATIO_LAYOUT_KEY = 'dst-helper.farming-ratio-layout';
  let ratioLayout = 'cards';
  try { if (localStorage.getItem(RATIO_LAYOUT_KEY) === 'table') ratioLayout = 'table'; } catch { /* The view still works without browser storage. */ }
  const crops = new Map(), plants = new Map();

  function node(tag, attrs = {}, children = []) {
    const item = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'text') item.textContent = value;
      else if (key === 'class') item.className = value;
      else if (key.startsWith('on')) item.addEventListener(key.slice(2), value);
      else item.setAttribute(key, value);
    }
    item.append(...children);
    return item;
  }
  const text = (tag, value, cls = '') => node(tag, { text: value, class: cls });
  const button = (label, click) => node('button', { type: 'button', class: 'secondary', text: label, onclick: click });
  const clone = value => JSON.parse(JSON.stringify(value));
  const name = id => plants.get(id)?.name_zh || id;
  const signed = n => n > 0 ? '+' + n : String(n);
  const vector = net => net.map(signed).join(' / ');
  const countsText = counts => Object.entries(counts).map(([id, n]) => name(id) + ' × ' + n).join(' + ');
  const sameCounts = (a, b) => a && b && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => a[k] === b[k]);
  const preferred = crop => plan.seasons.every(s => crop.preferred_seasons[s]);
  const fieldNumber = (x, y) => y * 2 + x + 1;
  const fitsFields = (p, count) => p.tile_x < (count === 1 ? 1 : 2) && p.tile_y < (count === 4 ? 2 : 1);

  function cropCounts(counts, label) {
    return node('dl', { class: 'ratio-crops', 'aria-label': label }, Object.entries(counts).map(([id, n]) =>
      node('div', { class: 'ratio-crop-row' }, [text('dt', name(id)), text('dd', n)])));
  }
  function renderRatioSwitch() {
    document.querySelectorAll('[data-ratio-layout]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.ratioLayout === ratioLayout)));
  }

  function error(message) {
    $('farm-error').hidden = !message;
    $('farm-error').textContent = message || '';
  }
  async function api(path, value) {
    const response = await fetch(path, value === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value)
    });
    const body = await response.json();
    if (!response.ok) {
      const issue = new Error(body.error || '请求失败，请重试。');
      issue.status = response.status;
      throw issue;
    }
    return body;
  }
  function unknownCare() {
    plan.care = {};
    plan.stages = [{}, {}, {}, {}];
    for (const k of Object.keys(flags)) plan[k] = null;
  }
  function changed({ controls = false, layout = false, care = false } = {}) {
    seq++;
    limit = 12;
    pending = true;
    error('');
    $('ratio-count').textContent = '计算中…';
    $('ratio-results').setAttribute('aria-busy', 'true');
    if (controls) renderControls();
    if (layout) renderGrid();
    if (care) renderCare();
    if (!blocked) $('save-status').textContent = '有更改，正在计算并保存…';
    clearTimeout(timer);
    timer = setTimeout(work, 120);
  }
  async function work() {
    if (busy || !plan || resetDialog.open || resetting) return;
    busy = true;
    try {
      while (pending && !resetDialog.open && !resetting) {
        pending = false;
        const captured = seq, draft = clone(plan);
        let analysis;
        try { analysis = await api('/api/farming/analyze', draft); }
        catch (issue) {
          if (captured !== seq) continue;
          throw issue;
        }
        if (captured !== seq) continue;
        result = analysis;
        renderResults();
        renderReport();
        renderStress();
        $('ratio-results').setAttribute('aria-busy', 'false');
        if (blocked) continue;
        try {
          const saved = await api('/api/farming/preferences', { expected_version: version, state: draft });
          version = saved.version;
          if (captured === seq) $('save-status').textContent = '已自动保存 · 规划版本 ' + version;
        } catch (issue) {
          if (issue.status === 409) blocked = true;
          $('save-status').textContent = '尚未保存：' + issue.message;
          error(issue.message + ' 当前草稿仍可导出。');
        }
      }
    } catch (issue) {
      result = null;
      $('ratio-results').replaceChildren(text('p', '当前条件未能完成计算，请保存 / 重试。', 'farm-empty'));
      $('ratio-count').textContent = '计算失败';
      $('layout-report').replaceChildren(text('p', '布局检查未完成。', 'status-unknown'));
      $('plant-report').replaceChildren();
      $('stress-output').textContent = '阶段记录尚未完成检查。';
      error(issue.message);
      $('save-status').textContent = '尚未保存；可导出当前草稿后重试。';
    } finally {
      busy = false;
      $('ratio-results').setAttribute('aria-busy', 'false');
      if (pending && !resetDialog.open && !resetting) work();
    }
  }

  function renderControls() {
    for (const input of $('season-checkboxes').querySelectorAll('input')) input.checked = plan.seasons.includes(input.value);
    for (const b of $('season-presets').querySelectorAll('button')) {
      const subset = b.dataset.seasons ? b.dataset.seasons.split(',') : [];
      b.setAttribute('aria-pressed', String(subset.length === plan.seasons.length && subset.every(s => plan.seasons.includes(s))));
    }
    let visible = 0;
    for (const [id, crop] of crops) {
      const row = $('crop-' + id);
      row.hidden = !preferred(crop);
      if (!row.hidden) visible++;
      row.querySelector('input[type=checkbox]').checked = plan.available.includes(id);
      row.querySelector('input[type=number]').value = plan.inventory[id] ?? '';
    }
    $('crop-count').textContent = visible + ' / 14 种作物适宜所选季节';
    $('ratio-scale').value = plan.scale;
    $('tile-count').value = plan.tile_count;
  }
  function initControls() {
    const presets = [[], ['autumn'], ['autumn', 'winter'], ['winter'], ['winter', 'spring'], ['spring'], ['spring', 'summer'], ['summer'], ['summer', 'autumn']];
    $('season-presets').replaceChildren(...presets.map(list => {
      const b = button(list.length ? list.map(s => seasons[s]).join(' + ') : '清除季节筛选', () => {
        plan.seasons = [...list]; changed({ controls: true });
      });
      b.dataset.seasons = list.join(',');
      return b;
    }));
    $('season-checkboxes').replaceChildren(...Object.entries(seasons).map(([id, label]) => {
      const input = node('input', { type: 'checkbox', value: id, onchange: () => {
        plan.seasons = input.checked ? [...plan.seasons, id] : plan.seasons.filter(s => s !== id);
        changed({ controls: true });
      } });
      return node('label', {}, [input, document.createTextNode(label)]);
    }));
    $('crop-rows').replaceChildren(...[...crops].map(([id, crop]) => {
      const available = node('input', { type: 'checkbox', 'aria-label': name(id) + '种子可用', onchange: () => {
        plan.available = available.checked ? [...plan.available, id] : plan.available.filter(k => k !== id);
        changed();
      } });
      const stock = node('input', { type: 'number', class: 'farm-number', min: '0', max: '1000000', step: '1', placeholder: '不限', 'aria-label': name(id) + '种子库存', onchange: () => {
        if (!stock.checkValidity()) { stock.reportValidity(); return; }
        if (stock.value === '') delete plan.inventory[id];
        else plan.inventory[id] = Number(stock.value);
        changed();
      } });
      const cells = [node('td', {}, [available]), node('th', { scope: 'row' }, [node('a', { class: 'crop-link', href: '/cooking?ingredient=' + encodeURIComponent(crop.product_ingredient_id), text: name(id) + ' ↗' }), text('span', id, 'crop-id')]),
        ...Object.keys(seasons).map(s => text('td', crop.preferred_seasons[s] ? '✓' : '—', crop.preferred_seasons[s] ? 'season-yes' : 'season-no')),
        ...crop.nutrient_delta_per_stage.map(n => text('td', signed(n), n < 0 ? 'nutrient-negative' : 'nutrient-positive')), node('td', {}, [stock])];
      return node('tr', { id: 'crop-' + id }, cells);
    }));
    $('crop-water').replaceChildren(text('p', '维基耗水原文（每阶段百分比，不是每秒或每天）：'), text('p', [...crops.values()].map(c => c.name_zh + ' ' + c.water_source_text).join('；')));
    $('weed-notes').textContent = [...plants.values()].filter(p => p.kind === 'weed').map(p => p.name_zh).join('、') + '：布局中已知的杂草会触发附近作物的杂物提示。';
    const brush = $('crop-brush');
    brush.replaceChildren(node('option', { value: '', text: '擦除 / 空格' }));
    for (const [kind, label] of [['crop', '作物'], ['weed', '杂草（危害检查）']]) {
      brush.append(node('optgroup', { label }, [...plants.values()].filter(p => p.kind === kind).map(p => node('option', { value: p.plant_id, text: p.name_zh }))));
    }
    brush.value = 'potato';
    $('layout-examples').replaceChildren(...data.examples.map(ex => button('载入示例：' + ex.label_zh, () => {
      plan.placements = clone(ex.placements);
      plan.seasons = [...ex.seasons];
      plan.tile_count = ex.placements.some(p => p.tile_x === 1) ? 2 : 1;
      plan.selected_counts = clone(ex.ratio);
      plan.scale = ex.id === 'single_tile_potato_tomato' ? 4 : 6;
      unknownCare();
      changed({ controls: true, layout: true, care: true });
    })));
    renderControls();
  }
  function renderResults() {
    renderRatioSwitch();
    $('ratio-count').textContent = result.ratios.length + ' 个配平组合';
    const table = ratioLayout === 'table';
    const list = table ? [...result.ratios] : result.ratios.slice(0, limit);
    const selected = result.ratios.find(r => sameCounts(r.counts, plan.selected_counts));
    if (selected && !list.includes(selected)) list.unshift(selected);
    const entries = list.map(r => {
      const chosen = sameCounts(r.counts, plan.selected_counts), scaled = r.scaled;
      const checked = chosen && result.layout_matches_selected;
      const family = scaled.all_global_counts_at_least_four ? '全局每种 ≥4 株；家族距离仍待核对' : '全局有作物不足 4 株，家族数量不足';
      const choose = button(table ? (chosen ? '已选配比 ↓' : '选择配比 ↓') : (chosen ? '已选配比 · 查看布局 ↓' : '选择配比，检查布局 ↓'), () => {
        plan.selected_counts = clone(r.counts);
        $('crop-brush').value = Object.keys(r.counts)[0];
        changed();
        $('layout-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      choose.setAttribute('aria-pressed', String(chosen));
      choose.setAttribute('aria-label', countsText(r.counts) + '，' + (chosen ? '已选配比，查看布局' : '选择配比，检查布局'));
      const layout = checked ? '当前布局用种一致；几何检查见下方（不保证通过）。' : '此配比未由当前布局验证；请手动摆放并核对。';
      const matchingSeasons = r.matching_seasons.map(s => seasons[s]).join('、') || '无共同适宜季节';
      if (table) return node('tr', { class: chosen ? 'selected' : '' }, [
        node('th', { scope: 'row' }, [cropCounts(r.counts, '最简配比')]),
        text('td', matchingSeasons), text('td', vector(r.net_per_stage)),
        node('td', {}, [cropCounts(scaled.seed_counts, plan.scale + ' 倍用种')]),
        node('td', {}, [text('div', scaled.total_plants + ' 株'), text('div', '≥ ' + scaled.area_lower_bound_9_slots + ' 块田')]),
        text('td', r.max_inventory_scale ?? '不限'),
        node('td', { class: 'ratio-table-checks' }, [text('p', family, 'muted'), text('p', layout, checked ? 'status-pass' : 'status-unknown')]),
        node('td', {}, [choose])
      ]);
      return node('article', { class: 'ratio-card' + (chosen ? ' selected' : '') }, [
        text('span', '养分配平 / Nutrient-balanced', 'tag'), text('h3', countsText(r.counts), 'sr-only'), cropCounts(r.counts, '最简配比'),
        text('p', '每阶段净变化（催长剂 / 堆肥 / 粪肥）：' + vector(r.net_per_stage)),
        text('p', '共同适宜季节：' + matchingSeasons),
        text('p', plan.scale + ' 倍用种：'), cropCounts(scaled.seed_counts, plan.scale + ' 倍用种'),
        text('p', '共 ' + scaled.total_plants + ' 株 · 面积下界 ' + scaled.area_lower_bound_9_slots + ' 块田（非摆放证明）'),
        text('p', '库存倍数上限：' + (r.max_inventory_scale ?? '不限')), text('p', family, 'muted'),
        text('p', layout, checked ? 'status-pass' : 'status-unknown'), choose
      ]);
    });
    const output = $('ratio-results');
    output.className = table && entries.length ? 'ratio-table-wrap farm-table-scroll' : 'ratio-grid';
    if (!entries.length) entries.push(node('div', { class: 'farm-empty' }, [
      text('h3', '当前条件下没有配平组合'),
      text('p', '请检查季节交集、可用种子、库存与倍数。默认仅搜索 2–3 种作物、最简系数 1 或 2；不会自动加入未勾选或不适季作物。'),
      button('清除季节筛选', () => { plan.seasons = []; changed({ controls: true }); }),
      document.createTextNode(' '), button('全选可用种子', () => { plan.available = [...crops.keys()]; changed({ controls: true }); })
    ]));
    if (table && result.ratios.length) output.replaceChildren(node('table', { class: 'farm-table ratio-table' }, [
      text('caption', '所有组合均养分配平。养分按催长剂 / 堆肥 / 粪肥顺序记录；面积仅是下界，家族与实际布局仍需检查。', 'sr-only'),
      node('thead', {}, [node('tr', {}, ['最简配比', '共同适宜季节', '每阶段净变化', plan.scale + ' 倍用种', '总株数 / 面积下界', '库存倍数上限', '家族 / 布局检查', '操作'].map(label => node('th', { scope: 'col', text: label })))]),
      node('tbody', {}, entries)
    ]));
    else output.replaceChildren(...entries);
    $('more-ratios').hidden = table || limit >= result.ratios.length;
  }
  function renderGrid(focusSlot) {
    $('tile-grids').dataset.tiles = plan.tile_count;
    $('tile-grids').replaceChildren(...Array.from({ length: plan.tile_count }, (_, tile) => {
      const tileX = tile % 2, tileY = Math.floor(tile / 2);
      const slots = Array.from({ length: 9 }, (_, i) => {
        const row = Math.floor(i / 3), col = i % 3, key = `${tile}-${row}-${col}`;
        const p = plan.placements.find(p => p.tile_x === tileX && p.tile_y === tileY && p.row === row && p.col === col);
        const b = node('button', { id: 'slot-' + key, type: 'button', class: 'plant-slot' + (p ? (plants.get(p.plant_id).kind === 'weed' ? ' weed' : ' planted') : ''),
          'aria-label': `田${tile + 1} 第${row + 1}行 第${col + 1}列：${p ? name(p.plant_id) : '空位'}，点击使用画笔`, onclick: () => {
            const brush = $('crop-brush').value;
            if ((p?.plant_id || '') === brush) return;
            plan.placements = plan.placements.filter(p => !(p.tile_x === tileX && p.tile_y === tileY && p.row === row && p.col === col));
            if (brush) plan.placements.push({ plant_id: brush, tile_x: tileX, tile_y: tileY, row, col });
            unknownCare();
            changed({ care: true });
            renderGrid(key);
          } }, [text('span', p ? name(p.plant_id) : '＋ 空位'), text('small', `${row + 1} 行 · ${col + 1} 列`)]);
        return b;
      });
      return node('div', { class: 'tile-board' }, [text('h3', '田 ' + (tile + 1) + ' · (' + tileX + ', ' + tileY + ')'), node('div', { class: 'tile-grid', role: 'group', 'aria-label': '田' + (tile + 1) + '九宫格' }, slots)]);
    }));
    if (focusSlot) $('slot-' + focusSlot).focus({ preventScroll: true });
  }
  const statusLabel = value => ({ pass: '通过', fail: '未通过', unknown: '未知（距离临界）', not_selected: '未选季节', no_known_weed_in_plan: '图中无已知杂草；外部未知' }[value] || value);
  function renderReport() {
    const a = result.layout;
    const offSeason = a.plants.filter(p => p.season_status === 'fail').length;
    const weedsNearby = a.plants.filter(p => p.known_weed_debris_status === 'fail').length;
    const reports = a.tiles.map(t => node('div', { class: 'tile-report' }, [
      text('strong', '田 ' + fieldNumber(...t.tile) + ' · ' + t.plant_count + ' 株'), text('p', countsText(t.counts)),
      text('p', '养分净变化：' + vector(t.net_per_stage), t.nutrient_balanced ? 'status-pass' : 'status-fail'),
      text('p', '各类缺口（催长剂 / 堆肥 / 粪肥）：' + vector(t.external_nutrient_deficit_per_stage)),
      text('p', '拥挤检查：' + statusLabel(t.overcrowding_status))
    ]));
    const intro = !plan.placements.length ? '先放入作物，或载入一个示例。' :
      `每田养分：${a.all_tiles_nutrient_balanced ? '均配平' : '有田未配平'}；家族距离：${a.all_crop_family_checks_pass ? '所有作物通过' : '有未通过 / 未知项'}。`;
    const layoutPassed = a.all_tiles_nutrient_balanced && a.all_crop_family_checks_pass;
    $('layout-report').replaceChildren(text('p', intro, layoutPassed ? 'layout-success' : 'small'),
      text('p', `不适宜所选季节：${offSeason} 株；已知附近杂草危害：${weedsNearby} 株。未选季节、外部杂物和实际养护仍不能推断。`, offSeason || weedsNearby ? 'small status-fail' : 'small muted'),
      text('p', result.layout_matches_selected ? '布局用种与选中配比的当前倍数一致。养护条件仍需记录。' : '布局用种尚未对应一个当前有效的选中配比。布局始终独立检查，不会自动填入比例。', 'small muted'),
      node('div', { class: 'report-grid' }, reports), text('p', '养分只在各自田块内计算，邻田不能抵消亏损。家族可以跨田界；九个位置是本工具的默认布局，不是游戏的绝对种植上限。', 'small muted'));
    $('plant-report').replaceChildren(node('table', { class: 'farm-table' }, [
      node('thead', {}, [node('tr', {}, ['位置', '作物', '半径内同类（含自身及边界）', '其中边界同类', '家族', '季节', '已知杂草'].map(label => node('th', { scope: 'col', text: label })))]),
      node('tbody', {}, a.plants.map(p => {
        const slot = plan.placements[p.index];
        return node('tr', {}, [text('td', `田${fieldNumber(slot.tile_x, slot.tile_y)} / ${slot.row + 1}行${slot.col + 1}列`), text('td', name(p.plant_id)),
          text('td', p.same_kind_within_radius), text('td', p.same_kind_on_boundary),
          text('td', statusLabel(p.family_status), 'status-' + p.family_status), text('td', statusLabel(p.season_status), 'status-' + p.season_status), text('td', statusLabel(p.known_weed_debris_status), 'status-' + p.known_weed_debris_status)]);
      }))
    ]));
  }
  function triSelect(value, onChange, stress = false, label = '') {
    const select = node('select', { 'aria-label': label, onchange: () => { onChange(select.value === '' ? null : select.value === 'true'); changed(); } },
      [['', '未知 / 未记录'], ['false', stress ? '无压力 · 0' : '未满足'], ['true', stress ? '有压力 · 1' : '已满足']].map(([v, label]) => node('option', { value: v, text: label })));
    select.value = value == null ? '' : String(value);
    return select;
  }
  function renderCare() {
    $('care-checks').replaceChildren(...Object.entries(careItems).map(([key, [label, desc]]) => node('label', { class: 'care-item' }, [text('strong', label), text('small', desc), triSelect(plan.care[key], v => { plan.care[key] = v; }, false, label)])));
    $('history-flags').replaceChildren(...Object.entries(flags).map(([key, label]) => node('label', { class: 'care-item' }, [text('span', label), triSelect(plan[key], v => { plan[key] = v; }, false, label)])));
    $('stress-table').replaceChildren(node('table', { class: 'farm-table' }, [node('thead', {}, [node('tr', {}, ['压力来源', '阶段 1', '阶段 2', '阶段 3', '阶段 4'].map(t => node('th', { scope: 'col', text: t })))]),
      node('tbody', {}, Object.entries(stressNames).map(([key, label]) => node('tr', {}, [node('th', { scope: 'row', text: label }), ...Array.from({ length: 4 }, (_, i) => node('td', {}, [triSelect(plan.stages[i]?.[key], v => { plan.stages[i] ??= {}; plan.stages[i][key] = v; }, true, label + '阶段' + (i + 1))]))])))
    ]));
  }
  function renderStress() {
    const s = result.stress;
    const label = { unknown: '巨大资格：未知，仍有未记录条件。', ineligible: '巨大资格：不满足已记录的维基条件。', eligible_under_wiki_rules: '符合已记录的维基巨大资格条件；不是游戏内结果保证。' }[s.giant_eligibility];
    $('stress-output').textContent = `总压力范围 ${s.stress_min}–${s.stress_max} / 28。${label}`;
  }

  async function load() {
    loading = true;
    updateResetButton();
    try {
      const loaded = await api('/api/farming');
      data = loaded;
      $('source-note').textContent = `灰机维基修订 ${data.metadata.source_revision} · 收到日期 ${data.metadata.received_date} · 基于维基的规划 · 目标版本 ${data.metadata.target_build}（${data.metadata.game_build_verified ? '已核验 ' + data.metadata.game_build_verified : '未核验'}）`;
      plan = clone(data.preferences.state);
      version = data.preferences.version;
      blocked = false;
      for (const p of data.plants) { plants.set(p.plant_id, p); if (p.kind === 'crop') crops.set(p.plant_id, p); }
      initControls(); renderGrid(); renderCare();
      $('planner').hidden = false;
      for (const id of ['save-plan', 'reload-plan', 'export-plan', 'import-plan']) $(id).disabled = false;
      changed();
    } catch (issue) { error(issue.message); $('save-status').textContent = '读取失败，请重试。'; $('reload-plan').disabled = false; }
    finally { loading = false; updateResetButton(); }
  }
  function updateResetButton() {
    $('reset-plan').disabled = !plan || resetting || loading || importing;
  }
  function exportPlan(snapshot) {
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), a = node('a', { href: url, download: 'dst-farming-plan.json' });
    try { (resetDialog.open ? resetDialog : document.body).append(a); a.click(); }
    finally { a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  }
  async function resetPlan(exportFirst) {
    if (resetting || !plan) return;
    resetting = true;
    updateResetButton();
    for (const b of resetDialog.querySelectorAll('button')) b.disabled = true;
    resetDialog.setAttribute('aria-busy', 'true');
    $('reset-plan-error').hidden = true;
    clearTimeout(timer);
    try {
      // Let any earlier save/import finish before exporting or writing defaults.
      // The dialog pauses queued autosaves so they cannot restore an old plan.
      while (busy || loading || importing) await new Promise(resolve => setTimeout(resolve, 20));
      if (exportFirst) exportPlan(clone(plan));
      const saved = await api('/api/farming/preferences', { expected_version: version, state: clone(data.defaults) });
      plan = clone(saved.state);
      version = saved.version;
      data.preferences = saved;
      blocked = false;
      pending = false;
      result = null;
      ratioLayout = 'cards';
      try { localStorage.removeItem(RATIO_LAYOUT_KEY); } catch { /* Reset remains usable when browser storage is unavailable. */ }
      initControls(); renderGrid(); renderCare(); renderRatioSwitch();
      document.querySelectorAll('#planner details[open]').forEach(d => { d.open = false; });
      $('ratio-results').replaceChildren();
      $('layout-report').replaceChildren();
      $('plant-report').replaceChildren();
      $('stress-output').textContent = '';
      changed();
      resetDialog.close();
    } catch (issue) {
      if (issue.status === 409) {
        blocked = true;
        $('save-status').textContent = '尚未保存：' + issue.message;
      }
      $('reset-plan-error').textContent = '重置未完成：' + issue.message;
      $('reset-plan-error').hidden = false;
    } finally {
      resetting = false;
      updateResetButton();
      for (const b of resetDialog.querySelectorAll('button')) b.disabled = false;
      resetDialog.setAttribute('aria-busy', 'false');
      if (pending && !resetDialog.open) work();
    }
  }
  $('reset-plan').addEventListener('click', () => {
    $('reset-plan-error').hidden = true;
    resetDialog.showModal();
  });
  $('close-reset-plan').addEventListener('click', () => { if (!resetting) resetDialog.close(); });
  resetDialog.addEventListener('cancel', event => { if (resetting) event.preventDefault(); });
  resetDialog.addEventListener('close', () => { if (pending && !resetting) work(); });
  $('confirm-reset-plan').addEventListener('click', () => resetPlan(false));
  $('export-reset-plan').addEventListener('click', () => resetPlan(true));
  $('all-seeds').addEventListener('click', () => { plan.available = [...crops.keys()]; changed({ controls: true }); });
  $('no-seeds').addEventListener('click', () => { plan.available = []; changed({ controls: true }); });
  $('ratio-scale').addEventListener('change', () => {
    const input = $('ratio-scale');
    if (!input.checkValidity() || input.value === '') { input.value = plan.scale; input.reportValidity(); return; }
    plan.scale = Number(input.value); changed();
  });
  $('tile-count').addEventListener('change', () => {
    const n = Number($('tile-count').value);
    if (plan.placements.some(p => !fitsFields(p, n))) { $('tile-count').value = plan.tile_count; error('将被移除的田还有植物。请先用擦除画笔清空这些田，再减少田地。'); return; }
    plan.tile_count = n; changed({ layout: true });
  });
  $('clear-layout').addEventListener('click', () => { plan.placements = []; unknownCare(); changed({ layout: true, care: true }); });
  $('more-ratios').addEventListener('click', () => { limit += 12; renderResults(); });
  document.querySelectorAll('[data-ratio-layout]').forEach(b => b.addEventListener('click', () => {
    ratioLayout = b.dataset.ratioLayout;
    try { localStorage.setItem(RATIO_LAYOUT_KEY, ratioLayout); } catch { /* Visual preference remains usable without persistence. */ }
    renderRatioSwitch();
    if (result) renderResults();
  }));
  $('save-plan').addEventListener('click', () => { if (blocked) { error('服务器有新版本。请先导出当前草稿，再用「读取服务器规划」载入新版本。'); return; } changed(); });
  $('reload-plan').addEventListener('click', async () => {
    if (busy) { error('正在处理当前更改，请稍后再读取。'); return; }
    clearTimeout(timer); pending = false;
    await load();
  });
  $('export-plan').addEventListener('click', () => exportPlan(plan));
  $('import-plan').addEventListener('change', async event => {
    importing = true;
    updateResetButton();
    try {
      const file = event.target.files[0];
      if (!file) return;
      if (file.size > 65536) throw new Error('规划文件不能超过 64KB。');
      const imported = JSON.parse(await file.text());
      await api('/api/farming/analyze', imported);
      plan = imported;
      plan.stages = Array.from({ length: 4 }, (_, i) => plan.stages[i] || {});
      renderControls(); renderGrid(); renderCare(); changed();
    } catch (issue) { error('导入失败：' + issue.message); }
    finally { event.target.value = ''; importing = false; updateResetButton(); }
  });
  window.addEventListener('beforeunload', event => {
    if (pending || busy || blocked || resetting || $('save-status').textContent.includes('尚未保存')) { event.preventDefault(); event.returnValue = ''; }
  });
  load();
})();
