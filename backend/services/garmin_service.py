"""Real Garmin Connect integration (Full Ecosystem: Stress, Body Battery, HRV, Sleep, SpO2, Training Status, Running Dynamics, PRs, Gear)."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import Garmin

from backend.config import GARMIN_TOKEN_DIR
from backend.database import db


_HRV_STATUS_IT = {
    "BALANCED": "Bilanciata",
    "UNBALANCED": "Sbilanciata",
    "LOW": "Bassa",
    "POOR": "Scarsa",
    "HIGH": "Alta",
    "NONE": "In calibrazione",
}

_TRAINING_STATUS_IT = {
    "PRODUCTIVE": "Produttivo",
    "PEAKING": "Picco di Forma",
    "RECOVERY": "Recupero",
    "MAINTAINING": "Mantenimento",
    "UNPRODUCTIVE": "Non Produttivo",
    "OVERREACHING": "Sovraccarico",
    "DETRAINING": "Detraining",
    "STRAINED": "Affaticato",
    "NO_STATUS": "In calibrazione",
    "PAUSED": "In pausa",
}

_LOAD_FOCUS_IT = {
    "ANAEROBIC_SHORTAGE": "Carenza Anaerobica",
    "HIGH_AEROBIC_SHORTAGE": "Carenza Aerobico Alto",
    "LOW_AEROBIC_SHORTAGE": "Carenza Aerobico Basso",
    "LOW_AEROBIC_OVERAGE": "Eccesso Aerobico Basso",
    "HIGH_AEROBIC_OVERAGE": "Eccesso Aerobico Alto",
    "ANAEROBIC_OVERAGE": "Eccesso Anaerobico",
    "OPTIMAL": "Bilanciato / Ottimale",
    "BALANCED": "Bilanciato",
}


def _translate_enum(raw: Optional[str], mapping: Dict[str, str]) -> Optional[str]:
    if not raw:
        return None
    up = str(raw).upper().strip()
    if up in mapping:
        return mapping[up]
    for prefix, label in mapping.items():
        if up.startswith(prefix):
            return label
    return raw.replace("_", " ").title()


_garmin_sync_lock = threading.Lock()
_mfa_lock = threading.Lock()
_current_mfa_attempt: Optional["_MfaAttempt"] = None


class _MfaAttempt:
    """Isolated per-login MFA attempt (prevents overlapping login calls from colliding on shared Events)."""
    def __init__(self) -> None:
        self.mfa_requested = threading.Event()
        self.mfa_provided = threading.Event()
        self.login_done = threading.Event()
        self.mfa_code: Optional[str] = None
        self.error: Optional[str] = None
        self.display_name: Optional[str] = None


def _persist_garmin_tokens_to_db() -> None:
    """Mirrors Garmin OAuth1/OAuth2 token JSON files into DB settings so cloud restarts keep Garmin connected."""
    o1 = GARMIN_TOKEN_DIR / "oauth1_token.json"
    o2 = GARMIN_TOKEN_DIR / "oauth2_token.json"
    updates: Dict[str, str] = {}
    if o1.exists():
        updates["garmin_oauth1_json"] = o1.read_text(encoding="utf-8")
    if o2.exists():
        updates["garmin_oauth2_json"] = o2.read_text(encoding="utf-8")
    if updates:
        db.update_settings(updates)


def _restore_garmin_tokens_from_db() -> bool:
    """Restores Garmin OAuth token files from DB onto ephemeral cloud container disk if missing."""
    o1 = GARMIN_TOKEN_DIR / "oauth1_token.json"
    o2 = GARMIN_TOKEN_DIR / "oauth2_token.json"
    if o1.exists() and o2.exists():
        return True
    s = db.get_settings()
    t1 = s.get("garmin_oauth1_json", "").strip()
    t2 = s.get("garmin_oauth2_json", "").strip()
    if t1 and t2:
        GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        o1.write_text(t1, encoding="utf-8")
        o2.write_text(t2, encoding="utf-8")
        return True
    return False


def has_garmin_tokens() -> bool:
    if (GARMIN_TOKEN_DIR / "oauth1_token.json").exists() and (GARMIN_TOKEN_DIR / "oauth2_token.json").exists():
        return True
    return _restore_garmin_tokens_from_db()


def is_garmin_connected() -> bool:
    return has_garmin_tokens() and db.get_setting("garmin_connected") == "true"


def disconnect_garmin() -> None:
    if GARMIN_TOKEN_DIR.exists():
        shutil.rmtree(GARMIN_TOKEN_DIR, ignore_errors=True)
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    db.update_settings(
        {
            "garmin_connected": "false",
            "garmin_display_name": "",
            "garmin_oauth1_json": "",
            "garmin_oauth2_json": "",
        }
    )


def _load_authenticated_client() -> Garmin:
    if not has_garmin_tokens():
        raise ValueError("Garmin Connect non è ancora collegato. Accedi dalle Impostazioni.")
    client = Garmin()
    client.login(tokenstore=str(GARMIN_TOKEN_DIR))
    return client


def login_garmin(email: str, password: str, mfa_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Authenticates with Garmin Connect via garth and dumps persistent OAuth tokens
    to `data/garmin_tokens/`. Supports interactive MFA with isolated per-attempt state.
    """
    global _current_mfa_attempt
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    attempt = _MfaAttempt()
    if mfa_code:
        attempt.mfa_code = mfa_code.strip()
        attempt.mfa_provided.set()
    with _mfa_lock:
        _current_mfa_attempt = attempt

    def prompt_mfa() -> str:
        attempt.mfa_requested.set()
        if not attempt.mfa_provided.wait(timeout=180):
            raise TimeoutError("Tempo scaduto per l'inserimento del codice MFA Garmin.")
        return attempt.mfa_code or ""

    def worker() -> None:
        try:
            client = Garmin(email=email.strip(), password=password)
            if hasattr(client, "garth"):
                client.garth.login(email.strip(), password, prompt_mfa=prompt_mfa)
                with _garmin_sync_lock:
                    client.garth.dump(str(GARMIN_TOKEN_DIR))
                    _persist_garmin_tokens_to_db()
                profile = getattr(client.garth, "profile", {}) or {}
                display_name = profile.get("fullName") or profile.get("displayName") or email.strip()
            else:
                client.prompt_mfa = prompt_mfa
                client.login()
                with _garmin_sync_lock:
                    if hasattr(client, "dump"):
                        client.dump(str(GARMIN_TOKEN_DIR))
                    _persist_garmin_tokens_to_db()
                display_name = (
                    getattr(client, "full_name", None)
                    or getattr(client, "display_name", None)
                    or email.strip()
                )
            attempt.display_name = display_name
            db.update_settings(
                {
                    "garmin_email": email.strip(),
                    "garmin_connected": "true",
                    "garmin_display_name": display_name,
                }
            )
        except Exception as exc:
            attempt.error = str(exc)
        finally:
            attempt.login_done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    deadline = datetime.utcnow() + timedelta(seconds=25)
    while datetime.utcnow() < deadline:
        if attempt.login_done.is_set():
            break
        if attempt.mfa_requested.is_set() and not attempt.mfa_provided.is_set():
            return {
                "status": "mfa_required",
                "message": "Garmin richiede il codice di verifica (MFA/OTP) inviato via email o SMS. Inseriscilo qui sotto.",
            }
        attempt.login_done.wait(timeout=0.25)

    if not attempt.login_done.is_set():
        return {
            "status": "error",
            "message": "Timeout durante il login su Garmin Connect. Riprova tra qualche secondo.",
        }

    if attempt.error:
        raise ValueError(f"Accesso Garmin non riuscito: {attempt.error}")

    return {
        "status": "connected",
        "display_name": attempt.display_name or email.strip(),
        "message": "Account Garmin Connect collegato con successo!",
    }


def submit_garmin_mfa(mfa_code: str) -> Dict[str, Any]:
    with _mfa_lock:
        attempt = _current_mfa_attempt
    if not attempt or not attempt.mfa_requested.is_set() or attempt.login_done.is_set():
        raise ValueError("Nessuna sessione MFA Garmin attiva. Avvia nuovamente il login.")
    attempt.mfa_code = mfa_code.strip()
    attempt.mfa_provided.set()
    finished = attempt.login_done.wait(timeout=25)
    if not finished:
        raise ValueError("Timeout verifica codice MFA Garmin.")
    if attempt.error:
        raise ValueError(f"Verifica MFA Garmin fallita: {attempt.error}")
    return {
        "status": "connected",
        "display_name": attempt.display_name or db.get_setting("garmin_email"),
        "message": "Autenticazione MFA completata! Garmin Connect collegato.",
    }


def _safe_call(fn, *args, retries: int = 2, **kwargs) -> Any:
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.4)
    return None


def _parse_garmin_day(client: Garmin, cdate: str, fetch_extended: bool = True) -> Tuple[Dict[str, Any], Optional[int]]:
    record: Dict[str, Any] = {"date_key": cdate, "is_demo": 0}
    user_profile_id: Optional[int] = None

    # 1. Daily summary stats (stress, body battery, resting HR, steps, calories, intensity mins, floors)
    stats = _safe_call(client.get_stats, cdate) or {}
    if isinstance(stats, dict):
        if stats.get("userProfileId"):
            try:
                user_profile_id = int(stats["userProfileId"])
            except Exception:
                pass
        if stats.get("averageStressLevel") is not None and stats.get("averageStressLevel") >= 0:
            record["stress_avg"] = int(stats["averageStressLevel"])
        if stats.get("maxStressLevel") is not None and stats.get("maxStressLevel") >= 0:
            record["stress_max"] = int(stats["maxStressLevel"])
        for src_k, dst_k in [
            ("restStressDuration", "stress_rest_min"),
            ("lowStressDuration", "stress_low_min"),
            ("mediumStressDuration", "stress_medium_min"),
            ("highStressDuration", "stress_high_min"),
        ]:
            if stats.get(src_k) is not None:
                record[dst_k] = int(round(float(stats[src_k]) / 60.0))
        if record.get("stress_avg") is not None and record.get("stress_high_min") is None:
            record["stress_high_min"] = 0

        if stats.get("bodyBatteryHighestValue") is not None:
            record["body_battery_max"] = int(stats["bodyBatteryHighestValue"])
        if stats.get("bodyBatteryLowestValue") is not None:
            record["body_battery_min"] = int(stats["bodyBatteryLowestValue"])
        if stats.get("bodyBatteryMostRecentValue") is not None:
            record["body_battery_current"] = int(stats["bodyBatteryMostRecentValue"])
        if stats.get("bodyBatteryChargedValue") is not None:
            record["body_battery_charged"] = int(stats["bodyBatteryChargedValue"])
        if stats.get("bodyBatteryDrainedValue") is not None:
            record["body_battery_drained"] = int(stats["bodyBatteryDrainedValue"])
        if stats.get("restingHeartRate") is not None:
            record["resting_hr"] = int(stats["restingHeartRate"])
        if stats.get("totalSteps") is not None:
            record["steps"] = int(stats["totalSteps"])
        if stats.get("activeKilocalories") is not None:
            record["active_calories"] = int(round(float(stats["activeKilocalories"])))
        if stats.get("totalKilocalories") is not None:
            record["total_calories"] = int(round(float(stats["totalKilocalories"])))
        if stats.get("moderateIntensityMinutes") is not None:
            record["intensity_moderate_min"] = int(stats["moderateIntensityMinutes"])
        if stats.get("vigorousIntensityMinutes") is not None:
            record["intensity_vigorous_min"] = int(stats["vigorousIntensityMinutes"])
        if stats.get("floorsAscended") is not None:
            record["floors_ascended"] = round(float(stats["floorsAscended"]), 1)
        if stats.get("wellnessEndTimeLocal"):
            record["watch_sync_time"] = str(stats["wellnessEndTimeLocal"]).replace("T", " ")[:16]

    # 2. Body Battery real-time array check for today (ensures freshest reading)
    if cdate == date.today().isoformat():
        bb_arr = _safe_call(client.get_body_battery, cdate, retries=1)
        if isinstance(bb_arr, list) and bb_arr and isinstance(bb_arr[0], dict):
            vals = [v[1] for v in (bb_arr[0].get("bodyBatteryValuesArray") or []) if isinstance(v, list) and len(v) >= 2 and v[1] is not None]
            if vals:
                record["body_battery_current"] = int(vals[-1])
                record["body_battery_max"] = max(record.get("body_battery_max") or 0, int(max(vals)))
                record["body_battery_min"] = min(record.get("body_battery_min") or 100, int(min(vals)))

    # 2b. Stress details fallback if missing
    if record.get("stress_avg") is None:
        stress_data = _safe_call(client.get_stress_data, cdate) or {}
        if isinstance(stress_data, dict):
            if stress_data.get("avgStressLevel") is not None and stress_data.get("avgStressLevel") >= 0:
                record["stress_avg"] = int(stress_data["avgStressLevel"])
            if stress_data.get("maxStressLevel") is not None and stress_data.get("maxStressLevel") >= 0:
                record["stress_max"] = int(stress_data["maxStressLevel"])

    # 3. HRV data
    hrv_data = _safe_call(client.get_hrv_data, cdate) or {}
    if isinstance(hrv_data, dict):
        summary = hrv_data.get("hrvSummary") or hrv_data
        if isinstance(summary, dict):
            val = summary.get("lastNightAvg") or summary.get("weeklyAvg")
            if val is not None:
                record["hrv_avg"] = float(val)
            baseline = summary.get("baseline") or {}
            if isinstance(baseline, dict):
                if baseline.get("balancedLow") is not None:
                    record["hrv_baseline_low"] = float(baseline["balancedLow"])
                if baseline.get("balancedUpper") is not None:
                    record["hrv_baseline_high"] = float(baseline["balancedUpper"])
            if summary.get("status"):
                record["hrv_status"] = _translate_enum(str(summary["status"]), _HRV_STATUS_IT)

    # 4. Sleep data
    sleep_data = _safe_call(client.get_sleep_data, cdate) or {}
    if isinstance(sleep_data, dict):
        dto = sleep_data.get("dailySleepDTO") or sleep_data
        if isinstance(dto, dict):
            if dto.get("sleepTimeSeconds"):
                record["sleep_seconds"] = int(dto["sleepTimeSeconds"])
            if dto.get("deepSleepSeconds") is not None:
                record["sleep_deep_sec"] = int(dto["deepSleepSeconds"])
            if dto.get("remSleepSeconds") is not None:
                record["sleep_rem_sec"] = int(dto["remSleepSeconds"])
            if dto.get("lightSleepSeconds") is not None:
                record["sleep_light_sec"] = int(dto["lightSleepSeconds"])
            if dto.get("averageSpO2Value") is not None:
                record["spo2_avg"] = round(float(dto["averageSpO2Value"]), 1)
            if dto.get("lowestSpO2Value") is not None:
                record["spo2_min"] = round(float(dto["lowestSpO2Value"]), 1)
            if dto.get("averageRespirationValue") is not None:
                record["respiration_sleep"] = round(float(dto["averageRespirationValue"]), 1)
            scores = dto.get("sleepScores") or {}
            overall = scores.get("overall") if isinstance(scores, dict) else None
            if isinstance(overall, dict) and overall.get("value") is not None:
                record["sleep_score"] = int(overall["value"])

    # 5. Training readiness + recovery time (Garmin returns recoveryTime in MINUTES -> convert to HOURS!)
    readiness = _safe_call(client.get_training_readiness, cdate)
    tr_item = readiness[0] if (isinstance(readiness, list) and readiness) else (readiness if isinstance(readiness, dict) else None)
    if isinstance(tr_item, dict):
        if tr_item.get("score") is not None:
            record["training_readiness"] = int(tr_item["score"])
        if tr_item.get("recoveryTime") is not None:
            record["recovery_time_hours"] = round(float(tr_item["recoveryTime"]) / 60.0, 2)

    # 6. VO2 Max (fetch max metrics)
    max_metrics = _safe_call(client.get_max_metrics, cdate)
    if isinstance(max_metrics, list) and max_metrics:
        generic = (max_metrics[0] or {}).get("generic") or {}
        if generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue"):
            record["vo2_max"] = float(generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue"))
    elif isinstance(max_metrics, dict):
        generic = max_metrics.get("generic") or {}
        if generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue"):
            record["vo2_max"] = float(generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue"))

    # 7. Extended daily biometrics (SpO2, Respiration, Hydration)
    if fetch_extended:
        if record.get("spo2_avg") is None:
            spo2 = _safe_call(client.get_spo2_data, cdate, retries=1)
            if isinstance(spo2, dict):
                if spo2.get("averageSpO2") is not None:
                    record["spo2_avg"] = round(float(spo2["averageSpO2"]), 1)
                if spo2.get("lowestSpO2") is not None:
                    record["spo2_min"] = round(float(spo2["lowestSpO2"]), 1)

        resp_data = _safe_call(client.get_respiration_data, cdate, retries=1)
        if isinstance(resp_data, dict):
            if resp_data.get("avgWakingRespirationValue") is not None:
                record["respiration_avg"] = round(float(resp_data["avgWakingRespirationValue"]), 1)
            if record.get("respiration_sleep") is None and resp_data.get("avgSleepRespirationValue") is not None:
                record["respiration_sleep"] = round(float(resp_data["avgSleepRespirationValue"]), 1)

        hyd = _safe_call(client.get_hydration_data, cdate, retries=1)
        if isinstance(hyd, dict) and hyd.get("valueInML") is not None and float(hyd["valueInML"]) > 0:
            record["hydration_ml"] = round(float(hyd["valueInML"]), 0)

    return record, user_profile_id


def _sync_garmin_account_wide(client: Garmin, today_str: str, profile_num: Optional[int] = None) -> Dict[str, Any]:
    """Pulls full Garmin ecosystem data: Training Status, Race Predictions, Endurance/Hill Score, PRs, Body Comp, Gear, Devices, and Running Dynamics."""
    pulled: Dict[str, Any] = {}

    # 1. Training Status & Load Focus (fallback to yesterday if midnight day is not populated yet)
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    parsed_ts: Dict[str, Any] = {}
    for probe_date in (today_str, yesterday_str):
        t_status = _safe_call(client.get_training_status, probe_date)
        if not isinstance(t_status, dict) or not t_status:
            continue
        latest_ts = t_status.get("mostRecentTrainingStatus") or {}
        latest_map = latest_ts.get("latestTrainingStatusData") or {}
        status_entry = next(iter(latest_map.values()), {}) if isinstance(latest_map, dict) and latest_map else {}
        load_bal = (t_status.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap") or {}
        load_entry = next(iter(load_bal.values()), {}) if isinstance(load_bal, dict) and load_bal else {}
        acute_dto = status_entry.get("acuteTrainingLoadDTO") or {}

        acute_l = acute_dto.get("dailyTrainingLoadAcute")
        chronic_l = acute_dto.get("dailyTrainingLoadChronic")
        acwr_r = acute_dto.get("dailyAcuteChronicWorkloadRatio")
        if acwr_r is None and acute_l and chronic_l and float(chronic_l) > 0:
            acwr_r = round(float(acute_l) / float(chronic_l), 2)

        # Extract authoritative Garmin VO2 Max from mostRecentVO2Max (Forerunner 265 stores it here!)
        mr_vo2 = (t_status.get("mostRecentVO2Max") or {}).get("generic") or {}
        real_vo2_precise = mr_vo2.get("vo2MaxPreciseValue")
        real_vo2_int = mr_vo2.get("vo2MaxValue")
        real_vo2 = float(real_vo2_int) if real_vo2_int is not None else (float(real_vo2_precise) if real_vo2_precise is not None else None)

        cand = {
            "date": probe_date,
            "status_phrase": _translate_enum(status_entry.get("trainingStatusFeedbackPhrase"), _TRAINING_STATUS_IT),
            "status_code": status_entry.get("trainingStatus"),
            "acute_load": round(float(acute_l)) if acute_l is not None else None,
            "chronic_load": round(float(chronic_l)) if chronic_l is not None else None,
            "acwr_ratio": round(float(acwr_r), 2) if acwr_r is not None else None,
            "acwr_status": _translate_enum(acute_dto.get("acwrStatus"), {"LOW": "Basso", "OPTIMAL": "Ottimale", "HIGH": "Alto", "VERY_HIGH": "Molto Alto"}),
            "load_focus_phrase": _translate_enum(load_entry.get("trainingBalanceFeedbackPhrase"), _LOAD_FOCUS_IT),
            "monthly_load_anaerobic": round(float(load_entry["monthlyLoadAnaerobic"]), 1) if load_entry.get("monthlyLoadAnaerobic") is not None else None,
            "monthly_load_aerobic_high": round(float(load_entry["monthlyLoadAerobicHigh"]), 1) if load_entry.get("monthlyLoadAerobicHigh") is not None else None,
            "monthly_load_aerobic_low": round(float(load_entry["monthlyLoadAerobicLow"]), 1) if load_entry.get("monthlyLoadAerobicLow") is not None else None,
            "monthly_load_anaerobic_target": [load_entry.get("monthlyLoadAnaerobicTargetMin"), load_entry.get("monthlyLoadAnaerobicTargetMax")],
            "monthly_load_aerobic_high_target": [load_entry.get("monthlyLoadAerobicHighTargetMin"), load_entry.get("monthlyLoadAerobicHighTargetMax")],
            "monthly_load_aerobic_low_target": [load_entry.get("monthlyLoadAerobicLowTargetMin"), load_entry.get("monthlyLoadAerobicLowTargetMax")],
            "vo2_max": real_vo2,
            "vo2_max_precise": round(float(real_vo2_precise), 1) if real_vo2_precise is not None else real_vo2,
            "vo2_max_date": mr_vo2.get("calendarDate"),
        }
        if any(cand.get(k) is not None for k in ("status_phrase", "acute_load", "load_focus_phrase", "vo2_max")):
            parsed_ts = cand
            break

    if parsed_ts:
        db.save_garmin_snapshot("training_status", parsed_ts)
        # Write the real Garmin VO2 Max onto the latest existing real garmin_daily row
        if parsed_ts.get("vo2_max") is not None:
            latest_real = db.get_latest_garmin()
            if latest_real and not latest_real.get("is_demo"):
                db.upsert_garmin_daily({"date_key": latest_real["date_key"], "vo2_max": parsed_ts["vo2_max"], "is_demo": 0})
        pulled["training_status"] = True

    # 2. Garmin Native Race Predictions (5K / 10K / HM / Marathon)
    race_pred = _safe_call(client.get_race_predictions)
    if isinstance(race_pred, list) and race_pred:
        race_pred = race_pred[-1]
    if isinstance(race_pred, dict) and any(race_pred.get(k) for k in ("time5K", "time10K", "timeHalfMarathon", "timeMarathon")):
        parsed_pred = {
            "date": race_pred.get("calendarDate") or today_str,
            "time_5k_sec": race_pred.get("time5K"),
            "time_10k_sec": race_pred.get("time10K"),
            "time_half_sec": race_pred.get("timeHalfMarathon"),
            "time_marathon_sec": race_pred.get("timeMarathon"),
        }
        db.save_garmin_snapshot("race_predictions", parsed_pred)
        pulled["race_predictions"] = True

    # 3. Endurance Score & Hill Score
    endurance = _safe_call(client.get_endurance_score, today_str)
    hill = _safe_call(client.get_hill_score, today_str)
    scores_snap: Dict[str, Any] = {}
    if isinstance(endurance, dict) and (endurance.get("overallScore") is not None or endurance.get("avg") is not None):
        scores_snap["endurance_score"] = endurance.get("overallScore") or endurance.get("avg")
        scores_snap["endurance_classification"] = endurance.get("classification")
    if isinstance(hill, dict) and (hill.get("overallScore") is not None or hill.get("strengthScore") is not None):
        scores_snap["hill_score"] = hill.get("overallScore")
        scores_snap["hill_strength"] = hill.get("strengthScore")
        scores_snap["hill_endurance"] = hill.get("enduranceScore")
    if scores_snap:
        db.save_garmin_snapshot("scores", scores_snap)
        pulled["scores"] = True

    # 4. Body Composition / Weight (last 90 days)
    start_90 = (date.today() - timedelta(days=90)).isoformat()
    body = _safe_call(client.get_body_composition, start_90, today_str)
    if isinstance(body, dict):
        tot = body.get("totalAverage") or {}
        wl = body.get("dateWeightList") or []
        latest_w = wl[-1] if isinstance(wl, list) and wl else tot
        if isinstance(latest_w, dict) and latest_w.get("weight"):
            wt_kg = round(float(latest_w["weight"]) / 1000.0, 1) if float(latest_w["weight"]) > 300 else round(float(latest_w["weight"]), 1)
            body_snap = {
                "date": latest_w.get("calendarDate") or today_str,
                "weight_kg": wt_kg,
                "bmi": round(float(latest_w["bmi"]), 1) if latest_w.get("bmi") else None,
                "body_fat_pct": round(float(latest_w["bodyFat"]), 1) if latest_w.get("bodyFat") else None,
                "muscle_mass_kg": round(float(latest_w["muscleMass"]) / 1000.0, 1) if latest_w.get("muscleMass") and float(latest_w["muscleMass"]) > 200 else latest_w.get("muscleMass"),
                "body_water_pct": round(float(latest_w["bodyWater"]), 1) if latest_w.get("bodyWater") else None,
            }
            db.save_garmin_snapshot("body_composition", body_snap)
            pulled["body_composition"] = True

    # 5. Personal Records (PRs)
    prs = _safe_call(client.get_personal_record)
    if isinstance(prs, list) and prs:
        pr_meta = {
            1: ("1K", "time"),
            2: ("1 Miglio", "time"),
            3: ("5K", "time"),
            4: ("10K", "time"),
            5: ("Mezza Maratona", "time"),
            6: ("Maratona", "time"),
            7: ("Corsa più lunga", "distance"),
            12: ("Record Passi Giorno", "steps"),
            13: ("Record Passi Settimana", "steps"),
            14: ("Record Passi Mese", "steps"),
        }
        parsed_prs = []
        for p in prs:
            if not isinstance(p, dict):
                continue
            tid = p.get("typeId")
            if tid not in pr_meta:
                continue
            label, unit = pr_meta[tid]
            parsed_prs.append(
                {
                    "label": label,
                    "type_id": tid,
                    "unit": unit,
                    "value": p.get("value"),
                    "date": str(p.get("actStartDateTimeInGMTFormatted") or p.get("prStartTimeGmtFormatted") or "")[:10],
                    "activity_name": p.get("activityName") or "",
                }
            )
        db.save_garmin_snapshot("personal_records", parsed_prs)
        pulled["personal_records"] = len(parsed_prs)

    # 6. Devices
    devices = _safe_call(client.get_devices)
    if isinstance(devices, list) and devices:
        parsed_devs = [
            {
                "name": d.get("productDisplayName") or d.get("deviceTypeName") or "Garmin",
                "part_number": d.get("partNumber"),
                "software": d.get("currentFirmwareVersion"),
                "active": bool(d.get("activeInd", True)),
            }
            for d in devices
            if isinstance(d, dict)
        ]
        db.save_garmin_snapshot("devices", parsed_devs)
        pulled["devices"] = len(parsed_devs)

    # 7. Gear / Running Shoes with mileage
    if not profile_num:
        try:
            if hasattr(client, "garth") and hasattr(client.garth, "profile"):
                prof = client.garth.profile or {}
                profile_num = prof.get("profileId") or prof.get("userProfileId") or prof.get("id")
            elif hasattr(client, "get_user_profile"):
                prof = client.get_user_profile() or {}
                profile_num = prof.get("profileId") or prof.get("userProfileId") or prof.get("id")
        except Exception:
            pass
    if profile_num:
        gear_list = _safe_call(client.get_gear, profile_num)
        if isinstance(gear_list, list) and gear_list:
            parsed_gear = []
            for g in gear_list:
                if not isinstance(g, dict):
                    continue
                uuid = g.get("uuid")
                stats_g = _safe_call(client.get_gear_stats, uuid) if uuid else {}
                total_dist_m = (stats_g or {}).get("totalDistance") or 0
                max_m = g.get("maximumMeters") or 0
                parsed_gear.append(
                    {
                        "name": g.get("displayName") or f"{g.get('gearMakeName', '')} {g.get('gearModelName', '')}".strip() or "Scarpe",
                        "type": g.get("gearTypeName") or "Shoes",
                        "status": g.get("gearStatusName") or "active",
                        "distance_km": round(float(total_dist_m) / 1000.0, 1),
                        "max_km": round(float(max_m) / 1000.0, 0) if max_m else None,
                        "activities_count": (stats_g or {}).get("totalActivities") or 0,
                    }
                )
            db.save_garmin_snapshot("gear", parsed_gear)
            pulled["gear"] = len(parsed_gear)

    # 8. Recent Garmin Activities with Running Dynamics & Training Effect (Power, GCT, Vertical Osc, Stride, TE)
    g_acts = _safe_call(client.get_activities, 0, 30)
    if isinstance(g_acts, list) and g_acts:
        parsed_acts = []
        for a in g_acts:
            if not isinstance(a, dict):
                continue
            atype = ((a.get("activityType") or {}).get("typeKey") or "").lower()
            dist_m = float(a.get("distance") or 0)
            dur_s = float(a.get("duration") or 0)
            pace_s = (dur_s / (dist_m / 1000.0)) if dist_m > 100 else None
            parsed_acts.append(
                {
                    "activity_id": a.get("activityId"),
                    "date": str(a.get("startTimeLocal") or "")[:10],
                    "name": a.get("activityName") or "Attività Garmin",
                    "type": atype,
                    "distance_km": round(dist_m / 1000.0, 2),
                    "duration_s": int(round(dur_s)),
                    "pace_sec_km": round(pace_s, 1) if pace_s else None,
                    "avg_hr": a.get("averageHR"),
                    "max_hr": a.get("maxHR"),
                    "avg_power_w": round(float(a["avgPower"])) if a.get("avgPower") else None,
                    "norm_power_w": round(float(a["normPower"])) if a.get("normPower") else None,
                    "gct_ms": round(float(a["avgGroundContactTime"]), 1) if a.get("avgGroundContactTime") else None,
                    "vertical_osc_cm": round(float(a["avgVerticalOscillation"]) / 10.0, 2) if a.get("avgVerticalOscillation") and float(a["avgVerticalOscillation"]) > 25 else (round(float(a["avgVerticalOscillation"]), 2) if a.get("avgVerticalOscillation") else None),
                    "stride_len_cm": round(float(a["avgStrideLength"]), 1) if a.get("avgStrideLength") else None,
                    "cadence_spm": round(float(a["averageRunningCadenceInStepsPerMinute"]), 1) if a.get("averageRunningCadenceInStepsPerMinute") else None,
                    "aerobic_te": round(float(a["aerobicTrainingEffect"]), 1) if a.get("aerobicTrainingEffect") is not None else None,
                    "anaerobic_te": round(float(a["anaerobicTrainingEffect"]), 1) if a.get("anaerobicTrainingEffect") is not None else None,
                    "te_label": a.get("trainingEffectLabel"),
                    "vo2_max": a.get("vO2MaxValue"),
                    "calories": a.get("calories"),
                    "elevation_gain_m": round(float(a["elevationGain"]), 1) if a.get("elevationGain") else None,
                    "steps": a.get("steps"),
                }
            )
        db.save_garmin_snapshot("garmin_activities", parsed_acts)
        pulled["garmin_activities"] = len(parsed_acts)

    return pulled


def sync_garmin_wellness(days: int = 14, force_full: bool = False) -> Dict[str, Any]:
    """
    Thread-safe, lock-protected parallel + smart incremental Garmin Connect sync.
    Uses isolated per-thread Garmin clients (never shares requests.Session across threads) and skips complete older days.
    """
    with _garmin_sync_lock:
        t0 = time.monotonic()
        client = _load_authenticated_client()
        try:
            if hasattr(client, "garth"):
                client.garth.dump(str(GARMIN_TOKEN_DIR))
            elif hasattr(client, "dump"):
                client.dump(str(GARMIN_TOKEN_DIR))
            _persist_garmin_tokens_to_db()
        except Exception:
            pass

        today = date.today()
        existing_by_date = {g["date_key"]: g for g in db.get_garmin_daily(days=max(days + 5, 45))}
        dates_to_fetch: List[Tuple[str, bool]] = []
        for offset in range(days):
            cdate = (today - timedelta(days=offset)).isoformat()
            ex = existing_by_date.get(cdate)
            needs_ext = offset < 14
            already_complete = (
                ex is not None
                and not ex.get("is_demo")
                and ex.get("stress_avg") is not None
                and (not needs_ext or ex.get("respiration_avg") is not None)
            )
            if offset < 3 or force_full or not already_complete:
                dates_to_fetch.append((cdate, needs_ext))

        synced = 0
        detected_profile_id: Optional[int] = None

        def _fetch_one_day(cdate: str, fetch_ext: bool) -> Tuple[Dict[str, Any], Optional[int]]:
            # Each worker thread loads its own tokenstore session so requests.Session is never shared across threads
            t_client = _load_authenticated_client()
            return _parse_garmin_day(t_client, cdate, fetch_ext)

        if len(dates_to_fetch) == 1:
            rec, prof_id = _parse_garmin_day(client, dates_to_fetch[0][0], dates_to_fetch[0][1])
            if prof_id:
                detected_profile_id = prof_id
            if any(rec.get(k) is not None for k in ("stress_avg", "body_battery_max", "hrv_avg", "sleep_seconds", "resting_hr", "steps", "active_calories")):
                db.upsert_garmin_daily(rec)
                synced += 1
        elif dates_to_fetch:
            with ThreadPoolExecutor(max_workers=min(4, len(dates_to_fetch))) as pool:
                futures = {
                    pool.submit(_fetch_one_day, cdate, fetch_ext): cdate
                    for cdate, fetch_ext in dates_to_fetch
                }
                for fut in as_completed(futures):
                    try:
                        rec, prof_id = fut.result()
                        if prof_id and not detected_profile_id:
                            detected_profile_id = prof_id
                        has_metric = any(
                            rec.get(k) is not None
                            for k in ("stress_avg", "body_battery_max", "hrv_avg", "sleep_seconds", "resting_hr", "steps", "active_calories")
                        )
                        if has_metric:
                            db.upsert_garmin_daily(rec)
                            synced += 1
                    except Exception:
                        continue

        if synced > 0:
            db.delete_demo_data()

        account_pulled = _sync_garmin_account_wide(client, today.isoformat(), profile_num=detected_profile_id)

        recent = db.get_garmin_daily(days=14)
        rhrs = [g["resting_hr"] for g in recent if g.get("resting_hr")]
        if rhrs:
            db.set_setting("resting_hr", str(int(round(sum(rhrs) / len(rhrs)))))

        duration_s = round(time.monotonic() - t0, 1)
        if synced > 0 or account_pulled:
            db.set_setting("garmin_last_sync", datetime.now().strftime("%Y-%m-%d %H:%M"))
        return {
            "status": "ok",
            "days_synced": synced,
            "duration_s": duration_s,
            "extended": account_pulled,
        }
