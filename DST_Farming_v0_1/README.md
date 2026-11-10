# DST Helper — Farming Data v0.1.0

This package supplies the curated data and calculation helpers for **Garden / Farming Planner (种植规划)** in `dst_helper`. It does not modify the cooking database.

## Use in this repository

1. Run `python dst_helper` from the workspace root and open `/farming`.
2. Read `DATA_DICTIONARY.md`, `UI_SPEC.md`, and the reference review before changing planner behavior. The workspace-root README describes the integrated application's current behavior.
3. The app reads `data/farming.json` as its authoritative snapshot. `farming.sqlite` is a packaged, rebuildable copy for inspection. Keep user plans in the separate `.local/` store.

The saved wiki archive is optional private source material excluded from Git. Keep
the original HTML and PNG paths locally for re-extraction. Dated validation and
reference reports remain as evidence; rerun the tests for the current checkout.
Obsolete implementation prompts, package checksum lists, and saved test-console
output have been removed after integration.

## Data and evidence

| Included | Coverage |
|---|---|
| Crop species | 14 |
| Weeds | 4; excluded from crop-ratio recommendations |
| Preferred seasons | All four seasons for all 18 plant records |
| Nutrients | Three signed changes per growth stage |
| Random-seed appearance rates | Rounded source percentages; separate from preferred-season flags |
| Water demand | Source percentage per stage, preserved with original text |
| Structured mechanics | 16 records covering seven stress sources and giant eligibility |
| Image references | 49; provenance and hashes, no game-art files bundled |
| Example planting layouts | Two, with per-tile nutrient and geometric family checks |
| Tests | 30 automated checks |
| Reference comparison | 14 crop records and all 16 season filter subsets match |

Source: user-saved Huiji **耕种** page, revision **203373**, received November 9, 2026. Exact original save/retrieval timestamp is unknown. The original uploaded ZIP remains the snapshot archive; normalized row evidence and relevant prose sections are included in JSON and SQLite. Source HTML hash and source URLs are recorded.

Last reported installed build: **762172**. It was not reconfirmed for this collection, and neither the wiki nor this package has been verified in that game build. This does not prevent use of the disclosed wiki-based planner.

The requested example, https://hzhangxyz.github.io/dst-farming/, was accessible by HTTP on November 9, 2026. Its HTML and embedded app behavior were inspected. Our original implementation reproduces its bounded search behavior; no browser-render or actual game verification is claimed. See REFERENCE_REVIEW.md and REFERENCE_COMPARISON.json.

## Run and rebuild (Python 3.10+)

```bash
python -m unittest discover -s tests -v
python scripts/planner_core.py
python scripts/build_database.py --output rebuilt_farming.sqlite
```

Normal use and rebuild need only Python's standard library. Re-extracting the user's original HTML needs `lxml`:

```bash
python -m pip install -r requirements-extraction.txt
python scripts/extract_snapshot.py "path/to/saved_farming.html"
python scripts/build_database.py --output refreshed_farming.sqlite
```

The builder refuses to overwrite an existing destination without `--overwrite` and stages the replacement in a temporary file. Never point it at the host's cooking database or user-history database. `migrations/001_farming_tables.sql` uses a farming namespace and a separate migration table; integrate with the host migration runner if consolidating databases later. It does not write the host `PRAGMA user_version`.

## What this planner can do now

- Filter crops that prefer **all** selected seasons; no selection means no season filter.
- Exclude unavailable seeds; optionally limit results by seed counts.
- Find exact nutrient-balanced two- and three-species ratios with primitive coefficients 1 or 2, matching the example site.
- Scale a ratio into whole-number seed requirements and show an area lower bound.
- Analyze supplied 3x3 planting grids: nutrients per tile, same-crop neighbors within four game units, season compatibility, and known weed hazards.
- Track a stress interval from user-supplied stage history without treating unknown conditions as satisfied.

## What a ratio does not establish

Nutrients are stored per tile, not shared across the whole farm. A zero-sum vector is a static balance statement: insufficient starting stock, nutrient caps, or asynchronous growth can still cause stress. Positive nutrient output depends on actual consumption. Do not equate zero net change with guaranteed nutrient availability.

Family checks use positions, not total counts or tile adjacency alone. On the default 3x3 grid, a 6:3 composition can be nutrient-balanced while its three minority plants lack enough family. One supplied two-tile layout places the minority plants near the shared border and passes the geometric check.

Giant crops require suitable seeds/history and at most one total stress point under the saved wiki rules. Players still need water, tending each stage, appropriate seasons, no nearby debris, and adequate soil. A ratio card must say **nutrient-balanced**, not **guaranteed giant**. Character skill effects and exact temporal simulation are deferred.

## Rights and provenance

This is an unofficial fan dataset/tool, not affiliated with Klei. Earlier project research reports Huiji text as CC BY-NC-SA 3.0 unless otherwise stated; confirm current applicable notices before redistribution. Wiki text licensing does not establish game-art rights. All indexed images remain rights-unconfirmed, with `redistributable=false`. No game artwork or third-party planner code is bundled. The reference repository advertises GPL-3.0; consult its license if directly reusing that implementation. The code here was written independently for this handoff.
