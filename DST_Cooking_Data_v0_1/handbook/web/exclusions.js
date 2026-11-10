'use strict';

const signatureExclusionsUI = (() => {
  let ready = false, defaults;
  const KEY = 'dst-helper.cooking.exclusions.v1';
  const valid = ids => Array.isArray(ids) && new Set(ids).size === ids.length &&
    ids.every(id => typeof id === 'string' && state.data.dishes.some(d => d.dish_id === id));
  function initialize() {
    defaults = [...preferences().dish_ids];
    accept({ version: 1, dish_ids: browserStorage.read(KEY, defaults, valid) }, false);
    ready = true;
  }
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
    button.disabled = !ready;
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
  function load() {
    accept({ version: preferences().version + 1, dish_ids: browserStorage.read(KEY, defaults, valid) });
    ready = true; renderLists();
    $('signature-exclusion-status').textContent = '修改后立即保存在当前浏览器。';
  }
  function save(ids) {
    try {
      browserStorage.write(KEY, ids);
      accept({ version: preferences().version + 1, dish_ids: ids });
      $('signature-exclusion-status').textContent = '已保存在当前浏览器。';
    } catch (error) { $('signature-exclusion-status').textContent = error.message; }
    renderLists();
  }
  function update(dishId, excluded) {
    const ids = new Set(browserStorage.read(KEY, preferences().dish_ids, valid));
    if (excluded) ids.add(dishId); else ids.delete(dishId);
    save([...ids]);
  }
  window.addEventListener('storage', event => {
    if (state.data && (event.key === KEY || event.key === null)) load();
  });
  function init() {
    $('manage-signature-exclusions').addEventListener('click', () => {
      $('signature-exclusion-search').value = '';
      $('signature-exclusion-dialog').showModal(); renderLists(); load();
    });
    $('close-signature-exclusions').addEventListener('click', () => $('signature-exclusion-dialog').close());
    $('signature-exclusion-search').addEventListener('input', renderLists);
    $('clear-signature-exclusions').addEventListener('click', () => save([]));
  }
  return { init, initialize, sync, accept };
})();
