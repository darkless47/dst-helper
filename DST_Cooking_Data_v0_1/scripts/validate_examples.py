"""Replay every dish example with default and signed custom rarity scenarios."""
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handbook.catalog import Catalog, DEFAULT_DATABASE
from handbook.examples import DishExamples
from handbook.prediction import ExactPotPredictor
from handbook.preparation import PREPARED_IDS


def main():
    before = hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest()
    snapshot = Catalog().prediction_snapshot()
    predictor = ExactPotPredictor(snapshot)
    started = perf_counter()
    replayed, queries, fewer, timings = 0, 0, [], []
    scenarios = [('default_zero', {}), ('signed_custom', {'mandrake': 25, 'butter': 12, 'twigs': -2, 'ice': -1, 'meat': 3})]
    for name, rarities in scenarios:
        search = DishExamples(predictor, snapshot['dishes'], rarities)
        for recipe, _ in predictor.recipes:
            for cooker in predictor.policy['cookers']:
                tick = perf_counter()
                result = search.examples(recipe['dish_id'], cooker)
                timings.append(perf_counter() - tick)
                assert result['complete']
                examples = result['examples']
                assert len(examples) <= 3
                assert [r['total_rarity'] for r in examples] == sorted(r['total_rarity'] for r in examples)
                assert len(examples) == len({tuple(sorted(r['ingredients'])) for r in examples})
                if result['available'] and len(examples) < 3:
                    fewer.append(dict(scenario=name, dish=recipe['name_zh'], cooker=cooker, count=len(examples)))
                if not result['available']:
                    assert not examples
                for row in examples:
                    pot = row['ingredients']
                    assert len(pot) == 4
                    assert not set(pot) & PREPARED_IDS  # No actual snapshot recipe explicitly requires a prepared-only named group.
                    assert row['total_rarity'] == sum(rarities.get(item, 0) for item in pot)
                    outcome = next(r for r in predictor.predict(pot, cooker)['outcomes'] if r['dish_id'] == recipe['dish_id'])
                    assert row['probability'] == outcome['probability'] and outcome['probability']['value'] > 0
                    replayed += 1
                queries += 1
    assert hashlib.sha256(DEFAULT_DATABASE.read_bytes()).hexdigest() == before
    report = dict(checked_date='2026-11-09', source_revision=predictor.metadata['source_revision'],
                  dishes=len(snapshot['dishes']), scenarios=[name for name, _ in scenarios],
                  complete_queries_checked=queries, example_pots_replayed=replayed,
                  processed_states_excluded=len(PREPARED_IDS), fewer_than_three=fewer,
                  cold_query_max_seconds=round(max(timings), 3), elapsed_seconds=round(perf_counter()-started, 3),
                  optimality_evidence='Independent exhaustive synthetic tests with zero, positive, negative and extreme signed costs; full snapshot witness replay',
                  evidence_level='Experimental exact-model/source-policy checks, not independent game outcomes',
                  content_database_sha256=before, content_modified=False, readiness_flags_promoted=False)
    (ROOT/'EXAMPLES_VALIDATION_REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
