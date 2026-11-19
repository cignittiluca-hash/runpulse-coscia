"""RunPulse FastAPI Backend — Strava + Garmin Personal Running Coach & PWA Server."""
import asyncio
import hashlib
import hmac
import html
import io
import logging
import os
import re
import socket
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

import segno
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles

from backend.config import APP_PORT, APP_SECRET_SALT, BASE_DIR, BASE_URL, FRONTEND_DIR
from backend.database import db

from backend.models import (
    AuthLoginRequest,
    CoachQuestionRequest,
    GarminLoginRequest,
    GarminMfaRequest,
    GarminImportTokensRequest,
    RaceGoalCreate,
    SettingsUpdate,
    SyncRequest,
    WorkoutToggleRequest,
    WhoopManualEntry,
    WhoopSyncRequest,
)
from backend.services.whoop_service import (
    is_whoop_connected,
    get_whoop_auth_url,
    exchange_whoop_code_for_token,
    sync_whoop_api,
    ingest_whoop_manual_entry,
    ingest_apple_health_whoop_bridge,
)
from backend.services.analytics import build_dashboard_summary, get_latest_valid_garmin
from backend.services.coach_engine import (
    analyze_single_run,
    ask_coach_question,
    chat_with_calippo,
    generate_daily_coach_advice,
    test_gemini_connection,
)
from backend.services.demo_data import seed_demo_data
from backend.services.garmin_service import (
    _persist_garmin_tokens_to_db,
    _restore_garmin_tokens_from_db,
    disconnect_garmin,
    is_garmin_connected,
    login_garmin,
    submit_garmin_mfa,
    import_garmin_tokens,
    sync_garmin_wellness,
)
from backend.services.plan_generator import adapt_plan_for_recovery, generate_race_plan
from backend.services.strava_service import (
    disconnect_strava,
    exchange_strava_code,
    fetch_strava_activity_detail,
    get_strava_auth_url,
    is_strava_connected,
    sync_strava_activities,
    verify_strava_oauth_state,
)

logger = logging.getLogger("runpulse")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_auto_sync_task: Optional[asyncio.Task] = None


async def _background_auto_sync_loop() -> None:
    """
    Wake-aware background auto-sync loop.
    Checks wall-clock time every 60 seconds so that right after the Mac wakes from sleep,
    Strava and Garmin sync automatically within ~60s instead of waiting out an old sleep timer.
    """
    await asyncio.sleep(8)
    last_sync_wall = 0.0
    while True:
        try:
            settings = db.get_settings()
            enabled = settings.get("auto_sync_enabled", "true").lower() == "true"
            interval_sec = max(5, int(settings.get("auto_sync_interval_min") or "15")) * 60
            now_wall = time.time()

            if enabled and (now_wall - last_sync_wall) >= interval_sec:
                attempted = False
                if is_strava_connected():
                    attempted = True
                    try:
                        res = await sync_strava_activities(days=21, fetch_details=True)
                        logger.info("Auto-sync Strava completato: %s", res)
                    except Exception as exc:
                        logger.warning("Auto-sync Strava fallito: %s", exc)
                if is_garmin_connected():
                    attempted = True
                    try:
                        res = await asyncio.to_thread(sync_garmin_wellness, 7, False)
                        logger.info("Auto-sync Garmin completato: %s", res)
                    except Exception as exc:
                        logger.warning("Auto-sync Garmin fallito: %s", exc)
                if is_whoop_connected():
                    attempted = True
                    try:
                        res = await asyncio.to_thread(sync_whoop_api, 7)
                        logger.info("Auto-sync Whoop completato: %s", res)
                    except Exception as exc:
                        logger.warning("Auto-sync Whoop fallito: %s", exc)
                # Always advance wall timer when a sync was attempted to avoid 60s retry storms on errors
                if attempted:
                    last_sync_wall = time.time()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Errore nel loop auto-sync: %s", exc)
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _auto_sync_task
    db.init_db()
    _auto_sync_task = asyncio.create_task(_background_auto_sync_loop())
    try:
        yield
    finally:
        if _auto_sync_task:
            _auto_sync_task.cancel()
            try:
                await _auto_sync_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="RunPulse — Personal Strava & Garmin Running Coach",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = list(dict.fromkeys([
    f"http://localhost:{APP_PORT}",
    f"http://127.0.0.1:{APP_PORT}",
    BASE_URL,
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


AUTH_COOKIE_NAME = "runpulse_auth"
_login_attempts: Dict[str, List[float]] = {}
_network_cache: Tuple[float, Optional[Dict[str, Any]]] = (0.0, None)


def _hash_password(raw_pw: str) -> str:
    return hashlib.sha256(f"{APP_SECRET_SALT}:{raw_pw}".encode("utf-8")).hexdigest()


def _active_password_hash() -> str:
    env_pw = os.getenv("RUNPULSE_ACCESS_PASSWORD", "").strip()
    if env_pw:
        return _hash_password(env_pw)
    return db.get_setting("app_password_hash", "").strip()


def _make_auth_token(pw_hash: str) -> str:
    return hmac.new(APP_SECRET_SALT.encode("utf-8"), pw_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def _is_request_authorized(request: Request) -> bool:
    pw_hash = _active_password_hash()
    if not pw_hash:
        return True
    cookie_val = request.cookies.get(AUTH_COOKIE_NAME, "")
    expected = _make_auth_token(pw_hash)
    return bool(cookie_val) and hmac.compare_digest(cookie_val, expected)


def _detect_network_urls(port: int = APP_PORT) -> Dict[str, Any]:
    lan_ip = None
    for iface in ("en0", "en1"):
        try:
            out = subprocess.check_output(["ipconfig", "getifaddr", iface], stderr=subprocess.DEVNULL, timeout=1.0)
            cand = out.decode("utf-8").strip()
            if cand and "." in cand:
                lan_ip = cand
                break
        except Exception:
            pass
    if not lan_ip:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            lan_ip = None

    tailscale_ip = None
    for ts_bin in ("tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale"):
        try:
            out = subprocess.check_output([ts_bin, "ip", "-4"], stderr=subprocess.DEVNULL, timeout=1.5)
            lines = [line.strip() for line in out.decode("utf-8").splitlines() if line.strip()]
            if lines:
                tailscale_ip = lines[0]
                break
        except Exception:
            pass

    # Fallback: scan macOS utun interfaces via ifconfig for Tailscale CGNAT 100.64.0.0/10
    if not tailscale_ip:
        try:
            out = subprocess.check_output(["ifconfig"], stderr=subprocess.DEVNULL, timeout=1.5).decode("utf-8", errors="ignore")
            for m in re.findall(r"inet\s+(100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)", out):
                tailscale_ip = m
                break
        except Exception:
            pass

    return {
        "port": port,
        "local_url": f"http://localhost:{port}",
        "wifi_url": f"http://{lan_ip}:{port}" if lan_ip else None,
        "tailscale_url": f"http://{tailscale_ip}:{port}" if tailscale_ip else None,
        "lan_ip": lan_ip,
        "tailscale_ip": tailscale_ip,
    }


@app.middleware("http")
async def auth_and_cache_middleware(request: Request, call_next):
    path = request.url.path
    # Protect private API routes when a personal password/PIN is set
    if path.startswith("/api/") and not path.startswith("/api/auth/") and path not in ("/api/health", "/api/strava/callback", "/api/whoop/callback", "/api/whoop/webhook", "/api/apple-health/sync"):
        if not _is_request_authorized(request):
            return JSONResponse({"detail": "Accesso protetto da password. Inserisci il PIN RunPulse."}, status_code=401)

    response = await call_next(request)
    if path == "/" or path.startswith("/static/") or path == "/sw.js":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def _public_settings() -> Dict[str, Any]:
    s = db.get_settings()
    return {
        "athlete_name": s.get("athlete_name", "Runner"),
        "max_hr": int(s.get("max_hr") or 190),
        "resting_hr": int(s.get("resting_hr") or 52),
        "threshold_pace_sec": int(s.get("threshold_pace_sec") or 275),
        "weekly_goal_km": float(s.get("weekly_goal_km") or 40),
        "auto_sync_enabled": s.get("auto_sync_enabled", "true").lower() == "true",
        "auto_sync_interval_min": int(s.get("auto_sync_interval_min") or 30),
        "strava_client_id": s.get("strava_client_id", ""),
        "strava_has_secret": bool(s.get("strava_client_secret", "").strip()),
        "strava_connected": is_strava_connected(),
        "strava_athlete_name": s.get("strava_athlete_name", ""),
        "strava_last_sync": s.get("strava_last_sync", ""),
        "garmin_email": s.get("garmin_email", ""),
        "garmin_connected": is_garmin_connected(),
        "garmin_display_name": s.get("garmin_display_name", ""),
        "garmin_last_sync": s.get("garmin_last_sync", ""),
        "whoop_connected": is_whoop_connected(),
        "whoop_client_id": s.get("whoop_client_id", ""),
        "whoop_has_secret": bool(s.get("whoop_client_secret", "").strip()),
        "whoop_api_key": s.get("whoop_api_key", ""),
        "whoop_last_sync": s.get("whoop_last_sync", ""),
        "gemini_configured": bool(s.get("gemini_api_key", "").strip()),
        "gemini_model": s.get("gemini_model", "gemini-3.8-flash"),
        "app_password_enabled": bool(_active_password_hash()),
        "storage_backend": "postgresql" if db.is_pg else "sqlite",
        "data_counts": db.has_any_data(),
    }


# ---------- Auth & Mobile Connection Info ----------
@app.get("/api/auth/status")
async def auth_status(request: Request):
    return {
        "password_enabled": bool(_active_password_hash()),
        "authenticated": _is_request_authorized(request),
    }


def _public_origin(request: Request) -> str:
    """Builds the true external HTTPS/HTTP origin behind reverse proxies like Render."""
    if os.getenv("RUNPULSE_BASE_URL", "").strip():
        return BASE_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _is_https_request(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    return proto == "https" or BASE_URL.startswith("https://")


@app.post("/api/auth/login")
async def auth_login(req: AuthLoginRequest, request: Request, response: Response):
    pw_hash = _active_password_hash()
    if not pw_hash:
        return {"authenticated": True}
    client_ip = (request.client.host if request.client else "unknown")
    now = time.time()
    recent = [t for t in _login_attempts.get(client_ip, []) if now - t < 300]
    if len(recent) >= 8:
        raise HTTPException(status_code=429, detail="Troppi tentativi falliti. Riprova tra 5 minuti.")
    if not hmac.compare_digest(_hash_password(req.password), pw_hash):
        recent.append(now)
        _login_attempts[client_ip] = recent
        raise HTTPException(status_code=401, detail="Password / PIN non corretto.")
    _login_attempts.pop(client_ip, None)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=_make_auth_token(pw_hash),
        max_age=90 * 24 * 3600,
        httponly=True,
        secure=_is_https_request(request),
        samesite="lax",
    )
    return {"authenticated": True}


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME)
    return {"authenticated": False}


@app.get("/api/mobile-info")
async def mobile_info(request: Request):
    global _network_cache
    now = time.time()
    if _network_cache[1] is not None and (now - _network_cache[0]) < 60:
        info = dict(_network_cache[1])
    else:
        info = await asyncio.to_thread(_detect_network_urls)
        _network_cache = (now, dict(info))
    info["current_origin"] = _public_origin(request)
    info["password_enabled"] = bool(_active_password_hash())
    return info


@app.get("/api/qr.svg")
async def qr_svg(data: str = Query(..., min_length=1, max_length=512)):
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=6, border=2, dark="#090c14", light="#ffffff")
    return RawResponse(content=buf.getvalue(), media_type="image/svg+xml")


# ---------- Health & Dashboard ----------
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "edition": "garmin_whoop",
        "storage_backend": "postgresql" if db.is_pg else "sqlite",
        "strava_connected": is_strava_connected(),
        "garmin_connected": is_garmin_connected(),
        "whoop_connected": is_whoop_connected(),
        "data_counts": db.has_any_data(),
    }


@app.get("/api/dashboard")
async def get_dashboard(use_ai: bool = False):
    activities = db.get_activities(limit=250)
    garmin_days = db.get_garmin_daily(days=30)
    whoop_days = db.get_whoop_daily(days=30)
    settings = db.get_settings()
    summary = build_dashboard_summary(activities, garmin_days, settings, whoop_days=whoop_days)
    active_goal = db.get_active_goal_with_workouts()
    advice = await generate_daily_coach_advice(
        use_ai=use_ai,
        summary=summary,
        activities=activities,
        active_goal=active_goal,
    )
    return {
        "summary": summary,
        "daily_advice": advice,
        "recent_activities": activities[:8],
        "active_goal": active_goal,
        "connections": {
            "strava_connected": is_strava_connected(),
            "garmin_connected": is_garmin_connected(),
            "whoop_connected": is_whoop_connected(),
            "gemini_configured": bool(settings.get("gemini_api_key", "").strip()),
            "strava_last_sync": settings.get("strava_last_sync", ""),
            "garmin_last_sync": settings.get("garmin_last_sync", ""),
            "whoop_last_sync": settings.get("whoop_last_sync", ""),
        },
    }


# ---------- Activities ----------
@app.get("/api/activities")
async def list_activities(
    limit: int = Query(2000, ge=1, le=5000),
    sport_type: Optional[str] = None,
    category: Optional[str] = None,
):
    return {"activities": db.get_activities(limit=limit, sport_type=sport_type, category=category)}


@app.get("/api/activities/{activity_id}")
async def get_activity_detail(activity_id: str, fetch_strava: bool = True):
    act = db.get_activity(activity_id)
    if not act:
        raise HTTPException(status_code=404, detail="Allenamento non trovato.")
    # On-demand Strava split enrichment if missing
    if fetch_strava and act.get("source") == "strava" and not act.get("splits") and not act.get("is_demo") and is_strava_connected():
        enriched = await fetch_strava_activity_detail(act["external_id"])
        if enriched:
            act = enriched
    return {"activity": act}


@app.post("/api/activities/{activity_id}/analyze")
async def analyze_activity_endpoint(activity_id: str):
    try:
        return await analyze_single_run(activity_id, force_ai=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------- Whoop 4.0 Endpoints ----------
@app.get("/api/whoop/auth-url")
async def whoop_auth_url_endpoint(request: Request):
    try:
        origin = _public_origin(request)
        redirect_uri = f"{origin}/api/whoop/callback"
        return {"url": get_whoop_auth_url(redirect_uri)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/whoop/callback")
async def whoop_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None, request: Request = None):
    if error or not code:
        err = html.escape(error or "Codice autorizzazione Whoop mancante.")
        return HTMLResponse(f"<h3>Errore connessione Whoop: {err}</h3><p><a href='/'>Torna a RunPulse</a></p>")
    try:
        origin = _public_origin(request) if request else ""
        redirect_uri = f"{origin}/api/whoop/callback"
        exchange_whoop_code_for_token(code, redirect_uri)
        asyncio.create_task(asyncio.to_thread(sync_whoop_api, 14))
        return RedirectResponse(url="/#settings?whoop=connected", status_code=303)
    except Exception as exc:
        return HTMLResponse(f"<h3>Errore scambio token Whoop: {html.escape(str(exc))}</h3><p><a href='/'>Torna a RunPulse</a></p>")


@app.post("/api/whoop/sync")
async def whoop_sync_endpoint():
    try:
        return await asyncio.to_thread(sync_whoop_api, 14)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/whoop/manual")
async def whoop_manual_endpoint(entry: WhoopManualEntry):
    try:
        return ingest_whoop_manual_entry(entry)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/whoop/webhook")
async def whoop_webhook_endpoint(request: Request):
    try:
        data = await request.json()
        # Official Whoop Developer Real-Time Event
        event_type = data.get("type")
        if event_type:
            logger.info("Ricevuto webhook Whoop real-time: %s", event_type)
            asyncio.create_task(asyncio.to_thread(sync_whoop_api, 3))
            return {"status": "ok", "event": event_type}

        token = request.headers.get("x-whoop-token") or data.get("auth_token")
        settings = db.get_settings()
        expected = settings.get("whoop_api_key", "").strip()
        if expected and token != expected:
            raise HTTPException(status_code=401, detail="Token webhook Whoop non valido.")

        if "hrv_sdnn_ms" in data or "sleep_deep_hours" in data:
            return ingest_apple_health_whoop_bridge(data)

        entry = WhoopManualEntry(**data)
        return ingest_whoop_manual_entry(entry)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/apple-health/sync")
async def apple_health_whoop_sync_endpoint(request: Request):
    """Seamless bridge: Whoop data flowing via Apple Health / iOS Shortcuts."""
    try:
        data = await request.json()
        return ingest_apple_health_whoop_bridge(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/whoop/config")
async def whoop_config_endpoint(request: Request):
    settings = db.get_settings()
    origin = _public_origin(request)
    token = settings.get("whoop_api_key", "")
    return {
        "webhook_url": f"{origin}/api/whoop/webhook",
        "auth_token": token,
        "is_connected": is_whoop_connected(),
        "latest": db.get_latest_whoop(),
    }


@app.get("/api/whoop/daily")
async def whoop_daily_endpoint(days: int = Query(30, ge=1, le=180)):
    return db.get_whoop_range(days=days)


# ---------- Garmin & Whoop Wellness ----------
@app.get("/api/wellness")
async def get_wellness(days: int = Query(30, ge=7, le=90)):
    garmin_days = db.get_garmin_daily(days=days)
    whoop_days = db.get_whoop_daily(days=days)
    activities = db.get_activities(limit=150)
    settings = db.get_settings()
    summary = build_dashboard_summary(activities, garmin_days, settings, whoop_days=whoop_days)
    snapshots = db.get_all_garmin_snapshots()
    return {
        "days": garmin_days,
        "latest": get_latest_valid_garmin(garmin_days),
        "whoop_days": whoop_days,
        "latest_whoop": db.get_latest_whoop(),
        "readiness": summary["readiness"],
        "snapshots": snapshots,
        "garmin_connected": is_garmin_connected(),
        "whoop_connected": is_whoop_connected(),
        "garmin_last_sync": settings.get("garmin_last_sync", ""),
        "whoop_last_sync": settings.get("whoop_last_sync", ""),
    }


@app.post("/api/garmin/login")
async def garmin_login_endpoint(req: GarminLoginRequest):
    try:
        return await asyncio.to_thread(login_garmin, req.email, req.password, req.mfa_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore login Garmin: {exc}")


@app.post("/api/garmin/mfa")
async def garmin_mfa_endpoint(req: GarminMfaRequest):
    try:
        return await asyncio.to_thread(submit_garmin_mfa, req.mfa_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/garmin/import-tokens")
async def garmin_import_tokens_endpoint(req: GarminImportTokensRequest):
    try:
        return await asyncio.to_thread(import_garmin_tokens, req.tokens_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore importazione token Garmin: {exc}")


@app.post("/api/garmin/sync")
async def garmin_sync_endpoint(req: SyncRequest = SyncRequest(days=14)):
    try:
        return await asyncio.to_thread(sync_garmin_wellness, min(req.days, 45), req.force_full)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione Garmin: {exc}")


@app.post("/api/garmin/disconnect")
async def garmin_disconnect_endpoint():
    disconnect_garmin()
    return {"status": "disconnected"}


# ---------- Strava OAuth & Sync ----------
@app.get("/api/strava/auth-url")
async def strava_auth_url_endpoint(request: Request):
    try:
        origin = _public_origin(request)
        callback = f"{origin}/api/strava/callback"
        return {"auth_url": get_strava_auth_url(redirect_uri=callback), "redirect_uri": callback}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/strava/callback")
async def strava_callback_endpoint(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error or not code or not verify_strava_oauth_state(state):
        return RedirectResponse(url="/?strava=error#settings")
    try:
        await exchange_strava_code(code)
        try:
            await sync_strava_activities(days=60, fetch_details=True)
        except Exception as sync_exc:
            logger.warning("Initial Strava sync warning: %s", sync_exc)
        return RedirectResponse(url="/?strava=connected#settings")
    except Exception as exc:
        logger.error("Strava callback error: %s", exc)
        safe_err = html.escape(str(exc))
        return HTMLResponse(
            f"<h2>Errore connessione Strava</h2><p>{safe_err}</p><a href='/'>Torna a RunPulse</a>",
            status_code=400,
        )


@app.post("/api/strava/sync")
async def strava_sync_endpoint(req: SyncRequest = SyncRequest(days=60)):
    try:
        return await sync_strava_activities(
            days=req.days,
            fetch_details=req.fetch_details,
            all_history=req.all_history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione Strava: {exc}")


@app.post("/api/strava/disconnect")
async def strava_disconnect_endpoint():
    disconnect_strava()
    return {"status": "disconnected"}


@app.post("/api/sync-all")
async def sync_all_endpoint(req: SyncRequest = SyncRequest(days=30)):
    results: Dict[str, Any] = {"strava": None, "garmin": None, "errors": []}
    if is_strava_connected():
        try:
            results["strava"] = await sync_strava_activities(days=req.days, fetch_details=True)
        except Exception as exc:
            results["errors"].append(f"Strava: {exc}")
    if is_garmin_connected():
        try:
            results["garmin"] = await asyncio.to_thread(sync_garmin_wellness, min(req.days, 21))
        except Exception as exc:
            results["errors"].append(f"Garmin: {exc}")
    if not is_strava_connected() and not is_garmin_connected():
        raise HTTPException(
            status_code=400,
            detail="Collega prima Strava e/o Garmin nelle Impostazioni (oppure carica i dati demo).",
        )
    return results


# ---------- Hybrid Coach & Calippo Chatbot ----------
@app.get("/api/coach/daily")
async def coach_daily_endpoint(use_ai: bool = True):
    return await generate_daily_coach_advice(use_ai=use_ai)


@app.post("/api/coach/ask")
async def coach_ask_endpoint(req: CoachQuestionRequest):
    return await ask_coach_question(req.question)


@app.get("/api/calippo/messages")
async def calippo_get_messages():
    settings = db.get_settings()
    return {
        "messages": db.get_chat_messages(limit=60),
        "gemini_configured": bool(settings.get("gemini_api_key", "").strip()),
        "suggestions": [
            "Come sto messo a stress Garmin e recupero oggi?",
            "Cosa mi conviene fare oggi in allenamento?",
            "Analizza le mie ultime corse su Strava",
            "Come procede il mio piano gara e quali sono i miei ritmi?",
            "Che tempi posso fare su 10K e Mezza Maratona?",
        ],
    }


@app.post("/api/calippo/chat")
async def calippo_chat_endpoint(req: CoachQuestionRequest):
    try:
        return await chat_with_calippo(req.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/calippo/messages")
async def calippo_clear_messages():
    db.clear_chat_messages()
    return {"status": "cleared"}


@app.post("/api/gemini/test")
async def gemini_test_endpoint():
    return await test_gemini_connection()


# ---------- Race Goals & Training Plans ----------
@app.get("/api/plans")
async def list_plans():
    goals = db.get_race_goals()
    active = db.get_active_goal_with_workouts()
    return {"goals": goals, "active_goal": active}


@app.get("/api/plans/{goal_id}")
async def get_plan(goal_id: int):
    goal = db.get_goal_with_workouts(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Piano gara non trovato.")
    return {"goal": goal}


@app.post("/api/plans")
async def create_plan(req: RaceGoalCreate):
    try:
        goal = await generate_race_plan(
            name=req.name,
            distance_type=req.distance_type,
            race_date_str=req.race_date,
            target_time_sec=req.target_time_sec,
            days_per_week=req.days_per_week,
            long_run_day=req.long_run_day,
            current_weekly_km=req.current_weekly_km,
            notes=req.notes or "",
            use_ai=req.use_ai,
        )
        return {"goal": goal}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/plans/{goal_id}/activate")
async def activate_plan(goal_id: int):
    if not db.set_active_goal(goal_id):
        raise HTTPException(status_code=404, detail="Piano gara non trovato.")
    return {"goal": db.get_goal_with_workouts(goal_id)}


@app.post("/api/plans/{goal_id}/adapt")
async def adapt_plan_endpoint(goal_id: int):
    try:
        return adapt_plan_for_recovery(goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.delete("/api/plans/{goal_id}")
async def delete_plan_endpoint(goal_id: int):
    db.delete_goal(goal_id)
    return {"status": "deleted"}


@app.patch("/api/workouts/{workout_id}")
async def toggle_workout_endpoint(workout_id: int, req: WorkoutToggleRequest):
    db.toggle_workout_completed(workout_id, req.completed, req.linked_activity_id)
    return {"status": "updated", "workout_id": workout_id, "completed": req.completed}


# ---------- Settings & Optional Demo Data ----------
@app.get("/api/settings")
async def get_settings_endpoint():
    return _public_settings()


@app.put("/api/settings")
async def update_settings_endpoint(req: SettingsUpdate, request: Request, response: Response):
    payload = req.model_dump(exclude_none=True)
    if "auto_sync_enabled" in payload:
        payload["auto_sync_enabled"] = "true" if payload["auto_sync_enabled"] else "false"
    if "app_password" in payload:
        if os.getenv("RUNPULSE_ACCESS_PASSWORD", "").strip():
            raise HTTPException(
                status_code=400,
                detail="La password è gestita dalla variabile ambiente RUNPULSE_ACCESS_PASSWORD.",
            )
        raw_pw = payload.pop("app_password").strip()
        if raw_pw == "__CLEAR__":
            payload["app_password_hash"] = ""
            response.delete_cookie(AUTH_COOKIE_NAME)
        elif raw_pw:
            pw_hash = _hash_password(raw_pw)
            payload["app_password_hash"] = pw_hash
            # Keep current browser authenticated immediately
            response.set_cookie(
                key=AUTH_COOKIE_NAME,
                value=_make_auth_token(pw_hash),
                max_age=90 * 24 * 3600,
                httponly=True,
                secure=_is_https_request(request),
                samesite="lax",
            )
    # Don't overwrite secrets with empty strings if user left field blank unintentionally
    for secret_k in ("strava_client_secret", "gemini_api_key"):
        if secret_k in payload and payload[secret_k] == "":
            payload.pop(secret_k)
    db.update_settings(payload)
    return _public_settings()


@app.post("/api/demo/seed")
async def demo_seed_endpoint():
    return seed_demo_data()


@app.delete("/api/demo/clear")
async def demo_clear_endpoint():
    return db.delete_demo_data()


# ---------- 1-Click Cloud Backup Export / Import ----------
@app.get("/api/backup/export")
async def backup_export_endpoint():
    # Ensure local Garmin OAuth token files are mirrored into settings before export
    _persist_garmin_tokens_to_db()
    payload = db.export_full_backup()
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="runpulse-backup.json"'},
    )


@app.post("/api/backup/import")
async def backup_import_endpoint(payload: Dict[str, Any]):
    if not isinstance(payload, dict) or "settings" not in payload:
        raise HTTPException(status_code=400, detail="File backup RunPulse non valido.")
    counts = db.import_full_backup(payload)
    _restore_garmin_tokens_from_db()
    return {"status": "ok", "imported": counts}


@app.get("/garmin_login.py")
async def download_garmin_script():
    script_path = BASE_DIR / "garmin_login.py"
    if script_path.exists():
        return FileResponse(str(script_path), media_type="text/x-python", filename="garmin_login.py")
    raise HTTPException(status_code=404, detail="Script non trovato")


# ---------- PWA Frontend Serving ----------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")
