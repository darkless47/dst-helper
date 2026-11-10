# Exact-pot prediction

Open **出锅预测**, choose an ordinary or portable cooking pot, and fill all four slots.
Select an ingredient repeatedly to add duplicates. Click a filled slot to replace it,
or its × button to remove it. Search accepts Chinese names, provisional English hints,
prefabs, and state IDs. An example button fills small meat plus three berries.

Click **开始预测** to see every highest-priority outcome, its chance, cooking time, base
table stats, and a link to its source details. Fractions such as **1/3** are exact;
displayed percentages are rounded. Lower-priority and cooker-excluded matches appear
only as explanations, not outcomes. Editing the pot/cooker invalidates old results and
aborts pending requests. Narrow screens move to the results after prediction.

## Supported rules and evidence

- Exactly four recorded ingredient **state IDs** are required; duplicates count as
  separate slots. Tags are summed using those state records.
- Named-item counts are grouped by game **prefab ID**, preserving the distinction
  between state identity and named-item identity.
- Shared forms include only those explicitly listed in the predicate. Raw/cooked/dried
  alternatives contribute to one combined count, then `=`, `>=`, or another recorded
  comparison is applied. This behavior was confirmed by the user on November 8, 2026.
- All supported AND/OR and strict/inclusive comparisons are interpreted declaratively.
  No downloaded code or `eval` is used. Tag arithmetic uses exact decimal fractions.
- Highest `recipe_rules.priority` wins. N equally highest matching recipes receive
  probability 1/N, as confirmed by the user. Negative priorities are valid rankings.
- The separate nullable `weight` column is preserved and unused by this uniform-tie
  policy. A future dataset with explicit non-NULL probability weights fails closed
  pending policy review; the predictor never turns NULL into an asserted weight of 1.

The independent source audit compared all 81 predicates and priorities with saved wiki
revision 193291. `data/prediction_policy.json` records user confirmations and the scope
assumptions separately from the replaceable SQLite snapshot.

## Experimental scope

The saved ingredient table covers cooking utensils collectively, including the ancient
kiln, but does not provide a complete per-cooker ingredient/recipe matrix. This version
uses the **145 recorded states** as its explicit prototype ingredient universe for both
supported pot profiles. This is an assumption, not verified eligibility for each item.

- **Recipe availability:** the user confirmed on November 8 that the 70 ordinary
  recipes can be made in either the ordinary crock pot or Warly's portable pot. The
  table, filter, and details now show both cookers rather than an unconfirmed matrix.
- **Ordinary crock pot:** excludes the 11 recipes marked portable-only in the wiki.
- **Portable crock pot (Warly):** includes all 81 captured recipes.
- **Ancient kiln:** unsupported until its distinct eligibility rules are sourced.

This confirms recipe availability for the two supported pots; per-ingredient cooker
eligibility remains a separate scope assumption.

The UI and API label outputs **experimental wiki predictions**. They do not establish
compatibility with target build 762172 or independent in-game validation. The original
`solver_ready` flags, NULL weights, state identities, schema, and database bytes are
unchanged. No migration is needed for this application feature. The catalog remains
available if the prediction dataset is unsupported; the prediction API returns 503.

The separate **优选料理** view searches complete pots containing one selected ingredient;
see `SIGNATURE_RECIPES.md`. No arbitrary multi-slot progressive search, inventory limits, character-effective stats, freshness,
spices, special effects, output quantities, or farming mechanics are modeled here.
Pot selections live only in page memory and are not saved into SQLite or local history.

## API and tests

The read-only GET endpoint accepts repeated `ingredient` parameters:

```text
/api/predict?cooker=crock_pot&ingredient=smallmeat&ingredient=berries&ingredient=berries&ingredient=berries
```

`cooker` is `crock_pot` or `portable`. Invalid counts, IDs, cookers, or parameters return
422 without an outcome. Responses include winners with exact probability numerator and
denominator, tag totals, prefab counts, discarded matches, source revision, target build,
and `eligibility_verified=false`. `/api/catalog` advertises prediction capabilities.

`data/prediction_fixtures.json` contains 13 manually derived wiki/policy cases, including
two-way and three-way ties, mixed ingredient forms, exact-count exclusions, cooker
availability, fractional meat, and negative-priority fallback. These are **not** claimed
as independent in-game pot fixtures. Additional synthetic tests cover differing tags for
states sharing one prefab, exact decimal sums, invalid grammar, and unsupported weights.

```powershell
python -m unittest discover -s tests -v
python scripts/validate_dataset.py
python scripts/audit_recipe_capture.py
```

Restart the local server after upgrading: prediction adds a Python module, API route,
and UI script. Restart after replacing the content dataset or local image archive too.
