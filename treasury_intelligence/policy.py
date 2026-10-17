"""Pure recommendations with explicit eligibility and modeled economics."""
from datetime import datetime, timedelta
from pydantic import StrictBool, field_validator, model_validator

from .economics import early_redemption_penalty, expected_net_economic_benefit, simple_annualized_vault_yield
from .reserve import calculate_required_reserve, candidate_deployable_surplus
from .types import Bps, Cents, Contract, DecisionResult, ForecastResult, Name, PositiveInt, TreasuryContext, TreasuryPolicy


class VaultTerms(Contract):
    """Caller-supplied product terms; maturity does not itself book cash."""
    vault_id: Name
    maturity_at: datetime | None = None  # None explicitly means no time lock.
    early_redemption_allowed: StrictBool = False
    early_redemption_penalty_bps: Bps = 0
    early_redemption_fixed_fee_cents: Cents = 0
    sweep_eligible: StrictBool = False
    transaction_cost_cents: Cents = 0  # Charged once for this modeled action.
    opportunity_cost_cents: Cents = 0

    @field_validator("maturity_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("maturity_at requires an ISO 8601 string or datetime")
        return value


class TreasuryDecisionPolicy(TreasuryPolicy):
    """Additive policy extension; original TreasuryPolicy fields stay frozen."""
    sweep_window_open: StrictBool = False
    sweep_cap_cents: Cents | None = None
    holding_minutes: PositiveInt = 1440
    vault_terms: tuple[VaultTerms, ...] = ()

    @model_validator(mode="after")
    def unique_terms(self):
        if len({v.vault_id for v in self.vault_terms}) != len(self.vault_terms):
            raise ValueError("vault terms must have unique IDs")
        return self


def recommend_treasury_action(context: TreasuryContext, forecast: ForecastResult,
                              policy: TreasuryPolicy) -> DecisionResult:
    if context.as_of != forecast.generated_at:
        raise ValueError("context and forecast timestamps must match")
    reserve = calculate_required_reserve(forecast, policy)
    balance = context.checking_balance_cents
    required = reserve.required_reserve_cents
    prefix = (f"checking_cents={balance}; peak_shortfall_cents={reserve.net_drain_cents}; "
              f"uncertainty_buffer_cents={reserve.uncertainty_buffer_cents}; "
              f"operational_buffer_cents={reserve.base_buffer_cents}; required_reserve_cents={required}; ")

    def result(action, reason, amount=0, vault_id=None):
        return DecisionResult(as_of=context.as_of, action=action, amount_cents=amount,
                              vault_id=vault_id, reserve=reserve, reason=prefix + reason)

    controls = policy if isinstance(policy, TreasuryDecisionPolicy) else None
    terms = {t.vault_id: t for t in controls.vault_terms} if controls else {}
    if set(terms) - {v.vault_id for v in context.vaults}:
        raise ValueError("vault terms reference an unknown vault")

    def penalty(gross, term, at):
        early = term.maturity_at is not None and at < term.maturity_at
        return early_redemption_penalty(gross, term.early_redemption_penalty_bps,
            early_redemption=early, fixed_fee_cents=term.early_redemption_fixed_fee_cents)

    # Immediate reserve protection takes precedence over every investment rule.
    if balance < required:
        deficit = required - balance
        candidates = []
        accessible = 0
        for vault in context.vaults:
            term = terms.get(vault.vault_id)
            if term is None or vault.withdrawal_delay_minutes != 0:
                continue
            locked = term.maturity_at is not None and context.as_of < term.maturity_at
            if locked and not term.early_redemption_allowed:
                continue
            maximum = vault.withdrawable_cents
            net_max = max(0, maximum - penalty(maximum, term, context.as_of) - term.transaction_cost_cents)
            accessible += net_max
            if net_max < deficit:
                continue
            # Find the smallest gross redemption whose net proceeds cover deficit.
            low, high = 1, maximum
            while low < high:
                mid = (low + high) // 2
                net = mid - penalty(mid, term, context.as_of) - term.transaction_cost_cents
                if net >= deficit:
                    high = mid
                else:
                    low = mid + 1
            cost = penalty(low, term, context.as_of)
            candidates.append((cost + term.transaction_cost_cents, vault.vault_id, low, cost, term.transaction_cost_cents))
        if not candidates:
            return result("LIQUIDITY_WARNING", f"deficit_cents={deficit}; accessible_net_cents={accessible}; "
                f"unfunded_cents={max(0, deficit - accessible)}; no single immediately redeemable vault covers deficit; "
                "multi-vault funding requires a separate plan.")
        _, vault_id, gross, cost, fee = min(candidates)
        net = gross - cost - fee
        return result("WITHDRAW", f"deficit_cents={deficit}; gross_redemption_cents={gross}; "
            f"penalty_cents={cost}; transaction_cost_cents={fee}; net_proceeds_cents={net}; "
            f"checking_after_cents={balance + net}; immediate liquidity takes precedence over yield.", gross, vault_id)

    surplus = candidate_deployable_surplus(balance, required)
    if balance * 10_000 <= required * (10_000 + policy.tolerance_bps):
        return result("HOLD", f"surplus_cents={surplus}; within tolerance_bps={policy.tolerance_bps}.")
    if surplus < policy.min_transfer_cents or surplus == 0:
        return result("HOLD", f"surplus_cents={surplus}; below minimum_sweep_cents={policy.min_transfer_cents}.")
    if controls is None or not controls.sweep_window_open:
        return result("HOLD", f"surplus_cents={surplus}; sweep window closed or eligibility unspecified.")
    cap = balance * policy.max_allocation_bps // 10_000
    if controls.sweep_cap_cents is not None:
        cap = min(cap, controls.sweep_cap_cents)
    exit_at = context.as_of + timedelta(minutes=controls.holding_minutes)
    candidates = []
    exclusions = []
    for vault in context.vaults:
        term = terms.get(vault.vault_id)
        if term is None or not term.sweep_eligible:
            exclusions.append(f"{vault.vault_id}: sweep ineligible")
            continue
        early_exit = term.maturity_at is not None and exit_at < term.maturity_at
        if early_exit and not term.early_redemption_allowed:
            exclusions.append(f"{vault.vault_id}: locked beyond holding period")
            continue
        if vault.withdrawal_delay_minutes > controls.holding_minutes:
            exclusions.append(f"{vault.vault_id}: settlement delay exceeds holding period")
            continue
        amount = min(cap, max(0, surplus - term.transaction_cost_cents))
        if amount == 0 or amount < policy.min_transfer_cents:
            exclusions.append(f"{vault.vault_id}: candidate_cents={amount} below minimum_sweep_cents={policy.min_transfer_cents}")
            continue
        expected = simple_annualized_vault_yield(amount, vault.annual_yield_bps,
                                               holding_minutes=controls.holding_minutes)
        cost = penalty(amount, term, exit_at)
        benefit = expected_net_economic_benefit(expected, penalty_cents=cost,
            transaction_cost_cents=term.transaction_cost_cents, opportunity_cost_cents=term.opportunity_cost_cents)
        explanation = (f"surplus_cents={surplus}; sweep_cap_cents={cap}; candidate_cents={amount}; "
            f"holding_minutes={controls.holding_minutes}; expected_yield_cents={expected}; penalty_cents={cost}; "
            f"transaction_cost_cents={term.transaction_cost_cents}; opportunity_cost_cents={term.opportunity_cost_cents}; "
            f"expected_net_benefit_cents={benefit}; checking_after_cents={balance - amount - term.transaction_cost_cents}")
        if benefit <= 0:
            exclusions.append(f"{vault.vault_id}: {explanation}; no positive modeled benefit")
            continue
        candidates.append((-benefit, vault.vault_id, amount, explanation))
    if not candidates:
        return result("HOLD", "; ".join(exclusions) or f"surplus_cents={surplus}; no eligible vaults.")
    _, vault_id, amount, explanation = min(candidates)
    return result("SWEEP", explanation + "; recommendation only; expected returns are not realized.", amount, vault_id)
