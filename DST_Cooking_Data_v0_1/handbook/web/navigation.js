'use strict';

// Same-document history: keep the address unchanged and store reading state per entry.
const cookingNavigation = (() => {
  const KEY = 'dstCookingNavigation';
  const controls = ['search', 'sort', 'cooker', 'stat-filter', 'tag-filter', 'tag-min',
    'signature-search', 'signature-ranking', 'signature-sort', 'prediction-search', 'prediction-cooker'];
  const snapshots = new Map();
  let current = null, generation = 0, traveling = false, restoring = false;
  const queued = [];
  const rarityKey = () => JSON.stringify(Object.entries(state.data.settings.rarities).sort(([a], [b]) => a.localeCompare(b)));

  function focusPath() {
    let element = document.activeElement;
    const parts = [];
    while (element && element !== document.body) {
      if (element.id) { parts.unshift('#' + CSS.escape(element.id)); break; }
      const siblings = [...element.parentElement.children].filter(node => node.tagName === element.tagName);
      parts.unshift(element.tagName.toLowerCase() + ':nth-of-type(' + (siblings.indexOf(element) + 1) + ')');
      element = element.parentElement;
    }
    return parts.join(' > ');
  }
  function capture() {
    return {
      view: state.view,
      controls: Object.fromEntries(controls.map(id => [id, $(id).value])),
      layouts: { ...state.layouts },
      rarityKey: rarityKey(),
      signature: signatureUI.snapshot(), prediction: predictionUI.snapshot(),
      detail: state.detail ? { ...state.detail, examples: examplesUI.snapshot() } : null,
      expanded: [...document.querySelectorAll('#detail-content details')].map(node => node.open),
      scroll: [...document.querySelectorAll('[id]')].filter(node => node.scrollTop || node.scrollLeft)
        .map(node => [node.id, node.scrollLeft, node.scrollTop]),
      windowScroll: [window.scrollX, window.scrollY], focus: focusPath(),
    };
  }
  function remember(replace = true) {
    if (!current || restoring) return;
    current.snapshot = capture();
    snapshots.set(current.id, current.snapshot);
    if (replace) history.replaceState({ ...history.state, [KEY]: current }, '');
  }
  function entry(index, base, snapshot) {
    return { version: 1, id: Date.now().toString(36) + Math.random().toString(36).slice(2), index, base, snapshot };
  }
  function go(action) {
    if (traveling) return new Promise((resolve, reject) => queued.push(() => {
      Promise.resolve(go(action)).then(resolve, reject);
    }));
    if (!current) return action();
    remember();
    const previous = current;
    restoring = false;
    const result = action();
    // Section changes start a new base; a chain of details shares its original section.
    const index = previous.index + 1;
    const base = state.detail ? (previous.snapshot.detail ? previous.base : previous.index) : index;
    current = entry(index, base, capture());
    snapshots.set(current.id, current.snapshot);
    history.pushState({ [KEY]: current }, '');
    generation++;
    return result;
  }
  async function restore(snapshot) {
    const token = ++generation;
    restoring = true;
    dismissDetail();
    if ($('signature-exclusion-dialog').open) $('signature-exclusion-dialog').close();
    for (const [id, value] of Object.entries(snapshot.controls)) $(id).value = value;
    state.layouts = { ...snapshot.layouts };
    // Restoring a screen must not reuse calculations from different saved preferences.
    const sameRarities = snapshot.rarityKey === rarityKey();
    signatureUI.restore(sameRarities ? snapshot.signature : { ...snapshot.signature, result: null, error: null });
    predictionUI.restore(snapshot.prediction);
    renderView(snapshot.view);
    if (snapshot.detail) {
      const { kind, id } = snapshot.detail;
      const detail = sameRarities ? snapshot.detail : { ...snapshot.detail,
        examples: snapshot.detail.examples ? { ...snapshot.detail.examples, data: null } : null };
      await showDetail(kind, id, detail);
    }
    if (token !== generation) return;
    document.querySelectorAll('#detail-content details').forEach((node, index) => {
      node.open = snapshot.expanded[index] || false;
    });
    // Let freshly rendered examples/layout finish before restoring the reading position.
    await new Promise(resolve => requestAnimationFrame(resolve));
    if (token !== generation) return;
    if (snapshot.focus) document.querySelector(snapshot.focus)?.focus({ preventScroll: true });
    for (const node of document.querySelectorAll('[id]')) {
      if (node.scrollTop || node.scrollLeft) node.scrollTo({ left: 0, top: 0, behavior: 'instant' });
    }
    for (const [id, x, y] of snapshot.scroll) $(id)?.scrollTo({ left: x, top: y, behavior: 'instant' });
    window.scrollTo({ left: snapshot.windowScroll[0], top: snapshot.windowScroll[1], behavior: 'instant' });
    restoring = false;
  }
  function initialize() {
    if (current) return true;
    history.scrollRestoration = 'manual';
    const saved = history.state?.[KEY];
    if (saved?.version === 1 && Object.hasOwn(copy, saved.snapshot?.view)) {
      current = saved;
      restore(saved.snapshot);
      return true;
    }
    current = entry(0, 0, capture());
    remember();
    return false;
  }
  function closeDetail() {
    if (!state.detail || traveling) return;
    if (current && current.base < current.index) {
      traveling = true;
      history.go(current.base - current.index);
    } else {
      dismissDetail(); remember();
    }
  }
  window.addEventListener('popstate', async event => {
    const target = event.state?.[KEY];
    if (!current || target?.version !== 1) return;
    // The browser has already moved, so retain the departing state in memory only.
    remember(false);
    current = target;
    const snapshot = snapshots.get(target.id) || target.snapshot;
    try { await restore(snapshot); }
    finally {
      if (current.id === target.id) {
        traveling = false;
        for (const action of queued.splice(0)) action();
      }
    }
  });
  window.addEventListener('pagehide', () => { if (!traveling) remember(); });
  return { initialize, go, closeDetail };
})();
