"""Replay every discovered witness for every recorded state and supported cooker."""
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.prediction import ExactPotPredictor
from handbook.signature import SignatureRecipes


def main():
    before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
    snapshot = Catalog().prediction_snapshot()
    predictor = ExactPotPredictor(snapshot)
    discovery = SignatureRecipes(predictor, snapshot['dishes'])
    started = perf_counter()
    queries, examples = 0, 0
    for selected in predictor.ingredients:
        for cooker in predictor.policy['cookers']:
            result = discovery.recommend(selected, cooker)
            assert result['complete']
            rows = result['special'] + result['other']
            assert len(rows) == len({row['dish_id'] for row in rows})
            for row in rows:
                pot = row['example']['ingredients']
                assert len(pot) == 4 and pot[0] == selected
                checked = predictor.predict(pot, cooker)
                actual = next((outcome for outcome in checked['outcomes'] if outcome['dish_id'] == row['dish_id']), None)
                assert actual is not None, (selected, cooker, row['dish_id'])
                assert actual['probability'] == row['example']['probability']
                assert actual['probability']['value'] > 0
                assert row['additional_rarity'] == row['example']['total_rarity'] == 0
                examples += 1
            queries += 1
    assert hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() == before
    report = dict(checked_date='2026-11-09', source_revision=predictor.metadata['source_revision'],
                  ingredient_states=len(predictor.ingredients), supported_cookers=list(predictor.policy['cookers']),
                  mechanical_profiles=discovery.profile_count, complete_queries_checked=queries,
                  example_pots_replayed=examples, elapsed_seconds=round(perf_counter() - started, 3),
                  all_examples_have_selected_state=True, all_examples_survive_priority_and_cooker_rules=True,
                  rarity_scenario='Default zero; signed-cost optimality covered by independent exhaustive synthetic fixtures',
                  classification='Positive explicit named ingredient groups first; general tag matches second',
                  completeness='All remaining triples with repetition, compressed only by equivalence under every captured recipe rule',
                  evidence_level='Exact-model and source-policy regression, not independent in-game outcomes',
                  content_database_sha256=before, content_modified=False, readiness_flags_promoted=False)
    (ROOT / 'SIGNATURE_VALIDATION_REPORT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
