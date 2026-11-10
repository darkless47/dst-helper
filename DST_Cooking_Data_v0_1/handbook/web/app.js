'use strict';

const $ = id => document.getElementById(id);
const LAYOUT_KEYS = { dishes: 'dst-handbook.dish-layout', ingredients: 'dst-handbook.ingredient-layout' };
function readLayout(view) {
  try { return localStorage.getItem(LAYOUT_KEYS[view]) === 'table' ? 'table' : 'cards'; }
  catch { return 'cards'; }
}
const state = { data: null, view: 'dishes', request: null,
  layouts: { dishes: readLayout('dishes'), ingredients: readLayout('ingredients') } };
const copy = {
  dishes: ['THE WILDERNESS TABLE / 01', '在荒野，好好吃饭。', '查阅料理的表格数值、食材标签与原始证据。每一条资料，都有来处。', '料理索引'],
  ingredients: ['KNOW YOUR INGREDIENTS / 02', '每种食材，各有分量。', '按状态查看维基记录的食材标签。标签贡献与具名食材计数，使用不同的身份。', '食材索引'],
  signature: ['SIGNATURE RECIPES / 03', '这一味，最适合哪道料理？', '配方点名的拿手料理排在前面，再按营养值发现更多搭配。', '优选料理'],
  prediction: ['EXACT POT / 04', '四格食材，会煮出什么？', '选满四件食材，按最高优先级计算料理；同分结果均分概率。', '出锅预测'],
  evidence: ['SOURCES & LIMITS', '让每条资料，都有来处。', '保留来源、缺失与疑问。目标游戏版本与数据核验等级，分别记录。', '数据与边界']
};
const issueLabels = {
  state_variant: ['同一 prefab 的不同状态', '两条营养砖状态各自保留。@wiki_state_ 是资料集后缀，不是游戏 prefab。'],
  composite_stat: ['复合数值尚待拆解', '原文合计不代表即时回复。效果时序、组成与生效条件仍待核实。'],
  unconfirmed_build: ['游戏版本兼容性未确认', '维基修订 193291 尚未对照目标安装版本 762172 核验。'],
  unconfirmed_weights: ['选择策略与概率字段', '优先级及同分等概率已由用户确认，预测直接使用 priority。原始 weight 字段的 NULL 保留，不当作已核验的游戏权重。'],
  dish_prefab_missing: ['料理 prefab 与英文名称待确认', '料理 ID 暂用稳定的维基键。英文仅是图片文件名提供的提示，并非已确认的官方译名。'],
  draft_predicates: ['全部规则均为待复核草稿', '语法解析与转录测试不能证明真实出锅结果。所有 solver_ready 标记保留为 false。'],
  cooker_matrix_missing: ['普通配方的锅具范围已确认', '用户确认：普通配方可由烹饪锅或沃利的便携烹饪锅制作；便携锅专属标记保留。各食材的锅具适用范围仍待核验。'],
  tag_coverage: ['标签词汇并不完整', '仅收录表格的 15 个标签列。已收录列的空白按 0 解读；未收录标签视为未知。食材肉度不等于成品食物类型。'],
  mechanics_missing: ['成品类型与角色机制尚未建模', '可穿戴品、动物食物与玩家料理的用途需要确认；表格数值不能直接当作玩家食用收益。特殊效果、角色、调味、产出数量与完整状态机制暂缺。'],
  asset_rights: ['图片来源与使用范围', '图片来自用户提供的本地网页存档，逐项核对哈希后显示。原始数据包的权利状态保留；可再分发权限尚未确认。']
};

function el(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}
const text = (tag, value, cls) => el(tag, { text: value, ...(cls ? { class: cls } : {}) });
const number = value => value == null ? '未知' : String(value);
const unknown = value => value == null || value === '' ? '未知 / 未确认' : String(value);
function link(label, value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsupported URL');
    return el('a', { href: url.href, target: '_blank', rel: 'noopener noreferrer', text: label });
  } catch { return text('span', label + '（无可用链接）'); }
}
function values(entries) {
  return el('dl', { class: 'key-values' }, entries.flatMap(([label, value]) => [text('dt', label), text('dd', unknown(value))]));
}
function section(title, children) {
  return el('section', { class: 'detail-section' }, [text('h3', title), ...children]);
}
function disclosure(label, content) { return el('details', {}, [text('summary', label), content]); }
function portrait(row, detailed = false) {
  const info = state.data.media?.catalog_images?.[row.icon_asset_id];
  const fallback = text('span', row.name_zh.slice(0, 1), 'image-fallback');
  const box = el('div', { class: 'food-portrait' + (detailed ? ' detail-portrait' : ''), 'aria-hidden': 'true' }, [fallback]);
  if (info) {
    fallback.hidden = true;
    const image = el('img', { class: 'food-image', src: info.url, alt: '', width: info.width, height: info.height,
      loading: detailed ? 'eager' : 'lazy', decoding: 'async', onerror: () => { image.remove(); fallback.hidden = false; } });
    box.append(image);
  }
  return box;
}
function statLabel(key, label, detailed) {
  const info = state.data.media?.stat_icons?.[key];
  const children = [];
  if (info) {
    const image = el('img', { class: 'stat-icon', src: info.url, alt: '', width: detailed ? 28 : 22,
      height: detailed ? 28 : 22, decoding: 'async', onerror: () => image.remove() });
    children.push(image);
  }
  children.push(text('span', label));
  return el('div', { class: 'stat-label' }, children);
}
function stats(dish, detailed = false) {
  return el('div', { class: 'stats' }, [['health', '生命'], ['hunger', '饥饿'], ['sanity', '理智']].map(([key, label]) => {
    const value = dish['base_' + key];
    const raw = dish[key + '_source_text'];
    const unresolved = value == null;
    const content = [statLabel(key, label, detailed),
      text('strong', unresolved ? (raw || '未知') : number(value), unresolved ? 'unknown' : ''),
      text('span', unresolved ? '待确认 / 原文值' : '基础表值', 'stat-caption')];
    if (detailed) content.push(text('small', unresolved ? '原文复合或缺失值；不作为即时回复。' : '原文：' + (raw || '未提供')));
    return el('div', { class: 'stat' }, content);
  }));
}
function perish(dish) {
  if (dish.perish_game_days != null) return number(dish.perish_game_days) + ' 游戏天';
  return dish.perish_source_text === '无' ? '原文：无腐烂' : '未知（原文：' + unknown(dish.perish_source_text) + '）';
}
function tagChips(tags, all = false) {
  const vocabulary = state.data.tag_labels;
  const items = all ? Object.keys(vocabulary) : Object.keys(tags);
  if (!items.length) return el('div', { class: 'tags' }, [text('span', '15 个已收录列均为空白', 'muted small')]);
  return el('div', { class: 'tags' }, items.map(key => text('span', (vocabulary[key] || key) + ' ' + number(tags[key] ?? 0), 'tag')));
}
function card(row) {
  const dish = state.view === 'dishes';
  const id = dish ? row.dish_id : row.ingredient_id;
  const portable = dish && row.cooker_scope_hint === 'portable_only_wiki_claim';
  const typeLabel = dish ? (portable ? '便携锅 · 维基提示' : '维基快照') : (id !== row.prefab_id ? '独立状态记录' : '食材状态');
  const content = [el('div', { class: 'card-top' }, [text('span', 'NO. ' + String(row.source_row).padStart(3, '0'), 'row-number'), text('span', typeLabel, 'type-chip' + (portable ? ' portable' : ''))]),
    el('div', { class: 'card-identity' }, [portrait(row), el('div', { class: 'card-heading' }, [
      text('h3', row.name_zh), text('p', (row.name_en_hint || '未提供英文') + ' · 暂译提示', 'english-hint')])])];
  if (dish) {
    content.push(stats(row), el('div', { class: 'card-foot' }, [text('span', number(row.cook_seconds) + ' 秒 · 优先级 ' + number(row.priority)), text('b', '查阅手记 ↗')]));
  } else {
    content.push(text('p', row.prefab_id, 'prefab'), tagChips(row.tags), el('div', { class: 'card-foot' }, [text('span', '稀有度 ' + (row.rarity ?? 0) + ' · 状态行 ' + row.source_row), text('b', '查看标签与证据 ↗')]));
  }
  return el('button', { type: 'button', class: 'catalog-card' + (dish ? '' : ' ingredient-card'),
    'aria-label': row.name_zh + '，查看详情，来源行 ' + row.source_row,
    onclick: () => openDetail(dish ? 'dish' : 'ingredient', id) }, content);
}
function dishTable(rows) {
  const headers = [text('th', '料理'),
    ...[['health', '生命'], ['hunger', '饥饿'], ['sanity', '理智']].map(([key, label]) => el('th', {}, [statLabel(key, label, false)])),
    ...['保鲜期', '烹饪时间', '优先级', '锅具提示'].map(label => text('th', label))];
  headers.forEach(header => header.setAttribute('scope', 'col'));
  const body = rows.map(dish => {
    const open = () => openDetail('dish', dish.dish_id);
    const name = el('button', { type: 'button', class: 'table-item-name table-dish-name',
      'aria-label': dish.name_zh + '，查看详情', onclick: open }, [text('span', dish.name_zh)]);
    const identity = el('div', { class: 'table-identity' }, [portrait(dish), el('div', {}, [name,
      text('div', (dish.name_en_hint || '未提供英文') + ' · 暂译', 'table-english')])]);
    const cells = [el('th', { scope: 'row' }, [identity])];
    for (const key of ['health', 'hunger', 'sanity']) {
      const value = dish['base_' + key];
      const unresolved = value == null;
      cells.push(el('td', { class: 'table-number' + (unresolved ? ' unresolved' : '') }, [
        text('span', unresolved ? (dish[key + '_source_text'] || '未知') : number(value)),
        ...(unresolved ? [text('small', '原文 · 待确认')] : [])]));
    }
    const portable = dish.cooker_scope_hint === 'portable_only_wiki_claim';
    cells.push(text('td', perish(dish), 'table-perish'), text('td', number(dish.cook_seconds) + ' 秒', 'table-number'),
      text('td', number(dish.priority), 'table-number'), el('td', {}, [
        text('span', portable ? '便携锅 · 维基提示' : '烹饪锅 / 便携烹饪锅', portable ? 'table-cooker portable' : 'table-cooker')]));
    return el('tr', { onclick: event => { if (!event.target.closest('button, a')) open(); } }, cells);
  });
  return el('table', { class: 'catalog-table dish-table' }, [
    text('caption', '料理基础表格数值。复合数值保留原文并标记待确认；点击料理名称查看来源与草稿规则。', 'sr-only'),
    el('colgroup', {}, ['name', 'stat', 'stat', 'stat', 'perish', 'cook', 'priority', 'cooker'].map(column => el('col', { class: 'column-' + column }))),
    el('thead', {}, [el('tr', {}, headers)]), el('tbody', {}, body)]);
}
function ingredientTable(rows) {
  const tags = Object.entries(state.data.tag_labels);
  const headers = ['食材', '稀有度', ...tags.map(([, label]) => label), '状态 ID / prefab'].map(label => el('th', { scope: 'col', text: label }));
  const body = rows.map(ingredient => {
    const open = () => openDetail('ingredient', ingredient.ingredient_id);
    const name = el('button', { type: 'button', class: 'table-item-name table-ingredient-name',
      'aria-label': ingredient.name_zh + '，查看详情，来源行 ' + ingredient.source_row, onclick: open }, [text('span', ingredient.name_zh)]);
    const identity = el('div', { class: 'table-identity' }, [portrait(ingredient), el('div', {}, [name,
      text('div', (ingredient.name_en_hint || '未提供英文') + ' · 暂译', 'table-english'),
      text('div', '状态行 ' + ingredient.source_row, 'table-english')])]);
    const ids = [text('code', ingredient.ingredient_id)];
    if (ingredient.ingredient_id !== ingredient.prefab_id) {
      ids.push(text('small', 'prefab：' + ingredient.prefab_id), text('small', '独立状态记录'));
    }
    return el('tr', { onclick: event => { if (!event.target.closest('button, a')) open(); } }, [
      el('th', { scope: 'row' }, [identity]),
      el('td', { class: 'table-number table-rarity' }, [el('button', { type: 'button', class: 'rarity-edit-button',
        text: (ingredient.rarity ?? 0) + ' ✎', 'aria-label': '编辑' + ingredient.name_zh + '的稀有度，当前 ' + (ingredient.rarity ?? 0),
        onclick: () => rarityUI.edit(ingredient.ingredient_id) })]),
      ...tags.map(([key]) => {
        const value = ingredient.tags[key] ?? 0;
        return text('td', number(value), 'table-number' + (value === 0 ? ' table-zero' : ''));
      }), el('td', { class: 'table-state-id' }, ids)]);
  });
  return el('table', { class: 'catalog-table ingredient-table' }, [
    text('caption', '食材状态与 15 个已收录标签的贡献值。源表空白按 0 解读；点击食材名称查看来源与完整标签。', 'sr-only'),
    el('colgroup', {}, ['name', 'rarity', ...tags.map(() => 'tag'), 'state-id'].map(column => el('col', { class: 'column-' + column }))),
    el('thead', {}, [el('tr', {}, headers)]), el('tbody', {}, body)]);
}
function setCatalogLayout(layout) {
  if (!LAYOUT_KEYS[state.view] || !['cards', 'table'].includes(layout)) return;
  state.layouts[state.view] = layout;
  try { localStorage.setItem(LAYOUT_KEYS[state.view], layout); } catch { /* Layout still works when browser storage is unavailable. */ }
  renderResults();
}
function setView(view) {
  state.view = view;
  const [kicker, title, description, indexTitle] = copy[view];
  $('section-kicker').textContent = kicker;
  $('page-title').textContent = title;
  $('page-description').textContent = description;
  $('catalog-title').textContent = indexTitle;
  $('catalog-section').hidden = !['dishes', 'ingredients'].includes(view) || !state.data;
  $('evidence-section').hidden = view !== 'evidence' || !state.data;
  $('prediction-section').hidden = view !== 'prediction' || !state.data;
  $('signature-section').hidden = view !== 'signature' || !state.data;
  $('dish-filters').hidden = view !== 'dishes';
  $('ingredient-filters').hidden = view !== 'ingredients';
  $('rarity-controls').hidden = view !== 'ingredients';
  $('catalog-layout-switch').hidden = !LAYOUT_KEYS[view];
  $('catalog-layout-switch').setAttribute('aria-label', view === 'ingredients' ? '食材显示方式' : '料理显示方式');
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('catalog-note').textContent = view === 'ingredients'
    ? '仅显示食材标签；食材基础食用数值未收录。相同 prefab 的不同状态分别保留，标签按状态 ID 记录。'
    : '数值来自维基基础表格，未经游戏验证；成品类型与食用对象尚未确认，不代表角色实际食用收益。';
  const sort = $('sort');
  const allowedSorts = view === 'ingredients' ? ['source', 'name', 'rarity'] : ['source', 'name', 'hunger', 'health', 'sanity', 'priority', 'cook'];
  for (const option of sort.options) option.disabled = !allowedSorts.includes(option.value);
  if (!allowedSorts.includes(sort.value)) sort.value = 'source';
  if (state.data && ['dishes', 'ingredients'].includes(view)) renderResults();
  if (state.data && view === 'prediction') predictionUI.render();
  if (state.data && view === 'signature') signatureUI.render();
}
function renderResults() {
  if (!state.data || !['dishes', 'ingredients'].includes(state.view)) return;
  const dish = state.view === 'dishes';
  const query = $('search').value.trim().toLocaleLowerCase();
  const source = dish ? state.data.dishes : state.data.ingredients;
  const rows = source.filter(row => {
    if (query && ![row.name_zh, row.name_en_hint, row.dish_id, row.ingredient_id, row.prefab_id].some(value => value && value.toLocaleLowerCase().includes(query))) return false;
    if (!dish) {
      const tag = $('tag-filter').value;
      return tag === 'all' || (row.tags[tag] != null && row.tags[tag] > 0 && row.tags[tag] >= Number($('tag-min').value));
    }
    const cooker = $('cooker').value;
    const portable = row.cooker_scope_hint === 'portable_only_wiki_claim';
    if (cooker === 'portable' && !portable || cooker === 'both' && portable) return false;
    switch ($('stat-filter').value) {
      case 'health': return row.base_health != null && row.base_health > 0;
      case 'hunger': return row.base_hunger != null && row.base_hunger >= 75;
      case 'sanity': return row.base_sanity != null && row.base_sanity > 0;
      case 'composite': return ['health', 'hunger', 'sanity'].some(key => row['base_' + key] == null && row[key + '_source_text']);
      default: return true;
    }
  });
  const sort = $('sort').value;
  rows.sort((a, b) => {
    if (sort === 'name') return a.name_zh.localeCompare(b.name_zh, 'zh-CN') || a.source_row - b.source_row;
    if (sort === 'source') return a.source_row - b.source_row;
    const field = { hunger: 'base_hunger', health: 'base_health', sanity: 'base_sanity', priority: 'priority', cook: 'cook_seconds', rarity: 'rarity' }[sort];
    if (a[field] == null) return b[field] == null ? a.source_row - b.source_row : 1;
    if (b[field] == null) return -1;
    return (['cook', 'rarity'].includes(sort) ? a[field] - b[field] : b[field] - a[field]) || a.source_row - b.source_row;
  });
  $('tag-min').disabled = $('tag-filter').value === 'all';
  const table = state.layouts[state.view] === 'table';
  const results = $('results');
  results.className = table ? 'table-results' : 'card-grid';
  if (table) {
    results.setAttribute('role', 'region');
    results.setAttribute('aria-label', (dish ? '料理' : '食材') + '表格，可横向滚动查看其余列');
    results.setAttribute('tabindex', '0');
  } else {
    for (const attribute of ['role', 'aria-label', 'tabindex']) results.removeAttribute(attribute);
  }
  results.replaceChildren(...(table ? [dish ? dishTable(rows) : ingredientTable(rows)] : rows.map(card)));
  results.hidden = rows.length === 0;
  $('table-hint').hidden = !table || rows.length === 0;
  $('table-hint').textContent = dish
    ? '点击料理名称查阅完整手记。表格可横向滚动，数值为基础表值；英文名称仅为暂译提示。'
    : '点击食材名称查阅完整手记。表格可横向滚动；15 个已收录标签的源表空白按 0 解读，不代表食材食用数值。';
  document.querySelectorAll('[data-layout]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.layout === state.layouts[state.view]));
  });
  $('results').setAttribute('aria-busy', 'false');
  $('empty').hidden = rows.length !== 0;
  $('result-count').textContent = rows.length + ' / ' + source.length + (dish ? ' 道料理' : ' 条食材状态');
}
function reset() {
  $('search').value = '';
  for (const id of ['cooker', 'stat-filter', 'tag-filter']) $(id).value = 'all';
  $('tag-min').value = '0';
  $('sort').value = 'source';
  renderResults();
}
async function getJSON(url, signal) {
  const response = await fetch(url, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '读取失败');
  return data;
}
function issueNode(issue) {
  const [label, explanation] = issueLabels[issue.issue_code] || [issue.issue_code, issue.details];
  return el('div', { class: 'issue' }, [text('h3', label), text('p', explanation),
    disclosure('原始审阅记录' + (issue.entity_id ? ' · ' + issue.entity_id : ''), text('pre', issue.details))]);
}
function renderEvidence() {
  const data = state.data, m = data.metadata;
  const ready = data.dishes.filter(row => row.solver_ready).length;
  $('evidence-section').replaceChildren(
    el('section', { class: 'evidence-panel' }, [text('h2', '一份快照，不是一份游戏验证报告。'),
      text('p', '收录 ' + data.dishes.length + ' 道料理与 ' + data.ingredients.length + ' 条食材状态（' + new Set(data.ingredients.map(i => i.prefab_id)).size + ' 个维基报告 prefab）。' + ready + ' 条配方标记为 solver_ready。18 个附带测试只核对转录与 AST 解读，不能证明真实烹饪结果。'),
      el('div', { class: 'metadata-grid' }, [
        el('div', {}, [text('span', '目标安装版本 · 用户报告'), text('strong', unknown(m.target_build))]),
        el('div', {}, [text('span', '数据证据等级'), text('strong', '单一维基快照 / ' + unknown(m.verification))]),
        el('div', {}, [text('span', '维基修订 / 资料集版本'), text('strong', unknown(m.source_revision) + ' / ' + unknown(m.dataset_version))]),
        el('div', {}, [text('span', '收到保存页的日期 · 非下载时间'), text('strong', unknown(m.source_received_date))])]),
      text('p', '来源为用户保存的灰机维基烹饪页。确切抓取时间未知；当前网页可能已变化。'),
      link('打开维基烹饪页 ↗', m.source_url),
      disclosure('完整快照元数据', text('pre', JSON.stringify(m, null, 2)))]),
    el('section', { class: 'evidence-panel' }, [text('h2', '尚待确认的内容'), ...data.issues.map(issueNode)]),
    el('section', { class: 'evidence-panel' }, [text('h2', '使用与来源说明'),
      text('p', '此版本提供只读目录、四格维基实验预测与含指定食材的优选料理。优选料理经完整四格结果复核，采用相同锅具和食材范围，不限制库存。优先级、同分概率、混合计数及普通配方双锅具适用性已由用户确认；各食材的锅具适用范围尚未核验。显示偏好保存在浏览器中，内容数据库保持只读。'),
      text('p', '稀有度由用户自定义，仅保存在当前浏览器，不影响其他用户。优选料理默认按其余食材的最低稀有度排序；料理详情提供按总稀有度选出的图片示例。未设置的稀有度按 0 计算。'),
      text('p', '图片来自用户提供的网页存档，只从本机读取。已匹配 ' + (data.media?.available_catalog_count ?? 0) + ' / ' + (data.media?.indexed_catalog_count ?? 0) + ' 张目录图片；HP、饥饿与理智图标同样保留来源和哈希。存档缺失或图片不匹配时显示文字。'),
      text('p', '文本许可说明来自既有研究，尚未重新审计。游戏美术权利另行确认；此应用不会从互联网下载图片，也不会发布本地素材。'),
      text('p', '数据库 schema v' + m.schema_version + '；内容更新使用显式 SQLite 迁移与可重复导入。'),
      text('p', '保存页 SHA-256', 'eyebrow'), text('div', unknown(m.source_sha256), 'hash'),
      disclosure('来源记录', text('pre', JSON.stringify(data.sources, null, 2))),
      disclosure('HP / 饥饿 / 理智图标来源', text('pre', JSON.stringify(data.media?.stat_provenance ?? {}, null, 2)))])
  );
}
function detailStatus(dish) {
  const status = el('div', { class: 'detail-status' }, [text('span', '维基快照 · 未经游戏验证', 'type-chip')]);
  if (dish) {
    const bubble = el('div', { id: 'dish-stat-warning', class: 'detail-warning-bubble', popover: 'auto', role: 'note' }, [
      text('p', '成品类型、食用对象与角色效果尚未确认。基础表格数值不等于玩家实际食用收益；复合值保留原文，效果尚未拆解。')]);
    const button = el('button', { type: 'button', class: 'detail-warning-button', text: '⚠',
      popovertarget: bubble.id, 'aria-label': '查看食用数值说明', title: '查看食用数值说明', onclick: () => {
        bubble.style.left = status.getBoundingClientRect().left + 'px';
        bubble.style.top = button.getBoundingClientRect().bottom + 8 + 'px';
      } });
    status.append(button, bubble);
  }
  return status;
}
function renderDetail(kind, d) {
  const dish = kind === 'dish';
  const title = text('h2', d.name_zh); title.id = 'detail-title';
  const content = [detailStatus(dish),
    el('div', { class: 'detail-identity' }, [portrait(d, true), el('div', {}, [title,
      text('p', (d.name_en_hint || '未提供英文') + ' · 图片文件名提示，非确认译名', 'detail-hint')])])];
  if (dish) {
    const rule = d.rule;
    content.push(el('div', { class: 'detail-stats' }, [stats(d, true)]),
      section('表格记录', [values([['保鲜期', perish(d)], ['保鲜原文', d.perish_source_text], ['烹饪时间', number(rule.cook_seconds) + ' 秒'],
        ['优先级', rule.priority], ['锅具提示', rule.cooker_scope_hint === 'portable_only_wiki_claim' ? '便携烹饪锅专属 · 维基提示' : '烹饪锅或沃利的便携烹饪锅均可制作（用户确认）']]),
        el('details', { id: 'dish-record-more', class: 'detail-more' }, [text('summary', '更多...'),
          values([['同分选择', '用户确认：最高优先级同分等概率'], ['额外概率权重', rule.weight == null ? '原始 NULL 保留；等概率策略不使用该字段' : rule.weight],
            ['成品食物类型', d.food_type], ['游戏 prefab', d.game_prefab_id], ['临时维基 ID', d.dish_id]])])]),
      section('配方条件', [text('p', '下列条件仅描述自身匹配；预测还需比较同锅全部可用配方的优先级。条件转录已审阅，游戏版本与食材适用范围尚未核验。', 'muted small'),
        text('div', rule.description || rule.display_error || '暂无可显示条件，请查阅原文。', 'rule-description'),
        el('details', { id: 'recipe-rule-more', class: 'detail-more' }, [text('summary', '更多...'),
          values([['解析状态', rule.parse_status], ['solver_ready', String(Boolean(rule.solver_ready))]]),
          disclosure('查看声明式 AST（仅供审阅）', text('pre', JSON.stringify(rule.conditions, null, 2)))])]), examplesUI.mount(d));
  } else {
    content.push(el('p', {}, [el('button', { type: 'button', class: 'secondary', text: '查看这件食材的优选料理 ↗',
      onclick: () => signatureUI.openIngredient(d.ingredient_id) })]), rarityUI.editor(d), section('状态标签', [tagChips(d.tags, true),
      text('p', '已收录的 15 列中，空白源单元格按 0 解读；其他标签未知。食材肉度不是成品食物类型。食用基础数值与锅具适用性尚未收录。', 'muted small'),
      values([['状态 ID', d.ingredient_id], ['维基 prefab', d.prefab_id]])]),
      text('p', '标签按状态 ID 累加；具名食材条件按 prefab 计数。@wiki_state_ 后缀只用于资料集状态区分，不是游戏 prefab。', 'notice'));
    if (d.states.length > 1) content.push(section('相同 prefab 的独立状态', d.states.map(s => el('p', {}, [
      el('button', { class: 'secondary', text: s.name_zh + ' · 源表行 ' + s.source_row, onclick: () => openDetail('ingredient', s.ingredient_id) })]))));
  }
  if (d.issues.length) content.push(section('此条目的审阅问题', d.issues.map(issueNode)));
  const source = d.source;
  const sourceSection = el('details', { id: 'source-evidence', class: 'detail-section source-evidence' }, [
    text('summary', '来源与证据'), values([['来源表 / 行', (dish ? '料理表 / ' : '食材表 / ') + d.source_row],
    ['核验状态', d.verification_status], ['维基修订', source.revision_id], ['保存页收到日期', source.received_date], ['已核验游戏版本', source.game_build_verified]]),
    el('p', { class: 'source-link' }, [link('打开条目维基页 ↗', d.source_url)]),
    text('p', '此链接指向当前网页；下方证据与条目图片来自本地保存的快照。', 'muted small'),
    disclosure('保存页来源及哈希', text('pre', JSON.stringify(source, null, 2)))]);
  if (d.evidence) {
    const headers = dish ? ['图标引用', '名称', '生命原文', '饥饿原文', '理智原文', '保鲜原文', '烹饪时间', '优先级', '标签条件', '具名条件 / 锅具提示']
      : ['图标引用', '名称', ...Object.values(state.data.tag_labels)];
    const table = el('table', { class: 'evidence-table' }, [el('tbody', {}, d.evidence.cells.map((cell, index) =>
      el('tr', {}, [text('th', headers[index] || '列 ' + (index + 1)), el('td', {}, [
        text('div', cell.text || '（空白）'), ...cell.links.map(l => el('div', {}, [link(l.title || '来源链接', l.url)]))])])))]);
    sourceSection.append(disclosure('原始表格单元格', table));
  }
  if (d.asset) sourceSection.append(disclosure('本地图片匹配、来源与权利记录', text('pre', JSON.stringify({ source_record: d.asset, local_image: d.local_image }, null, 2))));
  content.push(sourceSection);
  $('detail-content').replaceChildren(...content);
  $('detail-content').dataset.entityId = dish ? d.dish_id : d.ingredient_id;
  if (dish) examplesUI.fetchExamples();
}
function openIngredientDetail(id) {
  $('search').value = id; $('tag-filter').value = 'all'; $('tag-min').value = '0';
  setView('ingredients'); $('search').focus({ preventScroll: true });
  openDetail('ingredient', id);
}
async function openDetail(kind, id) {
  examplesUI.cancel();
  if (state.request) state.request.abort();
  const request = new AbortController();
  state.request = request;
  const title = text('h2', '正在读取条目…'); title.id = 'detail-title';
  $('detail-content').replaceChildren(title);
  const dialog = $('detail-dialog');
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
  try {
    const d = await getJSON('/api/detail?' + new URLSearchParams({ kind, id }), request.signal);
    if (kind === 'ingredient') d.rarity = state.data.settings.rarities[d.ingredient_id] ?? 0;
    if (state.request === request) renderDetail(kind, d);
  } catch (error) {
    if (error.name !== 'AbortError' && state.request === request) {
      const heading = text('h2', '无法读取条目'); heading.id = 'detail-title';
      $('detail-content').replaceChildren(heading, text('p', error.message), el('button', { class: 'secondary', text: '重试', onclick: () => openDetail(kind, id) }));
    }
  }
}
async function load() {
  $('error').hidden = true;
  $('retry').disabled = true;
  $('results').replaceChildren(text('div', '正在读取本地维基快照…', 'loading'));
  try {
    state.data = await getJSON('/api/catalog');
    rarityUI.initialize();
    signatureExclusionsUI.initialize();
    const d = state.data;
    $('dish-count').textContent = d.dishes.length;
    $('ingredient-count').textContent = d.ingredients.length;
    $('tag-filter').replaceChildren(el('option', { value: 'all', text: '全部标签' }),
      ...Object.entries(d.tag_labels).map(([key, label]) => el('option', { value: key, text: label })));
    renderEvidence();
    setView(state.view);
    const ingredient = new URLSearchParams(location.search).get('ingredient');
    if (ingredient && d.ingredients.some(row => row.ingredient_id === ingredient)) openIngredientDetail(ingredient);
  } catch (error) {
    $('error-message').textContent = error.message + '。请确认本地服务已启动，数据库可读取。';
    $('error').hidden = false;
    $('catalog-section').hidden = true;
    $('evidence-section').hidden = true;
    $('prediction-section').hidden = true;
    $('signature-section').hidden = true;
  } finally { $('retry').disabled = false; }
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
$('detail-dialog').addEventListener('close', () => { if (!$('detail-dialog').open) examplesUI.cancel(); });
document.querySelectorAll('[data-layout]').forEach(button => button.addEventListener('click', () => setCatalogLayout(button.dataset.layout)));
for (const id of ['search', 'sort', 'cooker', 'stat-filter', 'tag-filter', 'tag-min']) $(id).addEventListener(id === 'search' ? 'input' : 'change', renderResults);
document.querySelectorAll('.reset').forEach(button => button.addEventListener('click', reset));
$('retry').addEventListener('click', load);
$('close-detail').addEventListener('click', () => $('detail-dialog').close());
$('detail-dialog').addEventListener('close', () => {
  if (!$('detail-dialog').open) { state.request?.abort(); state.request = null; }
});
$('detail-dialog').addEventListener('click', event => { if (event.target === $('detail-dialog') && event.clientX < event.target.getBoundingClientRect().left) event.target.close(); });
document.addEventListener('keydown', event => {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !document.querySelector('dialog[open]') && state.view !== 'evidence') {
    event.preventDefault(); $({ prediction: 'prediction-search', signature: 'signature-search' }[state.view] || 'search').focus();
  }
});
predictionUI.init();
signatureUI.init();
signatureExclusionsUI.init();
$('clear-rarities').addEventListener('click', rarityUI.clearAll);
load();
