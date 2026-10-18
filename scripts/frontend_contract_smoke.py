#!/usr/bin/env python3
"""Frontend contract smoke test for the Reserve Juggler backend (Agent 3 QA).

Exercises the routes the frontend consumes and validates them against the
frontend wire format (frontend/src/api/validation.js + treasuryApi.js are the
authority). HTTP-only: it never reads or mutates the organizer CSV, the
database, or any local files. Safe to rerun: it always creates a fresh run.

Check sequence:
 1. GET  /health
 2. POST /api/v1/runs (documented create request)
 3. GET  /api/v1/runs/{id}/snapshot   (required fields, ISO UTC timestamp,
    integer cents, safe-integer range, status/policy/deployable-surplus
    presence, four_tier portfolio structure when present)
 4. POST /api/v1/runs/{id}/advance    (returned step advances by 1)
 5. POST /api/v1/runs/{id}/advance    (stale expected_step must yield HTTP 409)
 6. POST /api/v1/runs/{id}/scenario   (effective_step scheduling echo)
 7. PATCH /api/v1/runs/{id}/policy    (exact legacy frontend field names)
 8. GET  history / forecast / decisions / transactions ({items}/{points}
    envelopes and basic data types)
 9. POST /api/v1/runs/{id}/backtest   (frontend wire format first, then the
    documented variant; validates status, scenario, seed, days, the three
    strategy IDs, integer-cent metrics, timestamp/balance history points)
10. GET  /api/v1/runs/{id}/report

Endpoints still returning HTTP 501 are reported as "not implemented" and are
NOT counted as contract validation failures - but the script still exits
nonzero whenever the full contract check could not pass.

Scenario, backtest and policy parameters are configurable (see --help). The
script never asserts particular historical profits or fixture amounts.

Exit codes:
    0  every endpoint check passed
    1  at least one contract validation failure
    2  backend unreachable and/or endpoint checks skipped (e.g. HTTP 501),
       so the full contract check could not pass

Requires Python 3.10+ (standard library only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
MAX_SAFE_INTEGER = 9007199254740991  # Number.MAX_SAFE_INTEGER (2**53 - 1)
ISO_UTC_SUFFIX = re.compile(r"Z$|\+00:00$")

# Frontend Strategy Arena strategy IDs (frontend/src/mocks/constants.js)
ARENA_STRATEGY_IDS = ("STATIC", "REACTIVE", "RESERVE_JUGGLER")
# Published contract strategy IDs (contracts/openapi.yaml, backend v1_contracts.py)
DOCUMENTED_STRATEGY_IDS = ("STATIC_RESERVE", "REACTIVE_RESERVE", "RESERVE_JUGGLER")

SCENARIO_ENUMS = ("NORMAL", "HIGH_WITHDRAWAL", "LOW_DEPOSIT",
                  "SETTLEMENT_DELAY", "LIQUIDITY_SHOCK")
DECISION_ACTIONS = ("HOLD", "SWEEP", "WITHDRAW", "LIQUIDITY_WARNING")
TRANSACTION_TYPES = ("DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT")
DIRECTIONS = ("INFLOW", "OUTFLOW")

# Flat metric names the Strategy Arena table reads off each result item
# (frontend/src/mocks/mockEngine.js report(); StrategyArena.jsx exportCsv).
ARENA_FLAT_METRICS = (
    "realized_interest_cents", "average_checking_cents", "penalties_cents",
    "borrowing_costs_cents", "borrowing_outstanding_cents", "reserve_breaches",
    "emergency_events", "failed_payouts", "failed_payout_cents", "sweeps",
    "net_benefit_cents", "inflow_cents", "paid_outflow_cents",
)
# FinancialMetrics fields required by the published contract.
CONTRACT_METRICS = (
    "realized_interest_cents", "accrued_interest_cents", "average_checking_cents",
    "average_vault_cents", "redemption_penalties_cents",
    "emergency_borrowing_cost_cents", "emergency_events", "reserve_breaches",
    "failed_payouts", "unpaid_cents", "net_benefit_cents",
)

ICONS = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}


class Failure(Exception):
    """Contract validation failure inside one check."""


def fail(message: str):
    raise Failure(message)


class Smoke:
    """Collects check records (name, status, detail) and contract notes."""

    def __init__(self):
        self.records: list[tuple[str, str, str]] = []
        self.notes: list[str] = []

    def record(self, name: str, status: str, detail: str = ""):
        if status not in ICONS:
            raise ValueError(f"unknown status {status!r}")
        self.records.append((name, status, detail))
        print(f"    {ICONS[status]} {name}" + (f" - {detail}" if detail else ""))

    def note(self, message: str):
        self.notes.append(message)
        print(f"        || contract note: {message}")

    def run(self, name: str, function) -> str:
        print(f"\n>> {name}")
        length_before = len(self.records)
        try:
            function()
        except Failure as exc:
            self.record(name, "FAIL", str(exc))
        if len(self.records) == length_before:
            self.record(name, "PASS", "")
        elif len(self.records) == length_before + 1 and self.records[-1][0] != name:
            # A guard/helper recorded the verdict under the same check name.
            pass
        return self.records[-1][1] if self.records else "FAIL"

    @property
    def last_status(self) -> str:
        return self.records[-1][1] if self.records else "FAIL"


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def parse_json(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def describe(status: int | None, data, raw: str | None) -> str:
    if status is None:
        return "no response (transport error)"
    body = (raw or "").strip()[:200].replace("\n", " ")
    if isinstance(data, dict):
        for key in ("detail", "error_code", "message"):
            if key in data:
                body = f"{key}={data[key]}"
                break
    return f"HTTP {status}: {body}"


IN_PROCESS_CLIENT = None
REQUIRE_REAL = True


def detect_mock_fixture(data, context: str, smoke: Smoke | None = None) -> list[str]:
    """Inspects response payload for hallmarks of frontend mock fixtures."""
    indicators = []
    if not isinstance(data, dict):
        return indicators

    if data.get("mode") == "mock":
        indicators.append("top-level mode='mock'")
    if data.get("source") == "mock":
        indicators.append("top-level source='mock'")

    run_id = str(data.get("run_id") or "")
    if run_id.startswith("mock-") or run_id.startswith("backtest-"):
        indicators.append(f"synthetic mock run_id '{run_id}'")

    fc = data.get("forecast")
    if isinstance(fc, dict) and fc.get("model_version") == "mock-observed-baseline-v1":
        indicators.append("mock forecast model_version 'mock-observed-baseline-v1'")
    if data.get("model_version") == "mock-observed-baseline-v1":
        indicators.append("mock forecast model_version 'mock-observed-baseline-v1'")

    items = data.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            item_id = str(first.get("id") or "")
            if item_id.startswith("TX-") or item_id.startswith("D-"):
                indicators.append(f"synthetic mock collection item id '{item_id}'")
            if first.get("source") in ("Client deposits", "Merchant receipts"):
                indicators.append(f"synthetic mock transaction source '{first.get('source')}'")

    if indicators:
        reasons = "; ".join(indicators)
        if REQUIRE_REAL:
            fail(f"{context}: detected MOCK FIXTURE response ({reasons}). A live backend response is required!")
        elif smoke:
            smoke.note(f"{context}: mock fixture indicators detected ({reasons})")
    return indicators


def http(method: str, url: str, body: dict | None = None, timeout: float = 10.0):
    """Return (status, parsed_json_or_None, raw_text_or_None). `status` is None
    when the transport itself failed."""
    if IN_PROCESS_CLIENT is not None:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        try:
            resp = IN_PROCESS_CLIENT.request(method, path, json=body)
            return resp.status_code, parse_json(resp.text), resp.text
        except Exception as exc:
            print(f"        (in-process transport error: {exc})")
            return None, None, None

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json(raw), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, parse_json(raw), raw
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        print(f"        (transport error: {exc})")
        return None, None, None


def guard_available(smoke: Smoke, name: str, status, data, raw) -> bool:
    """True when the endpoint answered normally. Records SKIP when it is not
    implemented (HTTP 501) or the transport failed, distinguishing that state
    from a contract validation failure."""
    if status is None:
        smoke.record(name, "SKIP",
                     f"transport failure - {describe(None, data, raw)}")
        return False
    if status == 501:
        smoke.record(name, "SKIP",
                     "not implemented: HTTP 501 (contract defined; route is a "
                     "service stub) - NOT a contract validation failure: "
                     f"{describe(status, data, raw)}")
        return False
    return True


def have_run(smoke: Smoke, name: str, created: dict) -> bool:
    if created.get("run_id"):
        return True
    smoke.record(name, "SKIP",
                 "no run available (the create-run step failed or was skipped)")
    return False


def have_snapshot(smoke: Smoke, name: str, current: dict) -> bool:
    if is_int(current.get("step")):
        return True
    smoke.record(name, "SKIP",
                 "no post-advance snapshot available (the snapshot/advance "
                 "step failed or was skipped)")
    return False


# --------------------------------------------------------------------------- #
# Type validators (mirroring frontend/src/api/validation.js)
# --------------------------------------------------------------------------- #

def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def safe_int(value) -> bool:
    return is_int(value) and -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER


def nonneg_cents(value) -> bool:
    """Nonnegative integer cents within the JS safe range (None rejected)."""
    return safe_int(value) and value >= 0


def is_iso_utc(value) -> bool:
    if not isinstance(value, str) or not ISO_UTC_SUFFIX.search(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit_cents_fields(obj, label: str) -> None:
    """Every *_cents value must be an integer; values beyond the JS safe
    integer range are a genuine cross-stack contract failure (audit item 1)."""
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        if key.endswith("_cents") and value is not None:
            if not is_int(value):
                fail(f"{label}.{key} must be integer cents, got {value!r}")
            if abs(value) > MAX_SAFE_INTEGER:
                fail(f"{label}.{key}={value} exceeds JavaScript "
                     f"Number.MAX_SAFE_INTEGER ({MAX_SAFE_INTEGER}); JS consumers "
                     "cannot represent such JSON integers exactly (M11)")


def require_snapshot(data, context: str) -> dict:
    """Validate a SimulationSnapshot per the frontend validator."""
    if not isinstance(data, dict):
        fail(f"{context}: snapshot must be a JSON object, got {type(data).__name__}")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        fail(f"{context}: run_id must be a non-empty string")
    if not is_int(data.get("step")) or data["step"] < 0:
        fail(f"{context}: step must be a nonnegative integer")
    if not is_iso_utc(data.get("timestamp")):
        fail(f"{context}: timestamp {data.get('timestamp')!r} must be an ISO UTC "
             "string ending in 'Z' or '+00:00' (frontend validateSnapshot rule; "
             "organizer raw strings like '2026-01-02 18:00:00' are rejected)")
    for key in ("checking_cents", "vault_locked_cents",
                "vault_redeemable_cents", "required_reserve_cents"):
        value = data.get(key)
        if value is None:
            if key == "required_reserve_cents":
                fail(f"{context}: required_reserve_cents is null; the backend "
                     "contract permits null but the frontend validator requires "
                     "a nonnegative integer (checklist M10)")
            fail(f"{context}: {key} must be a nonnegative integer cent value")
        if not nonneg_cents(value):
            fail(f"{context}: {key} must be a nonnegative integer cent value")
    audit_cents_fields(data, context)
    decision = data.get("decision")
    if decision is not None:
        if not isinstance(decision, dict):
            fail(f"{context}: decision must be an object")
        if decision.get("action") not in DECISION_ACTIONS:
            fail(f"{context}: decision.action {decision.get('action')!r} must be "
                 f"one of {list(DECISION_ACTIONS)}")
        amount = decision.get("amount_cents")
        if not safe_int(amount):
            fail(f"{context}: decision.amount_cents must be an integer cent value")
        if not isinstance(decision.get("executed"), bool):
            fail(f"{context}: decision.executed must be boolean")
    return data


def audit_snapshot_contract_extras(smoke: Smoke, run_id: str, data: dict) -> None:
    """Snapshot requirements the audit adds beyond the frontend validator."""
    status = data.get("status")
    if not (isinstance(status, str) and status):
        smoke.note("snapshot lacks a readable 'status' string (audit item 6; the "
                   "pydantic contract defaults it to READY, openapi.yaml omits "
                   "it - M9)")
    policy = data.get("policy")
    if policy is not None:
        if not isinstance(policy, dict):
            smoke.note("snapshot.policy is present but not an object")
        else:
            legacy = sorted({"min_sweep_cents", "vault_rate_bps", "lock_steps",
                             "allow_early_redemption"} & set(policy))
            canonical = sorted({"minimum_sweep_cents", "vault_yield_bps",
                                "vault_lock_steps", "early_redemption_allowed"}
                               & set(policy))
            if canonical:
                smoke.note("snapshot.policy echoes canonical backend fields "
                           f"{canonical} - the frontend expects its own legacy "
                           f"names {legacy or '(absent)'}; policy writes accept "
                           "frontend names but policy reads do not (M8)")
            percentile = policy.get("risk_percentile")
            if is_int(percentile) and percentile > 1:
                smoke.note("snapshot.policy.risk_percentile uses the frontend"
                           f" percent scale ({percentile}) - good for the UI;"
                           " the canonical contract stores 0.95-fraction scale,"
                           " so list which scale implementations must return")
    surplus = data.get("deployable_surplus_cents")
    if not nonneg_cents(surplus):
        smoke.note(f"snapshot lacks a usable deployable_surplus_cents value "
                   f"(got {surplus!r}); audit item 6 requires this field")
    four_tier = data.get("four_tier")
    if four_tier is None:
        smoke.note("snapshot carries no four_tier portfolio yet (optional in the "
                   "contract; the frontend accepts enveloped four_tier or "
                   "top-level tier keys)")
    else:
        try:
            audit_four_tier(four_tier)
            smoke.note("snapshot.four_tier portfolio passed the structure audit")
        except Failure as exc:
            smoke.note(f"snapshot.four_tier present but invalid: {exc}")


def audit_four_tier(portfolio) -> None:
    """four_tier portfolio structure required by the frontend (audit item 5)."""
    if not isinstance(portfolio, dict):
        fail("four_tier must be an object")
    for key in ("tier0", "tier1", "tier2", "tier3", "overdraft", "aggregates"):
        if not isinstance(portfolio.get(key), dict):
            fail(f"four_tier.{key} is missing (frontend requires tier0, tier1, "
                 "tier2, tier3, overdraft and aggregates)")
    if not nonneg_cents(portfolio["tier0"].get("checking_cents")):
        fail("four_tier.tier0.checking_cents must be nonnegative integer cents")
    if not nonneg_cents(portfolio["tier1"].get("principal_cents")):
        fail("four_tier.tier1.principal_cents must be nonnegative integer cents")
    if not nonneg_cents(portfolio["tier2"].get("market_value_cents")):
        fail("four_tier.tier2.market_value_cents must be nonnegative integer "
             "cents")
    if not nonneg_cents(portfolio["tier3"].get("market_value_cents")):
        fail("four_tier.tier3.market_value_cents must be nonnegative integer "
             "cents")
    if not nonneg_cents(portfolio["overdraft"].get("borrowing_outstanding_cents")):
        fail("four_tier.overdraft.borrowing_outstanding_cents must be "
             "nonnegative integer cents")
    liability_status = portfolio["overdraft"].get("liability_status")
    if liability_status is not None and liability_status not in ("ACTIVE", "CLEARED"):
        fail(f"four_tier.overdraft.liability_status {liability_status!r} must be "
             "ACTIVE or CLEARED")
    audit_cents_fields(portfolio, "four_tier")
    audit_cents_fields(portfolio["aggregates"], "four_tier.aggregates")


def require_items_envelope(data, context: str) -> list:
    """Frontend validateItems: the response must be {items: [...]}."""
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, list):
        fail(f"{context}: frontend requires an '{{items: [...]}}' envelope; the "
             "backend returned a bare JSON array (which matches today's "
             "contracts/openapi.yaml). Genuine contract disagreement recorded - "
             "checklist M1; neither side was chosen silently.")
    fail(f"{context}: expected an {{items: [...]}} envelope, got "
         f"{type(data).__name__}")


def note_error_shape(smoke: Smoke, data, status: int, context: str) -> None:
    """HTTP error bodies should follow ErrorResponse or the plain FastAPI
    detail fallback; record which shape arrived."""
    if isinstance(data, dict):
        if {"error_code", "message", "details"} <= set(data):
            return
        if "detail" in data:
            smoke.note(f"{context}: HTTP {status} body uses the legacy FastAPI "
                       "'detail' shape rather than the ErrorResponse contract "
                       "(error_code/message/details)")
            return
    smoke.note(f"{context}: HTTP {status} body was not a recognizable error "
               f"object (type {type(data).__name__})")


# --------------------------------------------------------------------------- #
# Checks 1–10
# --------------------------------------------------------------------------- #

def check_health(smoke: Smoke, name: str, args, base: str) -> None:
    status, data, raw = http("GET", f"{base}/health", timeout=args.timeout)
    if status is None:
        fail(f"backend unreachable at {base} - start the service first (e.g. "
             "uvicorn app.main:app --port 8000)")
    if status != 200:
        fail(describe(status, data, raw))
    if not isinstance(data, dict) or not data.get("status"):
        fail(f"health payload is missing a 'status' value: {describe(status, data, raw)}")
    detect_mock_fixture(data, "health", smoke)


def check_create(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    body = {
        "initial_cash_cents": args.initial_cash_cents,
        "duration_steps": args.duration_steps,
        "seed": args.seed,
        "scenario": args.scenario,
    }
    if args.start_time:
        body["start_time"] = args.start_time
    status, data, raw = http("POST", f"{base}/api/v1/runs", body,
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status not in (200, 201):
        fail(describe(status, data, raw))
    if not isinstance(data, dict) or not isinstance(data.get("run_id"), str):
        fail(f"create response is missing a string run_id: {describe(status, data, raw)}")
    detect_mock_fixture(data, "create", smoke)
    try:
        uuid.UUID(data["run_id"])
    except ValueError:
        smoke.note(f"create returned run_id {data['run_id']!r}, which is not a "
                   "canonical UUID (contract type is uuid)")
    created.update(data)
    if created.get("status") is not None and created.get("status") != "READY":
        smoke.note(f"create returned status {created['status']!r}; the contract "
                   "pins 'READY' (the frontend mock returns 'PAUSED')")
    balance = created.get("checking_cents")
    if balance is not None:
        if not nonneg_cents(balance):
            fail(f"RunCreated.checking_cents {balance!r} must be nonnegative "
                 "integer cents")
        if balance != args.initial_cash_cents:
            fail(f"RunCreated.checking_cents {balance} != the requested initial "
                 f"cash {args.initial_cash_cents}")
        smoke.note(f"initial checking balance confirmed at "
                   f"${balance / 100:,.2f} ({balance} integer cents)")
    else:
        smoke.note("RunCreated response carries no checking_cents; the checklist "
                   "demo evidence expects the initial $20,000,000 balance there")
    vault = created.get("vault_locked_cents")
    if vault is not None and not nonneg_cents(vault):
        fail(f"RunCreated.vault_locked_cents {vault!r} must be nonnegative "
             "integer cents")


def probe_frontend_create(smoke: Smoke, name: str, args, base: str) -> None:
    """Probe create with the frontend's exact SimulationContext DEFAULT_RUN body
    ({seed, duration_steps, step_minutes: 15, start_time, initial_checking_cents,
    initial_vault_cents}). Records how the backend tolerates it non-fatally for
    the main flow, because the documented create was already validated."""
    from datetime import timedelta
    # Frontend constants (frontend/src/mocks/constants.js DEFAULT_RUN fields)
    body = {
        "seed": args.seed,
        "duration_steps": args.duration_steps,
        "step_minutes": 15,
        "start_time": (datetime.now(timezone.utc) + timedelta(hours=2))
                      .strftime("%Y-%m-%dT08:00:00.000Z"),
        "initial_checking_cents": args.initial_cash_cents,
        "initial_vault_cents": 600000000,
    }
    status, data, raw = http("POST", f"{base}/api/v1/runs", body,
                             timeout=args.timeout)
    if status is None:
        smoke.note("frontend create probe could not reach the backend")
        return
    if status in (200, 201):
        smoke.record(name, "PASS", "backend accepts the frontend DEFAULT_RUN "
                     "create body (incl. step_minutes/initial_vault_cents)")
        return
    if status in (400, 422):
        smoke.record(name, "FAIL", f"the frontend's real create body was "
                     f"rejected: {describe(status, data, raw)}. The backend must "
                     "alias step_minutes/initial_vault_cents (or the frontend "
                     "drop them) before live integration (M6)")
        return
    smoke.record(name, "FAIL", f"frontend probe create -> {describe(status, data, raw)}")


def check_snapshot(smoke: Smoke, name: str, args, base: str,
                   created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    url = run_path(base, created["run_id"], "snapshot")
    status, data, raw = http("GET", url, timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status != 200:
        fail(describe(status, data, raw))
    detect_mock_fixture(data, "snapshot", smoke)
    require_snapshot(data, "snapshot")
    if data["run_id"] != created["run_id"]:
        fail(f"snapshot.run_id {data['run_id']!r} does not match the created run "
             f"{created['run_id']!r}")
    audit_snapshot_contract_extras(smoke, created["run_id"], data)
    balance = data.get("checking_cents")
    smoke.note(f"root snapshot: step {data['step']}, checking balance "
               f"${balance / 100:,.2f} at {data['timestamp']}")


def run_path(base: str, run_id: str, resource: str = "") -> str:
    if resource:
        return f"{base}/api/v1/runs/{run_id}/{resource}"
    return f"{base}/api/v1/runs/{run_id}".rstrip("/")


def check_advance(smoke: Smoke, name: str, args, base: str, created: dict,
                  current: dict) -> None:
    if not have_run(smoke, name, created):
        return
    status, before, raw = http("GET", run_path(base, created["run_id"], "snapshot"),
                               timeout=args.timeout)
    if not guard_available(smoke, name, status, before, raw):
        return
    if status != 200:
        fail(f"could not read the snapshot before advancing: "
             f"{describe(status, before, raw)}")
    require_snapshot(before, "pre-advance snapshot")
    current.clear()
    current.update(before)

    status, after, raw = http("POST", run_path(base, created["run_id"], "advance"),
                              {"expected_step": current["step"], "steps": 1},
                              timeout=args.timeout)
    if not guard_available(smoke, name, status, after, raw):
        return
    if status not in (200, 201):
        fail(describe(status, after, raw))
    require_snapshot(after, "post-advance snapshot")
    if after["step"] != current["step"] + 1:
        fail(f"advance returned step {after['step']} instead of "
             f"{current['step'] + 1}")
    if parse_ts(after["timestamp"]) <= parse_ts(current["timestamp"]):
        fail(f"snapshot timestamp did not move forward: {current['timestamp']} -> "
             f"{after['timestamp']}")
    current.clear()
    current.update(after)
    smoke.note(f"step advanced {after['step'] - 1} -> {after['step']} "
               f"at {after['timestamp']}")


def check_stale(smoke: Smoke, name: str, args, base: str, created: dict,
                current: dict) -> None:
    if not have_snapshot(smoke, name, current):
        return
    stale_step = max(current["step"] - 1, 0)
    url = run_path(base, created["run_id"], "advance")
    status, data, raw = http("POST", url, {"expected_step": stale_step, "steps": 1},
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status == 200:
        fail("advance with a stale expected_step succeeded (HTTP 2xx); the "
             "contract requires HTTP 409 Conflict")
    if status != 409:
        fail(f"stale expected_step produced {describe(status, data, raw)}; the "
             "contract requires HTTP 409")
    note_error_shape(smoke, data, status, "stale advance")


def check_scenario(smoke: Smoke, name: str, args, base: str, created: dict,
                   current: dict) -> None:
    if not have_run(smoke, name, created):
        return
    try:
        parameters = json.loads(args.shock_params)
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be a JSON object")
    except json.JSONDecodeError as exc:
        fail(f"--shock-params must be valid JSON: {exc}")
    effective_step = current["step"] + 1 if is_int(current.get("step")) else None
    if effective_step is None:
        smoke.record(name, "SKIP", "current step unknown (no snapshot/advance)")
        return
    body = {
        "scenario": args.scenario_shock,
        "parameters": parameters,
        "effective_step": effective_step,
    }
    status, data, raw = http("POST", run_path(base, created["run_id"], "scenario"),
                             body, timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status not in (200, 201):
        fail(describe(status, data, raw))
    if not isinstance(data, dict):
        fail(f"scenario response must be an object, got {type(data).__name__}")
    if data.get("run_id") != created["run_id"]:
        fail(f"scenario response run_id {data.get('run_id')!r} must match the run")
    if data.get("scenario") != args.scenario_shock:
        fail(f"scenario name mismatch: sent {args.scenario_shock}, got "
             f"{data.get('scenario')!r}")
    if not is_int(data.get("effective_step")):
        fail("scenario response must carry an integer effective_step")
    if data["effective_step"] != effective_step:
        fail(f"scheduled at effective_step {effective_step}, backend answered "
             f"{data['effective_step']}")
    if not (data.get("parameters") is None or isinstance(data.get("parameters"), dict)):
        fail("scenario parameters echo must be an object")
    if "status" not in data and "id" not in data:
        smoke.note("scenario response echoes {run_id, scenario, effective_step, "
                   "parameters} but the frontend proposal expects {id, scenario, "
                   "effective_step, status}; the event status enum "
                   "(SCHEDULED/ACTIVE/COMPLETED) remains unpublished (M12)")


def check_policy(smoke: Smoke, name: str, args, base: str, created: dict,
                 current: dict) -> None:
    """PATCH using the exact legacy frontend policy field names."""
    if not have_run(smoke, name, created):
        return
    body = {
        "risk_percentile": args.policy_percentile,
        "min_sweep_cents": args.policy_min_sweep_cents,
        "vault_rate_bps": args.policy_vault_rate_bps,
        "lock_steps": args.policy_lock_steps,
        "allow_early_redemption": args.policy_allow_early_redemption,
    }
    url = run_path(base, created["run_id"], "policy")
    status, data, raw = http("PATCH", url, body, timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status in (400, 422):
        fail("the legacy frontend policy field names {min_sweep_cents, "
             "vault_rate_bps, lock_steps, allow_early_redemption} were rejected: "
             f"{describe(status, data, raw)} - audit item 10 requires the "
             "backend to honor the frontend wire names")
    if status != 200:
        fail(describe(status, data, raw))
    if not isinstance(data, dict):
        fail(f"policy response must be an object, got {type(data).__name__}")
    percentile = data.get("risk_percentile")
    if is_int(percentile) and percentile > 1:
        smoke.note("policy response echoes risk_percentile on the percent scale")
    elif isinstance(percentile, float) and percentile < 1:
        smoke.note(f"policy response returned risk_percentile {percentile} on the "
                   "fraction scale, while the frontend policy UI expects the "
                   "integer percent scale (90/95/99) - read-back mismatch (M8)")
    seen = sorted(k for k in data
                  if k in {"minimum_sweep_cents", "vault_yield_bps",
                           "vault_lock_steps", "early_redemption_allowed"})
    if seen:
        smoke.note(f"policy response used canonical names {seen} instead of the "
                   "legacy frontend names (M8)")


def check_history(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    status, data, raw = http("GET", run_path(base, created["run_id"], "history"),
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status != 200:
        fail(describe(status, data, raw))
    detect_mock_fixture(data, "history", smoke)
    items = require_items_envelope(data, "history")
    smoke.note(f"history returned {len(items)} snapshot item(s)")
    for index, item in enumerate(items):
        require_snapshot(item, f"history.items[{index}]")


def check_forecast(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    query = urllib.parse.urlencode({"horizon_minutes": args.horizon})
    url = run_path(base, created["run_id"], "forecast") + f"?{query}"
    status, data, raw = http("GET", url, timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status == 404:
        fail(describe(status, data, raw) + ". The run exists (create/snapshot "
             "worked), so a 404 here means the backend has no forecast data yet "
             "for this run (a fresh unadvanced run may have no forecastable "
             "history) - the frontend REQUIRES a points forecast at reasonable "
             "horizons")
    if status != 200:
        fail(describe(status, data, raw))
    if not isinstance(data, dict):
        fail(f"forecast must be an object, got {type(data).__name__}")
    detect_mock_fixture(data, "forecast", smoke)
    if isinstance(data.get("points"), list):
        for index, point in enumerate(data["points"]):
            if not isinstance(point, dict):
                fail(f"forecast.points[{index}] must be an object")
            for key in ("predicted_net_cents", "lower_cents", "upper_cents"):
                value = point.get(key)
                if value is not None and not safe_int(value):
                    fail(f"forecast.points[{index}].{key} must be an integer "
                         "cent value")
            if not is_iso_utc(point.get("timestamp")):
                fail(f"forecast.points[{index}].timestamp {point.get('timestamp')!r} "
                     "must be an ISO UTC timestamp")
        smoke.note(f"forecast envelope OK with {len(data['points'])} point(s) "
                   f"for horizon_minutes={args.horizon}")
        return
    keys = ", ".join(sorted(map(str, data)))
    smoke.note(f"forecast summary-only shape (keys: {keys}) - the frontend "
               "validateForecast REQUIRES {as_of, model_version, points: "
               "[{timestamp, predicted_net_cents, lower_cents, upper_cents}]}"
               " and ?horizon_minutes= (M2)")
    fail("forecast envelope mismatch: no {points: [...]} array (checklist M2)")


def check_decisions(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    status, data, raw = http("GET", run_path(base, created["run_id"], "decisions"),
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status != 200:
        fail(describe(status, data, raw))
    detect_mock_fixture(data, "decisions", smoke)
    items = require_items_envelope(data, "decisions")
    smoke.note(f"decisions returned {len(items)} item(s)")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"decisions.items[{index}] must be an object")
        if item.get("action") not in DECISION_ACTIONS:
            fail(f"decisions.items[{index}].action {item.get('action')!r} must "
                 f"be one of {list(DECISION_ACTIONS)}")
        if not safe_int(item.get("amount_cents")):
            fail(f"decisions.items[{index}].amount_cents must be an integer")
        if not isinstance(item.get("executed"), bool):
            fail(f"decisions.items[{index}].executed must be boolean")

    multi_asset = {"INVEST_REPO", "INVEST_BONDS", "INVEST_EQUITIES", "REBALANCE",
                   "LIQUIDATE"} & {item.get("action") for item in items
                                   if isinstance(item, dict)}
    if multi_asset:
        smoke.note("decisions contain multi-asset actions emitted outside the "
                   "contract enum (PENDING_BACKEND_MAPPINGS.md item 4; the "
                   "action enum remains HOLD/SWEEP/WITHDRAW/LIQUIDITY_WARNING)")
    if any("execution_status" not in item for item in items if isinstance(item, dict)):
        smoke.note("decision items lack 'execution_status' "
                   "(PENDING_BACKEND_MAPPINGS.md asks the backend to confirm it)")


def check_transactions(smoke: Smoke, name: str, args, base: str,
                       created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    status, data, raw = http("GET", run_path(base, created["run_id"],
                                             "transactions"),
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status != 200:
        fail(describe(status, data, raw))
    detect_mock_fixture(data, "transactions", smoke)
    items = require_items_envelope(data, "transactions")
    smoke.note(f"transactions returned {len(items)} item(s)")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"transactions.items[{index}] must be an object")
        if not isinstance(item.get("transaction_id"), str):
            fail(f"transactions.items[{index}].transaction_id must be a string")
        if item.get("type") not in TRANSACTION_TYPES:
            fail(f"transactions.items[{index}].type {item.get('type')!r} is not "
                 f"a documented transaction type {TRANSACTION_TYPES}")
        if item.get("direction") not in DIRECTIONS:
            fail(f"transactions.items[{index}].direction "
                 f"{item.get('direction')!r} is not a documented direction "
                 f"{DIRECTIONS}")
        expected_direction = {"DEPOSIT": "INFLOW",
                              "WITHDRAWAL": "OUTFLOW"}.get(item.get("type"))
        if expected_direction and item["direction"] != expected_direction:
            fail(f"transactions.items[{index}] direction conflicts with its type")
        if not (safe_int(item.get("amount_cents")) and item["amount_cents"] > 0):
            fail(f"transactions.items[{index}].amount_cents must be a positive "
                 "integer")
        if not isinstance(item.get("source"), str) or not item.get("source"):
            fail(f"transactions.items[{index}].source must be a non-empty string")
        if not is_iso_utc(item.get("timestamp")):
            fail(f"transactions.items[{index}].timestamp "
                 f"{item.get('timestamp')!r} must be an ISO UTC timestamp")


def check_backtest(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    """Submit the frontend wire format first; on rejection record the
    disagreement, then retry the documented request shape."""
    if not have_run(smoke, name, created):
        return
    arena_ids = [item.strip() for item in args.strategies.split(",") if item.strip()]
    frontend_body = {
        "scenario": args.backtest_scenario,
        "days": args.backtest_days,
        "seed": args.backtest_seed,
        "strategies": arena_ids,
    }
    documented_body = {"strategies": list(DOCUMENTED_STRATEGY_IDS)}
    timeout = args.timeout * 6  # backtests are heavier than CRUD calls

    url = run_path(base, created["run_id"], "backtest")
    status, data, raw = http("POST", url, frontend_body, timeout=timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status in (400, 422):
        smoke.note(f"frontend wire format {frontend_body} rejected with "
                   f"HTTP {status}; the contract only accepts {documented_body}"
                   " - genuine strategy-name + body-fields disagreement (M3/M4)")
        status, data, raw = http("POST", url, documented_body, timeout=timeout)
        if status is None or status == 501:
            guard_available(smoke, name, status, data, raw)
            return
        if status in (400, 422):
            fail(f"even the documented backtest request was rejected: "
                 f"{describe(status, data, raw)}")
        if status != 200:
            fail(describe(status, data, raw))
    elif status != 200:
        fail(describe(status, data, raw))
    if set(arena_ids) != set(DOCUMENTED_STRATEGY_IDS):
        smoke.note(f"backend accepted Arena/flexible strategy IDs {arena_ids}; "
                   "the published contract pins "
                   f"{list(DOCUMENTED_STRATEGY_IDS)}")
    audit_backtest_result(smoke, data)


def audit_backtest_result(smoke: Smoke, data) -> None:
    if not isinstance(data, dict):
        fail(f"backtest response must be an object, got {type(data).__name__}")
    detect_mock_fixture(data, "backtest", smoke)
    if not isinstance(data.get("run_id"), str) or not data.get("run_id"):
        fail("backtest.run_id must be a string UUID")
    if data.get("scenario") not in SCENARIO_ENUMS:
        fail(f"backtest.scenario {data.get('scenario')!r} must be one of "
             f"{list(SCENARIO_ENUMS)}")
    if not is_int(data.get("seed")):
        fail("backtest.seed must be an integer")
    for key in ("started_at", "ended_at"):
        if not is_iso_utc(data.get(key)):
            fail(f"backtest.{key} {data.get(key)!r} must be an ISO UTC timestamp")
    results = data.get("results")
    if not isinstance(results, list) or not results:
        fail("backtest.results must be a non-empty array")
    for index, result in enumerate(results):
        label = f"backtest.results[{index}]"
        if not isinstance(result, dict):
            fail(f"{label} must be an object")
        strategy = result.get("strategy")
        if strategy not in DOCUMENTED_STRATEGY_IDS:
            if strategy in ARENA_STRATEGY_IDS:
                smoke.note(f"{label}.strategy includes Arena ID; the contract "
                           "requires documented IDs (M4)")
            else:
                fail(f"{label}.strategy {strategy!r} is neither a documented ID "
                     f"{list(DOCUMENTED_STRATEGY_IDS)} nor an Arena ID")
        metrics = result.get("metrics")
        if metrics is None:
            smoke.note(f"{label} carries NO 'metrics' object; the Strategy "
                       "Arena expects flat metric fields directly on the result "
                       "item (its mock emits them flat) (M5)")
        elif isinstance(metrics, dict):
            missing = [key for key in CONTRACT_METRICS if key not in metrics]
            if missing:
                fail(f"{label}.metrics is missing contracted fields: {missing}")
            for key in CONTRACT_METRICS:
                value = metrics.get(key)
                if not safe_int(value):
                    fail(f"{label}.metrics.{key} must be an integer cent value")
                if key != "net_benefit_cents" and value < 0:
                    fail(f"{label}.metrics.{key} must be nonnegative")
        else:
            fail(f"{label}.metrics must be an object or null")
        flat_absent = [key for key in ARENA_FLAT_METRICS if key not in result]
        if flat_absent:
            smoke.note(f"{label} lacks Arena flat fields {flat_absent} (M5)")
        history = result.get("history")
        if not isinstance(history, list):
            smoke.note(f"{label} has no 'history' timestamp/balance points; the "
                       "Arena draws the checking-balance-over-time chart from "
                       "them (M5)")
        else:
            for index, point in enumerate(history):
                if not isinstance(point, dict):
                    fail(f"{label}.history[{index}] must be an object")
                if "step" in point and not is_int(point.get("step")):
                    fail(f"{label}.history[{index}].step must be an integer")
                if not nonneg_cents(point.get("checking_cents")):
                    fail(f"{label}.history[{index}].checking_cents must be a "
                         "nonnegative integer")
                ts = point.get("timestamp")
                if not isinstance(ts, str):
                    fail(f"{label}.history[{index}].timestamp must be a string")
                elif not is_iso_utc(ts):
                    smoke.note(f"{label}.history[{index}].timestamp {ts!r} lacks "
                               "explicit UTC Z/+00:00 suffix (organizer naive format M13)")
    for key in ("status", "source", "days", "model_evaluation"):
        if key not in data:
            smoke.note(f"backtest response lacks {key!r}, which the Strategy "
                       "Arena export/expose path expects (M5)")


def check_report(smoke: Smoke, name: str, args, base: str, created: dict) -> None:
    if not have_run(smoke, name, created):
        return
    status, data, raw = http("GET", run_path(base, created["run_id"], "report"),
                             timeout=args.timeout)
    if not guard_available(smoke, name, status, data, raw):
        return
    if status != 200:
        fail(describe(status, data, raw))
    if not isinstance(data, dict):
        fail(f"report must be an object, got {type(data).__name__}")
    detect_mock_fixture(data, "report", smoke)
    for key in ("run_id", "scenario", "seed", "started_at"):
        if key not in data:
            fail(f"report is missing the PerformanceReport field {key!r}")
    ended_at = data.get("ended_at")
    if ended_at is not None and not is_iso_utc(ended_at):
        fail(f"report.ended_at {ended_at!r} must be an ISO UTC timestamp or null")
    metrics = data.get("metrics")
    if metrics is None:
        smoke.note("report.metrics is null (allowed by the contract while the "
                   "run has no backtest/report data)")
        return
    if not isinstance(metrics, dict):
        fail(f"report.metrics must be an object or null, got {type(metrics).__name__}")
    missing = [key for key in CONTRACT_METRICS if key not in metrics]
    if missing:
        fail(f"report.metrics is missing the contracted fields {missing}")
    for key in CONTRACT_METRICS:
        if not safe_int(metrics.get(key)):
            fail(f"report.metrics.{key} must be an integer cent value")
    smoke.note("report.metrics passed the contract metric audit; the Strategy "
               "Arena still renders flat field names (M5)")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def parse_args(argv=None) -> argparse.Namespace:
    money = lambda text: int(float(text))
    parser = argparse.ArgumentParser(
        description="Frontend contract smoke test (HTTP only; safe to rerun; "
                    "never touches the organizer CSV)",
        epilog="Strategy naming: Arena IDs STATIC,REACTIVE,RESERVE_JUGGLER vs "
               "documented STATIC_RESERVE,REACTIVE_RESERVE,RESERVE_JUGGLER - "
               "see docs/FRONTEND_INTEGRATION_CHECKLIST.md")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"backend base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="per-request timeout seconds (default 10; "
                             "backtest gets 6x)")
    parser.add_argument("--initial-cash-cents", type=money,
                        default=2_000_000_000,
                        help="initial checking cash in integer cents "
                             "(default 2000000000 = $20,000,000)")
    parser.add_argument("--duration-steps", type=int, default=192,
                        help="run duration steps (default 192 = 2 days of "
                             "15-minute steps)")
    parser.add_argument("--seed", type=int, default=2026,
                        help="run creation seed (default 2026)")
    parser.add_argument("--scenario", default="NORMAL", choices=SCENARIO_ENUMS,
                        help="initial scenario for the run (default NORMAL)")
    parser.add_argument("--start-time", default=None,
                        help="optional ISO UTC start_time for the run; pass "
                             "e.g. 2026-10-18T08:00:00Z to walk the 17:00 repo "
                             "sweep window")
    parser.add_argument("--horizon", type=int, default=60,
                        help="forecast ?horizon_minutes value (default 60; "
                             "frontend uses 15|30|60|1440)")
    parser.add_argument("--scenario-shock", default="LIQUIDITY_SHOCK",
                        choices=SCENARIO_ENUMS,
                        help="scenario scheduled mid-run in check 6 (default "
                             "LIQUIDITY_SHOCK)")
    parser.add_argument("--shock-params",
                        default=json.dumps({"shock_cents": 800_000_000,
                                            "duration_steps": 8}),
                        help="JSON parameters for the mid-run scenario")
    parser.add_argument("--policy-percentile", type=int, default=95,
                        choices=(90, 95, 99),
                        help="risk_percentile percent value for the PATCH, as "
                             "the frontend sends it (default 95)")
    parser.add_argument("--policy-min-sweep-cents", type=money,
                        default=75_000_000,
                        help="min_sweep_cents (legacy frontend name) for the "
                             "PATCH (default 75000000)")
    parser.add_argument("--policy-vault-rate-bps", type=int, default=520,
                        help="vault_rate_bps (legacy frontend name) for the "
                             "PATCH (default 520)")
    parser.add_argument("--policy-lock-steps", type=int, default=96,
                        help="lock_steps (legacy frontend name) for the PATCH "
                             "(default 96)")
    parser.add_argument("--policy-allow-early-redemption",
                        type=lambda text: str(text).lower() == "true",
                        default=False,
                        help="allow_early_redemption (legacy frontend name) for "
                             "the PATCH (default False)")
    parser.add_argument("--no-probe-create", action="store_true",
                        help="skip the supplemental probe that submits the "
                             "frontend's exact DEFAULT_RUN create body")
    parser.add_argument("--backtest-scenario", default="LIQUIDITY_SHOCK",
                        choices=SCENARIO_ENUMS,
                        help="scenario field for the documented backtest request")
    parser.add_argument("--backtest-days", type=int, default=7, choices=(7, 14, 30),
                        help="days field for the documented backtest request "
                             "(default 7)")
    parser.add_argument("--backtest-seed", type=int, default=2026,
                        help="seed field for the documented backtest request")
    parser.add_argument("--strategies", default=",".join(ARENA_STRATEGY_IDS),
                        help="comma-separated strategy IDs for the frontend-format "
                             "backtest request (default 'STATIC,REACTIVE,"
                             "RESERVE_JUGGLER')")
    parser.add_argument("--in-process", action="store_true",
                        help="run smoke test in-process using FastAPI TestClient "
                             "(tests exact ASGI app routes without network bind)")
    parser.add_argument("--allow-mock", action="store_true",
                        help="permit mock fixture responses without failing "
                             "(default requires real backend responses)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    base = args.base_url.rstrip("/")
    smoke = Smoke()
    created: dict = {}
    current: dict = {}

    global REQUIRE_REAL, IN_PROCESS_CLIENT
    REQUIRE_REAL = not args.allow_mock
    if args.in_process:
        import os
        if not os.environ.get("DATABASE_URL"):
            os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5432/reserve_juggler"
        from fastapi.testclient import TestClient
        from app.main import app
        IN_PROCESS_CLIENT = TestClient(app)
        base = "http://testserver"

    print("Reserve Juggler frontend contract smoke test")
    print(f"  base URL     : {base} {'(in-process TestClient)' if args.in_process else ''}")
    print(f"  mode         : {'mock fixtures tolerated' if args.allow_mock else 'REAL BACKEND REQUIRED'}")
    print(f"  initial cash : {args.initial_cash_cents} cents "
          f"(${args.initial_cash_cents / 100:,.2f})")
    print(f"  seed         : {args.seed}   scenario: {args.scenario}")

    smoke.run("1. GET /health", lambda: check_health(smoke, "1. GET /health",
                                                     args, base))
    if smoke.last_status == "FAIL":
        return finish(smoke, args, unreachable=backend_down(smoke))

    smoke.run("2. POST /api/v1/runs",
              lambda: check_create(smoke, "2. POST /api/v1/runs", args, base, created))
    if not created.get("run_id"):
        return finish(smoke, args, unreachable=backend_down(smoke))

    if not args.no_probe_create:
        smoke.run("2b. POST /api/v1/runs (exact frontend DEFAULT_RUN body probe)",
                  lambda: probe_frontend_create(
                      smoke, "2b. frontend DEFAULT_RUN create probe", args, base))

    smoke.run("3. GET /api/v1/runs/{id}/snapshot",
              lambda: check_snapshot(smoke, "3. GET .../snapshot", args, base, created))
    if not created.get("run_id") or smoke.last_status == "FAIL":
        return finish(smoke, args)

    smoke.run("4. POST /api/v1/runs/{id}/advance",
              lambda: check_advance(smoke, "4. POST .../advance", args, base,
                                    created, current))
    # An advance failure does not block the remaining read/underlying checks;
    # they self-skip when the current step is unusable.

    smoke.run("5. POST .../advance (stale expected_step -> HTTP 409 expected)",
              lambda: check_stale(smoke, "5. stale advance", args, base, created, current))

    smoke.run("6. POST /api/v1/runs/{id}/scenario",
              lambda: check_scenario(smoke, "6. POST .../scenario", args, base,
                                     created, current))

    smoke.run("7. PATCH /api/v1/runs/{id}/policy",
              lambda: check_policy(smoke, "7. PATCH .../policy", args, base,
                                   created, current))

    for label, function in (
        ("8a. GET .../history", lambda: check_history(smoke, "8a. history", args,
                                                      base, created)),
        ("8b. GET .../forecast", lambda: check_forecast(smoke, "8b. forecast",
                                                        args, base, created)),
        ("8c. GET .../decisions", lambda: check_decisions(smoke, "8c. decisions",
                                                          args, base, created)),
        ("8d. GET .../transactions", lambda: check_transactions(
            smoke, "8d. transactions", args, base, created)),
    ):
        smoke.run(label, function)

    smoke.run("9. POST /api/v1/runs/{id}/backtest",
              lambda: check_backtest(smoke, "9. POST .../backtest", args, base,
                                     created))
    smoke.run("10. GET /api/v1/runs/{id}/report",
              lambda: check_report(smoke, "10. GET .../report", args, base, created))
    return finish(smoke, args)


def backend_down(smoke: Smoke) -> bool:
    """True when the failures indicate the service itself is not listening."""
    return any(status == "FAIL" and "unreachable" in detail
               for _, status, detail in smoke.records)


def finish(smoke: Smoke, args, unreachable: bool = False) -> int:
    statuses = [status for _, status, _ in smoke.records]
    counts = {label: statuses.count(label) for label in ("PASS", "FAIL", "SKIP")}
    failed = [(name, detail) for name, status, detail in smoke.records
              if status == "FAIL"]
    skipped = [(name, detail) for name, status, detail in smoke.records
               if status == "SKIP"]

    print("\n" + "=" * 72)
    print("SMOKE SUMMARY")
    print(f"  base URL : {args.base_url}")
    print(f"  checks   : {counts['PASS']} passed, {counts['FAIL']} failed "
          "(contract validation), "
          f"{counts['SKIP']} skipped (unavailable/not implemented)")
    if failed:
        print("\nCONTRACT VALIDATION FAILURES:")
        for name, detail in failed:
            print(f"  [FAIL] {name} - {detail}")
    if skipped:
        print("\nNOT IMPLEMENTED / UNAVAILABLE (informational, NOT failures):")
        for name, detail in skipped:
            print(f"  [SKIP] {name} - {detail}")
    if smoke.notes:
        print("\nCONTRACT MISMATCHES / OBSERVATIONS RECORDED "
              "(full audit in docs/FRONTEND_INTEGRATION_CHECKLIST.md):")
        for index, note in enumerate(smoke.notes, 1):
            print(f"  {index}. {note}")

    print()
    if unreachable:
        print("RESULT: backend unreachable - service could not be exercised "
              "(exit 2; this is NOT a contract validation failure)")
        print("=" * 72)
        return 2
    if counts["FAIL"]:
        print("RESULT: contract validation failure(s) above (exit 1)")
        print("=" * 72)
        return 1
    if counts["SKIP"]:
        print("RESULT: no validation failures, but the full contract check "
              "could not pass yet because endpoints are still unimplemented "
              "or the backend is unreachable (exit 2)")
        print("=" * 72)
        return 2
    print("RESULT: all contract checks passed (exit 0)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
