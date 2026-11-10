'use strict';

// UI state only. Mechanics are evaluated by the Python prediction module.
const predictionUI = (() => {
  let slots = [null, null, null, null];
  let active = 0;
  let request = null;
  const ingredient = id => state.data.ingredients.find(row => row.ingredient_id === id);
  const enabled = () => Boolean(state.data?.prediction?.enabled);
  const filled = () => slots.filter(Boolean).length;

  function invalidate() {
    if (request) request.abort();
    request = null;
    $('prediction-output').replaceChildren(text('p', filled() === 4
      ? '四格已满，点击「开始预测」查看这锅的结果。'
      : '选满四件食材后，查看这锅的料理与概率。', 'prediction-empty'));
  }

  function choose(id) {
    if (!enabled() || active == null) return;
    slots[active] = id;
    const next = slots.findIndex(item => item == null);
    active = next < 0 ? null : next;
    invalidate(); render();
    if (active == null) $('predict-pot').focus({ preventScroll: true });
    else [...document.querySelectorAll('.picker-item')].find(button => button.dataset.ingredient === id)?.focus({ preventScroll: true });
  }

  function renderPicker() {
    const query = $('prediction-search').value.trim().toLocaleLowerCase();
    const rows = state.data.ingredients.filter(row => [row.name_zh, row.name_en_hint, row.prefab_id, row.ingredient_id]
      .some(value => value && value.toLocaleLowerCase().includes(query)));
    $('picker-count').textContent = rows.length + ' / ' + state.data.ingredients.length;
    $('picker-instruction').textContent = active == null ? '四格已满。点击上方槽位可更换食材，或直接开始预测。'
      : '点击食材填入第 ' + (active + 1) + ' 格；可重复选择。';
    $('ingredient-picker').replaceChildren(...(rows.length ? rows.map(row => {
      const button = el('button', { type: 'button', class: 'picker-item', 'data-ingredient': row.ingredient_id,
        'aria-label': '选择' + row.name_zh, onclick: () => choose(row.ingredient_id) }, [portrait(row),
        el('div', {}, [text('span', row.name_zh), text('small', row.name_en_hint || '英文提示未提供')])]);
      button.disabled = !enabled() || active == null;
      return button;
    }) : [text('p', '没有符合搜索的食材。', 'muted small')]));
  }

  function render() {
    const config = state.data.prediction;
    const cooker = $('prediction-cooker');
    const previous = cooker.value;
    cooker.replaceChildren(...Object.entries(config?.cookers || {}).map(([id, info]) => el('option', { value: id, text: info.name_zh })));
    if ([...cooker.options].some(option => option.value === previous)) cooker.value = previous;
    cooker.disabled = !enabled();
    $('prediction-assumptions').replaceChildren(...(config?.assumptions_zh || [config?.error || '预测策略暂不可用。']).map(line => text('p', line, 'small muted')));
    $('pot-slots').replaceChildren(...slots.map((id, index) => {
      const row = id ? ingredient(id) : null;
      const chooseSlot = el('button', { type: 'button', class: 'pot-slot' + (active === index ? ' active' : ''),
        'aria-label': '第 ' + (index + 1) + ' 格，' + (row ? row.name_zh + '，点击更换' : '选择食材'),
        'aria-pressed': String(active === index), onclick: () => { active = index; render(); $('prediction-search').focus(); } }, [
        text('small', '0' + (index + 1)), ...(row ? [portrait(row), text('span', row.name_zh)] : [text('b', '+'), text('span', '选择食材')])]);
      const children = [chooseSlot];
      if (row) children.push(el('button', { type: 'button', class: 'slot-remove', text: '×', 'aria-label': '移除第 ' + (index + 1) + ' 格的' + row.name_zh,
        onclick: () => { slots[index] = null; active = index; invalidate(); render(); document.querySelectorAll('.pot-slot')[index].focus({ preventScroll: true }); } }));
      return el('div', { class: 'pot-slot-wrap' }, children);
    }));
    $('pot-count').textContent = filled() === 4 ? '4 / 4 件食材' : '还差 ' + (4 - filled()) + ' 件食材';
    $('predict-pot').disabled = !enabled() || filled() !== 4 || Boolean(request);
    $('predict-pot').textContent = request ? '正在预测…' : '开始预测';
    $('clear-pot').disabled = filled() === 0;
    $('example-pot').disabled = !enabled();
    renderPicker();
    if (!enabled()) $('prediction-output').replaceChildren(text('p', config?.error || '当前快照暂不支持预测。', 'notice'));
  }

  function matchingList(rows, explanation) {
    return el('div', {}, [text('p', explanation, 'muted small'), ...rows.map(row => el('div', { class: 'match-row' }, [
      el('button', { type: 'button', class: 'text-button', text: row.name_zh, onclick: () => openDetail('dish', row.dish_id) }),
      text('span', '优先级 ' + row.priority, 'muted small')]))]);
  }

  function showResult(result) {
    const outcomes = result.outcomes.map(outcome => {
      const dish = state.data.dishes.find(row => row.dish_id === outcome.dish_id) || outcome;
      const chance = outcome.probability;
      const percent = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(chance.value * 100) + '%';
      const heading = el('button', { type: 'button', class: 'outcome-open', 'aria-label': outcome.name_zh + '，概率 ' + percent + '，查看详情',
        onclick: () => openDetail('dish', outcome.dish_id) }, [portrait(dish),
        el('div', {}, [text('h3', outcome.name_zh), text('span', outcome.cook_seconds + ' 秒 · 查看手记 ↗', 'small muted')]),
        el('div', { class: 'outcome-chance' }, [text('strong', percent), text('small', chance.denominator > 1 ? '1 / ' + chance.denominator : '唯一最高优先级')])]);
      return el('article', { class: 'outcome-card' }, [heading, stats(dish)]);
    });
    const tags = Object.fromEntries(Object.entries(result.tag_totals).filter(([, value]) => value !== 0));
    const content = [text('p', '最高优先级 ' + result.highest_priority + ' · ' + outcomes.length + ' 种结果', 'result-summary'), ...outcomes,
      text('p', outcomes.length > 1 ? '所有并列最高优先级料理均分概率；分数为精确概率，百分比经四舍五入。' : '本锅在所选锅具下只有一种最高优先级料理。', 'muted small'),
      disclosure('这锅的标签合计', tagChips(tags)),
      text('p', '结果基于维基修订 ' + result.source_revision + '；料理数值为基础表值，非角色实际食用收益。', 'muted small')];
    if (result.suppressed_matches.length) content.push(disclosure('被更高优先级淘汰的匹配 · ' + result.suppressed_matches.length,
      matchingList(result.suppressed_matches, '这些料理满足自身条件，但不会在本锅中出锅。')));
    if (result.unavailable_matches.length) content.push(disclosure('条件匹配但当前锅具不可用 · ' + result.unavailable_matches.length,
      matchingList(result.unavailable_matches, '以下配方被标记为便携锅专属，未参与本次优先级比较。')));
    $('prediction-output').replaceChildren(...content);
  }

  async function predict() {
    if (!enabled() || filled() !== 4) return;
    if (request) request.abort();
    const current = new AbortController(); request = current;
    const params = new URLSearchParams({ cooker: $('prediction-cooker').value });
    slots.forEach(id => params.append('ingredient', id));
    $('prediction-output').replaceChildren(text('p', '正在比较可用配方与优先级…', 'prediction-empty'));
    render();
    try {
      const result = await getJSON('/api/predict?' + params, current.signal);
      if (request === current) {
        showResult(result);
        if (state.view === 'prediction' && window.matchMedia('(max-width:1150px)').matches) {
          document.querySelector('.prediction-panel').scrollIntoView({ block: 'start' });
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError' && request === current) $('prediction-output').replaceChildren(
        text('p', '暂时无法预测：' + error.message, 'notice'),
        el('button', { type: 'button', class: 'secondary', text: '重试预测', onclick: predict }));
    } finally {
      if (request === current) { request = null; render(); }
    }
  }

  function init() {
    $('prediction-search').addEventListener('input', renderPicker);
    $('prediction-cooker').addEventListener('change', () => { invalidate(); render(); });
    $('predict-pot').addEventListener('click', predict);
    $('clear-pot').addEventListener('click', () => { slots = [null, null, null, null]; active = 0; invalidate(); render(); });
    $('example-pot').addEventListener('click', () => {
      slots = ['smallmeat', 'berries', 'berries', 'berries']; active = null;
      invalidate(); render(); predict();
    });
  }
  function loadPot(ingredients, cooker) {
    if (!enabled() || ingredients.length !== 4 || ingredients.some(id => !ingredient(id))) return;
    slots = [...ingredients]; active = null;
    invalidate();
    setView('prediction');
    $('prediction-cooker').value = cooker;
    render(); $('predict-pot').focus({ preventScroll: true }); predict();
  }
  return { init, render, loadPot };
})();
