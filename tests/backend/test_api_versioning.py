"""Contract parity and validation, without pretending simulation is implemented."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.v1_contracts import CreateRunRequest, TransactionRecord, VaultPosition


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def test_openapi_matches_frozen_contract():
    stored = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8-sig"))
    assert stored == app.openapi()
    assert set(stored["paths"]) == {"/health", "/api/v1/runs"} | {
        f"/api/v1/runs/{{id}}/{suffix}" for suffix in (
            "snapshot", "advance", "scenario", "policy", "history", "forecast",
            "decisions", "transactions", "backtest", "report",
        )
    }


@pytest.mark.parametrize("method,suffix,body", [
    ("post", "", {}), ("get", "/snapshot", None),
    ("post", "/advance", {"expected_step": 0}),
    ("post", "/scenario", {"scenario": "HIGH_WITHDRAWAL", "parameters": {}}),
    ("patch", "/policy", {"minimum_sweep_cents": 100}),
    ("get", "/history", None), ("get", "/forecast", None),
    ("get", "/decisions", None), ("get", "/transactions", None),
    ("post", "/backtest", {}), ("get", "/report", None),
])
def test_contract_routes_return_honest_unimplemented_error(method, suffix, body):
    path = "/api/v1/runs" + (f"/{uuid4()}{suffix}" if suffix else "")
    response = client.request(method, path, **({"json": body} if body is not None else {}))
    assert response.status_code == 501
    assert response.json() == {
        "error_code": "NOT_IMPLEMENTED",
        "message": "This API contract is defined; the simulation service is not implemented.",
        "details": {},
    }


@pytest.mark.parametrize("body", [
    {"initial_cash_cents": -1}, {"initial_cash_cents": 1.5},
    {"initial_cash_cents": True}, {"initial_cash_cents": 2**63},
    {"scenario": "baseline"}, {"duration_steps": 0},
    {"start_time": "2026-10-17T09:00:00"},
    {"policy": {"vault_yield_bps": 5.5}}, {"policy": {"risk_percentile": 1.1}},
])
def test_create_request_rejects_incompatible_units_or_values(body):
    response = client.post("/api/v1/runs", json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"error_code", "message", "details"}


def test_uuid_and_expected_step_validation():
    response = client.get("/api/v1/runs/123/snapshot")
    assert response.status_code == 422
    response = client.post(f"/api/v1/runs/{uuid4()}/advance", json={"steps": 1})
    assert response.status_code == 422
    response = client.patch(f"/api/v1/runs/{uuid4()}/policy", json={"minimum_sweep_cents": None})
    assert response.status_code == 501  # null is permitted as an unchanged field


def test_internal_errors_use_safe_envelope(monkeypatch):
    from app.routers import runs

    def fail():
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(runs, "unavailable", fail)
    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/v1/runs/{uuid4()}/snapshot"
    )
    assert response.status_code == 500
    assert response.json() == {
        "error_code": "INTERNAL_ERROR",
        "message": "An unexpected internal error occurred.", "details": {},
    }


def test_spec_defaults_and_utc_normalization():
    request = CreateRunRequest(start_time="2026-10-17T14:30:00+05:30")
    assert request.initial_cash_cents == 2000000000
    assert request.duration_steps == 288
    assert request.policy.vault_yield_bps == 500
    assert request.policy.vault_lock_steps == 96
    assert request.start_time.isoformat() == "2026-10-17T09:00:00+00:00"


def test_transaction_direction_and_vault_timing_validation():
    values = dict(transaction_id=uuid4(), run_id=uuid4(), step=1,
                  timestamp=datetime.fromisoformat("2026-10-17T09:00:00+00:00"),
                  type="DEPOSIT", direction="OUTFLOW", amount_cents=100,
                  source="CUSTOMER", scenario="NORMAL")
    with pytest.raises(ValidationError):
        TransactionRecord(**values)
    with pytest.raises(ValidationError):
        VaultPosition(position_id=uuid4(), run_id=uuid4(), principal_cents=100,
                      annual_rate_bps=500, created_at=values["timestamp"],
                      matures_at=values["timestamp"], status="LOCKED",
                      early_redemption_allowed=False, early_redemption_penalty_bps=0)


def test_legacy_routes_stay_out_of_public_contract():
    assert client.get("/api/treasury/state").status_code == 200
    assert client.get("/api/transactions/recent").status_code == 200
    assert client.get("/api/metrics").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get(client.get("/").json()["contract"]).status_code == 200
    assert client.get("/api/v1/treasury/state").status_code == 404
