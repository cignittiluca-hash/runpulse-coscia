"""Dual-engine database layer for RunPulse (SQLite locally, PostgreSQL when DATABASE_URL is set)."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DATABASE_URL, DB_PATH, DEFAULT_SETTINGS


_NAMED_PARAM_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def _translate_sql_for_postgres(sql: str, params: Any) -> Tuple[str, Any]:
    """Converts SQLite-style `?` / `:name` placeholders & minor syntax to PostgreSQL psycopg3 format."""
    pg_sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    if "INSERT OR IGNORE INTO" in sql and "ON CONFLICT" not in pg_sql:
        pg_sql = pg_sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    if isinstance(params, dict):
        pg_sql = _NAMED_PARAM_RE.sub(r"%(\1)s", pg_sql)
        return pg_sql, params
    if params is not None:
        pg_sql = pg_sql.replace("?", "%s")
    return pg_sql, params


class _CompatConn:
    """Thin wrapper giving sqlite3 and psycopg3 an identical `.execute(sql, params)` interface."""

    def __init__(self, raw_conn: Any, is_pg: bool):
        self._conn = raw_conn
        self.is_pg = is_pg

    def execute(self, sql: str, params: Any = None):
        if self.is_pg:
            pg_sql, pg_params = _translate_sql_for_postgres(sql, params)
            cur = self._conn.cursor()
            cur.execute(pg_sql, pg_params)
            return cur
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def executescript(self, script: str) -> None:
        if self.is_pg:
            # Execute each DDL statement cleanly on PostgreSQL
            pg_script = (
                script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                .replace("REAL", "DOUBLE PRECISION")
                .replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT CURRENT_TIMESTAMP")
            )
            with self._conn.cursor() as cur:
                for stmt in pg_script.split(";"):
                    s = stmt.strip()
                    if s:
                        cur.execute(s)
        else:
            self._conn.executescript(script)


class Database:
    def __init__(self, db_path: Path = DB_PATH, database_url: Optional[str] = None):
        self.database_url = (database_url if database_url is not None else DATABASE_URL).strip()
        self.is_pg = self.database_url.startswith("postgres://") or self.database_url.startswith("postgresql://")
        self.db_path = Path(db_path)
        if not self.is_pg:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        if self.is_pg:
            import psycopg
            from psycopg.rows import dict_row

            raw = psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=15)
            wrapped = _CompatConn(raw, is_pg=True)
            try:
                yield wrapped
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()
        else:
            raw = sqlite3.connect(str(self.db_path), timeout=30.0)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA busy_timeout=30000;")
            raw.execute("PRAGMA synchronous=NORMAL;")
            raw.execute("PRAGMA foreign_keys=ON;")
            wrapped = _CompatConn(raw, is_pg=False)
            try:
                yield wrapped
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            if not self.is_pg:
                conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'strava',
                    external_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    sport_type TEXT NOT NULL DEFAULT 'Run',
                    workout_category TEXT DEFAULT 'easy',
                    start_date TEXT NOT NULL,
                    date_key TEXT NOT NULL,
                    distance_m REAL NOT NULL DEFAULT 0,
                    moving_time_s INTEGER NOT NULL DEFAULT 0,
                    elapsed_time_s INTEGER NOT NULL DEFAULT 0,
                    elevation_gain_m REAL DEFAULT 0,
                    avg_speed_ms REAL DEFAULT 0,
                    max_speed_ms REAL DEFAULT 0,
                    avg_pace_sec_km REAL DEFAULT 0,
                    avg_hr REAL,
                    max_hr REAL,
                    avg_cadence REAL,
                    calories REAL,
                    suffer_score REAL,
                    trimp REAL DEFAULT 0,
                    efficiency_factor REAL,
                    cardiac_drift_pct REAL,
                    splits_json TEXT DEFAULT '[]',
                    laps_json TEXT DEFAULT '[]',
                    hr_zones_json TEXT DEFAULT '{}',
                    ai_analysis TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    is_demo INTEGER DEFAULT 0,
                    raw_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date_key DESC);

                
                CREATE TABLE IF NOT EXISTS whoop_daily (
                    date_key TEXT PRIMARY KEY,
                    recovery_score INTEGER,
                    recovery_state TEXT,
                    day_strain REAL,
                    hrv_rmssd REAL,
                    resting_hr INTEGER,
                    sleep_performance_pct REAL,
                    sleep_debt_minutes INTEGER,
                    sleep_hours REAL,
                    sleep_deep_hours REAL,
                    sleep_rem_hours REAL,
                    sleep_light_hours REAL,
                    sleep_awake_hours REAL,
                    spo2_pct REAL,
                    skin_temp_celsius REAL,
                    kilojoules REAL,
                    cycle_id TEXT,
                    raw_json TEXT DEFAULT '{}',
                    is_demo INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS garmin_daily (
                    date_key TEXT PRIMARY KEY,
                    stress_avg INTEGER,
                    stress_max INTEGER,
                    stress_rest_min INTEGER,
                    stress_low_min INTEGER,
                    stress_medium_min INTEGER,
                    stress_high_min INTEGER,
                    body_battery_max INTEGER,
                    body_battery_min INTEGER,
                    body_battery_current INTEGER,
                    body_battery_charged INTEGER,
                    body_battery_drained INTEGER,
                    hrv_avg REAL,
                    hrv_baseline_low REAL,
                    hrv_baseline_high REAL,
                    hrv_status TEXT,
                    resting_hr INTEGER,
                    sleep_seconds INTEGER,
                    sleep_score INTEGER,
                    sleep_deep_sec INTEGER,
                    sleep_rem_sec INTEGER,
                    sleep_light_sec INTEGER,
                    training_readiness INTEGER,
                    vo2_max REAL,
                    steps INTEGER,
                    spo2_avg REAL,
                    spo2_min REAL,
                    respiration_avg REAL,
                    respiration_sleep REAL,
                    active_calories INTEGER,
                    total_calories INTEGER,
                    intensity_moderate_min INTEGER,
                    intensity_vigorous_min INTEGER,
                    floors_ascended REAL,
                    hydration_ml REAL,
                    weight_kg REAL,
                    body_fat_pct REAL,
                    training_status TEXT,
                    acute_load REAL,
                    chronic_load REAL,
                    endurance_score INTEGER,
                    hill_score INTEGER,
                    watch_sync_time TEXT,
                    recovery_time_hours REAL,
                    is_demo INTEGER DEFAULT 0,
                    raw_json TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS race_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    distance_type TEXT NOT NULL,
                    distance_km REAL NOT NULL,
                    race_date TEXT NOT NULL,
                    target_time_sec INTEGER NOT NULL,
                    current_vdot REAL,
                    target_vdot REAL,
                    days_per_week INTEGER NOT NULL DEFAULT 4,
                    long_run_day INTEGER NOT NULL DEFAULT 6,
                    current_weekly_km REAL DEFAULT 35,
                    notes TEXT DEFAULT '',
                    ai_summary TEXT DEFAULT '',
                    paces_json TEXT DEFAULT '{}',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS plan_workouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER NOT NULL,
                    week_number INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    scheduled_date TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    workout_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_distance_km REAL DEFAULT 0,
                    target_duration_min INTEGER DEFAULT 0,
                    target_pace_range TEXT DEFAULT '',
                    target_hr_zone TEXT DEFAULT '',
                    intensity TEXT DEFAULT 'easy',
                    completed INTEGER DEFAULT 0,
                    linked_activity_id TEXT,
                    adapted_reason TEXT DEFAULT '',
                    FOREIGN KEY (goal_id) REFERENCES race_goals(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_plan_workouts_goal ON plan_workouts(goal_id, scheduled_date);

                CREATE TABLE IF NOT EXISTS coach_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_key TEXT NOT NULL,
                    readiness_score INTEGER,
                    recommendation_title TEXT,
                    recommendation_body TEXT,
                    source TEXT DEFAULT 'hybrid',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ai_powered INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS garmin_snapshots (
                    key TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Safe schema migrations for older local SQLite databases
            if not self.is_pg:
                extra_garmin_cols = [
                    ("spo2_avg", "REAL"),
                    ("spo2_min", "REAL"),
                    ("respiration_avg", "REAL"),
                    ("respiration_sleep", "REAL"),
                    ("active_calories", "INTEGER"),
                    ("total_calories", "INTEGER"),
                    ("intensity_moderate_min", "INTEGER"),
                    ("intensity_vigorous_min", "INTEGER"),
                    ("floors_ascended", "REAL"),
                    ("hydration_ml", "REAL"),
                    ("weight_kg", "REAL"),
                    ("body_fat_pct", "REAL"),
                    ("training_status", "TEXT"),
                    ("acute_load", "REAL"),
                    ("chronic_load", "REAL"),
                    ("endurance_score", "INTEGER"),
                    ("hill_score", "INTEGER"),
                    ("watch_sync_time", "TEXT"),
                    ("recovery_time_hours", "REAL"),
                ]
                existing_cols = {
                    r["name"] for r in conn.execute("PRAGMA table_info(garmin_daily)").fetchall()
                }
                for col_name, col_type in extra_garmin_cols:
                    if col_name not in existing_cols:
                        conn.execute(f"ALTER TABLE garmin_daily ADD COLUMN {col_name} {col_type}")

            # Fix any legacy Garmin recoveryTime values that were stored in minutes instead of hours
            conn.execute(
                "UPDATE garmin_daily SET recovery_time_hours = ROUND(CAST(recovery_time_hours / 60.0 AS NUMERIC), 2) "
                "WHERE recovery_time_hours IS NOT NULL AND recovery_time_hours > 120"
                if self.is_pg
                else "UPDATE garmin_daily SET recovery_time_hours = ROUND(recovery_time_hours / 60.0, 2) "
                "WHERE recovery_time_hours IS NOT NULL AND recovery_time_hours > 120"
            )

            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
                    (k, str(v)),
                )

    # ---------- Settings ----------
    def get_settings(self) -> Dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            data = dict(DEFAULT_SETTINGS)
            for r in rows:
                data[r["key"]] = r["value"]
                        # Fallback to env vars if db setting is empty
            env_map = [
                ("GARMIN_EMAIL", "garmin_email"),
                ("WHOOP_CLIENT_ID", "whoop_client_id"),
                ("WHOOP_CLIENT_SECRET", "whoop_client_secret"),
                ("WHOOP_API_KEY", "whoop_api_key"),
                ("STRAVA_CLIENT_ID", "strava_client_id"),
                ("STRAVA_CLIENT_SECRET", "strava_client_secret"),
                ("GEMINI_API_KEY", "gemini_api_key"),
                ("GEMINI_MODEL", "gemini_model"),
            ]
            for env_k, set_k in env_map:
                if not data.get(set_k) and os.getenv(env_k):
                    data[set_k] = os.getenv(env_k, "").strip()
            return data

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else DEFAULT_SETTINGS.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value) if value is not None else ""),
            )

    def update_settings(self, updates: Dict[str, Any]) -> None:
        with self.connect() as conn:
            for key, value in updates.items():
                if value is None:
                    continue
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )

    # ---------- Activities ----------
    def upsert_activity(self, act: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO activities (
                    id, source, external_id, name, sport_type, workout_category,
                    start_date, date_key, distance_m, moving_time_s, elapsed_time_s,
                    elevation_gain_m, avg_speed_ms, max_speed_ms, avg_pace_sec_km,
                    avg_hr, max_hr, avg_cadence, calories, suffer_score, trimp,
                    efficiency_factor, cardiac_drift_pct, splits_json, laps_json,
                    hr_zones_json, ai_analysis, description, is_demo, raw_json
                ) VALUES (
                    :id, :source, :external_id, :name, :sport_type, :workout_category,
                    :start_date, :date_key, :distance_m, :moving_time_s, :elapsed_time_s,
                    :elevation_gain_m, :avg_speed_ms, :max_speed_ms, :avg_pace_sec_km,
                    :avg_hr, :max_hr, :avg_cadence, :calories, :suffer_score, :trimp,
                    :efficiency_factor, :cardiac_drift_pct, :splits_json, :laps_json,
                    :hr_zones_json, :ai_analysis, :description, :is_demo, :raw_json
                )
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    sport_type = excluded.sport_type,
                    workout_category = excluded.workout_category,
                    distance_m = excluded.distance_m,
                    moving_time_s = excluded.moving_time_s,
                    elapsed_time_s = excluded.elapsed_time_s,
                    elevation_gain_m = excluded.elevation_gain_m,
                    avg_speed_ms = excluded.avg_speed_ms,
                    max_speed_ms = excluded.max_speed_ms,
                    avg_pace_sec_km = excluded.avg_pace_sec_km,
                    avg_hr = excluded.avg_hr,
                    max_hr = excluded.max_hr,
                    avg_cadence = COALESCE(excluded.avg_cadence, activities.avg_cadence),
                    calories = COALESCE(excluded.calories, activities.calories),
                    suffer_score = COALESCE(excluded.suffer_score, activities.suffer_score),
                    trimp = excluded.trimp,
                    efficiency_factor = COALESCE(excluded.efficiency_factor, activities.efficiency_factor),
                    cardiac_drift_pct = COALESCE(excluded.cardiac_drift_pct, activities.cardiac_drift_pct),
                    splits_json = CASE WHEN excluded.splits_json != '[]' THEN excluded.splits_json ELSE activities.splits_json END,
                    laps_json = CASE WHEN excluded.laps_json != '[]' THEN excluded.laps_json ELSE activities.laps_json END,
                    hr_zones_json = CASE WHEN excluded.hr_zones_json != '{}' THEN excluded.hr_zones_json ELSE activities.hr_zones_json END,
                    ai_analysis = CASE WHEN excluded.ai_analysis != '' THEN excluded.ai_analysis ELSE activities.ai_analysis END,
                    description = CASE WHEN excluded.description != '' THEN excluded.description ELSE activities.description END,
                    raw_json = CASE WHEN excluded.splits_json != '[]' OR activities.splits_json = '[]' THEN excluded.raw_json ELSE activities.raw_json END
                """,
                {
                    "id": str(act["id"]),
                    "source": act.get("source", "strava"),
                    "external_id": str(act.get("external_id", act["id"])),
                    "name": act.get("name", "Allenamento"),
                    "sport_type": act.get("sport_type", "Run"),
                    "workout_category": act.get("workout_category", "easy"),
                    "start_date": act["start_date"],
                    "date_key": act["date_key"],
                    "distance_m": float(act.get("distance_m") or 0),
                    "moving_time_s": int(act.get("moving_time_s") or 0),
                    "elapsed_time_s": int(act.get("elapsed_time_s") or act.get("moving_time_s") or 0),
                    "elevation_gain_m": float(act.get("elevation_gain_m") or 0),
                    "avg_speed_ms": float(act.get("avg_speed_ms") or 0),
                    "max_speed_ms": float(act.get("max_speed_ms") or 0),
                    "avg_pace_sec_km": float(act.get("avg_pace_sec_km") or 0),
                    "avg_hr": act.get("avg_hr"),
                    "max_hr": act.get("max_hr"),
                    "avg_cadence": act.get("avg_cadence"),
                    "calories": act.get("calories"),
                    "suffer_score": act.get("suffer_score"),
                    "trimp": float(act.get("trimp") or 0),
                    "efficiency_factor": act.get("efficiency_factor"),
                    "cardiac_drift_pct": act.get("cardiac_drift_pct"),
                    "splits_json": json.dumps(act.get("splits", [])) if isinstance(act.get("splits"), list) else (act.get("splits_json") or "[]"),
                    "laps_json": json.dumps(act.get("laps", [])) if isinstance(act.get("laps"), list) else (act.get("laps_json") or "[]"),
                    "hr_zones_json": json.dumps(act.get("hr_zones", {})) if isinstance(act.get("hr_zones"), dict) else (act.get("hr_zones_json") or "{}"),
                    "ai_analysis": act.get("ai_analysis") or "",
                    "description": act.get("description") or "",
                    "is_demo": int(act.get("is_demo") or 0),
                    "raw_json": json.dumps(act.get("raw", {})) if isinstance(act.get("raw"), dict) else (act.get("raw_json") or "{}"),
                },
            )

    def _hydrate_activity(self, row: Any) -> Dict[str, Any]:
        d = dict(row)
        d["splits"] = json.loads(d.pop("splits_json", "[]") or "[]")
        d["laps"] = json.loads(d.pop("laps_json", "[]") or "[]")
        d["hr_zones"] = json.loads(d.pop("hr_zones_json", "{}") or "{}")
        d.pop("raw_json", None)
        return d

    def get_activities(
        self,
        limit: int = 100,
        sport_type: Optional[str] = None,
        category: Optional[str] = None,
        since_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM activities WHERE 1=1"
        params: List[Any] = []
        if sport_type and sport_type != "all":
            query += " AND LOWER(sport_type) LIKE ?"
            params.append(f"%{sport_type.lower()}%")
        if category and category != "all":
            query += " AND workout_category = ?"
            params.append(category)
        if since_date:
            query += " AND date_key >= ?"
            params.append(since_date)
        query += " ORDER BY start_date DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._hydrate_activity(r) for r in rows]

    def get_activity(self, activity_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
            return self._hydrate_activity(row) if row else None

    def save_activity_ai_analysis(self, activity_id: str, analysis_text: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE activities SET ai_analysis = ? WHERE id = ?",
                (analysis_text, activity_id),
            )

    def delete_demo_data(self) -> Dict[str, int]:
        with self.connect() as conn:
            a = conn.execute("DELETE FROM activities WHERE is_demo = 1").rowcount
            g = conn.execute("DELETE FROM garmin_daily WHERE is_demo = 1").rowcount
            return {"activities_deleted": a, "garmin_days_deleted": g}

    # ---------- Garmin Daily ----------
    def upsert_garmin_daily(self, record: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO garmin_daily (
                    date_key, stress_avg, stress_max, stress_rest_min, stress_low_min,
                    stress_medium_min, stress_high_min, body_battery_max, body_battery_min,
                    body_battery_current, body_battery_charged, body_battery_drained,
                    hrv_avg, hrv_baseline_low, hrv_baseline_high, hrv_status,
                    resting_hr, sleep_seconds, sleep_score, sleep_deep_sec,
                    sleep_rem_sec, sleep_light_sec, training_readiness, vo2_max,
                    steps, spo2_avg, spo2_min, respiration_avg, respiration_sleep,
                    active_calories, total_calories, intensity_moderate_min, intensity_vigorous_min,
                    floors_ascended, hydration_ml, weight_kg, body_fat_pct,
                    training_status, acute_load, chronic_load, endurance_score, hill_score,
                    watch_sync_time, recovery_time_hours,
                    is_demo, raw_json, updated_at
                ) VALUES (
                    :date_key, :stress_avg, :stress_max, :stress_rest_min, :stress_low_min,
                    :stress_medium_min, :stress_high_min, :body_battery_max, :body_battery_min,
                    :body_battery_current, :body_battery_charged, :body_battery_drained,
                    :hrv_avg, :hrv_baseline_low, :hrv_baseline_high, :hrv_status,
                    :resting_hr, :sleep_seconds, :sleep_score, :sleep_deep_sec,
                    :sleep_rem_sec, :sleep_light_sec, :training_readiness, :vo2_max,
                    :steps, :spo2_avg, :spo2_min, :respiration_avg, :respiration_sleep,
                    :active_calories, :total_calories, :intensity_moderate_min, :intensity_vigorous_min,
                    :floors_ascended, :hydration_ml, :weight_kg, :body_fat_pct,
                    :training_status, :acute_load, :chronic_load, :endurance_score, :hill_score,
                    :watch_sync_time, :recovery_time_hours,
                    :is_demo, :raw_json, :updated_at
                )
                ON CONFLICT(date_key) DO UPDATE SET
                    stress_avg = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_avg ELSE COALESCE(excluded.stress_avg, garmin_daily.stress_avg) END,
                    stress_max = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_max ELSE COALESCE(excluded.stress_max, garmin_daily.stress_max) END,
                    stress_rest_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_rest_min ELSE COALESCE(excluded.stress_rest_min, garmin_daily.stress_rest_min) END,
                    stress_low_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_low_min ELSE COALESCE(excluded.stress_low_min, garmin_daily.stress_low_min) END,
                    stress_medium_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_medium_min ELSE COALESCE(excluded.stress_medium_min, garmin_daily.stress_medium_min) END,
                    stress_high_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stress_high_min ELSE COALESCE(excluded.stress_high_min, garmin_daily.stress_high_min) END,
                    body_battery_max = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_battery_max ELSE COALESCE(excluded.body_battery_max, garmin_daily.body_battery_max) END,
                    body_battery_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_battery_min ELSE COALESCE(excluded.body_battery_min, garmin_daily.body_battery_min) END,
                    body_battery_current = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_battery_current ELSE COALESCE(excluded.body_battery_current, garmin_daily.body_battery_current) END,
                    body_battery_charged = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_battery_charged ELSE COALESCE(excluded.body_battery_charged, garmin_daily.body_battery_charged) END,
                    body_battery_drained = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_battery_drained ELSE COALESCE(excluded.body_battery_drained, garmin_daily.body_battery_drained) END,
                    hrv_avg = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_avg ELSE COALESCE(excluded.hrv_avg, garmin_daily.hrv_avg) END,
                    hrv_baseline_low = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_baseline_low ELSE COALESCE(excluded.hrv_baseline_low, garmin_daily.hrv_baseline_low) END,
                    hrv_baseline_high = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_baseline_high ELSE COALESCE(excluded.hrv_baseline_high, garmin_daily.hrv_baseline_high) END,
                    hrv_status = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_status ELSE COALESCE(excluded.hrv_status, garmin_daily.hrv_status) END,
                    resting_hr = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.resting_hr ELSE COALESCE(excluded.resting_hr, garmin_daily.resting_hr) END,
                    sleep_seconds = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_seconds ELSE COALESCE(excluded.sleep_seconds, garmin_daily.sleep_seconds) END,
                    sleep_score = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_score ELSE COALESCE(excluded.sleep_score, garmin_daily.sleep_score) END,
                    sleep_deep_sec = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_deep_sec ELSE COALESCE(excluded.sleep_deep_sec, garmin_daily.sleep_deep_sec) END,
                    sleep_rem_sec = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_rem_sec ELSE COALESCE(excluded.sleep_rem_sec, garmin_daily.sleep_rem_sec) END,
                    sleep_light_sec = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_light_sec ELSE COALESCE(excluded.sleep_light_sec, garmin_daily.sleep_light_sec) END,
                    training_readiness = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.training_readiness ELSE COALESCE(excluded.training_readiness, garmin_daily.training_readiness) END,
                    vo2_max = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.vo2_max ELSE COALESCE(excluded.vo2_max, garmin_daily.vo2_max) END,
                    steps = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.steps ELSE COALESCE(excluded.steps, garmin_daily.steps) END,
                    spo2_avg = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.spo2_avg ELSE COALESCE(excluded.spo2_avg, garmin_daily.spo2_avg) END,
                    spo2_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.spo2_min ELSE COALESCE(excluded.spo2_min, garmin_daily.spo2_min) END,
                    respiration_avg = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.respiration_avg ELSE COALESCE(excluded.respiration_avg, garmin_daily.respiration_avg) END,
                    respiration_sleep = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.respiration_sleep ELSE COALESCE(excluded.respiration_sleep, garmin_daily.respiration_sleep) END,
                    active_calories = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.active_calories ELSE COALESCE(excluded.active_calories, garmin_daily.active_calories) END,
                    total_calories = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.total_calories ELSE COALESCE(excluded.total_calories, garmin_daily.total_calories) END,
                    intensity_moderate_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.intensity_moderate_min ELSE COALESCE(excluded.intensity_moderate_min, garmin_daily.intensity_moderate_min) END,
                    intensity_vigorous_min = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.intensity_vigorous_min ELSE COALESCE(excluded.intensity_vigorous_min, garmin_daily.intensity_vigorous_min) END,
                    floors_ascended = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.floors_ascended ELSE COALESCE(excluded.floors_ascended, garmin_daily.floors_ascended) END,
                    hydration_ml = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hydration_ml ELSE COALESCE(excluded.hydration_ml, garmin_daily.hydration_ml) END,
                    weight_kg = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.weight_kg ELSE COALESCE(excluded.weight_kg, garmin_daily.weight_kg) END,
                    body_fat_pct = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.body_fat_pct ELSE COALESCE(excluded.body_fat_pct, garmin_daily.body_fat_pct) END,
                    training_status = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.training_status ELSE COALESCE(excluded.training_status, garmin_daily.training_status) END,
                    acute_load = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.acute_load ELSE COALESCE(excluded.acute_load, garmin_daily.acute_load) END,
                    chronic_load = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.chronic_load ELSE COALESCE(excluded.chronic_load, garmin_daily.chronic_load) END,
                    endurance_score = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.endurance_score ELSE COALESCE(excluded.endurance_score, garmin_daily.endurance_score) END,
                    hill_score = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hill_score ELSE COALESCE(excluded.hill_score, garmin_daily.hill_score) END,
                    watch_sync_time = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.watch_sync_time ELSE COALESCE(excluded.watch_sync_time, garmin_daily.watch_sync_time) END,
                    recovery_time_hours = CASE WHEN garmin_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.recovery_time_hours ELSE COALESCE(excluded.recovery_time_hours, garmin_daily.recovery_time_hours) END,
                    is_demo = excluded.is_demo,
                    updated_at = excluded.updated_at
                WHERE garmin_daily.is_demo = 1 OR excluded.is_demo = 0
                """,
                {
                    "date_key": record["date_key"],
                    "stress_avg": record.get("stress_avg"),
                    "stress_max": record.get("stress_max"),
                    "stress_rest_min": record.get("stress_rest_min"),
                    "stress_low_min": record.get("stress_low_min"),
                    "stress_medium_min": record.get("stress_medium_min"),
                    "stress_high_min": record.get("stress_high_min"),
                    "body_battery_max": record.get("body_battery_max"),
                    "body_battery_min": record.get("body_battery_min"),
                    "body_battery_current": record.get("body_battery_current"),
                    "body_battery_charged": record.get("body_battery_charged"),
                    "body_battery_drained": record.get("body_battery_drained"),
                    "hrv_avg": record.get("hrv_avg"),
                    "hrv_baseline_low": record.get("hrv_baseline_low"),
                    "hrv_baseline_high": record.get("hrv_baseline_high"),
                    "hrv_status": record.get("hrv_status"),
                    "resting_hr": record.get("resting_hr"),
                    "sleep_seconds": record.get("sleep_seconds"),
                    "sleep_score": record.get("sleep_score"),
                    "sleep_deep_sec": record.get("sleep_deep_sec"),
                    "sleep_rem_sec": record.get("sleep_rem_sec"),
                    "sleep_light_sec": record.get("sleep_light_sec"),
                    "training_readiness": record.get("training_readiness"),
                    "vo2_max": record.get("vo2_max"),
                    "steps": record.get("steps"),
                    "spo2_avg": record.get("spo2_avg"),
                    "spo2_min": record.get("spo2_min"),
                    "respiration_avg": record.get("respiration_avg"),
                    "respiration_sleep": record.get("respiration_sleep"),
                    "active_calories": record.get("active_calories"),
                    "total_calories": record.get("total_calories"),
                    "intensity_moderate_min": record.get("intensity_moderate_min"),
                    "intensity_vigorous_min": record.get("intensity_vigorous_min"),
                    "floors_ascended": record.get("floors_ascended"),
                    "hydration_ml": record.get("hydration_ml"),
                    "weight_kg": record.get("weight_kg"),
                    "body_fat_pct": record.get("body_fat_pct"),
                    "training_status": record.get("training_status"),
                    "acute_load": record.get("acute_load"),
                    "chronic_load": record.get("chronic_load"),
                    "endurance_score": record.get("endurance_score"),
                    "hill_score": record.get("hill_score"),
                    "watch_sync_time": record.get("watch_sync_time"),
                    "recovery_time_hours": record.get("recovery_time_hours"),
                    "is_demo": int(record.get("is_demo") or 0),
                    "raw_json": json.dumps(record.get("raw", {})) if isinstance(record.get("raw"), dict) else "{}",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

    def save_garmin_snapshot(self, key: str, data: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO garmin_snapshots (key, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                (key, json.dumps(data, ensure_ascii=False, default=str), datetime.utcnow().isoformat()),
            )

    def get_garmin_snapshot(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT data_json FROM garmin_snapshots WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["data_json"])
            except Exception:
                return default

    def get_all_garmin_snapshots(self) -> Dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, data_json, updated_at FROM garmin_snapshots").fetchall()
            out: Dict[str, Any] = {}
            for r in rows:
                try:
                    out[r["key"]] = json.loads(r["data_json"])
                except Exception:
                    out[r["key"]] = None
            return out

    def get_garmin_daily(self, days: int = 30) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM garmin_daily ORDER BY date_key DESC LIMIT ?",
                (days,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d.pop("raw_json", None)
                result.append(d)
            return list(reversed(result))

    def get_latest_garmin(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM garmin_daily ORDER BY date_key DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d.pop("raw_json", None)
            return d

    
    # ---------- Whoop Daily ----------
    def upsert_whoop_daily(self, record: Dict[str, Any]) -> None:
        rec = dict(record)
        if "raw_json" in rec and isinstance(rec["raw_json"], (dict, list)):
            rec["raw_json"] = json.dumps(rec["raw_json"], ensure_ascii=False)
        rec.setdefault("raw_json", "{}")

        keys = [
            "date_key", "recovery_score", "recovery_state", "day_strain", "hrv_rmssd",
            "resting_hr", "sleep_performance_pct", "sleep_debt_minutes", "sleep_hours",
            "sleep_deep_hours", "sleep_rem_hours", "sleep_light_hours", "sleep_awake_hours",
            "spo2_pct", "skin_temp_celsius", "kilojoules", "cycle_id", "is_demo", "raw_json"
        ]
        present = {k: rec.get(k) for k in keys if k in rec}
        present.setdefault("date_key", rec["date_key"])

        col_names = list(present.keys())
        placeholders = ", ".join(["?"] * len(col_names))
        updates = ", ".join([f"{c} = excluded.{c}" for c in col_names if c != "date_key"])
        sql = "INSERT INTO whoop_daily (" + ", ".join(col_names) + ") VALUES (" + placeholders + ") ON CONFLICT(date_key) DO UPDATE SET " + updates + ", updated_at = CURRENT_TIMESTAMP"
        with self.connect() as conn:
            conn.execute(sql, tuple(present.values()))

    def get_whoop_daily(self, date_key: Optional[str] = None, days: Optional[int] = None) -> Any:
        if days is not None or isinstance(date_key, int):
            d = days if days is not None else date_key
            return self.get_whoop_range(days=d)
        if date_key is None:
            return self.get_whoop_range(days=30)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM whoop_daily WHERE date_key = ?", (date_key,)).fetchone()
            return dict(row) if row else None

    def get_latest_whoop(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM whoop_daily ORDER BY date_key DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def get_whoop_range(self, days: int = 30) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM whoop_daily ORDER BY date_key DESC LIMIT ?", (days,)
            ).fetchall()
            return [dict(r) for r in rows]

    def has_whoop_data(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM whoop_daily").fetchone()
            return (row["c"] if row else 0) > 0

    # ---------- Race Goals & Plans ----------
    def create_race_goal(self, goal: Dict[str, Any], workouts: List[Dict[str, Any]]) -> int:
        with self.connect() as conn:
            conn.execute("UPDATE race_goals SET is_active = 0")
            sql = """
                INSERT INTO race_goals (
                    name, distance_type, distance_km, race_date, target_time_sec,
                    current_vdot, target_vdot, days_per_week, long_run_day,
                    current_weekly_km, notes, ai_summary, paces_json, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """
            params = (
                goal["name"],
                goal["distance_type"],
                goal["distance_km"],
                goal["race_date"],
                goal["target_time_sec"],
                goal.get("current_vdot"),
                goal.get("target_vdot"),
                goal["days_per_week"],
                goal["long_run_day"],
                goal.get("current_weekly_km", 35),
                goal.get("notes", ""),
                goal.get("ai_summary", ""),
                json.dumps(goal.get("paces", {})),
            )
            if self.is_pg:
                row = conn.execute(sql + " RETURNING id", params).fetchone()
                goal_id = int(row["id"])
            else:
                cur = conn.execute(sql, params)
                goal_id = int(cur.lastrowid)

            for w in workouts:
                conn.execute(
                    """
                    INSERT INTO plan_workouts (
                        goal_id, week_number, phase, scheduled_date, day_of_week,
                        workout_type, title, description, target_distance_km,
                        target_duration_min, target_pace_range, target_hr_zone,
                        intensity, completed, adapted_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '')
                    """,
                    (
                        goal_id,
                        w["week_number"],
                        w["phase"],
                        w["scheduled_date"],
                        w["day_of_week"],
                        w["workout_type"],
                        w["title"],
                        w["description"],
                        w.get("target_distance_km", 0),
                        w.get("target_duration_min", 0),
                        w.get("target_pace_range", ""),
                        w.get("target_hr_zone", ""),
                        w.get("intensity", "easy"),
                    ),
                )
            return goal_id

    def get_race_goals(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM race_goals ORDER BY is_active DESC, created_at DESC").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["paces"] = json.loads(d.pop("paces_json", "{}") or "{}")
                out.append(d)
            return out

    def get_goal_with_workouts(self, goal_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM race_goals WHERE id = ?", (goal_id,)).fetchone()
            if not row:
                return None
            goal = dict(row)
            goal["paces"] = json.loads(goal.pop("paces_json", "{}") or "{}")
            w_rows = conn.execute(
                "SELECT * FROM plan_workouts WHERE goal_id = ? ORDER BY scheduled_date ASC, id ASC",
                (goal_id,),
            ).fetchall()
            goal["workouts"] = [dict(w) for w in w_rows]
            return goal

    def get_active_goal_with_workouts(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM race_goals WHERE is_active = 1 LIMIT 1").fetchone()
            if not row:
                row = conn.execute("SELECT id FROM race_goals ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            goal_id = row["id"]
        return self.get_goal_with_workouts(goal_id)

    def set_active_goal(self, goal_id: int) -> bool:
        with self.connect() as conn:
            exists = conn.execute("SELECT 1 FROM race_goals WHERE id = ?", (goal_id,)).fetchone()
            if not exists:
                return False
            conn.execute("UPDATE race_goals SET is_active = 0")
            conn.execute("UPDATE race_goals SET is_active = 1 WHERE id = ?", (goal_id,))
            return True

    def delete_goal(self, goal_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM race_goals WHERE id = ?", (goal_id,))

    def toggle_workout_completed(self, workout_id: int, completed: bool, linked_activity_id: Optional[str] = None) -> None:
        with self.connect() as conn:
            if completed:
                conn.execute(
                    "UPDATE plan_workouts SET completed = 1, linked_activity_id = COALESCE(?, linked_activity_id) WHERE id = ?",
                    (linked_activity_id, workout_id),
                )
            else:
                conn.execute(
                    "UPDATE plan_workouts SET completed = 0, linked_activity_id = NULL WHERE id = ?",
                    (workout_id,),
                )

    def update_plan_workout(self, workout_id: int, updates: Dict[str, Any]) -> None:
        allowed = {
            "workout_type",
            "title",
            "description",
            "target_distance_km",
            "target_duration_min",
            "target_pace_range",
            "target_hr_zone",
            "intensity",
            "adapted_reason",
        }
        fields = [k for k in updates.keys() if k in allowed]
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = [updates[k] for k in fields] + [workout_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE plan_workouts SET {set_clause} WHERE id = ?", values)

    def auto_link_workouts_to_activities(self, goal_id: int) -> int:
        """Automatically marks planned workouts as completed if a matching real run exists on that date."""
        linked = 0
        with self.connect() as conn:
            workouts = conn.execute(
                "SELECT id, scheduled_date, workout_type FROM plan_workouts WHERE goal_id = ? AND completed = 0 AND workout_type != 'rest'",
                (goal_id,),
            ).fetchall()
            for w in workouts:
                act = conn.execute(
                    "SELECT id FROM activities WHERE date_key = ? AND is_demo = 0 AND LOWER(sport_type) LIKE '%run%' LIMIT 1",
                    (w["scheduled_date"],),
                ).fetchone()
                if act:
                    conn.execute(
                        "UPDATE plan_workouts SET completed = 1, linked_activity_id = ? WHERE id = ?",
                        (act["id"], w["id"]),
                    )
                    linked += 1
        return linked

    def update_goal_ai_summary(self, goal_id: int, summary: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE race_goals SET ai_summary = ? WHERE id = ?", (summary, goal_id))

    # ---------- Calippo Chat History ----------
    def get_chat_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, ai_powered, created_at FROM chat_messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def add_chat_message(self, role: str, content: str, ai_powered: bool = False) -> Dict[str, Any]:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = "INSERT INTO chat_messages (role, content, ai_powered, created_at) VALUES (?, ?, ?, ?)"
        params = (role, content, 1 if ai_powered else 0, ts)
        with self.connect() as conn:
            if self.is_pg:
                row = conn.execute(sql + " RETURNING id", params).fetchone()
                msg_id = int(row["id"])
            else:
                cur = conn.execute(sql, params)
                msg_id = int(cur.lastrowid)
            return {
                "id": msg_id,
                "role": role,
                "content": content,
                "ai_powered": 1 if ai_powered else 0,
                "created_at": ts,
            }

    def clear_chat_messages(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chat_messages")

    # ---------- Full Cloud Migration Export / Import ----------
    def export_full_backup(self) -> Dict[str, Any]:
        with self.connect() as conn:
            settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
            activities = [dict(r) for r in conn.execute("SELECT * FROM activities WHERE is_demo = 0 ORDER BY start_date ASC").fetchall()]
            garmin_daily = [dict(r) for r in conn.execute("SELECT * FROM garmin_daily WHERE is_demo = 0 ORDER BY date_key ASC").fetchall()]
            garmin_snapshots = [dict(r) for r in conn.execute("SELECT key, data_json, updated_at FROM garmin_snapshots").fetchall()]
            chat_messages = [dict(r) for r in conn.execute("SELECT role, content, ai_powered, created_at FROM chat_messages ORDER BY id ASC").fetchall()]
            goals = []
            for g in conn.execute("SELECT * FROM race_goals ORDER BY id ASC").fetchall():
                gd = dict(g)
                gd["workouts"] = [
                    dict(w)
                    for w in conn.execute("SELECT * FROM plan_workouts WHERE goal_id = ? ORDER BY scheduled_date ASC, id ASC", (gd["id"],)).fetchall()
                ]
                goals.append(gd)
            return {
                "version": 1,
                "exported_at": datetime.utcnow().isoformat(),
                "settings": settings,
                "activities": activities,
                "garmin_daily": garmin_daily,
                "garmin_snapshots": garmin_snapshots,
                "race_goals": goals,
                "chat_messages": chat_messages,
            }

    def import_full_backup(self, payload: Dict[str, Any]) -> Dict[str, int]:
        counts = {"settings": 0, "activities": 0, "garmin_days": 0, "snapshots": 0, "plans": 0, "messages": 0}
        if isinstance(payload.get("settings"), dict):
            self.update_settings(payload["settings"])
            counts["settings"] = len(payload["settings"])

        for act in payload.get("activities") or []:
            self.upsert_activity(act)
            counts["activities"] += 1

        for gd in payload.get("garmin_daily") or []:
            self.upsert_garmin_daily(gd)
            counts["garmin_days"] += 1

        for snap in payload.get("garmin_snapshots") or []:
            if snap.get("key") and snap.get("data_json") is not None:
                try:
                    parsed = json.loads(snap["data_json"]) if isinstance(snap["data_json"], str) else snap["data_json"]
                    self.save_garmin_snapshot(snap["key"], parsed)
                    counts["snapshots"] += 1
                except Exception:
                    pass

        goals = payload.get("race_goals") or []
        if goals:
            with self.connect() as conn:
                conn.execute("DELETE FROM race_goals")
            for g in goals:
                workouts = g.get("workouts") or []
                paces = g.get("paces")
                if paces is None and g.get("paces_json"):
                    try:
                        paces = json.loads(g["paces_json"])
                    except Exception:
                        paces = {}
                new_goal_id = self.create_race_goal({**g, "paces": paces or {}}, workouts)
                # Restore completed flags & linked activities if present in backup
                with self.connect() as conn:
                    inserted = conn.execute(
                        "SELECT id FROM plan_workouts WHERE goal_id = ? ORDER BY scheduled_date ASC, id ASC",
                        (new_goal_id,),
                    ).fetchall()
                    for row_w, orig_w in zip(inserted, workouts):
                        if orig_w.get("completed") or orig_w.get("adapted_reason") or orig_w.get("linked_activity_id"):
                            conn.execute(
                                "UPDATE plan_workouts SET completed = ?, linked_activity_id = ?, adapted_reason = ? WHERE id = ?",
                                (
                                    1 if orig_w.get("completed") else 0,
                                    orig_w.get("linked_activity_id"),
                                    orig_w.get("adapted_reason") or "",
                                    row_w["id"],
                                ),
                            )
                counts["plans"] += 1

        msgs = payload.get("chat_messages") or []
        if msgs:
            self.clear_chat_messages()
            for m in msgs:
                if m.get("role") and m.get("content"):
                    self.add_chat_message(m["role"], m["content"], bool(m.get("ai_powered")))
                    counts["messages"] += 1

        return counts

    def has_any_data(self) -> Dict[str, int]:
        with self.connect() as conn:
            a = conn.execute("SELECT COUNT(*) as c FROM activities").fetchone()["c"]
            g = conn.execute("SELECT COUNT(*) as c FROM garmin_daily").fetchone()["c"]
            p = conn.execute("SELECT COUNT(*) as c FROM race_goals").fetchone()["c"]
            return {"activities": a, "garmin_days": g, "race_goals": p}


db = Database()
