# Data contract v0.1.0

The schema is in `migrations/001_initial.sql`, with `PRAGMA user_version=1`. It supersedes the earlier proposed `schema.sql` as a new initial ingestion schema. It is not an ALTER migration for an existing populated database.

| Table | Purpose |
|---|---|
| dataset_metadata | JSON values: target build, evidence, dataset/schema versions, source snapshot, limits |
| sources | Saved page URL/revision, received date, hash; build verified remains NULL |
| ingredients | State-specific dataset ID; separately, wiki-reported prefab; source links and row evidence |
| ingredient_tags | Nonzero additive tag values, by state-specific ingredient ID |
| dishes | Provisional wiki ID; NULL game prefab; wiki stats and raw text |
| recipe_rules | Draft predicates, priority, seconds, unknown weight, cooker hint, readiness flag |
| source_rows | Structured cell-level text, links, images, source row number |
| assets | Local source references and hashes, original candidate URLs; unresolved rights |
| review_issues | Specific exceptions and dataset-wide missing information |
| schema_migrations | Applied schema versions |

`verification_status=wiki_snapshot_only` is evidence level, not accuracy certification. `source_received_date` is when this chat received the saved file, not the wiki's last edit or an exact download timestamp. `name_en_hint` is an image-filename-derived label.

Numeric stats preserve signs and fractional values. NULL means unknown/unresolved, not zero. `perish_game_days=NULL` combined with source text `无` means the page reports no perishability; do not infer that from NULL alone. No sourced real-time day length has been assumed. `cook_seconds` uses the source's second units directly. Static numerical entries may need semantic exceptions; see README.

## Predicate JSON, format v0.1

All expressions are declarative. Never eval downloaded code.

```json
{"all":[
  {"tag":"veggie","op":">=","value":0.5},
  {"tag":"meat","op":"==","value":0},
  {"item_sum":["butterflywings","moonbutterflywings"],"op":">=","value":1}
]}
```

- `all`: AND; an empty list is true (Wet Goop's unrestricted match).
- `any`: OR.
- `tag`: compare a pot's aggregate tag total.
- `item_sum`: compare the combined count of the listed prefabs. Raw/cooked alternatives may combine to reach a count. This is an interpretation of the wiki shorthand and must be reviewed.
- Operators: `==`, `>`, `<`, `>=`, `<=`.
- For a tag in the 15 captured columns, a blank source cell is interpreted as zero. Unknown/new tag vocabulary must be treated as unknown, not blindly defaulted to zero.
- A condition tree only describes a recipe's own match. It does not establish availability or output: first enforce four slots/cooker eligibility, then evaluate all available recipes, then priority and tie policy. Character edibility comes afterward and depends on finished food type.

Example: a candidate Meatballs match can lose to a higher-priority recipe. Do not label matching recipes as possible final outcomes until priority competition has been evaluated. Partial-pot feasibility requires an actual allowed four-item completion with nonzero final probability, not merely the ability to satisfy a recipe's own tree.

All ASTs are `parsed_draft`, `solver_ready=0`. Syntax checks and source-derived fixtures do not independently validate the wiki or its recipes. A release promoting readiness needs documented semantic review, source-completeness assessment, cooker rules, and tests of priority conflicts and ties.

## Useful read-only queries

```sql
SELECT name_zh, name_en_hint, base_health, base_hunger, base_sanity
FROM dishes ORDER BY base_hunger DESC;

SELECT d.name_zh, r.priority, r.cook_seconds, r.parse_status
FROM recipe_rules r JOIN dishes d USING(dish_id)
ORDER BY r.priority DESC;

SELECT * FROM review_issues;
```

## Future migration guidance

Use explicit numbered migrations. Add confirmed canonical IDs as mappings while preserving existing wiki keys and source evidence; avoid changing external IDs silently. Keep user history/settings in a separate writable database. Add multi-source/field evidence, verified localization, effects, output counts, stateful character rules, cooker eligibility, and versioned source comparisons gradually.
