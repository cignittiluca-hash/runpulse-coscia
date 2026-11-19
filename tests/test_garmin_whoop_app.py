"""Unit & Integration tests for RunPulse (Garmin + Whoop Edition)."""
import os
import pytest
from datetime import date
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import db, _translate_sql_for_postgres
from backend.services.analytics import compute_readiness, compute_training_load_series
from backend.services.whoop_service import _recovery_state_from_score, ingest_whoop_manual_entry
from backend.models import WhoopManualEntry


@pytest.fixture
def client():
    return TestClient(app)


def test_whoop_recovery_state_classification():
    assert _recovery_state_from_score(90) == "GREEN"
    assert _recovery_state_from_score(67) == "GREEN"
    assert _recovery_state_from_score(66) == "YELLOW"
    assert _recovery_state_from_score(34) == "YELLOW"
    assert _recovery_state_from_score(33) == "RED"
    assert _recovery_state_from_score(15) == "RED"
    assert _recovery_state_from_score(None) == "UNKNOWN"


def test_blended_garmin_whoop_readiness():
    today = date.today().isoformat()
    garmin_days = [
        {
            "date_key": today,
            "body_battery_max": 85,
            "body_battery_current": 80,
            "stress_avg": 24,
            "hrv_avg": 62.0,
            "sleep_seconds": 28800,  # 8h
            "resting_hr": 48,
        }
    ]
    whoop_days = [
        {
            "date_key": today,
            "recovery_score": 88,
            "recovery_state": "GREEN",
            "day_strain": 12.5,
            "hrv_rmssd": 68.0,
            "sleep_hours": 8.0,
            "sleep_debt_minutes": 20,
        }
    ]
    load = {"current": {"tsb": 2.0, "acwr": 1.05}}
    settings = {"resting_hr": "50"}

    readiness = compute_readiness(garmin_days, load, settings, whoop_days=whoop_days)
    assert readiness["score"] >= 75
    assert readiness["zone"] == "prime"
    assert readiness["has_garmin"] is True
    assert readiness["has_whoop"] is True

    # Check component presence
    keys = [c["key"] for c in readiness["components"]]
    assert "whoop_recovery" in keys
    assert "body_battery" in keys
    assert "stress" in keys
    assert "sleep" in keys


def test_whoop_manual_entry_flow(client):
    today = date.today().isoformat()
    payload = {
        "date": today,
        "recovery_score": 79,
        "day_strain": 14.2,
        "hrv_rmssd": 64.5,
        "resting_hr": 50,
        "sleep_performance_pct": 92.0,
        "sleep_debt_minutes": 15,
        "sleep_hours": 7.6,
    }
    resp = client.post("/api/whoop/manual", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["saved"]["recovery_score"] == 79
    assert data["saved"]["recovery_state"] == "GREEN"

    # Verify health endpoint
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    h_data = health_resp.json()
    assert h_data["edition"] == "garmin_whoop"
    assert h_data["status"] == "ok"


def test_postgres_sql_translator():
    sql = "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)"
    translated, params = _translate_sql_for_postgres(sql, ("foo", "bar"))
    assert "INSERT INTO settings" in translated
    assert "ON CONFLICT DO NOTHING" in translated
    assert "%s" in translated
    assert params == ("foo", "bar")


def test_seed_demo_and_dashboard_endpoint(client):
    from backend.services.demo_data import seed_demo_data
    seed_demo_data()

    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    summary = data.get("summary", data)
    assert "readiness" in summary
    assert summary["has_whoop"] is True
    assert summary["has_garmin"] is True
    assert summary["readiness"]["score"] > 0
    assert summary["readiness"]["has_whoop"] is True

