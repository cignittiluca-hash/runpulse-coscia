"""Real Strava API v3 OAuth2 & activity synchronization service."""
import asyncio
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from backend.config import BASE_URL
from backend.database import db
from backend.services.analytics import (
    analyze_splits_metrics,
    classify_workout,
    compute_trimp,
)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

_strava_token_lock = asyncio.Lock()
_strava_sync_lock = asyncio.Lock()
_oauth_states: Dict[str, float] = {}


def get_strava_auth_url(redirect_uri: Optional[str] = None) -> str:
    settings = db.get_settings()
    client_id = settings.get("strava_client_id", "").strip()
    if not client_id:
        raise ValueError("Inserisci prima il tuo Strava Client ID e Client Secret nelle Impostazioni.")
    callback = redirect_uri or f"{BASE_URL}/api/strava/callback"
    state = secrets.token_urlsafe(24)
    # Prune expired states (>10 min)
    now = time.time()
    for k in [k for k, ts in _oauth_states.items() if now - ts > 600]:
        _oauth_states.pop(k, None)
    _oauth_states[state] = now
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": callback,
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": state,
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


def verify_strava_oauth_state(state: Optional[str]) -> bool:
    if not state:
        return False
    ts = _oauth_states.pop(state, None)
    return ts is not None and (time.time() - ts) <= 600


async def exchange_strava_code(code: str) -> Dict[str, Any]:
    settings = db.get_settings()
    client_id = settings.get("strava_client_id", "").strip()
    client_secret = settings.get("strava_client_secret", "").strip()
    if not client_id or not client_secret:
        raise ValueError("Strava Client ID o Client Secret mancanti.")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"Errore OAuth Strava ({resp.status_code}): {resp.text}")
        data = resp.json()

    athlete = data.get("athlete") or {}
    full_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip() or "Atleta Strava"
    db.update_settings(
        {
            "strava_access_token": data.get("access_token", ""),
            "strava_refresh_token": data.get("refresh_token", ""),
            "strava_expires_at": str(data.get("expires_at", 0)),
            "strava_athlete_name": full_name,
            "strava_athlete_id": str(athlete.get("id", "")),
            "athlete_name": full_name if settings.get("athlete_name") in ("", "Runner") else settings.get("athlete_name"),
        }
    )
    return {"connected": True, "athlete_name": full_name, "athlete_id": athlete.get("id")}


async def get_valid_access_token() -> str:
    async with _strava_token_lock:
        settings = db.get_settings()
        access_token = settings.get("strava_access_token", "").strip()
        refresh_token = settings.get("strava_refresh_token", "").strip()
        expires_at = int(settings.get("strava_expires_at") or "0")

        if not refresh_token:
            raise ValueError("Strava non è ancora collegato. Connetti il tuo account nelle Impostazioni.")

        # Refresh token if expired or expiring within 3 minutes
        if access_token and time.time() < (expires_at - 180):
            return access_token

        client_id = settings.get("strava_client_id", "").strip()
        client_secret = settings.get("strava_client_secret", "").strip()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            if resp.status_code != 200:
                raise ValueError(f"Impossibile rinnovare il token Strava ({resp.status_code}): {resp.text}")
            data = resp.json()

        new_access = data["access_token"]
        db.update_settings(
            {
                "strava_access_token": new_access,
                "strava_refresh_token": data.get("refresh_token", refresh_token),
                "strava_expires_at": str(data.get("expires_at", 0)),
            }
        )
        return new_access


def is_strava_connected() -> bool:
    s = db.get_settings()
    return bool(s.get("strava_refresh_token", "").strip())


def disconnect_strava() -> None:
    db.update_settings(
        {
            "strava_access_token": "",
            "strava_refresh_token": "",
            "strava_expires_at": "0",
            "strava_athlete_name": "",
            "strava_athlete_id": "",
        }
    )


def _normalize_strava_activity(raw: Dict[str, Any], settings: Dict[str, str]) -> Dict[str, Any]:
    max_hr = float(settings.get("max_hr") or 190)
    resting_hr = float(settings.get("resting_hr") or 52)
    threshold_pace = float(settings.get("threshold_pace_sec") or 275)

    dist_m = float(raw.get("distance") or 0)
    moving_s = int(raw.get("moving_time") or 0)
    elapsed_s = int(raw.get("elapsed_time") or moving_s)
    avg_speed = float(raw.get("average_speed") or 0)
    avg_pace = (1000.0 / avg_speed) if avg_speed > 0 else ((moving_s / (dist_m / 1000.0)) if dist_m > 0 else 0)

    sport_type = raw.get("sport_type") or raw.get("type") or "Run"
    sport_lower = str(sport_type).lower()
    is_run = "run" in sport_lower

    avg_hr = raw.get("average_heartrate")
    max_act_hr = raw.get("max_heartrate")
    # Strava returns running/walking cadence as half-steps (spm/2); NEVER double cycling rpm!
    cadence = raw.get("average_cadence")
    if cadence and ("run" in sport_lower or "walk" in sport_lower) and cadence < 120:
        cadence = round(float(cadence) * 2, 1)

    start_local = raw.get("start_date_local") or raw.get("start_date") or datetime.utcnow().isoformat()
    date_key = str(start_local)[:10]

    category = classify_workout(
        name=raw.get("name", ""),
        distance_m=dist_m,
        avg_pace_sec_km=avg_pace,
        avg_hr=avg_hr,
        max_hr=max_hr,
        threshold_pace_sec=threshold_pace,
        sport_type=sport_type,
    )
    trimp = compute_trimp(
        moving_time_s=moving_s,
        avg_hr=avg_hr,
        max_hr=max_hr,
        resting_hr=resting_hr,
        avg_pace_sec_km=avg_pace,
        threshold_pace_sec=threshold_pace,
        is_run=is_run,
    )

    splits = raw.get("splits_metric") or []
    laps = raw.get("laps") or []
    split_metrics = analyze_splits_metrics(splits, avg_hr, max_hr) if is_run else {
        "cardiac_drift_pct": None, "efficiency_factor": None, "hr_zones": {}
    }

    # Efficiency factor strictly for running activities
    ef = split_metrics.get("efficiency_factor")
    if is_run and ef is None and avg_hr and avg_hr > 0 and moving_s > 0 and dist_m > 0:
        ef = round((dist_m / (moving_s / 60.0)) / float(avg_hr), 2)

    return {
        "id": f"strava_{raw['id']}",
        "source": "strava",
        "external_id": str(raw["id"]),
        "name": raw.get("name", "Allenamento Strava"),
        "sport_type": sport_type,
        "workout_category": category,
        "start_date": start_local,
        "date_key": date_key,
        "distance_m": dist_m,
        "moving_time_s": moving_s,
        "elapsed_time_s": elapsed_s,
        "elevation_gain_m": float(raw.get("total_elevation_gain") or 0),
        "avg_speed_ms": avg_speed,
        "max_speed_ms": float(raw.get("max_speed") or 0),
        "avg_pace_sec_km": round(avg_pace, 1) if avg_pace else 0,
        "avg_hr": avg_hr,
        "max_hr": max_act_hr,
        "avg_cadence": cadence,
        "calories": raw.get("calories"),
        "suffer_score": raw.get("suffer_score"),
        "trimp": trimp,
        "efficiency_factor": ef,
        "cardiac_drift_pct": split_metrics.get("cardiac_drift_pct"),
        "splits": splits,
        "laps": laps,
        "hr_zones": split_metrics.get("hr_zones") or {},
        "description": raw.get("description") or "",
        "is_demo": 0,
        "raw": raw,
    }


async def fetch_strava_activity_detail(external_id: str) -> Optional[Dict[str, Any]]:
    token = await get_valid_access_token()
    settings = db.get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/activities/{external_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            return None
        raw = resp.json()
    act = _normalize_strava_activity(raw, settings)
    db.upsert_activity(act)
    return db.get_activity(act["id"])


async def sync_strava_activities(
    days: int = 60,
    fetch_details: bool = True,
    all_history: bool = False,
) -> Dict[str, Any]:
    """Pulls Strava activities (last `days` days, or full history from run #1 when `all_history=True` or `days=0`)."""
    async with _strava_sync_lock:
        token = await get_valid_access_token()
        settings = db.get_settings()
        use_all = all_history or days <= 0
        after_ts = None if use_all else int((datetime.utcnow() - timedelta(days=days)).timestamp())

        fetched: List[Dict[str, Any]] = []
        page = 1
        max_pages = 50 if use_all else 5
        per_page = 200 if use_all else 60
        async with httpx.AsyncClient(timeout=30.0) as client:
            while page <= max_pages:
                params: Dict[str, Any] = {"per_page": per_page, "page": page}
                if after_ts is not None:
                    params["after"] = after_ts
                resp = await client.get(
                    f"{STRAVA_API_BASE}/athlete/activities",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                if resp.status_code == 429:
                    if fetched:
                        break
                    raise ValueError("Limite temporaneo API Strava (429): riprova tra 15 minuti.")
                if resp.status_code != 200:
                    raise ValueError(f"Errore sincronizzazione Strava ({resp.status_code}): {resp.text}")
                batch = resp.json()
                if not batch:
                    break
                fetched.extend(batch)
                if len(batch) < per_page:
                    break
                page += 1

            # Sort newest-first so detailed_count < 12 enriches the MOST RECENT runs, not the oldest!
            fetched.sort(key=lambda x: str(x.get("start_date_local") or x.get("start_date") or ""), reverse=True)

            synced_count = 0
            detailed_count = 0
            for raw in fetched:
                act_id = f"strava_{raw['id']}"
                existing = db.get_activity(act_id)
                normalized = _normalize_strava_activity(raw, settings)
                # Preserve split-derived metrics if existing already had splits
                if existing and existing.get("splits") and not normalized.get("splits"):
                    normalized["cardiac_drift_pct"] = existing.get("cardiac_drift_pct")
                    normalized["efficiency_factor"] = existing.get("efficiency_factor") or normalized.get("efficiency_factor")
                db.upsert_activity(normalized)
                synced_count += 1

                # Enrich up to 12 most recent running activities with splits/laps if not yet fetched
                is_run = "run" in str(normalized["sport_type"]).lower()
                needs_detail = (not existing) or (not existing.get("splits"))
                if fetch_details and is_run and needs_detail and detailed_count < 12:
                    d_resp = await client.get(
                        f"{STRAVA_API_BASE}/activities/{raw['id']}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if d_resp.status_code == 200:
                        det_norm = _normalize_strava_activity(d_resp.json(), settings)
                        db.upsert_activity(det_norm)
                        detailed_count += 1
                    elif d_resp.status_code == 429:
                        break

        # Automatically remove demo rows once real Strava activities are synced
        if synced_count > 0:
            db.delete_demo_data()

        # Link synced runs with active training plan
        active_goal = db.get_active_goal_with_workouts()
        linked = 0
        if active_goal:
            linked = db.auto_link_workouts_to_activities(active_goal["id"])

        db.set_setting("strava_last_sync", datetime.now().strftime("%Y-%m-%d %H:%M"))
        return {
            "status": "ok",
            "synced_activities": synced_count,
            "detailed_runs_fetched": detailed_count,
            "plan_workouts_linked": linked,
        }
