# 优选料理 / Signature recipes

Choose **优选料理** in the navigation, search for an ingredient, and select its exact
state. You can also open an ingredient's details and click **查看这件食材的优选料理**.
Choose the ordinary or portable pot, a ranking mode, and one shared nutrition metric:

- **特别料理:** all possible dishes whose predicates explicitly name the selected
  prefab in a positive ingredient-count requirement, including explicitly listed
  alternatives. Every dish in this group is shown and marked **特别**.
- **更多营养搭配:** other possible dishes that can include the selected ingredient.
  Initially five are shown. **再显示 5 道料理** adds five at a time; **收起为前 5 道**
  restores the compact view. Dishes do not repeat across groups.

**易获取优先** is the default: sort by the minimum rarity of the other three slots,
ascending, then by the selected nutrition value descending. **营养优先** reverses these
two criteria. Hunger is the default nutrition metric; HP and sanity are also available.
The named group always stays first, and both groups use the same controls. Source order
breaks remaining ties. Within the nutrition comparison, NULL/composite values sort after
known values and remain source text. Changing either ranking control resets the second
group to five. All rarity values start at zero; edit them in **食材探索** to customize costs.

“特别” indicates an explicit recipe reference, not exclusive ownership of a dish by
one ingredient. Raw/cooked alternatives are recognized through their listed prefab
groups. A general tag condition such as `meat > 0` or `frozen > 0` does not earn this
label. For example, ordinary-pot honey has three named dishes: 蜜汁火腿、蜜汁卤肉、粉末蛋糕.

## 不考虑名单 / Excluded suggestions

Use **管理不考虑名单** at the top of **优选料理**. The dialog shows excluded dishes
with **恢复推荐**, plus a searchable list of other dishes with **加入名单**. Changes
save immediately, refresh both recommendation groups, and reset expansion to five.
The complete special group remains first; exclusions apply to it too. Clearing the
list allows all feasible dishes and remains empty after restart.

On first run the list contains **蒸树枝**, **潮湿黏糊**, and **怪物千层饼**, as requested
by the user. These are recommendation preferences, not new food-type/game-rule data.
The initial stable dish IDs are in `data/signature_exclusions.default.json`. The mutable
server-wide list lives in `.local/signature_exclusions.json`, beside the selected
`--settings` database. LAN users share it. Back up this JSON separately from the wiki
snapshot. Defaults seed only a missing file and never overwrite an existing empty list.

The JSON is deliberately simple:

```json
{
  "schema_version": 1,
  "dish_ids": ["huiji:蒸树枝", "huiji:潮湿黏糊", "huiji:怪物千层饼"]
}
```

The filter runs **after** the full cooking search, only when returning signature
recommendations. Excluded recipes still participate in priority competition and ties.
Hiding a winning dish cannot promote a losing recipe or change any displayed example's
probability. Dish prediction, ingredient exploration, catalog cards/tables, detail views,
and dish examples use all original recipes. The source database and rarity settings
are unchanged by exclusion edits.

`GET /api/signature-exclusions` returns `{version, dish_ids}`; the version is a content
hash, so manual JSON edits are detected on the next read. `POST` accepts
`{dish_id, excluded, expected_version}` with a Boolean `excluded`. Signature responses
include `exclusion_version` and `excluded_dish_ids`. Writes use same-origin JSON requests,
atomic file replacement, and a server lock. Stale LAN edits return 409 with the latest
`exclusions`; review and retry the action. Failed writes retain the prior valid file.
Malformed saved JSON is reported rather than reset. Unknown stored IDs are preserved
for future snapshots, but API edits must reference known dishes.

`tests/test_signature_exclusions.py` checks defaults, persistence, empty lists, atomic
write failures, validation, concurrent conflicts, both-group filtering, and unchanged
predictor/catalog/ingredient/example results. Browser checks cover search, add/remove,
pagination refresh, error recovery, keyboard focus, and narrow screens.

## Actual outcome feasibility

An ingredient's presence in a recipe tree does not prove that dish can be produced.
Every listed dish must have a four-item completion containing the selected state that
survives cooker filtering and all higher-priority competition with nonzero probability.
Tied highest-priority recipes remain possible under the confirmed uniform-tie rule.
The same exact-pot ingredient universe, state tags, prefab counts, and cooker profiles
are used as **出锅预测**. Inventory is unlimited and duplicates are allowed.

Each card includes a concrete four-item example and that example's chance. This is not
the probability from an arbitrary pot containing the selected ingredient. Its other three
slots have the lowest possible total user-defined rarity under the exact model. One copy
of the selected state is fixed; additional copies contribute their rarity as usual. Common,
unprepared states break equal-cost representative ties. This is not an inventory-aware
search or a claim about actual acquisition effort. **放入出锅预测** transfers all four
state IDs and the selected cooker into the predictor and evaluates the pot there.

Search covers all remaining triples with repetition. It has no sampling or time cutoff.
To keep this practical, states are interchangeable for search only when their
contributions to **every captured tag and named-group condition** are identical. The
current snapshot's 145 states have 68 such profiles. Each profile uses its cheapest state
at the current settings revision, with no change to the selected exact state. A bit mask evaluates the final slot
in parallel, and descending priority groups exclude strictly higher matches while
preserving ties. All prefixes are compared for minimum additional cost; finding one witness
does not stop optimization. Each displayed example is replayed through `ExactPotPredictor`.

Search caches are in memory, bounded by the finite state/cooker universe, and cleared
on server restart or a rarity revision change. CPU searches are serialized across clients; browser requests are
cancelled when the selection changes, and stale results cannot replace a new selection.
Failed requests retain the selection and offer a retry.

## Scope and validation

This is a discovery feature for the existing **experimental wiki model**. It does not
promote readiness flags or establish independent in-game/build verification. Nutrition
uses wiki base table values, not character-effective stats. Per-cooker ingredient
eligibility retains the predictor's disclosed assumption; ancient kiln and inventory
constraints remain unsupported.

The signature search retains the exact predictor's full state universe, including prepared
states. The three **料理示例** in a dish detail use a separate unprepared-state selection
policy. See `RARITY_AND_EXAMPLES.md` for editing, minimum-cost examples, and persistence.

`tests/test_signature.py` compares complete result sets with a separate brute-force
completion loop over a synthetic universe, including exact decimal boundaries, OR
branches, tied priorities, portable-only rules, equivalent states, and a named recipe
that always loses to a higher-priority fallback. Actual-snapshot checks replay witnesses
for raw/cooked and duplicate-prefab states. Browser checks cover both groups, an
eight-dish first-group fixture, shared sorting, top-five expansion, unknown stats,
cooker changes, handoff to prediction, retry/cancellation, and narrow screens.

Run the full-snapshot witness validation:

```powershell
python scripts/validate_signature.py
```

It records all 290 state/cooker queries and their exact-model witness replays in
`SIGNATURE_VALIDATION_REPORT.json`. These are model/source-policy regression checks,
not claims of independent in-game outcomes. The content SQLite snapshot stays unchanged.

The read-only API returns both complete groups; the UI handles nutrition sorting and
the ranking modes and five-at-a-time display. Each row includes `additional_rarity` and
`example.total_rarity`; each response includes the coherent `rarity_version`:

```text
/api/signature?ingredient=honey&cooker=crock_pot
```

Both parameters must appear exactly once. Unknown states/cookers or extra parameters
return 422. Unsupported prediction data returns 503 without recommendations. Restart
the server after upgrading to load the new API and search index.
