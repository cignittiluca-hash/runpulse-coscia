import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RUNPULSE_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

GARMIN_TOKEN_DIR = DATA_DIR / "garmin_tokens"
GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "runpulse.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

FRONTEND_DIR = BASE_DIR / "frontend"

APP_PORT = int(os.getenv("PORT") or os.getenv("RUNPULSE_PORT", "8000"))
BASE_URL = os.getenv("RUNPULSE_BASE_URL", f"http://localhost:{APP_PORT}").rstrip("/")

APP_SECRET_SALT = os.getenv("RUNPULSE_SECRET_SALT", "runpulse-garmin-whoop-secret-salt-2026")

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"
WHOOP_SCOPES = "read:recovery read:cycles read:workout read:sleep read:profile"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_SETTINGS = {
    "athlete_name": "Runner",
    "max_hr": "190",
    "resting_hr": "52",
    "threshold_pace_sec": "275",
    "weekly_goal_km": "40",
    # Garmin
    "garmin_email": "",
    "garmin_display_name": "",
    "garmin_last_sync": "",
    # Whoop
    "whoop_client_id": os.getenv("WHOOP_CLIENT_ID", ""),
    "whoop_client_secret": os.getenv("WHOOP_CLIENT_SECRET", ""),
    "whoop_access_token": "",
    "whoop_refresh_token": "",
    "whoop_token_expires_at": "0",
    "whoop_user_id": "",
    "whoop_api_key": os.getenv("WHOOP_API_KEY") or secrets.token_hex(16),
    "whoop_last_sync": "",
    # Strava
    "strava_client_id": os.getenv("STRAVA_CLIENT_ID", ""),
    "strava_client_secret": os.getenv("STRAVA_CLIENT_SECRET", ""),
    "strava_access_token": "",
    "strava_refresh_token": "",
    "strava_token_expires_at": "0",
    "strava_athlete_name": "",
    "strava_last_sync": "",
    # AI Coach
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
    "auto_sync_enabled": "true",
    "auto_sync_interval_min": "30",
    "app_password_hash": "",
}
