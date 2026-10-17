"""Reproduce RJ-M1-14 measured evaluation and demos; never writes source data."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from treasury_intelligence.hourly_forecasting import load_organizer_dataset
from treasury_intelligence.ml_forecasting import evaluate_hourly_forecast_models
from treasury_intelligence.four_tier_demo import run_four_tier_demo
from treasury_intelligence.demo import run_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--output', type=Path, default=Path('docs/member1/RELEASE_RESULTS.json'))
    args = parser.parse_args()
    before = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    observations = load_organizer_dataset(args.dataset)
    reports = evaluate_hourly_forecast_models(observations, horizons=(1, 3, 6, 15, 24),
        train_ratio=0.70, val_ratio=0.15, eval_stride=24,
        algorithms=('hist_gradient_boosting',), random_state=42)
    demo = run_four_tier_demo(args.dataset, limit=None, seed=42)
    assert demo.all_passed
    # Validate the actual nested recommendation serialization boundary.
    for scenario in demo.scenarios:
        assert scenario.model_validate_json(scenario.model_dump_json()) == scenario
    run_demo()
    after = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    assert before == after
    output = {
        'dataset_sha256_before': before, 'dataset_sha256_after': after,
        'row_count': len(observations), 'source_field_count': len(type(observations[0]).model_fields),
        'source_start': observations[0].timestamp.isoformat(),
        'source_end': observations[-1].timestamp.isoformat(),
        'versions': {name: importlib.metadata.version(name) for name in ('pydantic', 'scikit-learn')},
        'configuration': {'train_ratio': '0.70', 'validation_ratio': '0.15', 'stride': 24, 'seed': 42,
            'net_target': 'deposits_minus_withdrawals',
            'peak_metric': 'hour-end cumulative drain, not intrahour payout failure',
            'paths_may_overlap': True,
            'training_rows': int(len(observations) * 0.70),
            'validation_end_exclusive': int(len(observations) * (0.70 + 0.15)),
            'calibration_cutoff': observations[int(len(observations) * (0.70 + 0.15)) - 1].timestamp.isoformat()},
        'evaluation': [r.model_dump(mode='json') for r in reports],
        'demo_passed': demo.all_passed,
        'demo_summary': demo.summary_report,
        'demo_scenarios': [{
            'id': s.scenario_id, 'summary_action': s.summary_action,
            'required_reserve_cents': s.required_reserve_cents,
            'estimated_income_cents': s.estimated_income_cents,
            'targets_cents': [s.tier0_cash_target_cents, s.tier1_repo_target_cents,
                s.tier2_bond_target_cents, s.tier3_equity_target_cents],
            'orders': [o.model_dump(mode='json') for o in s.recommended_orders],
            'calculations': s.calculation_breakdown} for s in demo.scenarios],
    }
    args.output.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(demo.summary_report)
    for report in reports:
        print(report.horizon_hours, report.test_sample_count, report.mae_net_usd,
              report.baseline_mae_net_usd, report.net_mae_improvement_pct)
    print('Source SHA256 unchanged:', after)


if __name__ == '__main__':
    main()
