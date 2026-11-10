"""Editable server-wide preferences, separate from the immutable wiki snapshot."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock

from .prediction import PredictionInputError

DEFAULT_SETTINGS = Path(__file__).resolve().parents[1] / '.local' / 'user_settings.sqlite'
MIN_RARITY, MAX_RARITY = -2147483648, 2147483647


class SettingsConflict(Exception):
    pass


class UserSettings:
    def __init__(self, path, ingredient_ids):
        self.path = Path(path).resolve()
        self.ingredient_ids = frozenset(ingredient_ids)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError('Settings path must reference a settings database, not content.')
                migration = Path(__file__).resolve().parents[1] / 'migrations/settings/001_rarity.sql'
                db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text(encoding='utf-8') + '\nCOMMIT;')
            elif version != 1:
                raise ValueError('Unsupported settings schema.')
            columns = [row[1] for row in db.execute('PRAGMA table_info(ingredient_preferences)')]
            revision_columns = [row[1] for row in db.execute('PRAGMA table_info(settings_revision)')]
            if columns != ['ingredient_id', 'rarity'] or revision_columns != ['singleton', 'revision']:
                raise ValueError('Settings file does not contain the expected preferences schema.')
            if db.execute('SELECT revision FROM settings_revision WHERE singleton=1').fetchone() is None:
                raise ValueError('Settings revision is missing.')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self):
        with self._lock, self.connect() as db:
            db.execute('BEGIN')
            version = db.execute('SELECT revision FROM settings_revision WHERE singleton=1').fetchone()[0]
            rarities = {key: value for key, value in db.execute('SELECT ingredient_id, rarity FROM ingredient_preferences')
                        if key in self.ingredient_ids}
            return dict(version=version, rarities=rarities)

    def update(self, ingredient_id, rarity, expected_version):
        if not isinstance(ingredient_id, str) or ingredient_id not in self.ingredient_ids:
            raise PredictionInputError('请选择已收录的食材状态。')
        if rarity is not None and (type(rarity) is not int or not MIN_RARITY <= rarity <= MAX_RARITY):
            raise PredictionInputError('稀有度须为 -2147483648 到 2147483647 的整数；留空恢复默认 0。')
        if type(expected_version) is not int or expected_version < 0:
            raise PredictionInputError('缺少有效的设置版本，请刷新后重试。')
        with self._lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('SELECT revision FROM settings_revision WHERE singleton=1').fetchone()[0]
            if expected_version != version:
                raise SettingsConflict('其他用户已修改设置。已读取最新值，请检查后再次保存。')
            old = db.execute('SELECT rarity FROM ingredient_preferences WHERE ingredient_id=?', (ingredient_id,)).fetchone()
            if (old[0] if old else None) != rarity:
                if rarity is None:
                    db.execute('DELETE FROM ingredient_preferences WHERE ingredient_id=?', (ingredient_id,))
                else:
                    db.execute('INSERT INTO ingredient_preferences VALUES(?,?) ON CONFLICT(ingredient_id) DO UPDATE SET rarity=excluded.rarity',
                               (ingredient_id, rarity))
                db.execute('UPDATE settings_revision SET revision=revision+1 WHERE singleton=1')
        return self.snapshot()
