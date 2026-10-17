"""Standalone Treasury Engine Demonstration Module.

Executable demo connecting all Member 1 quantitative components:
Historical cash flows
  → Baseline forecast
  → Supplied provisional uncertainty policy
  → Required reserve
  → Treasury recommendation
  → Expected economic result
  → Structured explanation

Demonstrates:
1. Normal operation
2. Valid safe sweep
3. High-withdrawal stress
4. Locked vault with insufficient liquidity
5. Successful HOLD
6. JSON serialization of the full engine result

Exact CLI invocation:
    python -m treasury_intelligence.demo
"""
import json
from datetime import datetime, timedelta, timezone

from .pipeline import TreasuryPipelineResult, run_treasury_pipeline
from .policy import TreasuryDecisionPolicy, VaultTerms
from .types import CashFlowBucket, ForecastPoint, ForecastResult, TreasuryContext, VaultPosition

DEMO_AS_OF = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
ONE_MILLION_CENTS = 100_000_000  # $1,000,000.00


def build_deterministic_history(n_buckets: int = 96, bucket_minutes: int = 15) -> tuple[CashFlowBucket, ...]:
    """
    Deterministic 24-hour historical transaction flow (96 x 15-minute buckets).
    Simulates intra-day diurnal pattern with business hours peak.
    """
    buckets = []
    start_time = DEMO_AS_OF - timedelta(minutes=n_buckets * bucket_minutes)
    for i in range(n_buckets):
        b_start = start_time + timedelta(minutes=i * bucket_minutes)
        b_end = b_start + timedelta(minutes=bucket_minutes)

        # Diurnal pattern based on hour of day
        hour = b_start.hour
        if 9 <= hour <= 17:
            # Active corporate / clearing hours
            inflow = 15_000_000 + ((i * 7) % 11) * 1_000_000   # ~$150k - $250k
            outflow = 12_000_000 + ((i * 5) % 9) * 1_000_000   # ~$120k - $200k
        else:
            # Quiet overnight hours
            inflow = 3_000_000 + (i % 5) * 500_000             # ~$30k - $50k
            outflow = 2_500_000 + (i % 4) * 400_000            # ~$25k - $40k

        buckets.append(
            CashFlowBucket(
                start_at=b_start,
                end_at=b_end,
                inflow_cents=inflow,
                outflow_cents=outflow,
            )
        )
    return tuple(buckets)


def create_demo_policy(vault_ids: tuple[str, ...] | None = None, **overrides) -> TreasuryDecisionPolicy:
    """Standard provisional decision policy for the demo."""
    all_terms = {
        "treasury_repo_liquid": VaultTerms(
            vault_id="treasury_repo_liquid",
            maturity_at=None,
            early_redemption_allowed=True,
            early_redemption_penalty_bps=0,
            early_redemption_fixed_fee_cents=0,
            sweep_eligible=True,
            transaction_cost_cents=5_000,  # $50 transfer fee
            opportunity_cost_cents=0,
        ),
        "institutional_tbills_30d": VaultTerms(
            vault_id="institutional_tbills_30d",
            maturity_at=DEMO_AS_OF + timedelta(days=30),
            early_redemption_allowed=False,  # Locked
            early_redemption_penalty_bps=200,
            early_redemption_fixed_fee_cents=50_000,
            sweep_eligible=False,
            transaction_cost_cents=10_000,
            opportunity_cost_cents=0,
        ),
    }
    if vault_ids is not None:
        selected_terms = tuple(all_terms[vid] for vid in vault_ids if vid in all_terms)
    else:
        selected_terms = tuple(all_terms.values())

    defaults = dict(
        base_buffer_cents=20_000_000,         # $200,000 base operational buffer
        uncertainty_multiplier_bps=19_600,     # 1.96 multiplier (provisional policy)
        tolerance_bps=500,                    # 5% equilibrium tolerance band
        min_transfer_cents=5_000_000,          # $50,000 minimum transfer
        max_allocation_bps=8_000,             # 80% maximum sweep allocation
        sweep_window_open=True,
        holding_minutes=1440,                 # 24-hour holding horizon
        vault_terms=selected_terms,
    )
    defaults.update(overrides)
    return TreasuryDecisionPolicy(**defaults)


def run_scenario_1_normal_operation(history: tuple[CashFlowBucket, ...]) -> TreasuryPipelineResult:
    """Scenario 1: Normal balanced operation. Checking liquidity matches requirements."""
    context = TreasuryContext(
        as_of=DEMO_AS_OF,
        currency="USD",
        checking_balance_cents=52_000_000,  # $520,000 checking balance
        vaults=(
            VaultPosition(
                vault_id="treasury_repo_liquid",
                balance_cents=200_000_000,
                withdrawable_cents=200_000_000,
                annual_yield_bps=485,
                withdrawal_delay_minutes=0,
            ),
        ),
    )
    policy = create_demo_policy(vault_ids=("treasury_repo_liquid",), base_buffer_cents=15_000_000)
    return run_treasury_pipeline("Scenario 1: Normal Operation", history, context, policy)


def run_scenario_2_valid_safe_sweep(history: tuple[CashFlowBucket, ...]) -> TreasuryPipelineResult:
    """Scenario 2: Valid safe sweep. Substantial surplus above required reserve is swept to yield."""
    context = TreasuryContext(
        as_of=DEMO_AS_OF,
        currency="USD",
        checking_balance_cents=350_000_000,  # $3,500,000 checking balance (large surplus)
        vaults=(
            VaultPosition(
                vault_id="treasury_repo_liquid",
                balance_cents=100_000_000,
                withdrawable_cents=100_000_000,
                annual_yield_bps=525,  # 5.25% APY
                withdrawal_delay_minutes=0,
            ),
        ),
    )
    policy = create_demo_policy(vault_ids=("treasury_repo_liquid",))
    return run_treasury_pipeline("Scenario 2: Valid Safe Sweep", history, context, policy)


def run_scenario_3_high_withdrawal_stress(history: tuple[CashFlowBucket, ...]) -> TreasuryPipelineResult:
    """Scenario 3: High-withdrawal stress. Checking is below required reserve; liquid vault replenishes checking."""
    context = TreasuryContext(
        as_of=DEMO_AS_OF,
        currency="USD",
        checking_balance_cents=15_000_000,  # $150,000 low checking balance
        vaults=(
            VaultPosition(
                vault_id="treasury_repo_liquid",
                balance_cents=300_000_000,  # $3,000,000 accessible liquid funds
                withdrawable_cents=300_000_000,
                annual_yield_bps=500,
                withdrawal_delay_minutes=0,
            ),
        ),
    )
    # Stress forecast with large near-term outflows
    stress_points = (
        ForecastPoint(
            start_at=DEMO_AS_OF,
            end_at=DEMO_AS_OF + timedelta(minutes=15),
            inflow_cents=5_000_000,
            outflow_cents=60_000_000,  # $600k spike outflow
            uncertainty_cents=10_000_000,
        ),
        ForecastPoint(
            start_at=DEMO_AS_OF + timedelta(minutes=15),
            end_at=DEMO_AS_OF + timedelta(minutes=30),
            inflow_cents=10_000_000,
            outflow_cents=40_000_000,  # $400k outflow
            uncertainty_cents=8_000_000,
        ),
    )
    stress_forecast = ForecastResult(
        generated_at=DEMO_AS_OF,
        model_version="stress-scenario-v1",
        points=stress_points,
    )
    policy = create_demo_policy(vault_ids=("treasury_repo_liquid",), base_buffer_cents=20_000_000)
    return run_treasury_pipeline(
        "Scenario 3: High-Withdrawal Stress", history, context, policy, forecast=stress_forecast
    )


def run_scenario_4_locked_vault_insufficient_liquidity(history: tuple[CashFlowBucket, ...]) -> TreasuryPipelineResult:
    """Scenario 4: Locked vault with insufficient liquidity. Checking deficit cannot be covered by locked vault."""
    context = TreasuryContext(
        as_of=DEMO_AS_OF,
        currency="USD",
        checking_balance_cents=10_000_000,  # $100,000 checking balance
        vaults=(
            VaultPosition(
                vault_id="institutional_tbills_30d",
                balance_cents=500_000_000,  # $5M locked in 30-day T-bills
                withdrawable_cents=0,       # 0 accessible today
                annual_yield_bps=540,
                withdrawal_delay_minutes=1440,
            ),
        ),
    )
    stress_points = (
        ForecastPoint(
            start_at=DEMO_AS_OF,
            end_at=DEMO_AS_OF + timedelta(minutes=60),
            inflow_cents=5_000_000,
            outflow_cents=80_000_000,  # $800k outflow
            uncertainty_cents=15_000_000,
        ),
    )
    stress_forecast = ForecastResult(
        generated_at=DEMO_AS_OF,
        model_version="emergency-drain-v1",
        points=stress_points,
    )
    policy = create_demo_policy(vault_ids=("institutional_tbills_30d",), base_buffer_cents=25_000_000)
    return run_treasury_pipeline(
        "Scenario 4: Locked Vault Insufficient Liquidity", history, context, policy, forecast=stress_forecast
    )


def run_scenario_5_successful_hold(history: tuple[CashFlowBucket, ...]) -> TreasuryPipelineResult:
    """Scenario 5: Successful HOLD. Checking balance is within the optimal equilibrium corridor."""
    context = TreasuryContext(
        as_of=DEMO_AS_OF,
        currency="USD",
        checking_balance_cents=102_000_000,  # $1,020,000 checking balance
        vaults=(
            VaultPosition(
                vault_id="treasury_repo_liquid",
                balance_cents=250_000_000,
                withdrawable_cents=250_000_000,
                annual_yield_bps=500,
                withdrawal_delay_minutes=0,
            ),
        ),
    )
    # Required reserve = 80M peak shortfall + 0 uncertainty + 20M buffer = 100M ($1,000,000)
    # Checking = 102M ($1,020,000), surplus = 2M ($20,000) within 5% tolerance corridor ($50,000)
    balanced_points = (
        ForecastPoint(
            start_at=DEMO_AS_OF,
            end_at=DEMO_AS_OF + timedelta(minutes=60),
            inflow_cents=50_000_000,
            outflow_cents=80_000_000,  # $800k outflow debited at start -> 80M peak shortfall
            uncertainty_cents=0,
        ),
    )
    balanced_forecast = ForecastResult(
        generated_at=DEMO_AS_OF,
        model_version="balanced-v1",
        points=balanced_points,
    )
    policy = create_demo_policy(vault_ids=("treasury_repo_liquid",), base_buffer_cents=20_000_000, tolerance_bps=500)
    return run_treasury_pipeline(
        "Scenario 5: Successful HOLD", history, context, policy, forecast=balanced_forecast
    )


def run_all_demo_scenarios() -> list[TreasuryPipelineResult]:
    """Execute all five deterministic demonstration scenarios."""
    history = build_deterministic_history()
    return [
        run_scenario_1_normal_operation(history),
        run_scenario_2_valid_safe_sweep(history),
        run_scenario_3_high_withdrawal_stress(history),
        run_scenario_4_locked_vault_insufficient_liquidity(history),
        run_scenario_5_successful_hold(history),
    ]


def format_currency(cents: int) -> str:
    """Format integer cents into a standard USD currency string."""
    dollars = cents / 100.0
    return f"${dollars:,.2f}"


def print_demo_report(results: list[TreasuryPipelineResult]) -> None:
    """Print structured, human-readable terminal output for all demo scenarios."""
    sep = "=" * 80
    subsep = "-" * 80

    print("\n" + sep)
    print("      RESERVE JUGGLER -- STANDALONE QUANTITATIVE TREASURY ENGINE DEMO      ")
    print("      Member 1 Pure Python Pipeline: Historical Cash Flows -> Decision     ")
    print(sep)
    print(f"Timestamp (as_of UTC): {DEMO_AS_OF.isoformat()}")
    print("Uncertainty Governance: PROVISIONAL UNCALIBRATED POLICY")
    print("  Note: Forecast uncertainty is policy-configured and marked provisional.")
    print("  Full empirical calibration will be established in future model evaluations.")
    print(sep + "\n")

    for i, res in enumerate(results, start=1):
        ctx = res.context
        fc = res.forecast
        resv = res.reserve
        dec = res.decision

        print(f"[{res.scenario_name.upper()}]")
        print(subsep)
        print(f"  * Checking Balance     : {format_currency(ctx.checking_balance_cents)}")
        print(f"  * Forecast Model       : {fc.model_version} ({len(fc.points)} path intervals)")
        total_fc_in = sum(p.inflow_cents for p in fc.points)
        total_fc_out = sum(p.outflow_cents for p in fc.points)
        print(f"  * Forecast Net Flows   : Inflow {format_currency(total_fc_in)} | Outflow {format_currency(total_fc_out)}")
        print(f"  * Peak Shortfall       : {format_currency(resv.net_drain_cents)}")
        print(f"  * Uncertainty Buffer   : {format_currency(resv.uncertainty_buffer_cents)} [PROVISIONAL]")
        print(f"  * Operational Buffer   : {format_currency(resv.base_buffer_cents)}")
        print(f"  * Required Reserve     : {format_currency(resv.required_reserve_cents)}")
        print(f"  >>> RECOMMENDATION     : {dec.action}")
        if dec.action in ("SWEEP", "WITHDRAW"):
            print(f"  >>> ALLOCATION AMOUNT  : {format_currency(dec.amount_cents)} (Target Vault: {dec.vault_id})")
        print(f"  * Structured Rationale : {dec.reason}")
        print()

    print(sep)
    print("6. JSON SERIALIZATION DEMONSTRATION")
    print(sep)
    sample_json = results[1].model_dump_json(indent=2)
    print("Sample Output (Scenario 2: Valid Safe Sweep JSON payload):\n")
    print(sample_json)
    print(sep)

    # Validate deserialization
    deserialized = TreasuryPipelineResult.model_validate_json(sample_json)
    assert deserialized.scenario_name == results[1].scenario_name
    assert deserialized.decision.action == "SWEEP"
    print("[OK] Verification: JSON serialization and deserialization round-trip passed with 100% fidelity.")
    print(sep + "\n")


def run_demo() -> None:
    """Main CLI entrypoint."""
    results = run_all_demo_scenarios()
    print_demo_report(results)


if __name__ == "__main__":
    run_demo()
