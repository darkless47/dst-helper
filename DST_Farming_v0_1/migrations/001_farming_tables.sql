-- Additive farming namespace. Safe to apply to a standalone data DB or integrate
-- through the host application's own migration runner. No host user_version writes.
PRAGMA foreign_keys=ON;
CREATE TABLE farming_schema_migrations(version INTEGER PRIMARY KEY,description TEXT NOT NULL);
INSERT INTO farming_schema_migrations VALUES(1,'Wiki-based farming static-planner dataset v0.1');
CREATE TABLE farming_metadata(key TEXT PRIMARY KEY,value_json TEXT NOT NULL CHECK(json_valid(value_json)));
CREATE TABLE farming_sources(source_id INTEGER PRIMARY KEY,url TEXT NOT NULL,revision TEXT,received_date TEXT NOT NULL,sha256 TEXT NOT NULL,verified_game_build TEXT,evidence_level TEXT NOT NULL);
CREATE TABLE farming_assets(asset_id TEXT PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES farming_sources,reference_json TEXT NOT NULL CHECK(json_valid(reference_json)),redistributable INTEGER NOT NULL DEFAULT 0 CHECK(redistributable IN(0,1)));
CREATE TABLE farming_plants(plant_id TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN('crop','weed')),product_ingredient_id TEXT,plant_prefab_id TEXT,seed_prefab_id TEXT,name_zh TEXT NOT NULL,plant_name_zh TEXT NOT NULL,name_en_hint TEXT,seed_name_en_hint TEXT,growth_formula_delta INTEGER NOT NULL,compost_delta INTEGER NOT NULL,manure_delta INTEGER NOT NULL,water_percent_points_per_stage REAL NOT NULL CHECK(water_percent_points_per_stage>=0),water_source_text TEXT NOT NULL,plant_asset_id TEXT REFERENCES farming_assets,seed_asset_id TEXT REFERENCES farming_assets,product_asset_id TEXT REFERENCES farming_assets,source_url TEXT NOT NULL,source_row INTEGER NOT NULL,source_id INTEGER NOT NULL REFERENCES farming_sources,verification_status TEXT NOT NULL);
CREATE TABLE farming_seasons(plant_id TEXT NOT NULL REFERENCES farming_plants,season TEXT NOT NULL CHECK(season IN('autumn','winter','spring','summer')),preferred INTEGER NOT NULL CHECK(preferred IN(0,1)),random_seed_percent REAL NOT NULL CHECK(random_seed_percent BETWEEN 0 AND 100),source_id INTEGER NOT NULL REFERENCES farming_sources,PRIMARY KEY(plant_id,season));
CREATE TABLE farming_mechanics(rule_id TEXT PRIMARY KEY,value_json TEXT NOT NULL CHECK(json_valid(value_json)),source_section TEXT NOT NULL,note TEXT NOT NULL,source_id INTEGER NOT NULL REFERENCES farming_sources,verification_status TEXT NOT NULL);
CREATE TABLE farming_row_evidence(plant_id TEXT PRIMARY KEY REFERENCES farming_plants,cells_json TEXT NOT NULL CHECK(json_valid(cells_json)),source_id INTEGER NOT NULL REFERENCES farming_sources);
CREATE TABLE farming_section_evidence(section_id INTEGER PRIMARY KEY,heading TEXT NOT NULL,paragraphs_json TEXT NOT NULL CHECK(json_valid(paragraphs_json)),source_id INTEGER NOT NULL REFERENCES farming_sources);
CREATE TABLE farming_review_issues(code TEXT PRIMARY KEY,details TEXT NOT NULL);
CREATE INDEX farming_idx_kind ON farming_plants(kind);
CREATE INDEX farming_idx_season ON farming_seasons(season,preferred);
