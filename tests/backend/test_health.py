import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "Reserve Juggler"

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data

def test_treasury_state_endpoint():
    response = client.get("/api/treasury/state")
    assert response.status_code == 200
    data = response.json()
    assert "liquidity" in data
    assert "latest_decision" in data
    assert "active_forecast" in data
