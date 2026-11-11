# Editable rarity and 料理示例

In **食材探索**, each state has a **稀有度** column and a detail editor. Click the column
value to focus the editor. Use **保存稀有度**, or **恢复默认 0** to remove the override.
Blank also removes it. The supported range is signed 32-bit integers, including negatives;
fractions, booleans, and numeric strings in the API are rejected. Unset means zero.
Initial values come from the human-editable `data/ingredient_rarities.default.json`. Each exact state has its own preference, including both
nutrition-brick rows. Repeated copies contribute separately, so `[A,A,B,C]` costs
`2*rarity(A)+rarity(B)+rarity(C)`. Negative costs prefer consuming that state.

## Persistence and sharing

Preferences are stored in browser localStorage under `dst-helper.cooking.rarities.v1`,
separate from Farming and Cooking exclusions. New browsers receive the source-controlled
`data/ingredient_rarities.default.json`, seeded with the existing 141 custom values.
`--settings <json>` selects an alternative read-only defaults file. It no longer points
to SQLite. The server does not read or write the former `.local/` preference stores.

**清空全部稀有度** saves an explicit empty object, making every ingredient cost zero.
It stays empty after reload; missing storage alone receives defaults. Edits are written
locally and storage errors retain the input and show a warning. There is no application
expiry, but clearing site data, private browsing, and browser eviction can remove data.
Same-origin tabs synchronize changes; independent browsers never share preferences.

Cooking calculations accept bounded, same-origin JSON requests containing validated
rarities, not preference writes. Cache keys use actual rarity values rather than local
revision counters. **不考虑名单** uses its own browser key and tracked JSON defaults;
see `SIGNATURE_RECIPES.md`. Clearing either set leaves the other and Farming untouched.

## Dish detail examples

**料理示例** appears immediately after **配方条件**, with no additional navigation
entry. Choose the cooker there; portable-only recipes initially select the portable pot.
Each example displays four separate small ingredient picture buttons, total rarity,
outcome chance, and **试煮**. Hovering or focusing an image reveals its name and rarity.
Clicking it switches the underlying section to **食材探索** and opens the exact state’s
detail. **试煮** transfers the four IDs and cooker to **出锅预测**.

Uncertain results display a yellow **非确定 · 本锅概率** badge with the percentage and
exact fraction. **只显示确定配方** beside the cooker selector excludes tied outcomes
before choosing the three cheapest examples, rather than hiding rows from the existing
three. It defaults to unchecked. The browser remembers this boolean in localStorage
under `dst-helper.cooking.examples.guaranteed-only.v1` across dishes and reloads, without
changing rarity, exclusions, or other modules. If fewer than three guaranteed combinations
exist, the available count is shown; the filter never falls back to uncertain examples.
“100%” describes the current prediction model, with the same evidence limits as prediction.

The examples are the three lowest-total-rarity distinct unordered four-state multisets.
Reordering ingredients is not a different example; duplicate copies still occupy slots.
Only pots where the dish survives all higher-priority available recipes qualify. Tied
highest-priority dishes show their exact-model chance, not a guaranteed result. Equal-cost
pots use a stable ingredient order favoring familiar unprepared ingredients; this does
not add an unrequested acquisition-effort score or optimize success probability.

The explicit `data/prepared_ingredients.json` lists 57 cooked, roasted, and dried states,
reviewed against captured Chinese names and IDs, with source row references. Runtime
selection uses this list, not string matching. These forms are excluded from dish examples
unless a positive named ingredient-count requirement explicitly lists only prepared forms.
A listed raw/cooked interchangeable group is satisfied with its raw forms instead. Other
ingredients remain selectable according to the predictor's experimental universe; this
policy does not assert game cooker eligibility or exclude every crafted ingredient.

Some dishes have fewer than three valid combinations under this policy. The UI reports
the available count instead of inventing duplicates or ignoring priority competition.
For this snapshot, 蘑菇蛋糕 has one unprepared-state combination in either cooker;
恐怖国王饼 has one in the portable pot. 怪物千层饼 has no winning combination in the
portable-pot model, although it has examples in the ordinary pot. These are observations
of the captured rules, not independently verified game behavior.

## Optimization and cache behavior

The signature search optimizes the other three slots while fixing one exact selected
state. It can compress mechanically equivalent states because the cheapest representative
dominates for a single minimum-cost witness. Signature search retains all predictor states,
including prepared forms. Its minimum additional cost drives the default **易获取优先**
ranking, followed by the chosen nutrition value. **营养优先** reverses these criteria;
the complete **特别** group remains first in both modes.

Dish examples enumerate actual states, preserving distinct equivalent substitutes. Three
prefix slots are searched in nondecreasing state order; bit masks evaluate all last-slot
possibilities against the target and strictly higher-priority rules. Nondecreasing rarity
allows exact cost bounds, including negative costs. When guaranteed-only is selected,
other equal-priority matches are also excluded, and the cache separates the two modes.
At most three last-slot candidates per
prefix can enter a global top three. There is no sampling or time cutoff. Every returned
pot is replayed through `ExactPotPredictor` and fails closed if its outcome disagrees.

Each response echoes the requesting page's local revision. A bounded cache keeps at most
eight configurations, keyed by normalized rarity values. Independent browsers can reuse
a configuration without sharing editable state. Saving an edit refreshes local lists and
invalidates in-flight requests; delayed results cannot overwrite a newer selection.
Other tabs in this browser synchronize through storage events.

## API and validation

```text
GET /api/rarity                         # read-only initial defaults
POST /api/examples
  {"dish":"huiji:华夫饼","cooker":"crock_pot","rarities":{"butter":20},"rarity_version":1,"guaranteed_only":true}
POST /api/signature
  {"ingredient":"meat","cooker":"crock_pot","rarities":{},"rarity_version":1}
```

Calculation POSTs require same-origin JSON bodies of at most 16 KB and validate every
rarity ID and signed integer. Empty `rarities` means all zero, not server defaults.
`POST /api/rarity` and `POST /api/signature-exclusions` return 405; no preference-write
API remains. GET search endpoints use defaults for compatibility. Exclusions are applied
by the browser to full search results, preserving priority competition and probabilities.

Examples accept optional boolean `guaranteed_only` (default false); the GET compatibility
endpoint accepts the query values `true` or `false`. Signature requests do not accept it.
Examples return `complete`, `rarity_version`, `available`, `guaranteed_only`, `fewer_than_requested`, and
`examples[{ingredients,total_rarity,probability}]`. Unknown dishes return 404, malformed
requests 422, unsupported model data 503. Catalog and detail GET responses carry initial
rarity defaults; the UI overlays browser preferences before display.

`tests/test_rarity_examples.py` independently enumerates all four-state combinations
and remaining triples in a synthetic universe, checking minimum costs and top-three
distinctness with zero, positive, negative, and extreme signed rarities, equivalent
states, prepared-only requirements, ties, shadowing, and cooker changes. It also checks
request isolation, equal browser revisions with different preferences, bounded cache
eviction, input validation, and immutable content. `scripts/validate_examples.py` replays all snapshot examples for 324 dish/cooker/
rarity-scenario queries; its report is `EXAMPLES_VALIDATION_REPORT.json`.

The existing experimental wiki evidence level, assumed ingredient universe, draft
readiness flags, source hashes, and unconfirmed build compatibility are unchanged.
