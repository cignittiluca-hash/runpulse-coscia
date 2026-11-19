"""Whoop 4.0 integration service: OAuth 2.0, Recovery, Cycle Strain, Sleep, and Quick-Checkin."""
import html
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
    """Fetches recovery, cycles (strain), and sleep from official Whoop developer API."""
    token = ensure_valid_whoop_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_iso = start_dt.isoformat().replace("+00:00", "Z")
    end_iso = end_dt.isoformat().replace("+00:00", "Z")

    records_by_date: Dict[str, Dict[str, Any]] = {}

    with httpx.Client(timeout=25.0) as client:
        # 1. Recovery
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

                row = records_by_date.setdefault(date_key, {"date_key": date_key})
                row["cycle_id"] = cycle_id
                row["recovery_score"] = int(rec_val) if rec_val is not None else None
                row["recovery_state"] = _recovery_state_from_score(row["recovery_score"])
                row["resting_hr"] = int(rhr) if rhr is not None else None
                row["hrv_rmssd"] = float(hrv) if hrv is not None else None
                row["spo2_pct"] = float(spo2) if spo2 is not None else None
                row["skin_temp_celsius"] = float(skin_temp) if skin_temp is not None else None

        # 2. Cycles (Strain)
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

                row = records_by_date.setdefault(date_key, {"date_key": date_key})
                if strain is not None:
                    row["day_strain"] = round(float(strain), 1)
                if kj is not None:
                    row["kilojoules"] = round(float(kj), 0)

        # 3. Sleep
        sleep_url = f"{WHOOP_API_BASE}/activity/sleep"
        slp_resp = client.get(sleep_url, headers=headers, params={"start": start_iso, "end": end_iso, "limit": 25})
        if slp_resp.status_code == 200:
            slp_data = slp_resp.json().get("records", [])
            for s in slp_data:
                if s.get("nap"):
                    continue
                start_time = s.get("start") or ""
                date_key = start_time[:10] if start_time else date.today().isoformat()
                score_obj = s.get("score") or {}
                perf = score_obj.get("sleep_performance_percentage")
                debt = score_obj.get("sleep_needed", {}).get("need_from_sleep_debt_milli", 0)
                stage_summary = score_obj.get("stage_summary") or {}

                in_bed_milli = stage_summary.get("total_in_bed_time_milli") or 0
                deep_milli = stage_summary.get("total_slow_wave_sleep_time_milli") or 0
                rem_milli = stage_summary.get("total_rem_sleep_time_milli") or 0
                light_milli = stage_summary.get("total_light_sleep_time_milli") or 0
                awake_milli = stage_summary.get("total_awake_time_milli") or 0

                row = records_by_date.setdefault(date_key, {"date_key": date_key})
                if perf is not None:
                    row["sleep_performance_pct"] = round(float(perf), 1)
                if debt is not None:
                    row["sleep_debt_minutes"] = int(debt / (1000 * 60))
                if in_bed_milli:
                    row["sleep_hours"] = round(float(in_bed_milli - awake_milli) / 3600000.0, 2)
                    row["sleep_deep_hours"] = round(float(deep_milli) / 3600000.0, 2)
                    row["sleep_rem_hours"] = round(float(rem_milli) / 3600000.0, 2)
                    row["sleep_light_hours"] = round(float(light_milli) / 3600000.0, 2)
                    row["sleep_awake_hours"] = round(float(awake_milli) / 3600000.0, 2)

    count = 0
    for d_key, r in records_by_date.items():
        db.upsert_whoop_daily(r)
        count += 1

    db.set_setting("whoop_last_sync", datetime.now().isoformat())
    return {"status": "ok", "synced_days": count}


def ingest_whoop_manual_entry(entry: WhoopManualEntry) -> Dict[str, Any]:
    """Allows 5-second quick log or webhook sync without needing a developer account."""
    date_key = entry.date.strip()
    rec_state = _recovery_state_from_score(entry.recovery_score)

    data = {
        "date_key": date_key,
        "recovery_score": entry.recovery_score,
        "recovery_state": rec_state,
        "day_strain": entry.day_strain,
        "hrv_rmssd": entry.hrv_rmssd,
        "resting_hr": entry.resting_hr,
        "sleep_performance_pct": entry.sleep_performance_pct,
        "sleep_debt_minutes": entry.sleep_debt_minutes,
        "sleep_hours": entry.sleep_hours,
        "spo2_pct": entry.spo2_percentage,
        "skin_temp_celsius": entry.skin_temp_celsius,
    }
    db.upsert_whoop_daily(data)
    db.set_setting("whoop_last_sync", datetime.now().isoformat())
    return {"status": "ok", "saved": data}
