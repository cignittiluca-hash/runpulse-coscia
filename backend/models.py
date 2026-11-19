from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class SettingsUpdate(BaseModel):
    athlete_name: Optional[str] = None
    max_hr: Optional[int] = None
    resting_hr: Optional[int] = None
    threshold_pace_sec: Optional[int] = None
    weekly_goal_km: Optional[float] = None
    strava_client_id: Optional[str] = None
    strava_client_secret: Optional[str] = None
    apple_health_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    auto_sync_enabled: Optional[bool] = None
    auto_sync_interval_min: Optional[int] = None
    app_password: Optional[str] = None


class SyncRequest(BaseModel):
    days: int = Field(14, ge=1, le=90)


class WorkoutToggleRequest(BaseModel):
    completed: bool
    linked_activity_id: Optional[str] = None


class RaceGoalCreate(BaseModel):
    name: str = Field(..., min_length=2)
    distance_type: str = Field(..., pattern=r"^(5k|10k|half_marathon|marathon)$")
    race_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    target_time_sec: int = Field(..., gt=600)
    days_per_week: int = Field(4, ge=3, le=6)
    long_run_day: int = Field(6, ge=0, le=6)
    current_weekly_km: float = Field(35.0, ge=10.0, le=160.0)
    current_vdot: Optional[float] = None
    notes: str = ""


class CoachQuestionRequest(BaseModel):
    question: str = Field(..., min_length=2)


class AppleHealthSyncRequest(BaseModel):
    """Payload accettato da iOS Shortcut ('Comandi Rapidi') o da webhook Health Auto Export."""
    date: Optional[str] = None  # YYYY-MM-DD
    hrv_sdnn_ms: Optional[float] = None
    resting_hr: Optional[int] = None
    sleep_hours: Optional[float] = None
    sleep_seconds: Optional[int] = None
    sleep_deep_hours: Optional[float] = None
    sleep_deep_sec: Optional[int] = None
    sleep_rem_hours: Optional[float] = None
    sleep_rem_sec: Optional[int] = None
    sleep_core_hours: Optional[float] = None
    sleep_light_sec: Optional[int] = None
    sleep_awake_hours: Optional[float] = None
    sleep_awake_sec: Optional[int] = None
    sleep_score: Optional[int] = None
    vo2_max: Optional[float] = None  # Apple Watch Cardio Fitness
    steps: Optional[int] = None
    active_calories: Optional[int] = None  # Move ring
    total_calories: Optional[int] = None
    exercise_min: Optional[int] = None  # Exercise ring
    stand_hours: Optional[int] = None  # Stand ring
    spo2_pct: Optional[float] = None
    respiration_rate: Optional[float] = None
    wrist_temperature_c: Optional[float] = None
    walking_hr: Optional[float] = None
    auth_token: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


class AppleHealthManualEntry(BaseModel):
    """Inserimento o correzione veloce dei dati Apple Health da interfaccia web."""
    date_key: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    hrv_avg: Optional[float] = None
    resting_hr: Optional[int] = None
    sleep_hours: Optional[float] = None
    sleep_deep_hours: Optional[float] = None
    sleep_rem_hours: Optional[float] = None
    vo2_max: Optional[float] = None
    steps: Optional[int] = None
    active_calories: Optional[int] = None
    exercise_min: Optional[int] = None
    stand_hours: Optional[int] = None
    spo2_avg: Optional[float] = None
    respiration_avg: Optional[float] = None
