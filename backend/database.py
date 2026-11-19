"""Dual-engine database layer for RunPulse Apple Watch Edition (SQLite locally, PostgreSQL on cloud)."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DATABASE_URL, DB_PATH, DEFAULT_SETTINGS

_NAMED_PARAM_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def _translate_sql_for_postgres(sql: str, params: Any) -> Tuple[str, Any]:
    """Converts SQLite-style ? / :name placeholders & minor syntax to PostgreSQL psycopg3 format."""
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
    """Thin wrapper giving sqlite3 and psycopg3 an identical .execute(sql, params) interface."""

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

                CREATE TABLE IF NOT EXISTS wellness_daily (
                    date_key TEXT PRIMARY KEY,
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
                    sleep_awake_sec INTEGER,
                    training_readiness INTEGER,
                    vo2_max REAL,
                    steps INTEGER,
                    active_calories INTEGER,
                    total_calories INTEGER,
                    exercise_min INTEGER,
                    stand_hours INTEGER,
                    spo2_avg REAL,
                    respiration_avg REAL,
                    wrist_temperature_c REAL,
                    walking_hr_avg REAL,
                    source TEXT DEFAULT 'apple_health',
                    is_demo INTEGER DEFAULT 0,
                    raw_json TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS wellness_snapshots (
                    key TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL DEFAULT '{}',
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
                """
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
            w = conn.execute("DELETE FROM wellness_daily WHERE is_demo = 1").rowcount
            return {"activities_deleted": a, "wellness_days_deleted": w}

    # ---------- Apple Health / Wellness Daily ----------
    def upsert_wellness_daily(self, record: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO wellness_daily (
                    date_key, hrv_avg, hrv_baseline_low, hrv_baseline_high, hrv_status,
                    resting_hr, sleep_seconds, sleep_score, sleep_deep_sec,
                    sleep_rem_sec, sleep_light_sec, sleep_awake_sec,
                    training_readiness, vo2_max, steps, active_calories, total_calories,
                    exercise_min, stand_hours, spo2_avg, respiration_avg,
                    wrist_temperature_c, walking_hr_avg, source,
                    is_demo, raw_json, updated_at
                ) VALUES (
                    :date_key, :hrv_avg, :hrv_baseline_low, :hrv_baseline_high, :hrv_status,
                    :resting_hr, :sleep_seconds, :sleep_score, :sleep_deep_sec,
                    :sleep_rem_sec, :sleep_light_sec, :sleep_awake_sec,
                    :training_readiness, :vo2_max, :steps, :active_calories, :total_calories,
                    :exercise_min, :stand_hours, :spo2_avg, :respiration_avg,
                    :wrist_temperature_c, :walking_hr_avg, :source,
                    :is_demo, :raw_json, :updated_at
                )
                ON CONFLICT(date_key) DO UPDATE SET
                    hrv_avg = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_avg ELSE COALESCE(excluded.hrv_avg, wellness_daily.hrv_avg) END,
                    hrv_baseline_low = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_baseline_low ELSE COALESCE(excluded.hrv_baseline_low, wellness_daily.hrv_baseline_low) END,
                    hrv_baseline_high = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_baseline_high ELSE COALESCE(excluded.hrv_baseline_high, wellness_daily.hrv_baseline_high) END,
                    hrv_status = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.hrv_status ELSE COALESCE(excluded.hrv_status, wellness_daily.hrv_status) END,
                    resting_hr = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.resting_hr ELSE COALESCE(excluded.resting_hr, wellness_daily.resting_hr) END,
                    sleep_seconds = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_seconds ELSE COALESCE(excluded.sleep_seconds, wellness_daily.sleep_seconds) END,
                    sleep_score = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_score ELSE COALESCE(excluded.sleep_score, wellness_daily.sleep_score) END,
                    sleep_deep_sec = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_deep_sec ELSE COALESCE(excluded.sleep_deep_sec, wellness_daily.sleep_deep_sec) END,
                    sleep_rem_sec = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_rem_sec ELSE COALESCE(excluded.sleep_rem_sec, wellness_daily.sleep_rem_sec) END,
                    sleep_light_sec = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_light_sec ELSE COALESCE(excluded.sleep_light_sec, wellness_daily.sleep_light_sec) END,
                    sleep_awake_sec = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.sleep_awake_sec ELSE COALESCE(excluded.sleep_awake_sec, wellness_daily.sleep_awake_sec) END,
                    training_readiness = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.training_readiness ELSE COALESCE(excluded.training_readiness, wellness_daily.training_readiness) END,
                    vo2_max = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.vo2_max ELSE COALESCE(excluded.vo2_max, wellness_daily.vo2_max) END,
                    steps = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.steps ELSE COALESCE(excluded.steps, wellness_daily.steps) END,
                    active_calories = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.active_calories ELSE COALESCE(excluded.active_calories, wellness_daily.active_calories) END,
                    total_calories = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.total_calories ELSE COALESCE(excluded.total_calories, wellness_daily.total_calories) END,
                    exercise_min = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.exercise_min ELSE COALESCE(excluded.exercise_min, wellness_daily.exercise_min) END,
                    stand_hours = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.stand_hours ELSE COALESCE(excluded.stand_hours, wellness_daily.stand_hours) END,
                    spo2_avg = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.spo2_avg ELSE COALESCE(excluded.spo2_avg, wellness_daily.spo2_avg) END,
                    respiration_avg = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.respiration_avg ELSE COALESCE(excluded.respiration_avg, wellness_daily.respiration_avg) END,
                    wrist_temperature_c = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.wrist_temperature_c ELSE COALESCE(excluded.wrist_temperature_c, wellness_daily.wrist_temperature_c) END,
                    walking_hr_avg = CASE WHEN wellness_daily.is_demo = 1 AND excluded.is_demo = 0 THEN excluded.walking_hr_avg ELSE COALESCE(excluded.walking_hr_avg, wellness_daily.walking_hr_avg) END,
                    source = excluded.source,
                    is_demo = excluded.is_demo,
                    updated_at = excluded.updated_at
                WHERE wellness_daily.is_demo = 1 OR excluded.is_demo = 0
                """,
                {
                    "date_key": record["date_key"],
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
                    "sleep_awake_sec": record.get("sleep_awake_sec"),
                    "training_readiness": record.get("training_readiness"),
                    "vo2_max": record.get("vo2_max"),
                    "steps": record.get("steps"),
                    "active_calories": record.get("active_calories"),
                    "total_calories": record.get("total_calories"),
                    "exercise_min": record.get("exercise_min"),
                    "stand_hours": record.get("stand_hours"),
                    "spo2_avg": record.get("spo2_avg"),
                    "respiration_avg": record.get("respiration_avg"),
                    "wrist_temperature_c": record.get("wrist_temperature_c"),
                    "walking_hr_avg": record.get("walking_hr_avg"),
                    "source": record.get("source", "apple_health"),
                    "is_demo": int(record.get("is_demo") or 0),
                    "raw_json": json.dumps(record.get("raw", {})) if isinstance(record.get("raw"), dict) else "{}",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

    def save_wellness_snapshot(self, key: str, data: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO wellness_snapshots (key, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                (key, json.dumps(data, ensure_ascii=False, default=str), datetime.utcnow().isoformat()),
            )

    def get_wellness_snapshot(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT data_json FROM wellness_snapshots WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["data_json"])
            except Exception:
                return default

    def get_all_wellness_snapshots(self) -> Dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, data_json, updated_at FROM wellness_snapshots").fetchall()
            out: Dict[str, Any] = {}
            for r in rows:
                try:
                    out[r["key"]] = json.loads(r["data_json"])
                except Exception:
                    out[r["key"]] = None
            return out

    def get_wellness_daily(self, days: int = 30) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM wellness_daily ORDER BY date_key DESC LIMIT ?",
                (days,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d.pop("raw_json", None)
                result.append(d)
            return list(reversed(result))

    def get_latest_wellness(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM wellness_daily ORDER BY date_key DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d.pop("raw_json", None)
            return d

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
            wellness_daily = [dict(r) for r in conn.execute("SELECT * FROM wellness_daily WHERE is_demo = 0 ORDER BY date_key ASC").fetchall()]
            snapshots = [dict(r) for r in conn.execute("SELECT key, data_json, updated_at FROM wellness_snapshots").fetchall()]
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
                "app_edition": "apple_watch",
                "exported_at": datetime.utcnow().isoformat(),
                "settings": settings,
                "activities": activities,
                "wellness_daily": wellness_daily,
                "wellness_snapshots": snapshots,
                "race_goals": goals,
                "chat_messages": chat_messages,
            }

    def import_full_backup(self, payload: Dict[str, Any]) -> Dict[str, int]:
        counts = {"settings": 0, "activities": 0, "wellness_days": 0, "snapshots": 0, "plans": 0, "messages": 0}
        if isinstance(payload.get("settings"), dict):
            self.update_settings(payload["settings"])
            counts["settings"] = len(payload["settings"])

        for act in payload.get("activities") or []:
            self.upsert_activity(act)
            counts["activities"] += 1

        for wd in payload.get("wellness_daily") or payload.get("garmin_daily") or []:
            self.upsert_wellness_daily(wd)
            counts["wellness_days"] += 1

        for snap in payload.get("wellness_snapshots") or payload.get("garmin_snapshots") or []:
            if snap.get("key") and snap.get("data_json") is not None:
                try:
                    parsed = json.loads(snap["data_json"]) if isinstance(snap["data_json"], str) else snap["data_json"]
                    self.save_wellness_snapshot(snap["key"], parsed)
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
            w = conn.execute("SELECT COUNT(*) as c FROM wellness_daily").fetchone()["c"]
            p = conn.execute("SELECT COUNT(*) as c FROM race_goals").fetchone()["c"]
            return {"activities": a, "wellness_days": w, "race_goals": p}


db = Database()
