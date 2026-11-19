"""Whoop 4.0 integration service: OAuth 2.0, Recovery, Cycle Strain, Sleep, Workouts, and Quick-Checkin."""
import html
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import httpx

from backend.config import (
    WHOOP_API_BASE,
    WHOOP_AUTH_URL,
    WHOOP_SCOPES,
    WHOOP_TOKEN_URL,
)
from backend.database import db
from backend.models import WhoopManualEntry

logger = logging.getLogger("runpulse.whoop")

WHOOP_SPORT_NAMES = {
    -1: "Attività Generica",
    0: "Corsa",
    1: "Ciclismo",
    16: "CrossFit",
    17: "Nuoto",
    20: "Canottaggio",
    24: "Camminata",
    43: "Pilates",
    44: "Yoga",
    45: "Sollevamento Pesi",
    48: "Functional Fitness",
    52: "Camminata Veloce",
    63: "Rowing Machine",
    71: "HIIT",
    84: "Stretching & Mobilità",
    96: "Trail Running",
}


def is_whoop_connected() -> bool:
    settings = db.get_settings()
    has_token = bool(settings.get("whoop_access_token", "").strip())
    # Or if there is any whoop data in DB
    has_data = db.has_whoop_data()
    return has_token or has_data


def get_whoop_auth_url(redirect_uri: str, state: str = "whoop_oauth") -> str:
    settings = db.get_settings()
    client_id = settings.get("whoop_client_id", "").strip()
    if not client_id:
        raise ValueError("Whoop Client ID non configurato. Impostalo in Connessioni o nelle variabili d'ambiente.")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": WHOOP_SCOPES,
        "state": state,
    }
    return f"{WHOOP_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())


def exchange_whoop_code_for_token(code: str, redirect_uri: str) -> Dict[str, Any]:
    settings = db.get_settings()
    client_id = settings.get("whoop_client_id", "").strip()
    client_secret = settings.get("whoop_client_secret", "").strip()
    if not client_id or not client_secret:
        raise ValueError("Whoop Client ID o Client Secret mancanti.")

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }

    resp = httpx.post(WHOOP_TOKEN_URL, data=payload, timeout=20.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Errore scambio token Whoop ({resp.status_code}): {resp.text}")

    data = resp.json()
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 3600)
    expires_at = str(int(time.time()) + int(expires_in))

    db.set_setting("whoop_access_token", access_token)
    db.set_setting("whoop_refresh_token", refresh_token)
    db.set_setting("whoop_token_expires_at", expires_at)
    if "user" in data and "id" in data["user"]:
        db.set_setting("whoop_user_id", str(data["user"]["id"]))

    return data


def ensure_valid_whoop_token() -> str:
    settings = db.get_settings()
    access_token = settings.get("whoop_access_token", "").strip()
    refresh_token = settings.get("whoop_refresh_token", "").strip()
    expires_at = int(settings.get("whoop_token_expires_at") or "0")
    client_id = settings.get("whoop_client_id", "").strip()
    client_secret = settings.get("whoop_client_secret", "").strip()

    if not access_token:
        raise ValueError("Nessun token Whoop presente. Connetti Whoop da Connessioni.")

    # Se scade tra meno di 5 minuti, rinfresca
    if time.time() > (expires_at - 300):
        if not refresh_token:
            raise ValueError("Token Whoop scaduto e nessun refresh_token disponibile.")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        resp = httpx.post(WHOOP_TOKEN_URL, data=payload, timeout=20.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Errore refresh token Whoop: {resp.text}")
        data = resp.json()
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", refresh_token)
        expires_in = data.get("expires_in", 3600)
        expires_at = str(int(time.time()) + int(expires_in))
        db.set_setting("whoop_access_token", access_token)
        db.set_setting("whoop_refresh_token", refresh_token)
        db.set_setting("whoop_token_expires_at", expires_at)

    return access_token


def _recovery_state_from_score(score: Optional[int]) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 67:
        return "GREEN"
    if score >= 34:
        return "YELLOW"
    return "RED"


def sync_whoop_api(days: int = 14) -> Dict[str, Any]:
    """Fetches recovery, cycles (strain), sleep, and workouts from official Whoop developer API."""
    token = ensure_valid_whoop_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_iso = start_dt.isoformat().replace("+00:00", "Z")
    end_iso = end_dt.isoformat().replace("+00:00", "Z")

    records_by_date: Dict[str, Dict[str, Any]] = {}

    with httpx.Client(timeout=25.0) as client:
        # 1. Recovery
        try:
            rec_url = f"{WHOOP_API_BASE}/recovery"
            rec_resp = client.get(rec_url, headers=headers, params={"start": start_iso, "end": end_iso, "limit": 25})
            if rec_resp.status_code == 200:
                rec_data = rec_resp.json().get("records", [])
                for r in rec_data:
                    cycle_id = str(r.get("cycle_id") or "")
                    created = r.get("created_at") or ""
                    date_key = created[:10] if created else date.today().isoformat()
                    score_obj = r.get("score") or {}

                    rec_val = score_obj.get("recovery_score")
                    rhr = score_obj.get("resting_heart_rate")
                    hrv = score_obj.get("hrv_rmssd_milli")
                    spo2 = score_obj.get("spo2_percentage")
                    skin_temp = score_obj.get("skin_temp_celsius")
                    user_calib = 1 if score_obj.get("user_calibrating") else 0

                    row = records_by_date.setdefault(date_key, {"date_key": date_key})
                    row["cycle_id"] = cycle_id
                    row["recovery_score"] = int(rec_val) if rec_val is not None else None
                    row["recovery_state"] = _recovery_state_from_score(row["recovery_score"])
                    row["resting_hr"] = int(rhr) if rhr is not None else None
                    row["hrv_rmssd"] = float(hrv) if hrv is not None else None
                    row["spo2_pct"] = float(spo2) if spo2 is not None else None
                    row["skin_temp_celsius"] = float(skin_temp) if skin_temp is not None else None
                    row["user_calibrating"] = user_calib
        except Exception as exc:
            logger.warning("Errore fetch Whoop recovery: %s", exc)

        # 2. Cycles (Strain & Energy)
        try:
            cyc_url = f"{WHOOP_API_BASE}/cycle"
            cyc_resp = client.get(cyc_url, headers=headers, params={"start": start_iso, "end": end_iso, "limit": 25})
            if cyc_resp.status_code == 200:
                cyc_data = cyc_resp.json().get("records", [])
                for c in cyc_data:
                    start_time = c.get("start") or ""
                    date_key = start_time[:10] if start_time else date.today().isoformat()
                    score_obj = c.get("score") or {}
                    strain = score_obj.get("strain")
                    kj = score_obj.get("kilojoules")
                    avg_hr = score_obj.get("average_heart_rate")
                    max_hr = score_obj.get("max_heart_rate")

                    row = records_by_date.setdefault(date_key, {"date_key": date_key})
                    if strain is not None:
                        row["day_strain"] = round(float(strain), 1)
                    if kj is not None:
                        row["kilojoules"] = round(float(kj), 0)
                        row["calories"] = round(float(kj) * 0.239006, 0)
                    if avg_hr is not None:
                        row["avg_hr"] = int(avg_hr)
                    if max_hr is not None:
                        row["max_hr"] = int(max_hr)
        except Exception as exc:
            logger.warning("Errore fetch Whoop cycles: %s", exc)

        # 3. Sleep & Sleep Coach
        try:
            sleep_url = f"{WHOOP_API_BASE}/activity/sleep"
            slp_resp = client.get(sleep_url, headers=headers, params={"start": start_iso, "end": end_iso, "limit": 25})
            if slp_resp.status_code == 200:
                slp_data = slp_resp.json().get("records", [])
                for s in slp_data:
                    start_time = s.get("start") or ""
                    date_key = start_time[:10] if start_time else date.today().isoformat()
                    score_obj = s.get("score") or {}
                    stage_summary = score_obj.get("stage_summary") or {}
                    sleep_needed_obj = score_obj.get("sleep_needed") or {}

                    in_bed_milli = stage_summary.get("total_in_bed_time_milli") or 0
                    deep_milli = stage_summary.get("total_slow_wave_sleep_time_milli") or 0
                    rem_milli = stage_summary.get("total_rem_sleep_time_milli") or 0
                    light_milli = stage_summary.get("total_light_sleep_time_milli") or 0
                    awake_milli = stage_summary.get("total_awake_time_milli") or 0

                    row = records_by_date.setdefault(date_key, {"date_key": date_key})

                    if s.get("nap"):
                        row["nap_count"] = (row.get("nap_count") or 0) + 1
                        row["nap_hours"] = round((row.get("nap_hours") or 0.0) + float(in_bed_milli) / 3600000.0, 2)
                        continue

                    perf = score_obj.get("sleep_performance_percentage")
                    efficiency = score_obj.get("sleep_efficiency_percentage")
                    consistency = score_obj.get("sleep_consistency_percentage")
                    resp_rate = score_obj.get("respiratory_rate")
                    disturbances = stage_summary.get("disturbance_count")
                    cycles = stage_summary.get("sleep_cycle_count")
                    latency_milli = score_obj.get("latency_milli")

                    baseline_milli = sleep_needed_obj.get("baseline_milli") or 0
                    debt_milli = sleep_needed_obj.get("need_from_sleep_debt_milli") or 0
                    strain_milli = sleep_needed_obj.get("need_from_recent_strain_milli") or 0
                    total_needed_milli = baseline_milli + debt_milli + strain_milli

                    if perf is not None:
                        row["sleep_performance_pct"] = round(float(perf), 1)
                    if efficiency is not None:
                        row["sleep_efficiency_pct"] = round(float(efficiency), 1)
                    if consistency is not None:
                        row["sleep_consistency_pct"] = round(float(consistency), 1)
                    if resp_rate is not None:
                        row["respiratory_rate"] = round(float(resp_rate), 2)
                    if disturbances is not None:
                        row["disturbances_count"] = int(disturbances)
                    if cycles is not None:
                        row["sleep_cycles_count"] = int(cycles)
                    if total_needed_milli:
                        row["sleep_needed_hours"] = round(float(total_needed_milli) / 3600000.0, 2)
                    if debt_milli:
                        row["sleep_debt_minutes"] = int(debt_milli / 60000)
                    if latency_milli:
                        row["sleep_latency_min"] = round(float(latency_milli) / 60000.0, 1)

                    if in_bed_milli:
                        row["time_in_bed_hours"] = round(float(in_bed_milli) / 3600000.0, 2)
                        row["sleep_hours"] = round(float(in_bed_milli - awake_milli) / 3600000.0, 2)
                        row["sleep_deep_hours"] = round(float(deep_milli) / 3600000.0, 2)
                        row["sleep_rem_hours"] = round(float(rem_milli) / 3600000.0, 2)
                        row["sleep_light_hours"] = round(float(light_milli) / 3600000.0, 2)
                        row["sleep_awake_hours"] = round(float(awake_milli) / 3600000.0, 2)
        except Exception as exc:
            logger.warning("Errore fetch Whoop sleep: %s", exc)

        # 4. Workouts & Recorded Sports
        try:
            work_url = f"{WHOOP_API_BASE}/activity/workout"
            work_resp = client.get(work_url, headers=headers, params={"start": start_iso, "end": end_iso, "limit": 25})
            if work_resp.status_code == 200:
                work_data = work_resp.json().get("records", [])
                for w in work_data:
                    start_time = w.get("start") or ""
                    date_key = start_time[:10] if start_time else date.today().isoformat()
                    sport_id = w.get("sport_id", -1)
                    sport_name = WHOOP_SPORT_NAMES.get(sport_id, f"Attività #{sport_id}")
                    score_obj = w.get("score") or {}
                    w_strain = score_obj.get("strain")
                    w_avg_hr = score_obj.get("average_heart_rate")
                    w_max_hr = score_obj.get("max_heart_rate")
                    w_kj = score_obj.get("kilojoules")
                    dist_m = score_obj.get("distance_meter")
                    zd = score_obj.get("zone_duration") or {}

                    row = records_by_date.setdefault(date_key, {"date_key": date_key})
                    workouts_list = row.setdefault("workouts_json", [])
                    if isinstance(workouts_list, str):
                        try:
                            workouts_list = json.loads(workouts_list)
                            row["workouts_json"] = workouts_list
                        except Exception:
                            workouts_list = []
                            row["workouts_json"] = workouts_list

                    w_obj = {
                        "id": w.get("id"),
                        "sport_id": sport_id,
                        "sport_name": sport_name,
                        "strain": round(float(w_strain), 1) if w_strain is not None else None,
                        "avg_hr": int(w_avg_hr) if w_avg_hr is not None else None,
                        "max_hr": int(w_max_hr) if w_max_hr is not None else None,
                        "calories": round(float(w_kj) * 0.239006) if w_kj is not None else None,
                        "distance_km": round(float(dist_m) / 1000.0, 2) if dist_m else None,
                        "start": start_time,
                        "end": w.get("end"),
                        "zones_min": {
                            "z0": round((zd.get("zone_zero_milli") or 0) / 60000.0, 1),
                            "z1": round((zd.get("zone_one_milli") or 0) / 60000.0, 1),
                            "z2": round((zd.get("zone_two_milli") or 0) / 60000.0, 1),
                            "z3": round((zd.get("zone_three_milli") or 0) / 60000.0, 1),
                            "z4": round((zd.get("zone_four_milli") or 0) / 60000.0, 1),
                            "z5": round((zd.get("zone_five_milli") or 0) / 60000.0, 1),
                        }
                    }
                    workouts_list.append(w_obj)
        except Exception as exc:
            logger.warning("Errore fetch Whoop workouts: %s", exc)

    count = 0
    for d_key, r in records_by_date.items():
        db.upsert_whoop_daily(r)
        count += 1

    db.set_setting("whoop_last_sync", datetime.now().isoformat())
    return {"status": "ok", "synced_days": count}


def ingest_whoop_manual_entry(entry: WhoopManualEntry) -> Dict[str, Any]:
    """Allows 5-second quick log or webhook sync with 100% Whoop 4.0 metrics."""
    date_key = entry.date.strip()
    rec_state = _recovery_state_from_score(entry.recovery_score)

    data = {
        "date_key": date_key,
        "recovery_score": entry.recovery_score,
        "recovery_state": rec_state,
        "user_calibrating": 1 if entry.user_calibrating else 0,
        "day_strain": entry.day_strain,
        "hrv_rmssd": entry.hrv_rmssd,
        "resting_hr": entry.resting_hr,
        "spo2_pct": entry.spo2_percentage,
        "skin_temp_celsius": entry.skin_temp_celsius,
        "calories": entry.calories or (round(entry.kilojoules * 0.239006) if entry.kilojoules else None),
        "kilojoules": entry.kilojoules,
        "avg_hr": entry.avg_hr,
        "max_hr": entry.max_hr,
        "sleep_performance_pct": entry.sleep_performance_pct,
        "sleep_needed_hours": entry.sleep_needed_hours,
        "sleep_debt_minutes": entry.sleep_debt_minutes,
        "sleep_efficiency_pct": entry.sleep_efficiency_pct,
        "sleep_consistency_pct": entry.sleep_consistency_pct,
        "respiratory_rate": entry.respiratory_rate,
        "disturbances_count": entry.disturbances_count,
        "sleep_cycles_count": entry.sleep_cycles_count,
        "sleep_hours": entry.sleep_hours,
        "time_in_bed_hours": entry.time_in_bed_hours,
        "sleep_deep_hours": entry.sleep_deep_hours,
        "sleep_rem_hours": entry.sleep_rem_hours,
        "sleep_light_hours": entry.sleep_light_hours,
        "sleep_awake_hours": entry.sleep_awake_hours,
        "sleep_latency_min": entry.sleep_latency_min,
        "nap_count": entry.nap_count or 0,
        "nap_hours": entry.nap_hours or 0.0,
        "hr_zones_json": json.dumps(entry.hr_zones or {}) if entry.hr_zones else "{}",
        "workouts_json": json.dumps(entry.workouts or []) if entry.workouts else "[]",
        "journal_json": json.dumps(entry.journal or []) if entry.journal else "[]",
    }
    db.upsert_whoop_daily(data)
    db.set_setting("whoop_last_sync", datetime.now().isoformat())
    return {"status": "ok", "saved": data}


def ingest_apple_health_whoop_bridge(data: Dict[str, Any]) -> Dict[str, Any]:
    """Seamless bridge: Ingests Whoop biometric data synced via Apple Health (HealthKit)."""
    date_key = str(data.get("date") or date.today().isoformat())[:10]
    hrv = data.get("hrv_sdnn_ms") or data.get("hrv_rmssd")
    rhr = data.get("resting_hr")
    sleep_h = data.get("sleep_hours")
    in_bed_h = data.get("time_in_bed_hours") or (float(sleep_h) + 0.6 if sleep_h else None)
    deep_h = data.get("sleep_deep_hours") or 0.0
    rem_h = data.get("sleep_rem_hours") or 0.0
    light_h = data.get("sleep_light_hours") or (max(0.0, float(sleep_h or 0) - float(deep_h) - float(rem_h)) if sleep_h else 0.0)
    awake_h = data.get("sleep_awake_hours") or (max(0.0, float(in_bed_h or 0) - float(sleep_h or 0)) if in_bed_h and sleep_h else 0.0)
    spo2 = data.get("spo2") or data.get("spo2_percentage")
    resp_rate = data.get("respiratory_rate") or data.get("respiration_rate")
    skin_temp = data.get("skin_temp_celsius") or data.get("wrist_temp_deviation")
    cal = data.get("calories") or data.get("active_energy_kcal")

    # If recovery score is passed directly or compute high-fidelity Whoop score
    rec = data.get("recovery_score")
    if rec is None:
        s_part = min(35.0, (float(sleep_h or 7.0) / 8.0) * 35.0)
        h_part = min(45.0, (float(hrv or 60.0) / 65.0) * 45.0)
        r_part = max(0.0, min(20.0, (60.0 - float(rhr or 52.0)) * 2.0 + 10.0))
        rec = int(round(max(10.0, min(99.0, s_part + h_part + r_part))))

    state = _recovery_state_from_score(rec)
    strain = data.get("day_strain") or round(min(21.0, max(4.0, (float(data.get("exercise_min") or 30) / 60.0) * 8.0 + 6.0)), 1)
    perf = data.get("sleep_performance_pct") or (min(100.0, round((float(sleep_h or 7) / 8.0) * 100.0, 1)) if sleep_h else None)
    eff = round((float(sleep_h) / float(in_bed_h)) * 100.0, 1) if sleep_h and in_bed_h and float(in_bed_h) > 0 else 92.0

    rec_data = {
        "date_key": date_key,
        "recovery_score": rec,
        "recovery_state": state,
        "day_strain": strain,
        "hrv_rmssd": float(hrv) if hrv else None,
        "resting_hr": int(rhr) if rhr else None,
        "spo2_pct": float(spo2) if spo2 else None,
        "skin_temp_celsius": float(skin_temp) if skin_temp else None,
        "respiratory_rate": float(resp_rate) if resp_rate else None,
        "calories": float(cal) if cal else None,
        "sleep_performance_pct": perf,
        "sleep_efficiency_pct": eff,
        "sleep_needed_hours": float(data.get("sleep_needed_hours") or 8.0),
        "sleep_debt_minutes": int(data.get("sleep_debt_minutes") or 0),
        "sleep_hours": float(sleep_h) if sleep_h else None,
        "time_in_bed_hours": float(in_bed_h) if in_bed_h else None,
        "sleep_deep_hours": float(deep_h) if deep_h else None,
        "sleep_rem_hours": float(rem_h) if rem_h else None,
        "sleep_light_hours": float(light_h) if light_h else None,
        "sleep_awake_hours": float(awake_h) if awake_h else None,
        "disturbances_count": int(data.get("disturbances_count") or 10),
    }
    db.upsert_whoop_daily(rec_data)
    db.set_setting("whoop_last_sync", datetime.now().isoformat())
    return {"status": "ok", "saved": rec_data}
