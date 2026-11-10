# Farming data contract v0.1.0

`data/farming.json` and `farming.sqlite` carry the same normalized facts. `farming_` table names avoid collisions with the existing cooking schema. Preserve existing cooking tables, IDs, and user data.

| Table | Purpose |
|---|---|
| farming_metadata | Version, source, target build, planner mode, units, enablement |
| farming_sources | URL, revision, receipt date, snapshot hash, evidence level |
| farming_plants | 14 crops and 4 weeds; nutrient changes, water demand, source row, art refs |
| farming_seasons | Preferred boolean plus separate random-seed percentage per season |
| farming_mechanics | 16 typed JSON rules with section references and notes |
| farming_assets | Source-relative paths, original srcset, hash, rights state |
| farming_row_evidence | Twelve original overview cells, colors, image labels, and links |
| farming_section_evidence | Saved wiki prose grouped by heading |
| farming_review_issues | Scope and unresolved edge cases, not planner blockers |
| farming_schema_migrations | Farming schema version history |

## Identifiers and localization

The 14 crop `plant_id` values use their raw-product ingredient IDs (e.g. `tomato`, `potato`, `dragonfruit`), cross-linked to the earlier cooking handoff. All 14 were checked against that earlier handoff. These are dataset crop keys, **not asserted plant prefab IDs**. `product_ingredient_id` identifies the cooking-side product. `plant_prefab_id` and `seed_prefab_id` remain NULL until sourced. Weed keys are explicitly provisional `huiji:<Chinese name>` IDs and are not game prefabs.

Chinese crop names are read from product-link titles; plant names from the table. `name_en_hint` and `seed_name_en_hint` are image-file labels, not verified official localization. Use the stable IDs for joins; do not join by translated names.

## Nutrients and water

Vector order is always:

1. `growth_formula` 催长剂
2. `compost` 堆肥
3. `manure` 粪肥

Positive = added to soil; negative = consumed from soil. Values are per growth stage. Do not reverse the signs because the wiki column title says nutrient consumption. For example, tomato `[-2,-2,+4]` plus potato `[+2,+2,-4]` totals zero. Two tomatoes plus one dragon fruit `[+4,+4,-8]` also totals zero.

Soil holds each nutrient independently in [0,100], initially 25–50 per the wiki. The four checked transitions imply four times the per-stage vector for an ideal static full cycle, but a net vector is not a time-ordered simulation. Lack of consumption can suppress corresponding production. Soil stores are per tile; neighboring tiles do not exchange nutrients just because plants are close.

`water_percent_points_per_stage` preserves the table's percentage magnitude, e.g. `0.75%` as 0.75. It is **not** 0.75 per second or per day. Keep the original string visible in advanced details. The moisture stress rule is different: soil must have moisture >0 for at least 10% of the stage's duration. Do not turn this into “keep moisture above 10.”

## Seasons and random seeds

The wiki column order is **autumn, winter, spring, summer**. Preferred seasons are encoded by green `#7FFFAA` cells; blue `#D1E8EF` means not preferred. Nonzero random-seed appearance probability does not make a crop in season. Values are rounded and may not sum to exactly 100%; do not silently renormalize them or interpret them as giant probabilities.

Multiple selected seasons use intersection semantics: a crop must prefer every selected season. This supports repeating a plan across those seasons, not a forecast of season changes during one plant's life. No selected season means unfiltered, not a claim all crops are in season.

## Stress and eligibility

Seven sources: nutrients, moisture, debris, season, family, overcrowding, tending. Each can add one point at each of four growth transitions, maximum 28. Giant threshold is 0–1 total; also require crop-specific seeds, no rot/regrowth history, and no forced ripening.

The stage recorder uses True = stress occurred, False = no stress, None/missing = unknown. It reports min/max stress. Only fully supplied applicable conditions can yield `eligible_under_wiki_rules`; that means wiki-rule eligibility, not independent game verification.

Family radius: four game units, minimum four same-type plants including self. One tile side is four game units. Do not assume that a global count of four establishes proximity. Our grid helper places 3x3 centers at offsets 2/3, 2, 10/3 from the tile origin; it is an app placement convention. In-game positioning should follow those centers. The integrated app includes equality at the radius boundary, following the user's confirmed rule for contiguous fields. It uses exact integer grid distances, so four consecutive same-type crops crossing a shared edge pass in horizontal and vertical directions. This app planning rule supersedes the original handoff's conservative unknown-boundary treatment; it is not a separate game-build audit.

Debris radius: six game units. Weeds in the supplied plan are detected; outside-plan hazards, rotten crops, rotten giant produce, and farm debris require a user checklist or additional world positions. No known weed does not mean debris-free.

The wiki wording for overcrowding is `10 株以上`, including crops and weeds. Exactly ten is left unresolved; <=9 is safe under either interpretation, >=11 is overcrowded. Default nine grid positions per tile avoids the boundary. Do not advertise nine as the game's hard maximum; manual ten-plant support can be added after confirming the boundary.

## Usability and verification

`planner_enabled=true`, `planner_mode=wiki_based_static_balance`, plant status `wiki_based_usable`. This explicitly authorizes use of the data in the feature. The user's chosen source is Huiji, with independent current-build verification deferred. Do not copy cooking's old `solver_ready=0` gate into this feature. Preserve the evidence level and disclose it once in the UI.

Not collected: exact fertilizer-item amounts; instrument ranges; character skills and exceptions; exact growth-clock equations; optimal layout synthesis; automatic season-transition or water/soil scheduling. Leave those capabilities absent or explicitly partial rather than fabricating them.
