# DST Helper

An unofficial, local-first Don't Starve Together helper with **Cooking** and
**Farming Planner** modules, connected through a shared home page. Requires Python
3.11+ with Starlette and Uvicorn; runtime dependencies are pinned in `requirements.txt`.

Cooking retains the recipe catalog, ingredient explorer, **优选料理**, four-slot
wiki-based outcome predictor, rarity settings, and recommendation exclusions.

Run these commands from this workspace directory (`C:\Users\oyblu\Dev\dst-helper`).

Create a virtual environment and install the runtime packages first:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If activation is blocked, use `.\.venv\Scripts\python.exe` directly for the commands below.
The existing entry points now launch Uvicorn with one worker.

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

The same `--database`, `--assets`, `--settings`, and `--exclusions` options work with either entry point. Paths to the
default content and saved images are resolved from the application files, not the
current working directory.

All editable preferences live in browser `localStorage`, independently for each browser
and site origin (scheme, host, and port). No accounts or server-side user stores are needed.
Cooking's initial values are human-editable, source-controlled JSON files:

- `DST_Cooking_Data_v0_1/data/ingredient_rarities.default.json`: the current 141 ingredient rarity values.
- `DST_Cooking_Data_v0_1/data/signature_exclusions.default.json`: the current three excluded dishes.

Restart the server after editing defaults. New browsers receive them once; existing saved
preferences, including explicitly empty values, remain unchanged. `--settings <json>` and
`--exclusions <json>` select alternative read-only default files. They no longer point to
writable SQLite/JSON user stores. Cooking has separate **清空全部稀有度** (all zero) and
**清空全部排除名单** controls, so either set can be cleared independently.

The browser keys are `dst-helper.cooking.rarities.v1`,
`dst-helper.cooking.exclusions.v1`, and `dst-helper.farming.plan.v1`. Each stores a
schema-versioned JSON value. Tabs in the same browser synchronize through storage events.
Browser storage has no application expiry, but clearing site data, private browsing,
or browser eviction can remove it. Storage failures show a warning rather than claiming
to save successfully. Use the same public HTTPS origin consistently to retain preferences.
Existing `.local/` user files are no longer read or written; personal Farming plans are
not copied into new visitors' browsers. Curated game data stays read-only.
**优选料理** defaults to **易获取优先**; dish details show pictured, minimum-rarity example pots.

See [the application README](DST_Cooking_Data_v0_1/README.md) for data, assets,
prediction behavior, checks, and firewall setup details.

## Server deployment

```sh
docker compose up -d --build
```

The container publishes `127.0.0.1:8765` for your existing host Nginx on port 80.
The image includes the runtime data and images, runs as a non-root user, and has a
`/healthz` check. Compose uses a read-only filesystem and needs no persistent volume.
See [DEPLOYMENT.md](DEPLOYMENT.md) for the Cloudflare Tunnel/Nginx configuration,
trusted proxy addresses, setup without Docker, checks, and updates.

## Repository contents

Commit application code, `assets/images/`, tests, migrations, curated JSON, both packaged content
databases, and source/validation documentation. The JSON supports offline database
rebuilds; the packaged Cooking database is also required for the default runtime.
Validation reports are dated evidence, not a substitute for running the checks below.

`.gitignore` excludes Python environments/caches, `.local/` state and QA output,
logs, environment files, generated databases, and the private `wiki-webpage-save/`
archive. The two packaged content databases are explicit exceptions. Keep personal
settings and farming plans in the browser; the two Cooking defaults are part of the source.

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
   placed for hazard checks.
5. Review the four general care reminders: water, tending, starting soil nutrients,
   and nearby debris. A balanced ratio does not guarantee giant crops.

The combination list has **卡片 / 表格** views, with the display preference saved
in the browser. Cards put each crop and its count on a separate row; the table
shows every matching combination with the same scale, stock and selection behavior.
Reducing the field count preserves plants: first erase any plants in fields that
would be removed.

Crop-name links open the matching ingredient in Cooking, using product ingredient
IDs. The planner uses `DST_Farming_v0_1/data/farming.json` as its authoritative curated
snapshot; it never rebuilds or merges the Cooking database.

Source: Huiji revision **203373**, received **2026-11-09**. These are usable
wiki-based static calculations; compatibility with reported game build **762172**
has not been verified. Exact growth timing, water scheduling, and automatic layout
synthesis are outside this implementation.

The working plan, seed availability, stock counts, filters and layout automatically
persist in this browser, separately from Cooking preferences. Changes save locally before
calculation requests complete. `/api/farming/analyze` validates a bounded JSON plan and
returns calculations without saving it. Cooking calculations likewise receive validated
rarities per request; their bounded cache is keyed by actual preference values, keeping
results isolated even when two browsers have the same local revision.

**重置全部种植数据** opens a confirmation dialog. **确认重置** restores Farming's default
plan and clears this browser's Farming display preference. Close the dialog or press Esc
to cancel. Reset leaves Cooking preferences and other browsers untouched. Failed storage
writes preserve the existing plan. Farming has no manual save, server reload, file upload,
import, export, or download workflow; the former server preference-write APIs are removed.

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
isolated headless browser contexts. They require the runtime packages above and
permission for local loopback debugging connections:

```powershell
python tests/browser_smoke.py
```

The browser checks cover navigation, season/seed constraints, layouts, stock caps,
mobile sizing, Cooking links, independent browser preferences, persistent clear-all values,
storage failure recovery, and resets during calculations; screenshots go to ignored `.local/qa/`.
