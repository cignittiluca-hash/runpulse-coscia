"""Pydantic models for RunPulse (Garmin + Whoop Edition)."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    athlete_name: Optional[str] = None
    max_hr: Optional[int] = Field(None, ge=120, le=230)
    resting_hr: Optional[int] = Field(None, ge=30, le=110)
    threshold_pace_sec: Optional[int] = Field(None, ge=150, le=600)
    weekly_goal_km: Optional[float] = Field(None, ge=5, le=250)
    auto_sync_enabled: Optional[bool] = None
    auto_sync_interval_min: Optional[int] = Field(None, ge=5, le=1440)
    strava_client_id: Optional[str] = None
    strava_client_secret: Optional[str] = None
    whoop_client_id: Optional[str] = None
    whoop_client_secret: Optional[str] = None
    whoop_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    app_password: Optional[str] = None


class AuthLoginRequest(BaseModel):
    password: str


class GarminLoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: Optional[str] = None


class GarminMfaRequest(BaseModel):
    mfa_code: str


class RaceGoalCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    distance_type: str = Field(..., pattern="^(5k|10k|half_marathon|marathon)$")
    race_date: str  # YYYY-MM-DD
    target_time_sec: Optional[int] = Field(None, ge=600, le=36000)
    days_per_week: int = Field(4, ge=3, le=6)
    long_run_day: int = Field(6, ge=0, le=6)  # 0=Mon .. 6=Sun
    current_weekly_km: Optional[float] = Field(None, ge=5, le=200)
    notes: Optional[str] = ""
    use_ai: bool = True


class WorkoutToggleRequest(BaseModel):
    completed: bool
    linked_activity_id: Optional[str] = None


class CoachQuestionRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)


class SyncRequest(BaseModel):
    days: int = Field(14, ge=0, le=3650)
    fetch_details: bool = True
    force_full: bool = False
    all_history: bool = False


# Whoop 4.0 Models
class WhoopManualEntry(BaseModel):
    date: str = Field(..., description="Data nel formato YYYY-MM-DD")
    recovery_score: Optional[int] = Field(None, ge=0, le=100, description="Punteggio Whoop Recovery 0-100%")
    day_strain: Optional[float] = Field(None, ge=0.0, le=21.0, description="Whoop Day Strain da 0.0 a 21.0")
    hrv_rmssd: Optional[float] = Field(None, ge=0.0, le=300.0, description="HRV RMSSD in ms")
    resting_hr: Optional[int] = Field(None, ge=30, le=140, description="Frequenza cardiaca a riposo")
    sleep_performance_pct: Optional[float] = Field(None, ge=0.0, le=150.0, description="Performance del sonno %")
    sleep_debt_minutes: Optional[int] = Field(None, ge=0, le=600, description="Debito di sonno in minuti")
    sleep_hours: Optional[float] = Field(None, ge=0.0, le=24.0, description="Ore totali di sonno")
    spo2_percentage: Optional[float] = Field(None, ge=70.0, le=100.0, description="Saturazione ossigeno SpO2")
    skin_temp_celsius: Optional[float] = Field(None, description="Deviazione o temperatura cutanea")


class WhoopSyncRequest(BaseModel):
    auth_token: Optional[str] = None
    date: Optional[str] = None
    recovery_score: Optional[int] = None
    day_strain: Optional[float] = None
    hrv_rmssd: Optional[float] = None
    resting_hr: Optional[int] = None
    sleep_performance_pct: Optional[float] = None
    sleep_debt_minutes: Optional[int] = None
    sleep_hours: Optional[float] = None
