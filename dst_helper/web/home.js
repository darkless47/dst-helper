'use strict';

(async () => {
  const value = item => item == null || item === '' ? '未知' : String(item);
  try {
    const response = await fetch('/api/catalog');
    if (!response.ok) throw new Error('Metadata unavailable');
    const { metadata } = await response.json();
    document.getElementById('target-build').textContent = value(metadata.target_build);
    document.getElementById('evidence-level').textContent = metadata.verification === 'single_wiki_snapshot'
      ? '单一维基快照' : value(metadata.verification);
    const compatibility = metadata.build_compatibility === 'unconfirmed'
      ? '版本兼容性未确认' : '版本核验状态：' + value(metadata.build_compatibility);
    document.getElementById('revision').textContent = '烹饪修订 ' + value(metadata.source_revision) + ' · ' + compatibility;
  } catch {
    document.getElementById('revision').textContent = '资料信息暂不可用';
    document.getElementById('home-metadata-error').hidden = false;
  }
})();
