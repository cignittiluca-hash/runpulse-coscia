"""Optional realistic 60-day Strava + Garmin demo dataset generator (1-click load & clear)."""
import math
import random
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from backend.database import db
from backend.services.analytics import analyze_splits_metrics, compute_trimp


def _generate_splits(dist_km: float, avg_pace: float, avg_hr: float, drift_factor: float) -> List[Dict[str, Any]]:
    full_kms = int(dist_km)
    splits = []
    for i in range(full_kms):
        frac = i / max(1, full_kms - 1)
        pace_i = avg_pace + random.uniform(-6, 6) + (frac - 0.5) * (drift_factor * 4.0)
        hr_i = avg_hr + (frac - 0.5) * (drift_factor * 14.0) + random.uniform(-2.5, 2.5)
        splits.append(
            {
                "split": i + 1,
                "distance": 1000.0,
                "moving_time": int(round(pace_i)),
                "elapsed_time": int(round(pace_i)),
                "elevation_difference": round(random.uniform(-6, 7), 1),
                "average_speed": round(1000.0 / pace_i, 3),
                "average_heartrate": round(hr_i, 1),
            }
        )
    return splits


def seed_demo_data() -> Dict[str, Any]:
    """Seeds 60 days of realistic road-running Strava workouts and Garmin wellness data."""
    rng = random.Random(42)
    random.seed(42)
    today = date.today()
    settings = db.get_settings()
    max_hr = float(settings.get("max_hr") or 190)
    resting_hr = float(settings.get("resting_hr") or 50)
    threshold_pace = float(settings.get("threshold_pace_sec") or 270)

    # Weekly schedule templates (0=Mon .. 6=Sun)
    templates = {
        1: ("Ripetute 6x1000m in soglia", "intervals", 10.5, 268, 169, 1.05),
        2: ("Corsa Rigenerante Z2", "recovery", 7.0, 338, 138, 0.35),
        3: ("Tempo Run / Medio Progressivo", "tempo", 11.5, 282, 162, 0.85),
        5: ("Corsa Facile + Allunghi", "easy", 8.5, 322, 144, 0.45),
        6: ("Lungo Domenicale Aerobico", "long", 18.0, 315, 149, 0.95),
    }

    activities_added = 0
    garmin_added = 0

    for offset in range(59, -1, -1):
        d = today - timedelta(days=offset)
        dow = d.weekday()
        week_progress = (60 - offset) / 60.0

        # Simulate realistic stress spike in the last 2 days or occasional busy workdays
        is_high_stress_day = offset in (2, 12, 27, 41)
        is_hard_yesterday = ((d - timedelta(days=1)).weekday() in (1, 3, 6))

        stress_avg = int(
            max(
                16,
                min(
                    72,
                    (54 if is_high_stress_day else 27)
                    + (7 if is_hard_yesterday else 0)
                    + rng.randint(-6, 7),
                ),
            )
        )
        stress_max = min(98, stress_avg + rng.randint(25, 42))
        bb_max = int(max(38, min(99, 92 - (stress_avg - 22) * 0.85 + rng.randint(-5, 6))))
        bb_min = max(8, bb_max - rng.randint(42, 62))
        hrv = round(
            max(
                36.0,
                min(
                    84.0,
                    61.0 + week_progress * 4.0 - (11.0 if is_high_stress_day else 0.0) + rng.uniform(-4.5, 4.5),
                ),
            ),
            1,
        )
        hrv_status = "LOW" if hrv < 51 else ("BALANCED" if hrv >= 55 else "UNBALANCED")
        rhr = int(round(50 - week_progress * 2 + (4 if is_high_stress_day else 0) + rng.randint(-1, 2)))
        sleep_h = round(max(5.2, min(8.8, (6.0 if is_high_stress_day else 7.5) + rng.uniform(-0.6, 0.6))), 2)
        sleep_sec = int(sleep_h * 3600)
        sleep_score = int(max(45, min(95, sleep_h * 10.6 - (stress_avg - 25) * 0.25 + rng.randint(-4, 5))))
        readiness = int(max(28, min(96, bb_max * 0.45 + sleep_score * 0.35 + (100 - stress_avg) * 0.20)))
        vo2_max = round(51.5 + week_progress * 2.1, 1)

        db.upsert_garmin_daily(
            {
                "date_key": d.isoformat(),
                "stress_avg": stress_avg,
                "stress_max": stress_max,
                "stress_rest_min": int(max(240, 620 - stress_avg * 6)),
                "stress_low_min": int(180 + stress_avg * 2),
                "stress_medium_min": int(60 + stress_avg * 2.2),
                "stress_high_min": int(max(10, (stress_avg - 20) * 2.5)),
                "body_battery_max": bb_max,
                "body_battery_min": bb_min,
                "body_battery_current": max(bb_min, bb_max - rng.randint(18, 38)),
                "body_battery_charged": rng.randint(45, 72),
                "body_battery_drained": rng.randint(42, 68),
                "hrv_avg": hrv,
                "hrv_baseline_low": 53.0,
                "hrv_baseline_high": 71.0,
                "hrv_status": hrv_status,
                "resting_hr": rhr,
                "sleep_seconds": sleep_sec,
                "sleep_score": sleep_score,
                "sleep_deep_sec": int(sleep_sec * 0.21),
                "sleep_rem_sec": int(sleep_sec * 0.23),
                "sleep_light_sec": int(sleep_sec * 0.56),
                "training_readiness": readiness,
                "vo2_max": vo2_max,
                "steps": rng.randint(6800, 16500),
                "is_demo": 1,
            }
        )
        garmin_added += 1

        # Create realistic running activity on training days (skip ~12% randomly + today)
        if dow in templates and offset > 0 and rng.random() > 0.12:
            title, cat, base_dist, base_pace, base_hr, drift_f = templates[dow]
            # Slight fitness progression over 60 days
            dist_km = round(base_dist * (0.88 + 0.20 * week_progress) + rng.uniform(-0.8, 1.0), 2)
            pace = round(base_pace - week_progress * 7.0 + rng.uniform(-4.5, 4.5), 1)
            avg_hr = round(base_hr + rng.uniform(-3.5, 3.5), 1)
            moving_s = int(round(dist_km * pace))
            dist_m = round(dist_km * 1000.0, 1)
            avg_speed = dist_m / max(1, moving_s)
            splits = _generate_splits(dist_km, pace, avg_hr, drift_f)
            split_metrics = analyze_splits_metrics(splits, avg_hr, max_hr)
            trimp = compute_trimp(moving_s, avg_hr, max_hr, resting_hr, pace, threshold_pace)
            start_dt = f"{d.isoformat()}T07:{rng.randint(10, 45):02d}:00"

            db.upsert_activity(
                {
                    "id": f"demo_run_{d.isoformat()}",
                    "source": "strava",
                    "external_id": f"demo_{d.isoformat()}",
                    "name": title,
                    "sport_type": "Run",
                    "workout_category": cat,
                    "start_date": start_dt,
                    "date_key": d.isoformat(),
                    "distance_m": dist_m,
                    "moving_time_s": moving_s,
                    "elapsed_time_s": moving_s + rng.randint(10, 90),
                    "elevation_gain_m": round(dist_km * rng.uniform(5.5, 11.5), 1),
                    "avg_speed_ms": round(avg_speed, 3),
                    "max_speed_ms": round(avg_speed * 1.24, 3),
                    "avg_pace_sec_km": pace,
                    "avg_hr": avg_hr,
                    "max_hr": round(min(max_hr, avg_hr + rng.uniform(11, 20)), 1),
                    "avg_cadence": round(rng.uniform(171, 181), 1),
                    "calories": round(dist_km * 66),
                    "suffer_score": round(trimp * 0.9),
                    "trimp": trimp,
                    "efficiency_factor": split_metrics.get("efficiency_factor"),
                    "cardiac_drift_pct": split_metrics.get("cardiac_drift_pct"),
                    "splits": splits,
                    "laps": [],
                    "hr_zones": split_metrics.get("hr_zones") or {},
                    "description": "Allenamento demo sincronizzato per anteprima dashboard RunPulse.",
                    "is_demo": 1,
                }
            )
            activities_added += 1

    return {
        "status": "ok",
        "activities_created": activities_added,
        "garmin_days_created": garmin_added,
    }
