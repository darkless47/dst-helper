'use strict';

const examplesUI = (() => {
  let current = null, request = null;
  function cancel() { request?.abort(); request = null; current = null; }
  function mount(dish) {
    cancel();
    const cooker = dish.rule.cooker_scope_hint === 'portable_only_wiki_claim' ? 'portable' : 'crock_pot';
    const select = el('select', { id: 'example-cooker', 'aria-label': '料理示例锅具', onchange: () => {
      current.cooker = select.value; fetchExamples();
    } }, Object.entries(state.data.prediction?.cookers || {}).map(([id, info]) => el('option', { value: id, text: info.name_zh })));
    select.value = cooker;
    const output = el('div', { id: 'dish-example-results', 'aria-live': 'polite' });
    const node = section('料理示例', [
      text('p', '按四份食材的总稀有度从低到高选出三种不同组合。优先原料，不选熟制、烘烤或晒干食材，除非配方明确需要该形态。', 'small muted'),
      el('label', { class: 'example-cooker-label' }, [text('span', '使用锅具'), select]), output,
      text('p', '基于维基实验规则，不限库存；同优先级的结果可能均分概率。悬停或聚焦图片查看食材名称，点击图片前往食材探索。', 'small muted')]);
    node.id = 'dish-examples'; current = { dish, cooker, node, output };
    return node;
  }
  function active(target) { return current === target && target.node.isConnected && $('detail-dialog').open; }
  async function fetchExamples() {
    const target = current;
    if (!target || !active(target)) return;
    request?.abort(); const controller = new AbortController(); request = controller;
    target.output.setAttribute('aria-busy', 'true');
    target.output.replaceChildren(text('p', '正在寻找稀有度最低的四格组合…', 'small muted'));
    if (!state.data.signature?.enabled) {
      target.output.replaceChildren(text('p', '当前预测规则不可用，暂不能生成料理示例。', 'notice'));
      target.output.setAttribute('aria-busy', 'false'); request = null; return;
    }
    try {
      const data = await rarityUI.calculate('/api/examples', { dish: target.dish.dish_id, cooker: target.cooker }, controller.signal);
      if (!active(target) || request !== controller) return;
      if (!data.complete || data.rarity_version < state.data.settings.version) throw new Error('稀有度已更新，请重新查找。');
      if (!active(target) || request !== controller) return;
      if (data.rarity_version !== state.data.settings.version) throw new Error('稀有度已再次更新，请重新查找。');
      const rows = data.examples.map((example, index) => {
        const pictures = el('div', { class: 'dish-example-pot', role: 'group', 'aria-label': '示例 ' + (index + 1) + '，四份食材' }, example.ingredients.map(id => {
          const item = state.data.ingredients.find(row => row.ingredient_id === id);
          const label = item.name_zh + ' · 稀有度 ' + item.rarity;
          return el('button', { type: 'button', class: 'example-ingredient', 'data-ingredient-id': id,
            title: label, 'aria-label': label + '，前往食材探索', onclick: () => openIngredientDetail(id) },
            [portrait(item), text('span', label, 'ingredient-tooltip')]);
        }));
        const chance = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(example.probability.value * 100) + '%';
        return el('article', { class: 'dish-example-row' }, [text('span', String(index + 1).padStart(2, '0'), 'row-number'), pictures,
          el('div', { class: 'dish-example-summary' }, [text('strong', '总稀有度 ' + example.total_rarity),
            text('small', '本锅概率 ' + chance + (example.probability.denominator > 1 ? ' · 1/' + example.probability.denominator : ''))]),
          el('button', { type: 'button', class: 'text-button', text: '试煮 ↗', onclick: () => {
            $('detail-dialog').close(); predictionUI.loadPot(example.ingredients, data.cooker);
          } })]);
      });
      if (!data.available) rows.push(text('p', '这道料理不适用于当前锅具，请选择便携烹饪锅。', 'notice'));
      else if (data.fewer_than_requested) rows.push(text('p', '在当前原料限制与锅具规则下，仅找到 ' + data.examples.length + ' 种可出锅的不同组合。', 'small muted'));
      target.output.replaceChildren(...rows);
    } catch (error) {
      if (error.name !== 'AbortError' && active(target) && request === controller) target.output.replaceChildren(
        text('p', '暂时无法查找料理示例：' + error.message, 'notice'), el('button', { type: 'button', class: 'secondary', text: '重试查找示例', onclick: fetchExamples }));
    } finally {
      if (request === controller) { request = null; target.output.setAttribute('aria-busy', 'false'); }
    }
  }
  function rarityChanged() { if (current && active(current)) fetchExamples(); }
  return { mount, fetchExamples, cancel, rarityChanged };
})();
