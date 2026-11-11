# DST Cooking Data — initial Huiji snapshot, v0.1.0

This package contains a populated SQLite database, normalized JSON, a repeatable importer, and the Cooking application. It is an unofficial fan project, not affiliated with Klei.

## Run the local handbook

From the **workspace root** (the parent of this data-package directory), use:

```powershell
python dst_helper --host localhost --port 8765
python dst_helper --host 192.168.1.50 --port 8765
```

The first command is local-only at **http://localhost:8765**; the second shares at
**http://192.168.1.50:8765**. Choose one as needed. `localhost` binds explicitly to
`127.0.0.1`; a private IP binds that interface. Ctrl+C stops a foreground server.
The older entry point below still works when running from this package directory.

The application includes a read-only Chinese wiki catalog, editable ingredient rarity,
experimental wiki-based exact-pot prediction, **优选料理** discovery, and pictured dish examples.
The app requires Python 3.11+ and the pinned Starlette/Uvicorn dependencies in
`../requirements.txt`. Install them into your virtual environment before running:

```bash
python -m pip install -r ../requirements.txt
```

No Node build or runtime network access is required. See `../DEPLOYMENT.md` for Docker
and Nginx setup; all existing entry points use Uvicorn.

```bash
python run_handbook.py
```

Open **http://127.0.0.1:8765** in a browser. Stop with Ctrl+C. Use `--port 8766` if the default port is occupied.
You can run the script by absolute path from any working directory. `--database path/to/content.sqlite`
selects a replacement content snapshot conforming to schema v1.

### Share on the LAN

To serve this prototype to devices on your LAN using this computer's private IP:

```powershell
python run_handbook.py --host 192.168.1.50 --port 8765
```

Your friend can open **http://192.168.1.50:8765** while the server is running and this
computer is connected to the LAN. The `--host` flag binds the requested interface;
the default remains `127.0.0.1` for local use. Update the address if your LAN IP changes.
Windows Firewall must allow inbound TCP 8765 from the local subnet for that interface.
Images, APIs, and predictions use relative URLs and work at the LAN address.

For this Windows setup, the rule can be created in **PowerShell as Administrator**
with the native firewall command (no script-execution-policy changes needed):

```powershell
$pythonExecutable = (Get-Command python).Source
netsh advfirewall firewall add rule name="DST Handbook LAN (TCP 8765)" dir=in action=allow profile=private protocol=TCP localport=8765 localip=192.168.1.50 remoteip=192.168.1.0/24 interfacetype=wireless program="$pythonExecutable" enable=yes
```

It allows only the selected Python executable, TCP 8765, local address `192.168.1.50`,
wireless interfaces, Private network profile, and remote subnet `192.168.1.0/24`. It leaves
the firewall enabled. To remove that rule later, run in administrator PowerShell:

```powershell
Remove-NetFirewallRule -DisplayName 'DST Handbook LAN (TCP 8765)'
```

The configured background LAN listener records its process ID in `.local/lan-server.json`
and writes logs to `.local/lan-server.stdout.log` and `.local/lan-server.stderr.log`.
It runs alongside an existing localhost listener and needs to be restarted after a reboot.

Search Chinese labels, provisional English hints, or IDs; sort and filter dish table values;
explore the 15 captured ingredient tags. Cards and detail views show local ingredient/dish
portraits, and dish stats include HP, hunger, and sanity meter icons. Each detail view includes
snapshot source rows, raw cell evidence, review issues, and image provenance records.
Composite values remain source text, missing values remain unknown, and both nutrition-brick
states are retained. Finished food types and edible/wearable/animal classifications remain
unconfirmed; displayed table stats are not character-effective benefits.

Use **卡片 / 表格** beside the dish or ingredient count to switch between the original cards and a dense
table. Both layouts share the current search, filters, and sort order. The table includes
pictures, names, HP, hunger, sanity, perishability, cooking time, priority, and cooker hints;
click a dish name or row to open its full details. Headers and dish names stay visible while
scrolling, and smaller screens can scroll horizontally within the table. The ingredient table
puts rarity immediately after the ingredient name, followed by all 15 captured tag contributions;
state IDs/prefabs are kept in the last column. The table preserves
fractional values and explicit zeroes for blank captured cells. Each state has its own row and
detail link. Dish and ingredient layout choices are remembered independently in this browser; if browser storage is
unavailable, switching still works for the current session.

The server defaults to loopback with optional LAN binding, serves an explicit static-file allowlist, and opens the
SQLite content with `mode=ro` and `query_only`. Display preferences use browser localStorage.
Editable rarities and exclusions use separate browser localStorage keys, isolated between browsers.
New browsers receive the tracked `data/ingredient_rarities.default.json` and
`data/signature_exclusions.default.json` values. `--settings <json>` and `--exclusions <json>`
select alternative read-only default files. Clear-all controls persist empty values; defaults
do not return on reload. The wiki database stays unchanged. No user preferences are saved by the server. The **出锅预测** view accepts exactly four
recorded ingredient states, including duplicates, and predicts highest-priority outcomes with
equal chances among ties. It supports ordinary and portable pot profiles with disclosed
eligibility assumptions. **优选料理** searches completions containing one selected ingredient:
all named recipes appear first with a **特别** tag, followed by five general recipes at a time.
**易获取优先** is the default: minimum total rarity for the other three slots, then the chosen
hunger/HP/sanity value. **营养优先** reverses these criteria. Each card includes a minimum-cost
checked example pot that can be loaded into the predictor.

In **食材探索**, click a table's **稀有度** value or open any ingredient detail to edit a signed
integer; unset/blank values count as zero. A negative value means prefer consuming that state.
Dish details include **料理示例** just after **配方条件**: the three cheapest distinct
four-item combinations, with small ingredient pictures, total rarity, and outcome probability.
Uncertain outcomes have a yellow probability badge. **只显示确定配方**, beside the cooker
selector, searches for the cheapest 100% combinations and remembers the choice in this
browser across dishes and reloads. Fewer than three guaranteed combinations are disclosed.
Hover or focus a picture for its name; click it to open that exact state in **食材探索**.
Cooked/roasted/dried states are excluded unless explicitly required without a listed raw
alternative. Fewer than three possible combinations are disclosed rather than duplicated.
See `PREDICTION.md`, `SIGNATURE_RECIPES.md`, and `RARITY_AND_EXAMPLES.md`.

The target-build and evidence summary appears on **助手首页**. Cooking's sidebar lists
four functions; open **数据与边界** from the button beside **非官方 · 本地手册** for
the full source/limitations page. The snapshot-version badge and prediction-status summary
are omitted from Cooking's header; the underlying metadata and predictor behavior stay intact.

Dish details keep **表格记录** concise: **更多...** reveals tie selection, extra probability
weight, finished food type, game prefab, and provisional dish ID. **配方条件** has its own
**更多...** for parser/readiness metadata and the review AST. The **⚠** button beside
the wiki-status badge opens the nutrition caveat in a dismissible bubble. These display
changes preserve the original draft metadata and numerical interpretation.
In dish and ingredient details, **来源与证据** is collapsed by default. Click its heading
to expand the complete source records, original cells, links, hashes, and image provenance.

Use **管理不考虑名单** in **优选料理** to add or restore excluded suggestions. Initially
蒸树枝、潮湿黏糊、怪物千层饼 are excluded. Changes save immediately in this browser.
**清空全部排除名单** removes every exclusion; **清空全部稀有度** resets ingredient costs to zero.
These actions are independent and do not reset Farming. This filter affects only signature recommendations; prediction, cooking
competition/probabilities, ingredient exploration, dish catalog, and dish examples use
the complete dataset. Removing every entry stays empty across restarts.
The AST module validates grammar and renders explanations; `handbook/prediction.py` evaluates
the supported conditions separately from the UI and ingestion helpers.
Readiness flags, NULL weights, IDs, and the content schema are unchanged. No database migration
is necessary for these catalog and image increments. No images are downloaded from the
internet or published.

### Local pictures

The app automatically reads the committed PNGs from `../assets/images/`.
A fresh checkout includes all runtime pictures; `wiki-webpage-save/` is not needed
to run the app. All 226 catalog images match the
existing database hashes; the three meter icons are indexed separately in `data/stat_icons.json`
with their saved-page references, original candidate URLs, and SHA-256 hashes.

To use another image directory or an original archive location:

```bash
python run_handbook.py --assets "path/to/assets/images"
```

Only known, hash-matched PNG files are served, by an explicit URL allowlist. The saved HTML,
scripts, unrelated files, and directory listings are never served. Runtime files use stable
asset-ID filenames; original saved-page references remain unchanged as provenance.
Verified image bytes are loaded on
startup; restart the server after replacing the archive. Missing or mismatched images fall back
to text while the catalog remains usable. No images need to be installed for text-only use.
Artwork redistribution flags remain unconfirmed/false in the content records.

To regenerate the packaged images from the matching private archive:

```bash
python scripts/package_assets.py ../wiki-webpage-save
```

The source archive remains ignored by Git. Keep its original HTML and PNG files
in their original `_files` paths for source audits and re-extraction; saved website
scripts, styles, and analytics files are not needed.

The meter-icon index is repeatable from the same saved HTML:

```bash
python scripts/index_stat_icons.py "path/to/wiki-webpage-save/saved-page.html"
```

The indexer requires the HTML to match the source hash in the content dataset. It reads the
page as data and never executes its scripts. This supplementary index does not change the
content schema, data verification level, or solver readiness.

Application layout:

- `handbook/catalog.py`: read-only SQLite queries, metadata, and row evidence.
- `handbook/assets.py`: hash-checked packaged/archive images and image provenance.
- `handbook/rules.py`: strict declarative AST validation and Chinese descriptions, independent of UI.
- `handbook/prediction.py`: four-item prediction, exact tag arithmetic, priority competition, and probabilities.
- `handbook/signature.py`: complete one-ingredient search with minimum additional rarity and priority-aware feasibility.
- `handbook/examples.py`: three cheapest distinct dish examples and bounded caches keyed by request rarity values.
- `handbook/settings.py`: read-only JSON rarity defaults and validation of request rarity values.
- `handbook/exclusions.py`: read-only JSON default exclusions; the browser filters displayed suggestions.
- `data/prepared_ingredients.json`: explicit 57-state prepared-form selection policy with source-row references.
- `data/prediction_policy.json`: user-confirmed selection/grouping rules and explicit cooker assumptions.
- `handbook/server.py`: local/LAN server, read-only content/search APIs, and same-origin stateless calculations.
- `handbook/web/`: responsive UI with no external assets or libraries.
- `tests/test_handbook.py`: independent grammar fixtures, content contracts, and HTTP checks.
- `tests/test_assets.py`: file containment, image integrity, graceful fallback, and archive coverage.
- `tests/test_signature.py`: brute-force reference comparisons, special/general classification, witnesses, and HTTP contracts.
- `tests/test_rarity_examples.py`: independent exhaustive cost references, negative costs, prepared forms, preference-isolated caches, and stateless HTTP calculations.
- `tests/test_signature_exclusions.py`: read-only default validation and full cooking competition despite display exclusions.

Run validation from this directory:

```bash
python scripts/validate_dataset.py
python -m unittest discover -s tests -v
```

The ingestion scripts explicitly use UTF-8 so Chinese data rebuilds on Windows as well as Unix.
The application tests cover read-only enforcement, NULL preservation, distinct ingredient states,
AST rejection, source evidence for every record, Unicode HTTP access, and blocked file/write routes.
Media checks cover missing, modified, and non-PNG files; archive containment; frozen verified
bytes; all 226 pictures; distinct nutrition-brick artwork; and the reproducible meter-icon index.
Packaged-image checks always run. Source-archive integration checks skip when the
optional saved-page folder is absent.
They do not establish actual cooking results or current-build compatibility.

`APP_VALIDATION_REPORT.json` records historical application checks separately from the
original extraction report. These dated reports are retained as evidence; rerun the
checks above to validate the current checkout. Obsolete package checksum manifests
have been removed; source and image hashes remain in the curated data and audit records.

The November 8 recipe verification is documented in `RECIPE_VERIFICATION.md`, with all
81 recipe comparisons in `RECIPE_CAPTURE_AUDIT.json`. Run `python scripts/audit_recipe_capture.py`
to compare the matching saved HTML with SQLite independently of the original extractor.
Fractional-boundary and boolean-grouping fixtures are in `tests/test_recipe_audit.py`.
Run `python scripts/validate_signature.py` to replay all discovered examples for all 145 states
and both cookers; its record is in `SIGNATURE_VALIDATION_REPORT.json`. This checks model
consistency and does not claim independent in-game verification.
Run `python scripts/validate_examples.py` for all 81 dishes in both cookers under zero
and signed custom rarity scenarios; see `EXAMPLES_VALIDATION_REPORT.json`.

## Start here

1. Run the integrated app using the workspace-root README.
2. Inspect `DATA_DICTIONARY.md` and the database before changing the curated data.
3. Open `dst_cooking.sqlite` in DB Browser for SQLite if you want to inspect the tables yourself.
4. Run `python scripts/validate_dataset.py` (Python 3.10+) to validate extraction and a fresh rebuild. This uses only Python's standard library.

To rebuild offline from the included data:

```bash
python scripts/build_database.py --output rebuilt.sqlite
```

The builder refuses to overwrite an existing destination unless `--overwrite` is supplied. Never point it at a database containing user inventory, settings, or history.

To re-extract the original saved page, install `lxml` and supply the HTML path from your original ZIP:

```bash
python -m pip install -r requirements-extraction.txt
python scripts/extract_snapshot.py "path/to/saved.html" --output data/snapshot.json
python scripts/build_database.py --output refreshed.sqlite
python scripts/validate_dataset.py
```

The extractor intentionally checks the known source row counts. A different wiki snapshot may need reviewed changes to the parser and regression expectations. It never runs JavaScript from the saved page.

## Contents and coverage

| Item | Coverage |
|---|---|
| Ingredient records | 145 wiki rows; 144 distinct wiki-reported prefab IDs |
| Ingredient tag vocabulary | 15 table columns; only nonzero values stored |
| Dish records and priorities | 81 |
| Recipe predicates | 81 machine-parsed draft ASTs; all require semantic review |
| Portable-only recipe hints | 11 |
| Asset evidence records | 226 distinct local references used by the two data tables; runtime PNGs in `../assets/images/` |
| Source-derived AST regression checks | 18; these are individual predicate tests, not actual pot outcomes |
| Game-build / in-game verification | None |

Source: Huiji DST cooking page, https://dontstarve.huijiwiki.com/wiki/%E7%83%B9%E9%A5%AA, wiki revision 193291. User-supplied saved HTML received November 7, 2026; original HTML SHA-256 is in `dataset_metadata`. Exact retrieval time is unknown. The original source ZIP remains the evidence archive; this package includes extracted cell text, image labels/references, and links rather than the original site scripts and ancillary files.

Target installed build: 762172, reported by the user. The reported version-file modification time is November 5, 2026, 23:32 America/New_York (UTC-05:00). This identifies the user's target; it does not prove the wiki reflects that build.

## Important limits

This is not an in-game-verified cooking simulator database. Every recipe retains `solver_ready=0`.
The November 8 audit confirms source transcription; the user confirmed maximum-priority selection,
uniform ties, and shared counting of explicitly listed forms. The wiki's `优先级` is fully populated
in `recipe_rules.priority`. The separate nullable `weight` field describes potential relative
probability weights, not that priority column, and is unnecessary for uniform ties. Exact-pot
prediction is labeled experimental because per-cooker ingredient eligibility and current-build
compatibility remain unverified. See `RECIPE_VERIFICATION.md` and `PREDICTION.md`.

Dish game-prefab IDs are absent and remain NULL. `huiji:<Chinese page title>` IDs are explicitly provisional wiki keys. Ingredient prefab IDs are extracted from table sort metadata and remain wiki-sourced. English name hints come from image filenames and are not confirmed official localization. Preserve these distinctions.

The nutrition brick appears in two states with the same prefab. Both rows are preserved; one has a `@wiki_state_` suffix in its dataset ID. That suffix is not a game prefab. Counts for named-item predicates use `prefab_id`; selected state records determine tag contributions. Do not merge all future state-dependent data based on prefab alone.

Jellybeans health is reported as `122(2+120)` and Soothing Tea sanity as `45(15+30)`. Their corresponding immediate base-value fields remain NULL. Confirm timing, components, and conditions from detail pages. Milkmade Hat and animal foods also need type-specific interpretation; a numerical table entry alone is not proof of a player on-eat benefit.

Missing: confirmed dish prefab mapping; finished food types; character mechanics; detailed special effects; spices; output quantities; exact ingredient/cooker eligibility; full cooker/recipe matrix; independently verified example pots. No farming mechanics included. The prose mentions a preprocessed tag not included in the table; do not assume the 15 columns cover all game tags.

## Provenance and artwork

Each row records source ID and table row number. `source_rows` retains cell evidence and source links. `assets` retains saved-file references, hashes, and original srcset candidates (including resolution descriptors). Runtime PNGs are packaged separately in `../assets/images/`; `redistributable=0` still means permission has not been established. The original saved archive remains optional source material for inspection and audits.

Earlier project research reports Huiji text as CC BY-NC-SA 3.0 unless otherwise specified; this package does not claim a fresh license audit. Retain source attribution, confirm the applicable license and notices before distribution, and assess game-art rights separately. Do not treat this database or bundled original code as universally licensed game data. No Klei scripts are bundled.
