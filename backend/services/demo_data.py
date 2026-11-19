"""Realistic Apple Watch & Strava demo dataset generator for RunPulse."""
import json
import math
import random
from datetime import date, datetime, timedelta
from typing import Any, Dict

from backend.database import db
from backend.services.analytics import (
    analyze_splits_metrics,
    classify_workout,
    compute_trimp,
    compute_vdot,
)


def seed_demo_data() -> Dict[str, int]:
    """Generates 45 days of realistic Strava runs and Apple Watch health metrics."""
    # Clean previous demo data first
    db.delete_demo_data()

    today = date.today()
    settings = db.get_settings()
    max_hr = float(settings.get("max_hr") or 190)
    resting_hr = float(settings.get("resting_hr") or 52)
    threshold_pace = float(settings.get("threshold_pace_sec") or 275)

    activities_count = 0
    wellness_count = 0

    # 1. Generate 30 days of Apple Watch health data
    random.seed(42)
    base_hrv = 64.0
    base_rhr = 52.0

    for i in range(30, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.isoformat()

        # Slight wave patterns for HRV and recovery
        wave = math.sin(i / 3.0) * 8.0 + random.uniform(-4.0, 4.0)
        day_hrv = round(max(42.0, min(85.0, base_hrv + wave)), 1)
        day_rhr = int(round(max(47, min(62, base_rhr - wave * 0.4 + random.uniform(-1.5, 1.5)))))

        # Sleep: 6.8h to 8.2h
        total_sleep_h = max(6.0, min(8.6, 7.5 + (wave / 20.0) + random.uniform(-0.4, 0.4)))
        total_sleep_sec = int(round(total_sleep_h * 3600))
        deep_sec = int(round(total_sleep_sec * random.uniform(0.15, 0.22)))
        rem_sec = int(round(total_sleep_sec * random.uniform(0.19, 0.26)))
        awake_sec = int(round(random.uniform(900, 2400)))
        light_sec = total_sleep_sec - deep_sec - rem_sec

        sleep_score = int(round(max(60, min(96, 72.0 + (total_sleep_h - 7.0) * 15.0 + random.uniform(-4, 5)))))

        # Apple Rings
        active_cals = int(round(random.uniform(520, 850)))
        exercise_m = int(round(random.uniform(35, 75)))
        stand_h = int(round(random.uniform(11, 15)))
        steps = int(round(random.uniform(9000, 16000)))

        # HRV status
        if day_hrv >= 68:
            hrv_status = "Ottimale"
        elif day_hrv < 50:
            hrv_status = "Basso / Affaticato"
        else:
            hrv_status = "Equilibrato"

        # Readiness (0-100)
        readiness = int(round(max(40, min(95, 76.0 + (day_hrv - 60.0) * 0.6 - (day_rhr - 52.0) * 1.5 + (total_sleep_h - 7.0) * 6.0))))

        record = {
            "date_key": d_str,
            "hrv_avg": day_hrv,
            "hrv_baseline_low": 52.0,
            "hrv_baseline_high": 74.0,
            "hrv_status": hrv_status,
            "resting_hr": day_rhr,
            "sleep_seconds": total_sleep_sec,
            "sleep_score": sleep_score,
            "sleep_deep_sec": deep_sec,
            "sleep_rem_sec": rem_sec,
            "sleep_light_sec": light_sec,
            "sleep_awake_sec": awake_sec,
            "training_readiness": readiness,
            "vo2_max": 52.4,  # Apple Watch Cardio Fitness estimate
            "steps": steps,
            "active_calories": active_cals,
            "total_calories": active_cals + 1850,
            "exercise_min": exercise_m,
            "stand_hours": stand_h,
            "spo2_avg": round(random.uniform(97.2, 99.1), 1),
            "respiration_avg": round(random.uniform(14.2, 15.8), 1),
            "wrist_temperature_c": round(random.uniform(-0.25, 0.35), 2),
            "walking_hr_avg": round(random.uniform(85, 96), 1),
            "source": "apple_health",
            "is_demo": 1,
            "raw": {"simulated": True, "device": "Apple Watch Ultra 2"},
        }
        db.upsert_wellness_daily(record)
        wellness_count += 1

    # Save Apple Watch snapshots
    db.save_wellness_snapshot("device_info", {
        "model": "Apple Watch Ultra 2 (watchOS 11)",
        "source": "Apple HealthKit",
        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 2. Generate 45 days of realistic running activities
    run_templates = [
        {"name": "Corsa Facile Mattutina", "dist": 8.2, "pace": 315, "hr": 142, "cad": 172, "cat": "easy"},
        {"name": "Progressivo Aerobico", "dist": 10.5, "pace": 290, "hr": 154, "cad": 176, "cat": "tempo"},
        {"name": "Ripetute 5x1000m (Soglia)", "dist": 11.2, "pace": 268, "hr": 168, "cad": 182, "cat": "intervals"},
        {"name": "Lungo Collinare Domenicale", "dist": 18.5, "pace": 325, "hr": 146, "cad": 170, "cat": "long"},
        {"name": "Rigenerante Leggero", "dist": 6.0, "pace": 345, "hr": 130, "cad": 168, "cat": "recovery"},
        {"name": "Medio a Ritmo Maratona", "dist": 12.0, "pace": 282, "hr": 160, "cad": 178, "cat": "tempo"},
    ]

    for day_offset in range(45, 0, -1):
        d = today - timedelta(days=day_offset)
        # Run ~4 times per week (e.g. Tue, Thu, Sat, Sun)
        if d.weekday() in (1, 3, 5, 6):
            if d.weekday() == 6:
                tmpl = run_templates[3]  # Long run on Sunday
            elif d.weekday() == 3:
                tmpl = run_templates[2]  # Intervals on Thursday
            elif d.weekday() == 1:
                tmpl = run_templates[1]  # Tempo on Tuesday
            else:
                tmpl = random.choice([run_templates[0], run_templates[4]])

            dist_m = tmpl["dist"] * 1000.0 + random.uniform(-300, 500)
            target_pace = tmpl["pace"] + random.uniform(-6, 8)
            moving_s = int(round((dist_m / 1000.0) * target_pace))
            avg_hr = round(tmpl["hr"] + random.uniform(-3, 4), 1)
            cadence = round(tmpl["cad"] + random.uniform(-2, 3), 1)
            elev = round(dist_m / 1000.0 * random.uniform(4, 12), 1)

            # Splits
            splits = []
            num_km = int(dist_m // 1000)
            drift_factor = 1.0
            for k in range(num_km):
                split_pace = target_pace + (k * 0.8 if tmpl["cat"] != "tempo" else -k * 1.5) + random.uniform(-4, 4)
                split_hr = min(max_hr, avg_hr - 6 + (k * 1.4))
                splits.append({
                    "split": k + 1,
                    "distance": 1000.0,
                    "elapsed_time": int(round(split_pace)),
                    "moving_time": int(round(split_pace)),
                    "average_speed": round(1000.0 / split_pace, 2),
                    "average_heartrate": round(split_hr, 1),
                    "elevation_difference": round(random.uniform(-4, 6), 1),
                })

            rem = dist_m % 1000
            if rem > 100:
                s_pace = target_pace + random.uniform(-3, 3)
                splits.append({
                    "split": num_km + 1,
                    "distance": round(rem, 1),
                    "elapsed_time": int(round((rem / 1000.0) * s_pace)),
                    "moving_time": int(round((rem / 1000.0) * s_pace)),
                    "average_speed": round(1000.0 / s_pace, 2),
                    "average_heartrate": round(avg_hr + 4, 1),
                    "elevation_difference": 0.0,
                })

            split_metrics = analyze_splits_metrics(splits, avg_hr, max_hr)
            trimp_val = compute_trimp(moving_s, avg_hr, max_hr, resting_hr, target_pace, threshold_pace)

            act_id = f"demo_act_{d.isoformat()}"
            act_record = {
                "id": act_id,
                "source": "strava",
                "external_id": act_id,
                "name": tmpl["name"],
                "sport_type": "Run",
                "workout_category": tmpl["cat"],
                "start_date": f"{d.isoformat()}T07:30:00Z",
                "date_key": d.isoformat(),
                "distance_m": round(dist_m, 1),
                "moving_time_s": moving_s,
                "elapsed_time_s": int(round(moving_s * 1.03)),
                "elevation_gain_m": elev,
                "avg_speed_ms": round(dist_m / moving_s, 2),
                "max_speed_ms": round((dist_m / moving_s) * 1.35, 2),
                "avg_pace_sec_km": round(target_pace, 1),
                "avg_hr": avg_hr,
                "max_hr": round(avg_hr + 16, 1),
                "avg_cadence": cadence,
                "calories": round((dist_m / 1000.0) * 65.0, 1),
                "suffer_score": round(trimp_val * 0.8),
                "trimp": trimp_val,
                "efficiency_factor": split_metrics.get("efficiency_factor"),
                "cardiac_drift_pct": split_metrics.get("cardiac_drift_pct"),
                "splits": splits,
                "laps": [],
                "hr_zones": split_metrics.get("hr_zones", {}),
                "ai_analysis": "",
                "description": "Allenamento sincronizzato via Apple Watch Workout & Strava.",
                "is_demo": 1,
            }
            db.upsert_activity(act_record)
            activities_count += 1

    return {
        "wellness_days_created": wellness_count,
        "activities_created": activities_count,
    }
