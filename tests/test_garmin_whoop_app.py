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


def test_whoop_full_metrics_storage_and_wellness(client):
    today = date.today().isoformat()
    full_payload = {
        "date": today,
        "recovery_score": 85,
        "day_strain": 16.4,
        "hrv_rmssd": 78.5,
        "resting_hr": 49,
        "spo2_percentage": 98.4,
        "skin_temp_celsius": -0.15,
        "respiratory_rate": 14.2,
        "sleep_performance_pct": 94.0,
        "sleep_needed_hours": 8.3,
        "sleep_debt_minutes": 18,
        "sleep_efficiency_pct": 93.5,
        "sleep_consistency_pct": 88.0,
        "disturbances_count": 11,
        "sleep_cycles_count": 5,
        "sleep_hours": 7.8,
        "time_in_bed_hours": 8.35,
        "sleep_deep_hours": 1.7,
        "sleep_rem_hours": 1.9,
        "sleep_light_hours": 3.7,
        "sleep_awake_hours": 0.55,
        "calories": 2750.0,
        "avg_hr": 64,
        "max_hr": 178,
        "workouts": [
            {
                "sport_name": "Corsa Ripetute",
                "strain": 14.8,
                "avg_hr": 162,
                "max_hr": 178,
                "calories": 680,
                "distance_km": 10.2,
            }
        ],
    }

    resp = client.post("/api/whoop/manual", json=full_payload)
    assert resp.status_code == 200

    # Check latest whoop record in DB
    latest = db.get_latest_whoop()
    assert latest is not None
    assert latest["recovery_score"] == 85
    assert latest["day_strain"] == 16.4
    assert latest["respiratory_rate"] == 14.2
    assert latest["disturbances_count"] == 11
    assert latest["sleep_deep_hours"] == 1.7
    assert latest["calories"] == 2750.0
    assert len(latest.get("workouts", [])) == 1
    assert latest["workouts"][0]["sport_name"] == "Corsa Ripetute"

    # Test /api/wellness
    w_resp = client.get("/api/wellness")
    assert w_resp.status_code == 200
    w_data = w_resp.json()
    assert "whoop_days" in w_data
    assert "latest_whoop" in w_data
    assert w_data["latest_whoop"]["recovery_score"] == 85


def test_apple_health_whoop_bridge_sync(client):
    today = date.today().isoformat()
    bridge_payload = {
        "date": today,
        "hrv_sdnn_ms": 72.0,
        "resting_hr": 51,
        "sleep_hours": 7.5,
        "time_in_bed_hours": 8.1,
        "sleep_deep_hours": 1.6,
        "sleep_rem_hours": 1.8,
        "spo2": 98.0,
        "respiratory_rate": 14.4,
        "active_energy_kcal": 650.0,
        "day_strain": 12.8,
    }
    resp = client.post("/api/apple-health/sync", json=bridge_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


