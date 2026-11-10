# Recipe capture verification — November 8, 2026

Compared the saved Huiji cooking page (revision **193291**, SHA-256
`3072e6cc0e7be112a7cfc91f1c02cdd2078960543be1d9accc35dd5d4fe0effa`)
directly with the SQLite content. This is a source-transcription audit, not a comparison
against game scripts or in-game results.

## Results

- **81/81 recipe condition trees match** the source under the data dictionary's existing
  interpretation of grouped ingredient icons. Strict/inclusive comparisons, fractional
  thresholds, chained bounds, AND/OR groups, named prefab references, and portable-cooker
  hints were compared. No transcription discrepancies were found.
- **81/81 priorities match**, including zero and negative values. The range is **−10 to 100**.
- **145 ingredient states / 2,175 tag cells match** the source's 15 captured columns,
  including interpreting blank cells in those columns as zero.
- The database, schema, original snapshot, and solver readiness flags were not changed.

The audit uses a separate standard-library HTML parser and token-based expression parser;
it does not invoke the original extraction parser. Full per-recipe evidence is in
`RECIPE_CAPTURE_AUDIT.json`. Re-run with:

```powershell
python scripts/audit_recipe_capture.py
python -m unittest discover -s tests -p test_recipe_audit.py -v
```

## Meat value is different from an integer item count

`肉度 > 0` is **not** equivalent to `肉度 ≥ 1`. The meat tag is an additive numeric value,
with fractional contributions recorded as SQLite REAL values:

| Ingredient / aggregate meat value | `meat > 0` | `meat >= 1` |
|---|---|---|
| No meat contribution / 0 | false | false |
| One barnacle / 0.25 | true | false |
| One morsel (小肉) / 0.5 | true | false |
| Aggregate meat value 1 | true | true |

For example, the Meatballs predicate stores `{"tag":"meat","op":">","value":0.0}`,
along with its other conditions. It must not be rounded or rewritten to `>= 1`.
This describes the recipe's own match, not a guaranteed final output.

For an **integer named-item count**, such as the number of twigs, `count > 0` and
`count >= 1` are equivalent. Selecting one meat-bearing ingredient is also enough for
positive meat value when its contribution is positive; it need not contribute a whole
unit of meat value.

Additional stored-rule fixtures check the 1.5 boundary between Honey Ham and Honey
Nuggets, Rabbit Stew's strict `0 < meat < 1`, Turkey Dinner's AND/OR grouping, and
Glow Berry Mousse's separate large-berry/small-berry alternatives.

## Outcome selection policy confirmed by the user

The saved page explicitly says to select the highest-priority matching recipes, then
choose equally among recipes tied for that highest priority. The user confirmed this
policy on November 8, 2026. This confirmation supersedes treating the tie policy as an
unaccepted assumption for the planned **wiki-based predictor**; it does not establish
current-build or in-game verification.

The user's term “outcome weight” corresponds to the wiki's **优先级**, stored in
**`recipe_rules.priority`**. Examples already present in SQLite:

| Dish | `priority` |
|---|---:|
| 琥珀美食 | 100 |
| 果冻沙拉 | 50 |
| 培根煎蛋 | 10 |
| 肉丸 | −1 |
| 潮湿黏糊 | −10 |

The separate **`recipe_rules.weight`** column remains NULL for all 81 recipes. That
column was reserved for potential *relative probability weights within ties*. It is
not the wiki priority column and is unnecessary for the confirmed uniform-tie policy.
Do not copy priority into it or turn NULLs into asserted game weights.

For a legal four-item pot and its cooker:

1. Evaluate all available recipe predicates against summed state-specific ingredient
   tags and prefab-based named-item counts.
2. Find the maximum `priority` among matching recipes.
3. Discard matches with lower priorities.
4. If N matches remain, assign each probability **1/N**.

Abstract candidate examples (not in-game pot fixtures): priorities `[10, 10, 5]` yield
`[50%, 50%, 0%]`; `[30, 10, −1]` yield `[100%, 0%, 0%]`. Negative priorities are valid
rankings, so `[−1, −4, −10]` also yield `[100%, 0%, 0%]`. Never normalize the priority
numbers into proportional probabilities.

## Grouped forms confirmed by the user

The page uses shared icon shorthand such as “raw potato / cooked potato ≥ 2”. The
current AST counts the **combined total** of the explicitly listed prefabs. The user
confirmed this behavior on November 8: two raw, two cooked, or one of each satisfy a
shared `>= 2` requirement. The preceding confirmation applies the same shared-count
rule to exact comparisons: sum the listed forms first, then apply `=` or `>=`.

Ten recipes have such quantity-sensitive groups: 加州卷、奶油土豆泥、芦笋冷汤、蓝带鱼排、
恐怖国王饼、蓬松土豆蛋奶酥、藤壶中细面、叶肉糕、果冻沙拉、香蕉奶昔. They are individually
identified in the audit report as quantity-sensitive groups; their pending confirmation
flags are now false. This is a user-confirmed behavior, distinct from independent
in-game verification by this project. Tests include mixed potatoes/asparagus and exact
kelp counts.

The user also confirmed that ordinary recipes can be made in either the ordinary
crock pot or Warly's portable crock pot. Portable-only recipe hints remain distinct.
This is recorded separately from the original source snapshot in the prediction policy.

Per-ingredient cooker eligibility and independent actual-output examples remain
separate work before a trustworthy solver release. An experimental wiki-based exact-pot
predictor is now available with explicit cooker/ingredient assumptions; source readiness
flags remain false. See `PREDICTION.md` and `data/prediction_policy.json`.
