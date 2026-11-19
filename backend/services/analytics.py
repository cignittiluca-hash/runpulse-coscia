"""Sports-science running analytics engine (CTL/ATL/TSB, ACWR, VDOT, Readiness, Run Decomposition)."""
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


DISTANCE_MAP_KM = {
    "5k": 5.0,
    "10k": 10.0,
    "half_marathon": 21.0975,
    "marathon": 42.195,
}


def format_pace(sec_per_km: Optional[float]) -> str:
    if not sec_per_km or sec_per_km <= 0 or math.isinf(sec_per_km) or math.isnan(sec_per_km):
        return "--:--"
    total = int(round(sec_per_km))
    mins = total // 60
    secs = total % 60
    return f"{mins}:{secs:02d}"


def format_hm(seconds: Optional[float]) -> str:
    """Formats seconds into human-readable hours & minutes (e.g. '7h 25m' or '45m'), never decimal hours."""
    if seconds is None or seconds <= 0:
        return "0m"
    total_min = int(round(seconds / 60.0))
    h = total_min // 60
    m = total_min % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "0m"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def format_race_time(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "--:--"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------- Jack Daniels VDOT Model ----------
def compute_vdot(distance_m: float, time_sec: float) -> Optional[float]:
    """Computes Jack Daniels VDOT score from distance (m) and time (s)."""
    if distance_m < 1500 or time_sec <= 0:
        return None
    t_min = time_sec / 60.0
    v_m_per_min = distance_m / t_min
    if v_m_per_min < 100 or v_m_per_min > 450:
        return None
    # Daniels & Gilbert (1979) equations
    vo2 = -4.60 + 0.182258 * v_m_per_min + 0.000104 * (v_m_per_min ** 2)
    pct_max = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * t_min)
        + 0.2989558 * math.exp(-0.1932605 * t_min)
    )
    if pct_max <= 0:
        return None
    vdot = vo2 / pct_max
    return round(max(25.0, min(85.0, vdot)), 1)


def predict_race_time_sec(vdot: float, distance_m: float) -> int:
    """Solves Daniels equation numerically via binary search for predicted race time (seconds)."""
    low_t = distance_m / 450.0 * 60.0  # fast bound
    high_t = distance_m / 90.0 * 60.0  # slow bound
    for _ in range(40):
        mid = (low_t + high_t) / 2.0
        est = compute_vdot(distance_m, mid) or 0.0
        if est > vdot:
            low_t = mid
        else:
            high_t = mid
    return int(round((low_t + high_t) / 2.0))


def vdot_training_paces(vdot: float) -> Dict[str, Dict[str, Any]]:
    """Calculates structured training pace zones (sec/km & formatted) from VDOT."""
    # Velocity at 100% VO2max (solve 0.000104 v^2 + 0.182258 v - (4.60 + vdot) = 0)
    def pace_at_vo2_pct(pct: float) -> float:
        target_vo2 = vdot * pct
        a = 0.000104
        b = 0.182258
        c = -(4.60 + target_vo2)
        disc = max(0.0, b * b - 4 * a * c)
        v_m_min = (-b + math.sqrt(disc)) / (2 * a)
        if v_m_min <= 0:
            return 360.0
        return (1000.0 / v_m_min) * 60.0

    easy_fast = pace_at_vo2_pct(0.74)
    easy_slow = pace_at_vo2_pct(0.65)
    marathon_pace = pace_at_vo2_pct(0.815)
    threshold_pace = pace_at_vo2_pct(0.88)
    interval_pace = pace_at_vo2_pct(0.975)
    rep_pace = pace_at_vo2_pct(1.04)

    return {
        "recovery": {
            "label": "Rigenerante (Z1-Z2)",
            "min_sec": int(round(easy_slow)),
            "max_sec": int(round(easy_slow + 25)),
            "range": f"{format_pace(easy_slow)} - {format_pace(easy_slow + 25)} /km",
        },
        "easy": {
            "label": "Corsa Facile (Z2)",
            "min_sec": int(round(easy_fast)),
            "max_sec": int(round(easy_slow)),
            "range": f"{format_pace(easy_fast)} - {format_pace(easy_slow)} /km",
        },
        "marathon": {
            "label": "Ritmo Maratona (Z3)",
            "min_sec": int(round(marathon_pace - 4)),
            "max_sec": int(round(marathon_pace + 5)),
            "range": f"{format_pace(marathon_pace - 4)} - {format_pace(marathon_pace + 5)} /km",
        },
        "threshold": {
            "label": "Soglia / Tempo (Z4)",
            "min_sec": int(round(threshold_pace - 4)),
            "max_sec": int(round(threshold_pace + 4)),
            "range": f"{format_pace(threshold_pace - 4)} - {format_pace(threshold_pace + 4)} /km",
        },
        "interval": {
            "label": "Ripetute VO2max (Z5)",
            "min_sec": int(round(interval_pace - 4)),
            "max_sec": int(round(interval_pace + 4)),
            "range": f"{format_pace(interval_pace - 4)} - {format_pace(interval_pace + 4)} /km",
        },
        "repetition": {
            "label": "Velocità / Allunghi",
            "min_sec": int(round(rep_pace - 3)),
            "max_sec": int(round(rep_pace + 3)),
            "range": f"{format_pace(rep_pace - 3)} - {format_pace(rep_pace + 3)} /km",
        },
    }


def estimate_athlete_vdot(activities: List[Dict[str, Any]], garmin_days: List[Dict[str, Any]], threshold_pace_sec: float) -> Tuple[float, str]:
    """Estimates current VDOT from recent best running efforts, Garmin VO2max, or threshold pace."""
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    best_vdot = 0.0
    source = "ritmo soglia"

    for act in activities:
        if "run" not in str(act.get("sport_type", "")).lower():
            continue
        if act.get("date_key", "") < cutoff:
            continue
        # Exclude paused interval workouts that inflate moving-time VDOT
        if act.get("workout_category") == "intervals":
            continue
        dist = float(act.get("distance_m") or 0)
        moving = float(act.get("moving_time_s") or 0)
        elapsed = float(act.get("elapsed_time_s") or moving)
        if dist >= 3000 and moving > 0:
            if elapsed > moving * 1.10:
                continue
            eff_time = elapsed if elapsed >= moving else moving
            v = compute_vdot(dist, eff_time)
            if v and v > best_vdot:
                best_vdot = v
                source = f"miglior corsa recente ({act.get('name', 'Run')})"

    # Check Apple Watch Cardio Fitness / VO2 max if no hard efforts exist
    apple_vo2 = next((g["vo2_max"] for g in reversed(garmin_days) if g.get("vo2_max")), None)
    if best_vdot == 0 and apple_vo2:
        best_vdot = round(float(apple_vo2) * 0.94, 1)
        source = "Apple Watch Cardio Fitness (VO2 Max)"
    elif best_vdot > 0 and apple_vo2:
        # Blend slightly if recent runs were mostly easy
        g_est = float(apple_vo2) * 0.92
        if g_est > best_vdot + 4:
            best_vdot = round(best_vdot * 0.65 + g_est * 0.35, 1)
            source = "corse recenti + Apple Watch VO2 Max"

    if best_vdot == 0:
        # Derive from threshold pace (approx 10K-15K effort)
        v_from_thresh = compute_vdot(10000.0, threshold_pace_sec * 10.0 * 0.97) or 44.0
        best_vdot = round(v_from_thresh, 1)
        source = "impostazioni profilo"

    return round(best_vdot, 1), source


# ---------- Activity-Level Metrics ----------
def compute_trimp(
    moving_time_s: int,
    avg_hr: Optional[float],
    max_hr: float,
    resting_hr: float,
    avg_pace_sec_km: float = 0,
    threshold_pace_sec: float = 275,
    is_run: bool = True,
) -> float:
    """Computes Banister TRIMP (or pace-based rTSS fallback for running when HR is absent)."""
    duration_min = max(0.0, moving_time_s / 60.0)
    if duration_min <= 0:
        return 0.0

    if avg_hr and max_hr > resting_hr:
        hrr = max(0.05, min(1.0, (avg_hr - resting_hr) / (max_hr - resting_hr)))
        # Banister TRIMP scaled to TSS-like 0..250 range
        raw_trimp = duration_min * hrr * 0.64 * math.exp(1.92 * hrr)
        return round(raw_trimp * 0.72, 1)

    # Pace-based rTSS fallback strictly for running activities
    if is_run and avg_pace_sec_km > 0 and threshold_pace_sec > 0:
        intensity_factor = max(0.5, min(1.25, threshold_pace_sec / avg_pace_sec_km))
        rtss = (moving_time_s / 3600.0) * (intensity_factor ** 2) * 100.0
        return round(rtss, 1)

    return round(duration_min * 0.85, 1)


def classify_workout(
    name: str,
    distance_m: float,
    avg_pace_sec_km: float,
    avg_hr: Optional[float],
    max_hr: float,
    threshold_pace_sec: float,
    sport_type: str = "Run",
) -> str:
    """Classifies an activity into: recovery, easy, tempo, intervals, long, race, strength, cross_training."""
    sp = (sport_type or "Run").lower()
    if "run" not in sp:
        if any(k in sp for k in ("weight", "strength", "workout", "highintensity", "hiit", "crossfit")):
            return "strength"
        return "cross_training"

    lower = (name or "").lower()
    if any(w in lower for w in ["gara", "race", "maratona", "mezza", "10k", "5k", "pb", "pr"]):
        if any(w in lower for w in ["gara", "race", "maratona", "mezza"]):
            return "race"
    if any(w in lower for w in ["ripetut", "interval", "fartlek", "pista", "track", "vo2", "400m", "800m", "1000m"]):
        return "intervals"
    if any(w in lower for w in ["tempo", "soglia", "threshold", "medio", "progressivo", "ritmo gara"]):
        return "tempo"
    if any(w in lower for w in ["lungo", "long", "lunghissimo"]) or distance_m >= 16000:
        return "long"
    if any(w in lower for w in ["rigener", "recovery", "defatic", "scarico"]):
        return "recovery"

    hr_pct = (avg_hr / max_hr) if (avg_hr and max_hr > 0) else None
    if avg_pace_sec_km > 0 and threshold_pace_sec > 0:
        if avg_pace_sec_km <= threshold_pace_sec * 0.97:
            return "intervals"
        if avg_pace_sec_km <= threshold_pace_sec * 1.05:
            return "tempo"
        if avg_pace_sec_km >= threshold_pace_sec * 1.24:
            return "recovery"

    if hr_pct is not None:
        if hr_pct >= 0.89:
            return "intervals"
        if hr_pct >= 0.82:
            return "tempo"
        if hr_pct <= 0.70:
            return "recovery"

    return "easy"


def analyze_splits_metrics(splits: List[Dict[str, Any]], avg_hr: Optional[float], max_hr: float) -> Dict[str, Any]:
    """Calculates cardiac drift, efficiency factor, negative split, and estimated HR zone distribution from splits."""
    out: Dict[str, Any] = {
        "cardiac_drift_pct": None,
        "efficiency_factor": None,
        "split_strategy": "uniforme",
        "hr_zones": {},
    }
    valid_splits = [
        s for s in splits
        if (s.get("distance", 0) >= 400 and s.get("moving_time", 0) > 0)
    ]
    if not valid_splits:
        return out

    # Efficiency factor (speed m/min divided by time-weighted avg HR on valid splits)
    hr_splits = [s for s in valid_splits if s.get("average_heartrate") and s.get("moving_time", 0) > 0]
    if hr_splits:
        d_hr = sum(s.get("distance", 0) for s in hr_splits)
        t_hr = sum(s.get("moving_time", 0) for s in hr_splits)
        w_hr = sum(float(s["average_heartrate"]) * float(s["moving_time"]) for s in hr_splits) / max(1.0, t_hr)
        if t_hr > 0 and w_hr > 0:
            out["efficiency_factor"] = round((d_hr / (t_hr / 60.0)) / w_hr, 2)
    else:
        total_dist = sum(s.get("distance", 0) for s in valid_splits)
        total_time = sum(s.get("moving_time", 0) for s in valid_splits)
        if total_time > 0 and avg_hr and avg_hr > 0:
            out["efficiency_factor"] = round((total_dist / (total_time / 60.0)) / avg_hr, 2)

    # First half vs second half (use full >=800m splits and split at 50% cumulative distance)
    full_splits = [s for s in valid_splits if s.get("distance", 0) >= 800]
    if len(full_splits) >= 4:
        tot_d = sum(s.get("distance", 0) for s in full_splits)
        half_d = tot_d / 2.0
        cum = 0.0
        split_idx = len(full_splits) // 2
        for i, s in enumerate(full_splits):
            cum += s.get("distance", 0)
            if cum >= half_d:
                split_idx = max(1, min(len(full_splits) - 1, i + 1))
                break
        first_half = full_splits[:split_idx]
        second_half = full_splits[split_idx:]

        d1 = sum(s.get("distance", 0) for s in first_half)
        t1 = sum(s.get("moving_time", 0) for s in first_half)
        d2 = sum(s.get("distance", 0) for s in second_half)
        t2 = sum(s.get("moving_time", 0) for s in second_half)

        if d1 > 0 and d2 > 0 and t1 > 0 and t2 > 0:
            pace1 = t1 / (d1 / 1000.0)
            pace2 = t2 / (d2 / 1000.0)
            diff_pct = ((pace2 - pace1) / pace1) * 100.0
            if diff_pct <= -1.5:
                out["split_strategy"] = "negative_split"
            elif diff_pct >= 2.5:
                out["split_strategy"] = "positive_split"
            else:
                out["split_strategy"] = "even_split"

            # Time-weighted HR & EF strictly on splits that have HR readings
            fh_hr = [s for s in first_half if s.get("average_heartrate") and s.get("moving_time", 0) > 0]
            sh_hr = [s for s in second_half if s.get("average_heartrate") and s.get("moving_time", 0) > 0]
            if fh_hr and sh_hr:
                t1_h = sum(s["moving_time"] for s in fh_hr)
                t2_h = sum(s["moving_time"] for s in sh_hr)
                d1_h = sum(s["distance"] for s in fh_hr)
                d2_h = sum(s["distance"] for s in sh_hr)
                avg_hr1 = sum(float(s["average_heartrate"]) * float(s["moving_time"]) for s in fh_hr) / max(1.0, t1_h)
                avg_hr2 = sum(float(s["average_heartrate"]) * float(s["moving_time"]) for s in sh_hr) / max(1.0, t2_h)
                ef1 = (d1_h / (t1_h / 60.0)) / avg_hr1
                ef2 = (d2_h / (t2_h / 60.0)) / avg_hr2
                if ef1 > 0:
                    drift = ((ef1 - ef2) / ef1) * 100.0
                    out["cardiac_drift_pct"] = round(drift, 1)

    # HR zone breakdown from splits
    zones = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0}
    has_hr = False
    for s in valid_splits:
        hr = s.get("average_heartrate")
        dur = int(s.get("moving_time") or 0)
        if not hr or max_hr <= 0:
            continue
        has_hr = True
        pct = hr / max_hr
        if pct < 0.68:
            zones["Z1"] += dur
        elif pct < 0.78:
            zones["Z2"] += dur
        elif pct < 0.86:
            zones["Z3"] += dur
        elif pct < 0.93:
            zones["Z4"] += dur
        else:
            zones["Z5"] += dur

    if has_hr:
        tot = sum(zones.values()) or 1
        out["hr_zones"] = {k: round((v / tot) * 100, 1) for k, v in zones.items()}

    return out


# ---------- Longitudinal Training Load (CTL / ATL / TSB / ACWR) ----------
def compute_training_load_series(activities: List[Dict[str, Any]], days: int = 60) -> Dict[str, Any]:
    """Computes daily CTL (42d EMA), ATL (7d EMA), TSB (CTL - ATL), and ACWR."""
    today = date.today()
    # Warm-up window of 90 days so CTL stabilizes properly
    total_window = max(days + 45, 90)
    start = today - timedelta(days=total_window - 1)

    daily_load: Dict[str, float] = {}
    daily_km: Dict[str, float] = {}
    for act in activities:
        dk = act.get("date_key", "")
        if not dk:
            continue
        daily_load[dk] = daily_load.get(dk, 0.0) + float(act.get("trimp") or 0.0)
        if "run" in str(act.get("sport_type", "")).lower():
            daily_km[dk] = daily_km.get(dk, 0.0) + float(act.get("distance_m") or 0.0) / 1000.0

    ctl = 0.0
    atl = 0.0
    alpha_ctl = 1.0 - math.exp(-1.0 / 42.0)
    alpha_atl = 1.0 - math.exp(-1.0 / 7.0)

    series = []
    recent_loads: List[float] = []
    for i in range(total_window):
        d = start + timedelta(days=i)
        dk = d.isoformat()
        load = daily_load.get(dk, 0.0)
        km = daily_km.get(dk, 0.0)
        ctl = ctl + (load - ctl) * alpha_ctl
        atl = atl + (load - atl) * alpha_atl
        tsb = ctl - atl
        recent_loads.append(load)

        # ACWR (7-day avg / 28-day avg)
        acute_7 = sum(recent_loads[-7:]) / 7.0
        chronic_28 = sum(recent_loads[-28:]) / max(1, min(28, len(recent_loads)))
        acwr = round(acute_7 / chronic_28, 2) if chronic_28 > 3.0 else 1.0

        series.append(
            {
                "date": dk,
                "load": round(load, 1),
                "km": round(km, 2),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
                "acwr": acwr,
            }
        )

    trimmed = series[-days:]
    current = trimmed[-1] if trimmed else {"ctl": 0.0, "atl": 0.0, "tsb": 0.0, "acwr": 1.0}

    # Weekly volume aggregation (last 8 weeks)
    weekly_volumes = []
    # Align to Monday of current week
    monday_this_week = today - timedelta(days=today.weekday())
    for w in range(7, -1, -1):
        w_start = monday_this_week - timedelta(days=w * 7)
        w_end = w_start + timedelta(days=6)
        w_km = 0.0
        w_load = 0.0
        w_runs = 0
        for act in activities:
            dk = act.get("date_key", "")
            if w_start.isoformat() <= dk <= w_end.isoformat():
                w_load += float(act.get("trimp") or 0)
                if "run" in str(act.get("sport_type", "")).lower():
                    w_km += float(act.get("distance_m") or 0) / 1000.0
                    w_runs += 1
        weekly_volumes.append(
            {
                "week_label": w_start.strftime("%d/%m"),
                "start_date": w_start.isoformat(),
                "km": round(w_km, 1),
                "load": round(w_load, 1),
                "runs": w_runs,
            }
        )

    return {
        "current": current,
        "series": trimmed,
        "weekly_volumes": weekly_volumes,
        "this_week_km": weekly_volumes[-1]["km"] if weekly_volumes else 0.0,
        "this_week_runs": weekly_volumes[-1]["runs"] if weekly_volumes else 0,
    }


# ---------- Apple Health / Wellness Recovery & Readiness Score ----------
def get_latest_valid_wellness(wellness_days: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Returns the most recent wellness day with biometrics, carrying forward latest known VO2 Max and HRV baseline."""
    if not wellness_days:
        return None
    chosen = None
    for g in reversed(wellness_days):
        if any(
            g.get(k) is not None
            for k in ("hrv_avg", "sleep_seconds", "resting_hr", "vo2_max", "steps", "active_calories", "training_readiness")
        ):
            chosen = dict(g)
            break
    if chosen is None:
        chosen = dict(wellness_days[-1])

    # Carry forward latest known VO2 max (Apple Cardio Fitness) and HRV baseline if today didn't emit a new reading
    for carry_key in ("vo2_max", "hrv_baseline_low", "hrv_baseline_high"):
        if chosen.get(carry_key) is None:
            for g in reversed(wellness_days):
                if g.get(carry_key) is not None:
                    chosen[carry_key] = g[carry_key]
                    break

    return chosen


# Backwards compatibility alias
get_latest_valid_garmin = get_latest_valid_wellness


def compute_readiness(
    wellness_days: List[Dict[str, Any]],
    load_summary: Dict[str, Any],
    settings: Dict[str, str],
) -> Dict[str, Any]:
    """
    Computes a transparent 0-100 Readiness Score combining Apple Watch biometric recovery
    (HRV SDNN, Resting HR, Sleep & stages, Activity Rings) and Strava training load (TSB, ACWR).
    """
    latest = get_latest_valid_wellness(wellness_days)
    current_load = load_summary.get("current", {})
    tsb = float(current_load.get("tsb") or 0.0)
    acwr = float(current_load.get("acwr") or 1.0)
    base_rhr = float(settings.get("resting_hr") or 52)

    components: List[Dict[str, Any]] = []
    weighted_sum = 0.0
    total_weight = 0.0

    # 1. Apple Watch HRV vs Baseline (weight 28)
    if latest and latest.get("hrv_avg") is not None:
        hrv = float(latest["hrv_avg"])
        b_low = latest.get("hrv_baseline_low")
        b_high = latest.get("hrv_baseline_high")
        if b_low is not None and b_high is not None and float(b_high) > 0:
            hrv_base = (float(b_low) + float(b_high)) / 2.0
        else:
            prior_hrv = [g["hrv_avg"] for g in wellness_days[-15:] if g.get("hrv_avg") is not None and g["date_key"] != latest["date_key"]]
            hrv_base = (sum(prior_hrv) / len(prior_hrv)) if prior_hrv else hrv

        ratio = hrv / max(1.0, hrv_base)
        hrv_score = max(15.0, min(100.0, 78.0 + (ratio - 1.0) * 160.0))
        hrv_status_norm = str(latest.get("hrv_status") or "").strip().lower()

        if "basso" in hrv_status_norm or "low" in hrv_status_norm or ratio < 0.85:
            status = "basso"
            hrv_score = min(hrv_score, 48.0)
        elif "ottimale" in hrv_status_norm or ratio >= 1.05:
            status = "ottimo"
            hrv_score = max(hrv_score, 88.0)
        else:
            status = "equilibrato"

        components.append(
            {
                "key": "hrv",
                "label": "HRV Notturna (Apple Watch)",
                "value": f"{round(hrv)} ms",
                "score": round(hrv_score),
                "status": status,
                "detail": f"SDNN {round(hrv)} ms vs baseline ({round(hrv_base)} ms)",
            }
        )
        weighted_sum += hrv_score * 28
        total_weight += 28

    # 2. Apple Watch Sleep & Stages (weight 26)
    if latest and (latest.get("sleep_score") is not None or (latest.get("sleep_seconds") is not None and latest.get("sleep_seconds") > 0)):
        has_dur = latest.get("sleep_seconds") is not None and float(latest["sleep_seconds"]) > 0
        sleep_h = (float(latest["sleep_seconds"]) / 3600.0) if has_dur else None
        if latest.get("sleep_score") is not None:
            sleep_score = float(latest["sleep_score"])
        else:
            sleep_score = max(20.0, min(100.0, ((sleep_h or 7.0) / 8.0) * 95.0))
        status = "ottimo" if sleep_score >= 78 else ("moderato" if sleep_score >= 60 else "scarso")
        sleep_str = format_hm(latest["sleep_seconds"]) if has_dur else "Durata N/D"
        val_label = f"{sleep_str} (score {int(sleep_score)})" if latest.get("sleep_score") is not None else sleep_str

        # Detail with deep & REM breakdown if available
        stage_details = []
        if latest.get("sleep_deep_sec"):
            stage_details.append(f"Profondo: {format_hm(latest['sleep_deep_sec'])}")
        if latest.get("sleep_rem_sec"):
            stage_details.append(f"REM: {format_hm(latest['sleep_rem_sec'])}")
        stage_txt = f" ({', '.join(stage_details)})" if stage_details else ""

        components.append(
            {
                "key": "sleep",
                "label": "Sonno Apple Health",
                "value": val_label,
                "score": round(sleep_score),
                "status": status,
                "detail": f"Durata {sleep_str}{stage_txt}",
            }
        )
        weighted_sum += sleep_score * 26
        total_weight += 26

    # 3. Resting HR delta (weight 18)
    if latest and latest.get("resting_hr") is not None:
        rhr = float(latest["resting_hr"])
        rhr_hist = [g["resting_hr"] for g in wellness_days[-15:] if g.get("resting_hr") is not None and g["date_key"] != latest["date_key"]]
        rhr_base = (sum(rhr_hist) / len(rhr_hist)) if rhr_hist else base_rhr
        delta = rhr - rhr_base
        rhr_score = max(20.0, min(100.0, 88.0 - delta * 8.0))
        status = "ottimo" if delta <= 1.5 else ("moderato" if delta <= 3.5 else "elevato")
        components.append(
            {
                "key": "rhr",
                "label": "FC a Riposo",
                "value": f"{int(rhr)} bpm",
                "score": round(rhr_score),
                "status": status,
                "detail": f"{int(rhr)} bpm ({'+' if delta >= 0 else ''}{delta:.1f} rispetto alla media)",
            }
        )
        weighted_sum += rhr_score * 18
        total_weight += 18

    # 4. Apple Watch Activity Rings / Steps (weight 8)
    if latest and (latest.get("active_calories") is not None or latest.get("steps") is not None):
        cals = latest.get("active_calories") or 0
        steps = latest.get("steps") or 0
        # Light score indication of daily activity
        ring_score = min(100.0, 75.0 + (cals / 600.0) * 15.0) if cals else 80.0
        components.append(
            {
                "key": "activity_rings",
                "label": "Attività Apple Watch",
                "value": f"{int(cals)} kcal | {steps:,} passi".replace(",", "."),
                "score": round(ring_score),
                "status": "ottimo" if cals >= 450 else "moderato",
                "detail": f"Movimento {int(cals)} kcal, {steps} passi",
            }
        )
        weighted_sum += ring_score * 8
        total_weight += 8

    # 5. Training Load Balance — TSB & ACWR (weight 20)
    load_weight = 20 if total_weight > 0 else 100
    tsb_score = max(20.0, min(100.0, 78.0 + tsb * 1.4))
    if acwr > 1.45:
        tsb_score = min(tsb_score, 42.0)
    elif acwr > 1.30:
        tsb_score = min(tsb_score, 62.0)
    status = "ottimo" if (acwr <= 1.25 and tsb >= -10) else ("carico alto" if acwr > 1.35 or tsb < -20 else "moderato")
    components.append(
        {
            "key": "load",
            "label": "Carico Allenamento",
            "value": f"TSB {tsb:+.0f} | ACWR {acwr:.2f}",
            "score": round(tsb_score),
            "status": status,
            "detail": f"Forma (TSB) {tsb:+.1f}, rapporto acuto/cronico {acwr:.2f}",
        }
    )
    weighted_sum += tsb_score * load_weight
    total_weight += load_weight

    final_score = int(round(weighted_sum / total_weight)) if total_weight > 0 else 72

    if latest and latest.get("training_readiness") is not None:
        final_score = int(round(final_score * 0.70 + float(latest["training_readiness"]) * 0.30))

    final_score = max(5, min(100, final_score))

    if final_score >= 78:
        zone = "prime"
        zone_label = "Pronto a spingere"
        color = "#10b981"
    elif final_score >= 58:
        zone = "moderate"
        zone_label = "Allenamento moderato"
        color = "#f59e0b"
    elif final_score >= 40:
        zone = "recovery"
        zone_label = "Solo scarico / Z2"
        color = "#f97316"
    else:
        zone = "rest"
        zone_label = "Riposo consigliato"
        color = "#ef4444"

    return {
        "score": final_score,
        "zone": zone,
        "zone_label": zone_label,
        "color": color,
        "has_apple_health": latest is not None,
        "latest_wellness_date": latest["date_key"] if latest else None,
        "components": components,
    }


def build_dashboard_summary(
    activities: List[Dict[str, Any]],
    wellness_days: List[Dict[str, Any]],
    settings: Dict[str, str],
) -> Dict[str, Any]:
    """Aggregates all KPIs, predictions, readiness, and time-series for the main dashboard."""
    threshold_pace = float(settings.get("threshold_pace_sec") or 275)
    load_data = compute_training_load_series(activities, days=60)
    readiness = compute_readiness(wellness_days, load_data, settings)
    vdot, vdot_source = estimate_athlete_vdot(activities, wellness_days, threshold_pace)
    paces = vdot_training_paces(vdot)

    predictions = {
        "5k": format_race_time(predict_race_time_sec(vdot, 5000)),
        "10k": format_race_time(predict_race_time_sec(vdot, 10000)),
        "half_marathon": format_race_time(predict_race_time_sec(vdot, 21097.5)),
        "marathon": format_race_time(predict_race_time_sec(vdot, 42195)),
    }

    # Last 30 days running totals
    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
    recent_runs = [
        a for a in activities
        if a.get("date_key", "") >= cutoff_30 and "run" in str(a.get("sport_type", "")).lower()
    ]
    km_30d = round(sum(float(a.get("distance_m") or 0) for a in recent_runs) / 1000.0, 1)
    runs_30d = len(recent_runs)
    avg_pace_30d = (
        sum(float(a.get("moving_time_s") or 0) for a in recent_runs) / max(0.1, km_30d)
        if km_30d > 0
        else 0
    )

    # Workout mix last 30 days
    mix: Dict[str, int] = {"recovery": 0, "easy": 0, "tempo": 0, "intervals": 0, "long": 0, "race": 0}
    for r in recent_runs:
        cat = r.get("workout_category", "easy")
        mix[cat] = mix.get(cat, 0) + 1

    latest_wellness = get_latest_valid_wellness(wellness_days)

    return {
        "readiness": readiness,
        "load": load_data,
        "vdot": vdot,
        "vdot_source": vdot_source,
        "paces": paces,
        "race_predictions": predictions,
        "stats_30d": {
            "km": km_30d,
            "runs": runs_30d,
            "avg_pace": format_pace(avg_pace_30d) if avg_pace_30d else "--:--",
            "workout_mix": mix,
        },
        "latest_wellness": latest_wellness,
        "wellness_series": wellness_days[-30:],
        "weekly_goal_km": float(settings.get("weekly_goal_km") or 40),
    }
