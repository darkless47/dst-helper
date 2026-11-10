"""Server-shared signature display preferences; never modify cooking competition."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from .prediction import PredictionInputError

DEFAULTS = Path(__file__).resolve().parents[1] / 'data/signature_exclusions.default.json'


class ExclusionConflict(Exception):
    pass


class SignatureExclusions:
    def __init__(self, path, dish_ids):
        self.path = Path(path).resolve()
        self.dish_ids = frozenset(dish_ids)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            seed = json.loads(DEFAULTS.read_text(encoding='utf-8'))
            self._write(seed)
        self.snapshot()  # Invalid saved data must not be silently replaced with defaults.

    def _read(self):
        raw = self.path.read_bytes()
        data = json.loads(raw.decode('utf-8'))
        if (not isinstance(data, dict) or set(data) != {'schema_version', 'dish_ids'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1
                or not isinstance(data['dish_ids'], list)
                or any(not isinstance(item, str) for item in data['dish_ids'])
                or len(data['dish_ids']) != len(set(data['dish_ids']))):
            raise ValueError('Invalid signature exclusion preferences.')
        return data, hashlib.sha256(raw).hexdigest()

    def _write(self, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                             dir=self.path.parent, prefix='.signature-exclusions-', delete=False) as output:
                temporary = Path(output.name)
                output.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def snapshot(self):
        with self._lock:
            data, version = self._read()
            return dict(version=version, dish_ids=[item for item in data['dish_ids'] if item in self.dish_ids])

    def update(self, dish_id, excluded, expected_version):
        if not isinstance(dish_id, str) or dish_id not in self.dish_ids:
            raise PredictionInputError('请选择已收录的料理。')
        if type(excluded) is not bool:
            raise PredictionInputError('请明确选择排除或恢复推荐。')
        if not isinstance(expected_version, str):
            raise PredictionInputError('缺少有效的名单版本，请刷新后重试。')
        with self._lock:
            data, version = self._read()
            if version != expected_version:
                raise ExclusionConflict('其他用户已修改名单。已读取最新名单，请检查后重试。')
            ids = set(data['dish_ids'])
            if excluded:
                ids.add(dish_id)
            else:
                ids.discard(dish_id)
            if ids != set(data['dish_ids']):
                self._write(dict(schema_version=1, dish_ids=sorted(ids)))
            return self.snapshot()

    def filter(self, result):
        preferences = self.snapshot()
        excluded = set(preferences['dish_ids'])
        # Apply after full prediction/optimization: an excluded winner still suppresses
        # lower-priority recipes and still participates in uniform tie probabilities.
        groups = {key: [row for row in result[key] if row['dish_id'] not in excluded]
                  for key in ('special', 'other')}
        return dict(result, **groups, exclusion_version=preferences['version'],
                    excluded_dish_ids=preferences['dish_ids'])
