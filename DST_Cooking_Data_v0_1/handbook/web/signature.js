'use strict';

const signatureUI = (() => {
  let selected = null, cooker = 'crock_pot', result = null, request = null;
  let shown = 5, error = null, lastAttempt = null;
  const enabled = () => Boolean(state.data?.signature?.enabled);
  const nutrition = { hunger: ['base_hunger', '饥饿值'], health: ['base_health', '生命值'], sanity: ['base_sanity', '理智值'] };
  const ingredient = id => state.data.ingredients.find(row => row.ingredient_id === id);

  function resetResult() {
    if (request) request.abort();
    request = null; result = null; error = null; lastAttempt = null; shown = 5;
  }

  function choose(id) {
    if (selected === id && (request || result)) return;
    selected = id; resetResult(); render();
    [...document.querySelectorAll('.signature-ingredient')].find(button => button.dataset.signatureIngredient === id)?.focus({ preventScroll: true });
  }

  function renderPicker() {
    const query = $('signature-search').value.trim().toLocaleLowerCase();
    const rows = state.data.ingredients.filter(row => [row.name_zh, row.name_en_hint, row.prefab_id, row.ingredient_id]
      .some(value => value && value.toLocaleLowerCase().includes(query)));
    $('signature-picker').replaceChildren(...(rows.length ? rows.map(row => {
      const button = el('button', { type: 'button', class: 'signature-ingredient' + (row.ingredient_id === selected ? ' selected' : ''),
        'data-signature-ingredient': row.ingredient_id, 'aria-pressed': String(row.ingredient_id === selected),
        'aria-label': '查看' + row.name_zh + '的优选料理', onclick: () => choose(row.ingredient_id) }, [portrait(row), text('span', row.name_zh)]);
      button.disabled = !enabled();
      return button;
    }) : [text('p', '没有符合搜索的食材。', 'small muted')]));
  }

  function sorted(rows) {
    const [field] = nutrition[$('signature-sort').value];
    return [...rows].sort((a, b) => {
      const rarity = (a.additional_rarity ?? 0) - (b.additional_rarity ?? 0);
      const value = a[field] == null ? (b[field] == null ? 0 : 1) : b[field] == null ? -1 : b[field] - a[field];
      return ($('signature-ranking').value === 'accessible' ? rarity || value : value || rarity) || a.source_row - b.source_row;
    });
  }

  function recipeCard(row) {
    const probability = row.example.probability;
    const percent = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(probability.value * 100) + '%';
    const counts = new Map();
    row.example.ingredients.forEach(id => counts.set(id, (counts.get(id) || 0) + 1));
    const combination = el('div', { class: 'signature-example', 'aria-label': '包含所选食材的四格示例' },
      [...counts].map(([id, count]) => {
        const item = ingredient(id);
        return el('span', { class: 'example-chip' + (id === selected ? ' selected' : '') }, [portrait(item), text('span', item.name_zh + ' ×' + count)]);
      }));
    const heading = el('button', { type: 'button', class: 'signature-dish', 'aria-label': row.name_zh + '，查看料理详情',
      onclick: () => openDetail('dish', row.dish_id) }, [portrait(row), el('div', {}, [text('h3', row.name_zh),
        text('small', (row.name_en_hint || '英文未提供') + ' · 暂译提示')])]);
    const content = [el('div', { class: 'signature-card-head' }, [heading,
      ...(row.special ? [text('span', '特别', 'special-badge')] : [])]), stats(row),
      text('p', '其余三格最低稀有度 ' + (row.additional_rarity ?? 0) + ' · 本锅概率 ' + percent + (probability.denominator > 1 ? '（1/' + probability.denominator + '）' : ''), 'signature-example-label'), combination,
      el('button', { type: 'button', class: 'secondary signature-try', text: '放入出锅预测 ↗',
        onclick: () => predictionUI.loadPot(row.example.ingredients, result.cooker) })];
    return el('article', { class: 'signature-card', 'data-dish-id': row.dish_id }, content);
  }

  function renderResults() {
    const output = $('signature-results');
    output.setAttribute('aria-busy', String(Boolean(request)));
    if (!enabled()) {
      output.replaceChildren(text('p', state.data.signature?.error || '当前服务尚未启用优选料理，请重启更新后的服务器。', 'notice'));
      return;
    }
    if (!selected) { output.replaceChildren(text('p', '选择一种食材，发现它的优选料理。', 'prediction-empty')); return; }
    if (error) {
      output.replaceChildren(text('p', '暂时无法查找：' + error, 'notice'),
        el('button', { type: 'button', class: 'secondary', text: '重试查找', onclick: () => { lastAttempt = null; fetchResults(); } }));
      return;
    }
    if (!result) { output.replaceChildren(text('p', '正在查找含有「' + ingredient(selected).name_zh + '」的四格配方…', 'prediction-empty')); return; }
    const excluded = new Set(state.data.signature.exclusions.dish_ids);
    const special = sorted(result.special.filter(r => !excluded.has(r.dish_id))), other = sorted(result.other.filter(r => !excluded.has(r.dish_id)));
    const [, label] = nutrition[$('signature-sort').value];
    const ordering = $('signature-ranking').value === 'accessible' ? '按其余三格最低稀有度排序，同分再按基础' + label + '排序。' : '按基础' + label + '排序，同分再按其余三格最低稀有度排序。';
    const first = el('section', { id: 'signature-special', class: 'signature-group' }, [
      el('div', { class: 'section-heading' }, [text('h2', '拿手的特别料理'), text('span', special.length + ' 道 · 全部展示')]),
      text('p', '配方明确点名这件食材，或将其列为可替代形态。组内' + ordering, 'small muted'),
      ...(special.length ? [el('div', { class: 'signature-grid' }, special.map(recipeCard))]
        : [text('p', '没有配方直接点名这件食材；下方仍有可以搭配的料理。', 'signature-empty')])]);
    const second = el('section', { id: 'signature-other', class: 'signature-group' }, [
      el('div', { class: 'section-heading' }, [text('h2', '更多营养搭配'), text('span', '显示 ' + Math.min(shown, other.length) + ' / ' + other.length + ' 道')]),
      text('p', '同样可以包含这件食材，' + ordering, 'small muted'),
      ...(other.length ? [el('div', { class: 'signature-grid' }, other.slice(0, shown).map(recipeCard))]
        : [text('p', '当前锅具下没有其他可出锅的料理。', 'signature-empty')])]);
    const actions = [];
    if (shown < other.length) actions.push(el('button', { type: 'button', class: 'secondary', id: 'signature-more',
      text: '再显示 ' + Math.min(5, other.length - shown) + ' 道料理', onclick: () => {
        shown += 5; renderResults(); ($('signature-more') || $('signature-collapse'))?.focus({ preventScroll: true });
      } }));
    if (shown > 5) actions.push(el('button', { type: 'button', class: 'text-button', id: 'signature-collapse', text: '收起为前 5 道',
      onclick: () => { shown = 5; renderResults(); $('signature-other').scrollIntoView({ block: 'start' }); $('signature-more')?.focus({ preventScroll: true }); } }));
    if (actions.length) second.append(el('div', { class: 'signature-more-actions' }, actions));
    output.replaceChildren(first, second);
  }

  async function fetchResults() {
    if (!selected || !enabled()) return;
    const key = selected + ':' + cooker;
    if (request || lastAttempt === key) return;
    const current = new AbortController(); request = current; lastAttempt = key; error = null;
    renderResults();
    try {
      const data = await rarityUI.calculate('/api/signature', { ingredient: selected, cooker }, current.signal);
      if (data.complete !== true) throw new Error('搜索尚未完成，请重试。');
      if (data.rarity_version < state.data.settings.version) throw new Error('稀有度已更新，请重新查找。');
      if (data.rarity_version !== state.data.settings.version) throw new Error('稀有度已再次更新，请重新查找。');
      if (request === current) {
        result = data;
      }
    } catch (failure) {
      if (failure.name !== 'AbortError' && request === current) error = failure.message;
    } finally {
      if (request === current) { request = null; renderResults(); }
    }
  }

  function render() {
    if (result && result.rarity_version !== state.data.settings.version) resetResult();
    signatureExclusionsUI.sync();
    const config = state.data.prediction;
    const cookerSelect = $('signature-cooker');
    cookerSelect.replaceChildren(...Object.entries(config?.cookers || {}).map(([id, info]) => el('option', { value: id, text: info.name_zh })));
    if (!config?.cookers?.[cooker]) cooker = cookerSelect.value;
    cookerSelect.value = cooker;
    cookerSelect.disabled = !enabled();
    if (selected) {
      const item = ingredient(selected);
      $('signature-selected').replaceChildren(el('div', { class: 'signature-selection' }, [portrait(item, true),
        el('div', {}, [text('h2', item.name_zh), text('p', (item.name_en_hint || '英文未提供') + ' · 暂译提示', 'small muted')])]));
    } else $('signature-selected').replaceChildren(text('p', '选择食材，看看它的拿手料理。', 'muted'));
    renderPicker(); renderResults();
    if (selected && !result && !request) fetchResults();
  }

  function openIngredient(id) {
    if ($('detail-dialog').open) $('detail-dialog').close();
    selected = id; resetResult(); $('signature-search').value = '';
    setView('signature');
    $('signature-section').scrollIntoView({ block: 'start' });
  }

  function init() {
    $('signature-search').addEventListener('input', renderPicker);
    $('signature-cooker').addEventListener('change', () => { cooker = $('signature-cooker').value; resetResult(); render(); });
    $('signature-sort').addEventListener('change', () => { shown = 5; renderResults(); });
    $('signature-ranking').addEventListener('change', () => { shown = 5; renderResults(); });
  }
  function rarityChanged() { resetResult(); if (state.view === 'signature') render(); }
  function exclusionsChanged() { if (state.view === 'signature') renderResults(); }
  return { init, render, openIngredient, rarityChanged, exclusionsChanged };
})();
