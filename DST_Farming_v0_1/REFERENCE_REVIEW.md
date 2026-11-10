# Requested reference review

Requested page: https://hzhangxyz.github.io/dst-farming/
Repository: https://github.com/hzhangxyz/dst-farming
License page: https://github.com/hzhangxyz/dst-farming/blob/main/LICENSE.md
Inspection date: November 9, 2026.

The page returned HTTP 200. The HTML includes the Vue app and its static crop facts. The embedded implementation and labels were inspected; browser-rendered appearance was not separately tested. The GitHub repository API identifies GPL-3.0, with a LICENSE.md file. No source or artwork from that application is bundled here. We use its visible functional design and compare factual numeric data; the supplied engine is original code.

## Observed interaction model

| Area | Observed behavior | Handoff specification |
|---|---|---|
| Introduction | Explains giant crops and nutrient complementarity | Short explanation plus explicit remaining care conditions |
| Quick choices | Clear filter; each season; adjacent season pairs | Same capabilities in host app styling |
| Season checkboxes | Multiple can be selected | Crop must prefer every selected season |
| Crop table | Availability checkbox, Chinese name, four seasons, signed nutrient values | Same data plus optional seed inventory and water detail |
| Ratio list | Two- and three-species exact zero-sum nutrient combinations | Same bounded default search, informative result cards |
| Search coefficients | Positive integers 1 or 2, normalized to primitive ratios | Clearly label this scope; do not call it all possible integer ratios |
| Spatial/family check | No spatial planting-grid validator in inspected app | Add optional 3x3 tile editor or supplied layout examples |

The observed reference lists 74 ratios with no season filter, 43 in spring, 22 in autumn, 12 in summer and 4 in winter under its bounded search. See REFERENCE_COMPARISON.json for every season subset. All 14 crop season/nutrient records agree with the uploaded Huiji overview. The independent checker reproduced the bounded result set for all 16 filter subsets.

These agreements establish transcription and functional consistency, not an official current-game audit. Date, source hash, and comparison scope are recorded. The optional checker reads literal data without executing downloaded JavaScript; a changed bundle may require manual parser updates.
