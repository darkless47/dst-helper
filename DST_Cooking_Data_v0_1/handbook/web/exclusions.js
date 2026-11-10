'use strict';

const signatureExclusionsUI = (() => {
  let request = null, ready = false, saving = false;
  const preferences = () => state.data?.signature?.exclusions;

  function sync() {
    const count = preferences()?.dish_ids.length ?? 0;
    $('signature-exclusion-summary').textContent = '已排除 ' + count + ' 道料理，仅影响优选料理推荐。';
    $('manage-signature-exclusions').textContent = '管理不考虑名单（' + count + '）';
  }
  function accept(snapshot, notify = true) {
    const changed = snapshot.version !== preferences()?.version;
    state.data.signature.exclusions = snapshot;
    sync();
    if (changed && notify) signatureUI.exclusionsChanged();
  }
  function row(dish, excluded) {
    const button = el('button', { type: 'button', class: excluded ? 'text-button' : 'secondary',
      text: excluded ? '恢复推荐' : '加入名单', 'aria-label': dish.name_zh + (excluded ? '，恢复推荐' : '，加入不考虑名单'),
      onclick: () => update(dish.dish_id, !excluded) });
    button.disabled = saving || !ready;
    return el('div', { class: 'exclusion-dish', 'data-exclusion-dish': dish.dish_id }, [portrait(dish),
      el('div', { class: 'exclusion-dish-name' }, [text('strong', dish.name_zh), text('small', dish.name_en_hint || '英文提示未提供')]), button]);
  }
  function renderLists() {
    const ids = new Set(preferences()?.dish_ids || []);
    const query = $('signature-exclusion-search').value.trim().toLocaleLowerCase();
    const excluded = state.data.dishes.filter(dish => ids.has(dish.dish_id));
    const candidates = state.data.dishes.filter(dish => !ids.has(dish.dish_id) &&
      [dish.name_zh, dish.name_en_hint, dish.dish_id].some(value => value && value.toLocaleLowerCase().includes(query)));
    $('excluded-count').textContent = excluded.length + ' 道';
    $('excluded-dishes').replaceChildren(...(excluded.length ? excluded.map(dish => row(dish, true)) : [text('p', '名单为空，全部料理都可参与推荐。', 'small muted')]));
    $('exclusion-candidates').replaceChildren(...(candidates.length ? candidates.map(dish => row(dish, false)) : [text('p', '没有可加入的匹配料理。', 'small muted')]));
  }
  async function load() {
    if (saving) return;
    request?.abort(); const current = new AbortController(); request = current; ready = false;
    $('signature-exclusion-status').textContent = '正在读取名单…'; $('retry-signature-exclusions').hidden = true; renderLists();
    try {
      const data = await getJSON('/api/signature-exclusions', current.signal);
      if (request !== current) return;
      accept(data); ready = true;
      $('signature-exclusion-status').textContent = '修改后会立即保存。';
    } catch (error) {
      if (error.name !== 'AbortError' && request === current) {
        $('signature-exclusion-status').textContent = '无法读取名单：' + error.message;
        $('retry-signature-exclusions').hidden = false;
      }
    } finally {
      if (request === current) { request = null; renderLists(); }
    }
  }
  async function update(dishId, excluded) {
    if (saving || !ready) return;
    request?.abort(); request = null; saving = true;
    $('signature-exclusion-status').textContent = '正在保存…'; renderLists();
    try {
      const response = await fetch('/api/signature-exclusions', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dish_id: dishId, excluded, expected_version: preferences().version }) });
      const data = await response.json();
      if (!response.ok) {
        if (data.exclusions) accept(data.exclusions);
        throw new Error(data.error || '保存失败');
      }
      accept(data); ready = true;
      $('signature-exclusion-status').textContent = excluded ? '已加入名单，仅从优选料理中排除。' : '已恢复推荐。';
    } catch (error) { $('signature-exclusion-status').textContent = error.message + '；可检查名单后重试。'; }
    finally {
      saving = false; renderLists();
      if ($('signature-exclusion-dialog').open) $('signature-exclusion-search').focus({ preventScroll: true });
    }
  }
  function init() {
    $('manage-signature-exclusions').addEventListener('click', () => {
      $('signature-exclusion-search').value = '';
      $('signature-exclusion-dialog').showModal(); renderLists(); load();
    });
    $('close-signature-exclusions').addEventListener('click', () => $('signature-exclusion-dialog').close());
    $('signature-exclusion-dialog').addEventListener('close', () => {
      if (!$('signature-exclusion-dialog').open) {
        request?.abort(); request = null;
        if (state.view === 'signature' && !document.querySelector('dialog[open]')) $('manage-signature-exclusions').focus({ preventScroll: true });
      }
    });
    $('signature-exclusion-search').addEventListener('input', renderLists);
    $('retry-signature-exclusions').addEventListener('click', load);
  }
  return { init, sync, accept };
})();
