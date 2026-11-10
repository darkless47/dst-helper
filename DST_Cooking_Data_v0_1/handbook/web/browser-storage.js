'use strict';

const browserStorage = (() => {
  function warn(message) {
    let notice = document.getElementById('browser-storage-warning');
    if (!notice) {
      notice = document.createElement('p');
      notice.id = 'browser-storage-warning'; notice.className = 'notice';
      notice.setAttribute('role', 'alert');
      document.querySelector('main').prepend(notice);
    }
    notice.textContent = message;
  }
  function write(key, value) {
    try { localStorage.setItem(key, JSON.stringify({ schema_version: 1, value })); }
    catch {
      const message = '浏览器无法保存数据（存储被禁用或空间不足）。当前更改尚未保存，关闭页面后可能丢失。';
      warn(message); throw new Error(message);
    }
  }
  function read(key, defaults, valid) {
    const fallback = () => JSON.parse(JSON.stringify(defaults));
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) { const value = fallback(); write(key, value); return value; }
      const saved = JSON.parse(raw);
      if (saved?.schema_version !== 1 || !valid(saved.value)) throw new Error('invalid');
      return saved.value;
    } catch {
      warn('无法读取浏览器保存的数据，当前使用默认值。原数据未被清除；请检查浏览器存储设置，或使用清空 / 重置重新开始。');
      return fallback();
    }
  }
  return { read, write, warn };
})();
