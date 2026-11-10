# Editable rarity and 料理示例

In **食材探索**, each state has a **稀有度** column and a detail editor. Click the column
value to focus the editor. Use **保存稀有度**, or **恢复默认 0** to remove the override.
Blank also removes it. The supported range is signed 32-bit integers, including negatives;
fractions, booleans, and numeric strings in the API are rejected. Unset means zero.
No rarity guesses are supplied. Each exact state has its own preference, including both
nutrition-brick rows. Repeated copies contribute separately, so `[A,A,B,C]` costs
`2*rarity(A)+rarity(B)+rarity(C)`. Negative costs prefer consuming that state.

## Persistence and sharing

Preferences are stored in `.local/user_settings.sqlite`, separate from the immutable
`dst_cooking.sqlite`. This is a server-wide preference store: LAN visitors share these
values. They survive restarts and replacement of the content snapshot, keyed by stable
state IDs. Preferences for temporarily absent IDs stay stored. Back up this settings file
separately; it is ignored by Git and package hashes. Use `--settings <path>` to choose a
different file. A content database cannot also be the settings database.

`migrations/settings/001_rarity.sql` initializes the separate schema (user_version 1),
with `ingredient_preferences(ingredient_id, rarity)` and a monotonic settings revision.
Writes are transactional and parameterized. An expected revision prevents a stale LAN
editor from silently replacing another edit: HTTP 409 returns the latest settings, keeps
the typed input, and asks the user to check and save again. Failed writes retain input.
Content writes remain rejected; the rarity POST requires JSON and rejects
cross-origin browser requests. This is still a local/LAN prototype without user accounts.

The signature-only **不考虑名单** uses a separate `signature_exclusions.json` beside this
settings database. Its edits do not modify rarity values or dish-detail examples; see
`SIGNATURE_RECIPES.md`.

## Dish detail examples

**料理示例** appears immediately after **配方条件**, with no additional navigation
entry. Choose the cooker there; portable-only recipes initially select the portable pot.
Each example displays four separate small ingredient picture buttons, total rarity,
outcome chance, and **试煮**. Hovering or focusing an image reveals its name and rarity.
Clicking it switches the underlying section to **食材探索** and opens the exact state’s
detail. **试煮** transfers the four IDs and cooker to **出锅预测**.

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
allows exact cost bounds, including negative costs. At most three last-slot candidates per
prefix can enter a global top three. There is no sampling or time cutoff. Every returned
pot is replayed through `ExactPotPredictor` and fails closed if its outcome disagrees.

Responses use one coherent settings revision. The planner discards both signature and
example caches on a revision change. Saving an edit refreshes local lists and invalidates
in-flight example/signature requests; delayed results cannot overwrite a newer selection.
Other LAN clients read fresh settings on subsequent detail/search requests or page reload.
Already displayed results are not pushed live to other browsers.

## API and validation

```text
GET /api/rarity
POST /api/rarity
  {"ingredient_id":"butter","rarity":20,"expected_version":0}
GET /api/examples?dish=huiji:华夫饼&cooker=crock_pot
```

`rarity:null` removes an override. POST returns `{version, rarities}`; conflicts return
409 with `settings`, invalid input 422, unrelated/unsupported write routes 405.
Examples return `complete`, `rarity_version`, `available`, `fewer_than_requested`, and
`examples[{ingredients,total_rarity,probability}]`. Unknown dishes return 404, malformed
queries 422, unsupported model data 503. Catalog ingredient rows include effective
`rarity`; ingredient detail includes `rarity` and `rarity_version`.

`tests/test_rarity_examples.py` independently enumerates all four-state combinations
and remaining triples in a synthetic universe, checking minimum costs and top-three
distinctness with zero, positive, negative, and extreme signed rarities, equivalent
states, prepared-only requirements, ties, shadowing, and cooker changes. It also checks
persistence, reset, LAN conflicts, revision invalidation, input validation, and immutable
content. `scripts/validate_examples.py` replays all snapshot examples for 324 dish/cooker/
rarity-scenario queries; its report is `EXAMPLES_VALIDATION_REPORT.json`.

The existing experimental wiki evidence level, assumed ingredient universe, draft
readiness flags, source hashes, and unconfirmed build compatibility are unchanged.
