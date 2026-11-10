'use strict';

const rarityUI = (() => {
  function apply(snapshot, notify = true) {
    if (!state.data || snapshot.version < (state.data.settings?.version ?? -1)) return;
    const changed = snapshot.version !== state.data.settings?.version;
    state.data.settings = snapshot;
    state.data.ingredients.forEach(row => { row.rarity = snapshot.rarities[row.ingredient_id] ?? 0; });
    if (changed && notify) {
      renderResults(); signatureUI.rarityChanged(); examplesUI.rarityChanged();
    }
  }

  async function refresh(signal, notify = true) {
    const snapshot = await getJSON('/api/rarity', signal);
    apply(snapshot, notify);
    return snapshot;
  }

  function editor(row) {
    const input = el('input', { type: 'number', step: '1', min: '-2147483648', max: '2147483647',
      id: 'rarity-input', name: 'rarity', placeholder: '0', 'aria-label': row.name_zh + '的稀有度' });
    input.value = state.data.settings.rarities[row.ingredient_id] ?? '';
    const status = el('p', { class: 'small muted rarity-status', role: 'status', 'aria-live': 'polite' });
    const save = el('button', { type: 'submit', class: 'secondary', text: '保存稀有度' });
    const reset = el('button', { type: 'button', class: 'text-button', text: '恢复默认 0', onclick: () => saveValue(null) });
    let saving = false;
    const form = el('form', { class: 'rarity-editor', onsubmit: event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const raw = input.value.trim();
      saveValue(raw === '' ? null : Number(raw));
    } }, [el('label', {}, [text('span', '稀有度'), input]), save, reset]);
    async function saveValue(value) {
      if (saving) return;
      if (value !== null && (!Number.isInteger(value) || value < -2147483648 || value > 2147483647)) {
        status.textContent = '请输入有效的整数；可以为负数。'; return;
      }
      saving = true; save.disabled = true; reset.disabled = true; input.disabled = true;
      status.textContent = '正在保存…';
      try {
        const response = await fetch('/api/rarity', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ingredient_id: row.ingredient_id, rarity: value, expected_version: state.data.settings.version }) });
        const data = await response.json();
        if (!response.ok) {
          if (data.settings) apply(data.settings);
          throw new Error(data.error || '保存失败');
        }
        apply(data);
        input.value = data.rarities[row.ingredient_id] ?? '';
        status.textContent = value === null ? '已恢复默认稀有度 0。' : '已保存稀有度 ' + value + '，料理示例与优选排序将使用新值。';
      } catch (error) { status.textContent = error.message + '；尚未保存的输入仍保留。'; }
      finally { saving = false; save.disabled = false; reset.disabled = false; input.disabled = false; }
    }
    return section('稀有度 · 自定义', [form, status,
      text('p', '值越高越难获取，负数表示优先消耗；未设置按 0 计算，每份重复食材分别计分。设置保存在本机，并由本服务器的 LAN 用户共享。', 'small muted')]);
  }

  function edit(id) {
    openDetail('ingredient', id).then(() => {
      if ($('detail-dialog').open && $('detail-content').dataset.entityId === id && $('rarity-input')) {
        $('rarity-input').focus(); $('rarity-input').select();
      }
    });
  }
  return { apply, refresh, editor, edit };
})();
