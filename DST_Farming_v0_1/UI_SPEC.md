# Garden / Farming Planner UI

Use the existing `dst_helper` stack, typography, navigation, localization, and state management. Add a **Farming / 种植规划** navigation item beside Cooking. Keep Cooking working.

## Initial usable page (required)

1. Compact introduction: “Choose seasons and available seeds to find nutrient-balanced crop combinations.” Explain once that water, tending, spacing and initial soil still matter. Small source label: Huiji revision 203373; wiki-based data, target build 762172 (unverified).
2. Quick choices: Autumn, Autumn+Winter, Winter, Winter+Spring, Spring, Spring+Summer, Summer, Summer+Autumn, Clear season filter. Checkboxes for all four seasons remain available. “Clear” clears seasons only; do not silently erase seed availability or saved plans. Explicit helper: “Crops must prefer every selected season. Select none to show all crops.”
3. Crop table/cards: availability checkbox, name, four preferred-season markers, three signed nutrient changes per stage. Optional seed count; blank = unspecified, zero = none. Changing season visibility must not erase stored crop availability. Provide Select all/Clear available seeds. Distinguish these from Clear season filter.
4. Result cards: ratio in readable names, per-stage net vector, matching seasons, scale multiplier, seed totals, area lower bound using nine slots per tile, and whether geometric layout has been checked. Default to the reference's two-/three-crop search with coefficients 1 or 2. Preserve availability/season settings in user preferences, not the curated data DB.
5. Empty state: explain that no ratio exists under the current season/seed/search constraints. Offer clearing restrictions, not silently including unavailable/off-season crops. More coefficients/types can be an explicitly slower advanced option.

Mark a result **Nutrient-balanced / 养分配平**. Do not label a bare ratio “guaranteed giant,” “no fertilizer ever,” or “family requirement met.” The area estimate is a lower bound, not proof that a spatial layout fits.

## Layout assist (include if feasible in this implementation)

Provide one or two adjacent 3x3 tile grids initially, extendable later. A user selects a crop brush, clicks slots, and clears slots. Support keyboard access and visible crop names; color alone is insufficient. Planting positions come from actual game-distance coordinates, not UI pixel distances. All nine slot positions are within their tile. Show:

- Per-tile counts and nutrient net; shortages in each nutrient shown separately.
- Per-plant same-type neighbor counts and family pass/fail/unknown.
- Off-season plants and known weeds nearby.
- A checklist for water, tending, sufficient starting soil, no outside debris, crop-specific seeds and plant history.

Load the two included example layouts. Keep a deliberate negative example in tests: one tile with six tomatoes and three dragon fruits is nutrient-balanced but fails the minority family check.

Do not mark an unknown or not-recorded care item as satisfied. Separate static layout checks from four-stage growth history. The diagram is a placement guide; it does not remotely place plants in the game.

## Acceptance examples

| Action | Expected behavior |
|---|---|
| No season selected, all crops available | 14 crops; 74 bounded ratios |
| Winter selected | 5 eligible crop types; 4 bounded ratios |
| All four seasons selected | Garlic only; no two-/three-species ratio |
| Potato + tomato available in spring | Ratio 1:1 available |
| Four potatoes + four tomatoes on one tile | Nutrients and family checks pass; one empty slot; care conditions still required |
| Six tomatoes + three dragon fruits on one tile | Nutrients pass; dragon-fruit family fails |
| Supplied adjacent-tile tomato/dragon-fruit layout | Per-tile balance and family checks pass |
| Globally balanced farm with nutrients split across tiles | Show individual tile deficits; do not share fertilizer across tiles |
| Zero seeds for a species | Exclude plans requiring it |

Avoid a large verification warning blocking the page. Source status belongs in a compact info label/details panel. An unresolved future feature must not hide the functioning ratio planner.
