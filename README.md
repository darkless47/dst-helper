# DST Helper

An unofficial, local-first Don't Starve Together helper with **Cooking** and
**Farming Planner** modules, connected through a shared home page. Requires Python
3.10+; no additional runtime packages.

Cooking retains the recipe catalog, ingredient explorer, **优选料理**, four-slot
wiki-based outcome predictor, rarity settings, and recommendation exclusions.

Run these commands from this workspace directory (`C:\Users\oyblu\Dev\dst-helper`).

Local-only test server:

```powershell
python dst_helper --host localhost --port 8765
```

Open **http://localhost:8765** for the home page, **/cooking** for Cooking, or
**/farming** for the Farming Planner. `localhost` binds explicitly to `127.0.0.1`.

LAN share server:

```powershell
python dst_helper --host 192.168.1.50 --port 8765
```

Share **http://192.168.1.50:8765** with devices on the LAN. The existing Windows
firewall rule allows this Python executable and port from `192.168.1.0/24` on Private
wireless networks. Use your current private IP if it changes.

Stop a foreground server with **Ctrl+C**. If an instance is already listening on the
requested address and port, stop that instance first or choose another port. Omitting
`--host` defaults to local-only access. `python -m dst_helper` is also supported, and
the earlier `DST_Cooking_Data_v0_1/run_handbook.py` entry point remains available.

The same `--database`, `--assets`, and `--settings` options work with either entry point. Paths to the
default content and saved images are resolved from the application files, not the
current working directory.

Ingredient rarity edits are shared by users of this server and stored separately in
`DST_Cooking_Data_v0_1/.local/user_settings.sqlite`. Unset values count as zero.
**优选料理** defaults to **易获取优先**; dish details show pictured, minimum-rarity example pots.

See [the application README](DST_Cooking_Data_v0_1/README.md) for data, assets,
prediction behavior, checks, and firewall setup details.

## Repository contents

Commit application code, `assets/images/`, tests, migrations, curated JSON, both packaged content
databases, and source/validation documentation. The JSON supports offline database
rebuilds; the packaged Cooking database is also required for the default runtime.
Validation reports are dated evidence, not a substitute for running the checks below.

`.gitignore` excludes Python environments/caches, `.local/` state and QA output,
logs, environment files, generated databases, and the private `wiki-webpage-save/`
archive. The two packaged content databases are explicit exceptions. Keep personal
settings and farming plans locally; they are not part of the initial commit.

The app loads its 226 catalog pictures and three stat icons from the committed
`assets/images/` directory. A fresh checkout includes all runtime images and does
not need the wiki archive. See [asset documentation](assets/README.md) for source
records and the repeatable packaging command. `--assets` can select another image
directory or an original saved-page archive.

For source audits or re-extraction, retain your saved wiki HTML and matching PNG
files locally under `wiki-webpage-save/`, preserving original filenames and `_files/`
paths. Saved website scripts, styles, and analytics files are unnecessary. The
original HTML is retained unchanged for hash-based source verification; it is not
a standalone offline wiki viewer.

## Farming Planner

1. Select seasons; crops must prefer every selected season. Select none to show
   all 14 crops. Quick choices include single seasons and neighboring pairs.
2. Select available seeds. Enter optional stock counts: blank means unconstrained,
   zero means unavailable. Season changes preserve hidden crop selections and counts.
3. Choose a nutrient-balanced ratio and an integer planting multiplier. Results
   include seed totals, inventory limits, shared preferred seasons, and an area
   lower bound using nine positions per tile. The default bounded search finds
   74 primitive ratios with no filters, or four in winter.
4. Paint crop positions on one, two, or four adjacent 3×3 tile grids, or load an included
   example. Each tile has its own nutrient balance and deficits. Family checks use
   actual intended game coordinates, including cross-tile neighbors at distance
   **≤4** (boundary included, per the user's confirmed planning rule). Four fields
   form a **2×2** square numbered top-left 1, top-right 2, bottom-left 3, bottom-right 4.
   All fields touch without an intervening game-distance gap. Weeds can be
   placed for hazard checks. Placement changes reset care and growth records.
5. Follow the care checklist. Optionally record the seven stress sources across
   four growth stages and the required seed/history conditions. Unknown conditions
   remain unknown. A balanced ratio does not guarantee giant crops.

The combination list has **卡片 / 表格** views, with the display preference saved
in the browser. Cards put each crop and its count on a separate row; the table
shows every matching combination with the same scale, stock and selection behavior.
Reducing the field count preserves plants: first erase any plants in fields that
would be removed. Existing one-/two-field plans still import without conversion.

Crop-name links open the matching ingredient in Cooking, using product ingredient
IDs. The planner uses `DST_Farming_v0_1/data/farming.json` as its authoritative curated
snapshot; it never rebuilds or merges the Cooking database.

Source: Huiji revision **203373**, received **2026-11-09**. These are usable
wiki-based static calculations; compatibility with reported game build **762172**
has not been verified. Exact growth timing, water scheduling, and automatic layout
synthesis are outside this implementation.

The working plan, seed availability, stock counts, filters, care records and layout
automatically persist in `DST_Cooking_Data_v0_1/.local/farming_plans.sqlite`, separately
from Cooking preferences and both curated datasets. `--settings` relocates this
default alongside the Cooking settings; `--farming-settings <path>` overrides only
the Farming store. Server users share this working plan, with version checks to
prevent concurrent edits from silently overwriting each other. If another page
saves first, export the retained draft before loading the server's latest plan.
Export/import JSON includes schema and dataset versions. Importing a different
version is rejected without replacing the current plan.

**重置全部数据** opens a confirmation dialog. **Reset** restores Farming's default
plan and clears this browser's Farming display preference. **Export and Reset**
first downloads the current draft as JSON, then performs the same reset. Close the
dialog or press Esc to cancel. Reset affects the shared Farming plan; Cooking's
settings and curated datasets remain separate. Failed or conflicting saves keep
the current draft available for export instead of replacing it locally.

## Checks

From the workspace root:

```powershell
python -m unittest discover -s DST_Farming_v0_1/tests -v
python -m unittest discover -s tests -v
```

Cooking's existing suite runs from its package directory:

```powershell
Push-Location DST_Cooking_Data_v0_1
python -m unittest discover -s tests -v
Pop-Location
```

Optional real-browser acceptance checks use an installed Windows Edge/Chrome,
temporary user settings and an isolated headless browser profile, with no Python
dependencies. They require permission for local loopback debugging connections:

```powershell
python tests/browser_smoke.py
```

The browser checks cover navigation, season/seed constraints, layouts, stock caps,
mobile sizing and Cooking links; screenshots go to ignored `.local/qa/`.
