CREATE TABLE ingredient_preferences (
    ingredient_id TEXT PRIMARY KEY,
    rarity INTEGER NOT NULL CHECK(typeof(rarity)='integer' AND rarity BETWEEN -2147483648 AND 2147483647)
);
CREATE TABLE settings_revision (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL);
INSERT INTO settings_revision VALUES(1, 0);
PRAGMA user_version=1;
