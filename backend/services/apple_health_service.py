"""Apple Health & Apple Watch ingestion, baseline tracking, and readiness engine."""
import logging
import math
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from backend.database import db
from backend.models import AppleHealthManualEntry, AppleHealthSyncRequest

logger = logging.getLogger("runpulse.apple_health")


def parse_health_auto_export_payload(raw: Dict[str, Any], token: Optional[str] = None) -> AppleHealthSyncRequest:
    """
    Parses a payload from the 'Health Auto Export' iOS app (REST API / Webhook export).
    Compatible with {"data": {"metrics": [...]}} or {"metrics": [...]}.
    """
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    metrics = data.get("metrics") or []
    extracted: Dict[str, Any] = {"raw_payload": raw, "auth_token": token}
    target_date = None

    for m in metrics:
        name = (m.get("name") or "").lower()
        samples = m.get("data") or []
        if not samples:
            continue
        # Take the most recent sample
        latest = samples[-1]
        val = latest.get("qty") if "qty" in latest else (latest.get("value") if "value" in latest else latest.get("avg"))

        sample_date_str = latest.get("date") or latest.get("startDate") or ""
        if sample_date_str and not target_date and len(sample_date_str) >= 10:
            target_date = sample_date_str[:10]

        if name in ("heart_rate_variability_sdnn", "hrv", "variabilità della frequenza cardiaca", "variabilità fc"):
            extracted["hrv_sdnn_ms"] = val
        elif name in ("resting_heart_rate", "resting_hr", "frequenza cardiaca a riposo"):
            extracted["resting_hr"] = val
        elif name in ("sleep_analysis", "sleep", "sonno"):
            extracted["sleep_hours"] = val
            if "deep" in latest:
                extracted["sleep_deep_hours"] = latest["deep"]
            if "rem" in latest:
                extracted["sleep_rem_hours"] = latest["rem"]
            if "core" in latest or "light" in latest:
                extracted["sleep_core_hours"] = latest.get("core") or latest.get("light")
            if "awake" in latest:
                extracted["sleep_awake_hours"] = latest["awake"]
        elif name in ("vo2_max", "cardio_fitness", "cardio fitness"):
            extracted["vo2_max"] = val
        elif name in ("step_count", "steps", "passi"):
            extracted["steps"] = val
        elif name in ("active_energy", "active_calories", "energia attiva"):
            extracted["active_calories"] = val
        elif name in ("apple_exercise_time", "exercise_time", "tempo di esercizio"):
            extracted["exercise_min"] = val
        elif name in ("apple_stand_hour", "stand_hour", "ore in piedi"):
            extracted["stand_hours"] = val
        elif name in ("oxygen_saturation", "spo2", "saturazione ossigeno"):
            extracted["spo2_pct"] = val * 100.0 if val and val <= 1.0 else val
        elif name in ("respiratory_rate", "respiration_rate", "frequenza respiratoria"):
            extracted["respiration_rate"] = val
        elif name in ("wrist_temperature", "body_temperature", "temperatura al polso"):
            extracted["wrist_temperature_c"] = val

    if target_date:
        extracted["date"] = target_date

    return AppleHealthSyncRequest(**extracted)


def calculate_sleep_score(
    total_sec: int,
    deep_sec: Optional[int] = None,
    rem_sec: Optional[int] = None,
    awake_sec: Optional[int] = None,
) -> int:
    """Computes a 0-100 sleep quality score based on total duration and Apple Watch stages."""
    if total_sec <= 0:
        return 0
    hours = total_sec / 3600.0

    # Duration score: 7.5 - 8.5 hours is optimal 100
    if 7.5 <= hours <= 8.5:
        dur_score = 100.0
    elif 6.5 <= hours < 7.5:
        dur_score = 80.0 + (hours - 6.5) * 20.0
    elif hours > 8.5:
        dur_score = max(70.0, 100.0 - (hours - 8.5) * 12.0)
    elif 5.0 <= hours < 6.5:
        dur_score = 50.0 + (hours - 5.0) * 20.0
    else:
        dur_score = max(20.0, hours * 10.0)

    # Stages modifier (if Apple Watch sleep stages were tracked)
    if deep_sec is not None and rem_sec is not None and total_sec > 0:
        deep_pct = deep_sec / total_sec
        rem_pct = rem_sec / total_sec

        # Ideal deep: 13-23%, Ideal REM: 18-25%
        deep_score = min(100.0, (deep_pct / 0.16) * 100.0) if deep_pct < 0.16 else 100.0
        rem_score = min(100.0, (rem_pct / 0.20) * 100.0) if rem_pct < 0.20 else 100.0
        stage_score = (deep_score * 0.5) + (rem_score * 0.5)

        # Awake deduction
        awake_penalty = 0.0
        if awake_sec and awake_sec > 1800:  # > 30 min awake
            awake_penalty = min(25.0, ((awake_sec - 1800) / 1800.0) * 15.0)

        final_score = (dur_score * 0.65) + (stage_score * 0.35) - awake_penalty
    else:
        final_score = dur_score

    return int(round(max(10, min(100, final_score))))


def compute_hrv_baseline_and_readiness(
    target_date: str,
    today_hrv: Optional[float],
    today_rhr: Optional[int],
    today_sleep_score: Optional[int],
    today_sleep_hours: Optional[float],
) -> Tuple[Optional[float], Optional[float], str, int]:
    """
    Calculates 14-day rolling HRV baseline, HRV status (Ottimale/Equilibrato/Basso),
    and a scientific Training Readiness score (0-100) combining Apple Watch HRV, RHR, and Sleep.
    """
    settings = db.get_settings()
    baseline_rhr = int(settings.get("resting_hr") or 52)

    past_days = db.get_wellness_daily(days=21)
    hrv_values = [
        d["hrv_avg"]
        for d in past_days
        if d.get("hrv_avg") and d.get("date_key") != target_date
    ]

    hrv_low = None
    hrv_high = None
    hrv_status = "Equilibrato"

    if len(hrv_values) >= 3:
        mean_hrv = sum(hrv_values) / len(hrv_values)
        variance = sum((x - mean_hrv) ** 2 for x in hrv_values) / len(hrv_values)
        std_hrv = math.sqrt(variance) if variance > 0 else 5.0
        std_hrv = max(std_hrv, 4.0)

        hrv_low = round(mean_hrv - 0.75 * std_hrv, 1)
        hrv_high = round(mean_hrv + 0.75 * std_hrv, 1)

        if today_hrv is not None:
            if today_hrv >= hrv_high:
                hrv_status = "Ottimale"
            elif today_hrv < hrv_low:
                hrv_status = "Basso / Affaticato"
            else:
                hrv_status = "Equilibrato"
    else:
        # Default typical Apple Watch SDNN baseline (~50-80 ms)
        hrv_low = 45.0
        hrv_high = 75.0
        if today_hrv is not None:
            if today_hrv >= 70:
                hrv_status = "Ottimale"
            elif today_hrv < 40:
                hrv_status = "Basso / Affaticato"
            else:
                hrv_status = "Equilibrato"

    # Compute Scientific Readiness (0-100)
    # Component 1: HRV (40%)
    hrv_comp = 75.0
    if today_hrv is not None and hrv_low is not None and hrv_high is not None:
        if today_hrv >= hrv_high:
            hrv_comp = min(100.0, 90.0 + (today_hrv - hrv_high) * 0.5)
        elif today_hrv < hrv_low:
            deficit = hrv_low - today_hrv
            hrv_comp = max(25.0, 65.0 - deficit * 2.5)
        else:
            spread = max(1.0, hrv_high - hrv_low)
            pos = (today_hrv - hrv_low) / spread
            hrv_comp = 75.0 + pos * 15.0

    # Component 2: Resting HR (25%)
    rhr_comp = 75.0
    if today_rhr:
        diff = today_rhr - baseline_rhr
        if diff <= -2:
            rhr_comp = 95.0
        elif diff <= 1:
            rhr_comp = 88.0
        elif diff <= 4:
            rhr_comp = 70.0
        elif diff <= 7:
            rhr_comp = 50.0
        else:
            rhr_comp = max(20.0, 40.0 - (diff - 7) * 4.0)

    # Component 3: Sleep (35%)
    sleep_comp = 75.0
    if today_sleep_score is not None:
        sleep_comp = float(today_sleep_score)
    elif today_sleep_hours is not None:
        if today_sleep_hours >= 7.5:
            sleep_comp = 90.0
        elif today_sleep_hours >= 6.5:
            sleep_comp = 75.0
        elif today_sleep_hours >= 5.5:
            sleep_comp = 55.0
        else:
            sleep_comp = max(20.0, today_sleep_hours * 10.0)

    readiness = int(round(hrv_comp * 0.40 + rhr_comp * 0.25 + sleep_comp * 0.35))
    readiness = max(10, min(100, readiness))

    return hrv_low, hrv_high, hrv_status, readiness


def ingest_apple_health_payload(payload: AppleHealthSyncRequest) -> Dict[str, Any]:
    """Ingests, normalizes, and upserts a sync payload from Apple Health."""
    target_date = payload.date or date.today().isoformat()

    # Normalize sleep times
    sleep_sec = payload.sleep_seconds
    if sleep_sec is None and payload.sleep_hours is not None:
        sleep_sec = int(round(payload.sleep_hours * 3600))

    deep_sec = payload.sleep_deep_sec
    if deep_sec is None and payload.sleep_deep_hours is not None:
        deep_sec = int(round(payload.sleep_deep_hours * 3600))

    rem_sec = payload.sleep_rem_sec
    if rem_sec is None and payload.sleep_rem_hours is not None:
        rem_sec = int(round(payload.sleep_rem_hours * 3600))

    light_sec = payload.sleep_light_sec
    if light_sec is None and payload.sleep_core_hours is not None:
        light_sec = int(round(payload.sleep_core_hours * 3600))

    awake_sec = payload.sleep_awake_sec
    if awake_sec is None and payload.sleep_awake_hours is not None:
        awake_sec = int(round(payload.sleep_awake_hours * 3600))

    sleep_score = payload.sleep_score
    if sleep_score is None and sleep_sec and sleep_sec > 0:
        sleep_score = calculate_sleep_score(sleep_sec, deep_sec, rem_sec, awake_sec)

    sleep_hours_approx = (sleep_sec / 3600.0) if sleep_sec else None

    # Compute baseline & readiness
    hrv_low, hrv_high, hrv_status, readiness = compute_hrv_baseline_and_readiness(
        target_date=target_date,
        today_hrv=payload.hrv_sdnn_ms,
        today_rhr=payload.resting_hr,
        today_sleep_score=sleep_score,
        today_sleep_hours=sleep_hours_approx,
    )

    record = {
        "date_key": target_date,
        "hrv_avg": round(payload.hrv_sdnn_ms, 1) if payload.hrv_sdnn_ms is not None else None,
        "hrv_baseline_low": hrv_low,
        "hrv_baseline_high": hrv_high,
        "hrv_status": hrv_status,
        "resting_hr": payload.resting_hr,
        "sleep_seconds": sleep_sec,
        "sleep_score": sleep_score,
        "sleep_deep_sec": deep_sec,
        "sleep_rem_sec": rem_sec,
        "sleep_light_sec": light_sec,
        "sleep_awake_sec": awake_sec,
        "training_readiness": readiness,
        "vo2_max": round(payload.vo2_max, 1) if payload.vo2_max is not None else None,
        "steps": payload.steps,
        "active_calories": payload.active_calories,
        "total_calories": payload.total_calories,
        "exercise_min": payload.exercise_min,
        "stand_hours": payload.stand_hours,
        "spo2_avg": round(payload.spo2_pct, 1) if payload.spo2_pct is not None else None,
        "respiration_avg": round(payload.respiration_rate, 1) if payload.respiration_rate is not None else None,
        "wrist_temperature_c": round(payload.wrist_temperature_c, 2) if payload.wrist_temperature_c is not None else None,
        "walking_hr_avg": round(payload.walking_hr, 1) if payload.walking_hr is not None else None,
        "source": "apple_health",
        "is_demo": 0,
        "raw": payload.raw_payload or payload.model_dump(exclude_none=True),
    }

    db.upsert_wellness_daily(record)
    db.set_setting("apple_health_last_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Also save snapshot of latest Apple Health sync
    db.save_wellness_snapshot("latest_apple_health_sync", {
        "date_key": target_date,
        "readiness": readiness,
        "hrv": payload.hrv_sdnn_ms,
        "resting_hr": payload.resting_hr,
        "vo2_max": payload.vo2_max,
        "sleep_score": sleep_score,
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    logger.info("Apple Health sincronizzato con successo per data %s (Readiness %d)", target_date, readiness)
    return {
        "status": "ok",
        "date": target_date,
        "readiness": readiness,
        "hrv_status": hrv_status,
        "sleep_score": sleep_score,
    }


def ingest_manual_entry(entry: AppleHealthManualEntry) -> Dict[str, Any]:
    """Handles manual entry or correction from the Web UI."""
    sleep_sec = int(round(entry.sleep_hours * 3600)) if entry.sleep_hours is not None else None
    deep_sec = int(round(entry.sleep_deep_hours * 3600)) if entry.sleep_deep_hours is not None else None
    rem_sec = int(round(entry.sleep_rem_hours * 3600)) if entry.sleep_rem_hours is not None else None

    sleep_score = None
    if sleep_sec and sleep_sec > 0:
        sleep_score = calculate_sleep_score(sleep_sec, deep_sec, rem_sec)

    hrv_low, hrv_high, hrv_status, readiness = compute_hrv_baseline_and_readiness(
        target_date=entry.date_key,
        today_hrv=entry.hrv_avg,
        today_rhr=entry.resting_hr,
        today_sleep_score=sleep_score,
        today_sleep_hours=entry.sleep_hours,
    )

    record = {
        "date_key": entry.date_key,
        "hrv_avg": round(entry.hrv_avg, 1) if entry.hrv_avg is not None else None,
        "hrv_baseline_low": hrv_low,
        "hrv_baseline_high": hrv_high,
        "hrv_status": hrv_status,
        "resting_hr": entry.resting_hr,
        "sleep_seconds": sleep_sec,
        "sleep_score": sleep_score,
        "sleep_deep_sec": deep_sec,
        "sleep_rem_sec": rem_sec,
        "sleep_light_sec": (sleep_sec - (deep_sec or 0) - (rem_sec or 0)) if sleep_sec else None,
        "training_readiness": readiness,
        "vo2_max": round(entry.vo2_max, 1) if entry.vo2_max is not None else None,
        "steps": entry.steps,
        "active_calories": entry.active_calories,
        "total_calories": None,
        "exercise_min": entry.exercise_min,
        "stand_hours": entry.stand_hours,
        "spo2_avg": entry.spo2_avg,
        "respiration_avg": entry.respiration_avg,
        "source": "manual",
        "is_demo": 0,
        "raw": entry.model_dump(exclude_none=True),
    }

    db.upsert_wellness_daily(record)
    db.set_setting("apple_health_last_sync", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "status": "ok",
        "date_key": entry.date_key,
        "readiness": readiness,
        "hrv_status": hrv_status,
    }


def is_apple_health_connected() -> bool:
    """Returns True if there is at least one non-demo Apple Health record or recent sync."""
    with db.connect() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM wellness_daily WHERE is_demo = 0").fetchone()
        return bool(row and row["c"] > 0)
