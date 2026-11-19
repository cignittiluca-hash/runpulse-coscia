"""Automated Test Suite for RunPulse Apple Watch & Strava Edition."""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.database import Database, _translate_sql_for_postgres
from backend.main import app
from backend.services.analytics import (
    compute_trimp,
    compute_vdot,
    format_hm,
    format_pace,
    predict_race_time_sec,
    vdot_training_paces,
)
from backend.services.apple_health_service import (
    calculate_sleep_score,
    compute_hrv_baseline_and_readiness,
    ingest_apple_health_payload,
)
from backend.models import AppleHealthSyncRequest


@pytest.fixture(autouse=True)
def _use_temp_db(monkeypatch, tmp_path):
    temp_db_path = tmp_path / "test_apple_runpulse.db"
    test_db = Database(db_path=temp_db_path, database_url="")
    monkeypatch.setattr("backend.database.db", test_db)
    monkeypatch.setattr("backend.main.db", test_db)
    monkeypatch.setattr("backend.services.apple_health_service.db", test_db)
    monkeypatch.setattr("backend.services.coach_engine.db", test_db)
    monkeypatch.setattr("backend.services.strava_service.db", test_db)
    monkeypatch.setattr("backend.services.demo_data.db", test_db)
    monkeypatch.setattr("backend.services.plan_generator.db", test_db)
    yield test_db


def test_vdot_and_race_predictions():
    # 5K in 20:00 (1200 sec) -> VDOT approx 49.8
    vdot = compute_vdot(5000, 1200)
    assert vdot is not None
    assert 48.5 <= vdot <= 51.5

    # Predict race time for 10K with VDOT 50 -> approx 41:20 (2480 sec)
    pred_10k = predict_race_time_sec(50.0, 10000)
    assert 2350 <= pred_10k <= 2600

    paces = vdot_training_paces(50.0)
    assert "easy" in paces
    assert "threshold" in paces
    assert paces["easy"]["min_sec"] > paces["threshold"]["min_sec"]


def test_trimp_calculation():
    # 60 min run @ avg HR 150, max HR 190, resting HR 50 -> HRR = (150-50)/(190-50) = 0.714
    trimp = compute_trimp(
        moving_time_s=3600,
        avg_hr=150.0,
        max_hr=190.0,
        resting_hr=50.0,
        avg_pace_sec_km=300.0,
    )
    assert 60.0 <= trimp <= 140.0


def test_sleep_and_readiness_calculation():
    # 7.5 hours optimal sleep
    score = calculate_sleep_score(int(7.5 * 3600), deep_sec=int(1.3 * 3600), rem_sec=int(1.5 * 3600))
    assert 80 <= score <= 100

    # Under-sleep 4.5h
    bad_score = calculate_sleep_score(int(4.5 * 3600))
    assert bad_score <= 55

    # HRV baseline & readiness test
    low, high, status, readiness = compute_hrv_baseline_and_readiness(
        target_date="2026-11-19",
        today_hrv=72.0,
        today_rhr=49,
        today_sleep_score=88,
        today_sleep_hours=7.8,
    )
    assert 75 <= readiness <= 100
    assert status in ("Ottimale", "Equilibrato")


def test_apple_health_sync_endpoint():
    client = TestClient(app)

    # Health check
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["edition"] == "apple_watch"

    # Settings config check
    s = client.get("/api/settings").json()
    token = s["apple_health_api_key"]
    assert token

    # Sync payload via Shortcut
    sync_payload = {
        "date": "2026-11-19",
        "hrv_sdnn_ms": 68.5,
        "resting_hr": 50,
        "sleep_hours": 7.6,
        "sleep_deep_hours": 1.4,
        "sleep_rem_hours": 1.7,
        "vo2_max": 53.0,
        "steps": 12400,
        "active_calories": 680,
        "exercise_min": 50,
        "stand_hours": 14,
        "auth_token": token,
    }
    resp = client.post("/api/apple-health/sync", json=sync_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert res_data["date"] == "2026-11-19"
    assert res_data["readiness"] >= 70

    # Wellness endpoint reflects synced day
    w = client.get("/api/wellness").json()
    assert len(w["days"]) >= 1
    latest = w["latest"]
    assert latest["date_key"] == "2026-11-19"
    assert latest["resting_hr"] == 50
    assert latest["vo2_max"] == 53.0
    assert latest["steps"] == 12400


def test_manual_entry_and_backup_flow():
    client = TestClient(app)

    # Manual entry
    entry = {
        "date_key": "2026-11-18",
        "hrv_avg": 62.0,
        "resting_hr": 53,
        "sleep_hours": 7.2,
        "vo2_max": 52.5,
        "steps": 9500,
        "active_calories": 550,
        "exercise_min": 40,
    }
    m_resp = client.post("/api/apple-health/manual", json=entry)
    assert m_resp.status_code == 200

    # Export backup
    b_resp = client.get("/api/backup/export")
    assert b_resp.status_code == 200
    backup_data = b_resp.json()
    assert backup_data["app_edition"] == "apple_watch"
    assert len(backup_data["wellness_daily"]) >= 1

    # Clear and Import backup
    imp_resp = client.post("/api/backup/import", json=backup_data)
    assert imp_resp.status_code == 200
    assert imp_resp.json()["imported"]["wellness_days"] >= 1


def test_postgres_sql_translator():
    # SQLite ? -> %s
    sql, params = _translate_sql_for_postgres(
        "SELECT * FROM wellness_daily WHERE date_key = ? LIMIT ?",
        ("2026-11-19", 1),
    )
    assert "%s" in sql
    assert "?" not in sql

    # Named params :name -> %(name)s
    sql_named, _ = _translate_sql_for_postgres(
        "INSERT INTO wellness_daily (date_key, hrv_avg) VALUES (:date_key, :hrv_avg)",
        {"date_key": "2026-11-19", "hrv_avg": 70.0},
    )
    assert "%(date_key)s" in sql_named
    assert "%(hrv_avg)s" in sql_named


def test_apple_health_italian_strings_and_empty():
    client = TestClient(app)
    s = client.get("/api/settings").json()
    token = s["apple_health_api_key"]

    # Typical Italian iOS Shortcut payload with units, commas and empty values
    payload = {
        "date": "2026-11-20",
        "hrv_sdnn_ms": "64,2 ms",
        "resting_hr": "51 bpm",
        "sleep_hours": "7,8 ore",
        "sleep_deep_hours": "1,3 h",
        "sleep_rem_hours": "1,9 h",
        "vo2_max": "54,2",
        "steps": "11.850 passi",
        "active_calories": "630 kcal",
        "exercise_min": "45 min",
        "stand_hours": "12 ore",
        "spo2_pct": "98 %",
        "respiration_rate": "",  # Empty string from iOS
        "auth_token": token,
    }
    resp = client.post("/api/apple-health/sync", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    w = client.get("/api/wellness").json()
    day = next(d for d in w["days"] if d["date_key"] == "2026-11-20")
    assert day["hrv_avg"] == 64.2
    assert day["resting_hr"] == 51
    assert day["steps"] == 11850
    assert day["active_calories"] == 630


def test_apple_health_get_query_sync():
    client = TestClient(app)
    s = client.get("/api/settings").json()
    token = s["apple_health_api_key"]

    # Simple GET ping test
    ping = client.get("/api/apple-health/sync")
    assert ping.status_code == 200
    assert "riuscita" in ping.json()["message"]

    # 1-action iOS Shortcut GET sync via URL parameters
    resp = client.get(
        f"/api/apple-health/sync?date=2026-11-21&hrv_sdnn_ms=66.0&resting_hr=48&sleep_hours=8.0&steps=10500&auth_token={token}"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_apple_health_auto_export_format():
    client = TestClient(app)
    s = client.get("/api/settings").json()
    token = s["apple_health_api_key"]

    hae_payload = {
        "data": {
            "metrics": [
                {
                    "name": "heart_rate_variability_sdnn",
                    "units": "ms",
                    "data": [{"date": "2026-11-22 07:15:00 +0100", "qty": 71.5}],
                },
                {
                    "name": "resting_heart_rate",
                    "units": "count/min",
                    "data": [{"date": "2026-11-22 07:15:00 +0100", "qty": 49}],
                },
                {
                    "name": "sleep_analysis",
                    "units": "hr",
                    "data": [{"date": "2026-11-22 07:00:00 +0100", "qty": 7.5, "deep": 1.4, "rem": 1.8}],
                },
                {
                    "name": "step_count",
                    "data": [{"date": "2026-11-22 18:00:00 +0100", "qty": 13200}],
                },
            ]
        }
    }
    resp = client.post(
        "/api/apple-health/sync",
        headers={"x-apple-health-token": token},
        json=hae_payload,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

