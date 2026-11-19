"""Periodized Road Running Race Plan Generator (5K, 10K, Half Marathon, Marathon) + Garmin Stress Adaptation."""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.database import db
from backend.services.analytics import (
    DISTANCE_MAP_KM,
    build_dashboard_summary,
    compute_vdot,
    estimate_athlete_vdot,
    format_pace,
    format_race_time,
    predict_race_time_sec,
    vdot_training_paces,
)
from backend.services.coach_engine import _call_gemini


DISTANCE_LABELS = {
    "5k": "5 km",
    "10k": "10 km",
    "half_marathon": "Mezza Maratona (21.1 km)",
    "marathon": "Maratona (42.2 km)",
}

# Peak long run km targets per distance
PEAK_LONG_RUN_KM = {
    "5k": 14.0,
    "10k": 18.0,
    "half_marathon": 22.0,
    "marathon": 34.0,
}

# Suggested peak weekly km ceiling multiplier
PEAK_WEEKLY_MULTIPLIER = {
    "5k": 1.25,
    "10k": 1.35,
    "half_marathon": 1.45,
    "marathon": 1.65,
}


def _select_training_days(days_per_week: int, long_run_day: int) -> Dict[str, int]:
    """
    Assigns optimal non-consecutive quality days relative to the chosen long_run_day (0=Mon..6=Sun).
    Returns mapping of role -> weekday index.
    """
    # Place key quality session 3 days before long run, secondary quality 5 days before
    q1 = (long_run_day - 3) % 7  # e.g., Thursday if Sunday long run
    q2 = (long_run_day - 5) % 7  # e.g., Tuesday if Sunday long run
    easy1 = (long_run_day - 1) % 7  # Saturday shakeout / easy
    easy2 = (long_run_day - 4) % 7  # Wednesday
    easy3 = (long_run_day - 2) % 7  # Friday

    if days_per_week == 3:
        return {"quality1": q2, "quality2": q1, "long": long_run_day}
    if days_per_week == 4:
        return {"quality1": q2, "easy1": easy2, "quality2": q1, "long": long_run_day}
    if days_per_week == 5:
        return {"quality1": q2, "easy1": easy2, "quality2": q1, "easy2": easy1, "long": long_run_day}
    return {
        "quality1": q2,
        "easy1": easy2,
        "quality2": q1,
        "easy2": easy3,
        "easy3": easy1,
        "long": long_run_day,
    }


def _phase_for_week(week_idx: int, total_weeks: int) -> str:
    """Returns periodization phase name in Italian for 1-based week_idx."""
    if week_idx == total_weeks:
        return "Settimana Gara"
    if total_weeks >= 4 and week_idx == total_weeks - 1:
        return "Scarico / Taper"
    if total_weeks >= 12 and week_idx == total_weeks - 2:
        return "Scarico / Taper"
    progress = week_idx / max(1, total_weeks)
    if progress <= 0.35:
        return "Costruzione Base"
    if progress <= 0.72:
        return "Sviluppo Specifico"
    return "Picco Gara"


def _build_quality_session(
    distance_type: str,
    phase: str,
    week_idx: int,
    slot: int,
    paces: Dict[str, Dict[str, Any]],
    race_pace_str: str,
    is_cutback: bool,
) -> Dict[str, Any]:
    """Generates specific road-running quality workout details."""
    easy_p = paces["easy"]["range"]
    thresh_p = paces["threshold"]["range"]
    int_p = paces["interval"]["range"]
    mar_p = paces["marathon"]["range"]

    if is_cutback or phase == "Scarico / Taper":
        return {
            "workout_type": "tempo",
            "title": "Richiamo Ritmo Gara (Scarico)",
            "description": (
                f"2 km riscaldamento ({easy_p}) + 3x1 km a ritmo gara ({race_pace_str}) "
                f"con 2 min di recupero lento + 2 km defaticamento. Gambe fresche!"
            ),
            "target_distance_km": 8.0,
            "target_pace_range": race_pace_str,
            "target_hr_zone": "Z3 - Z4 controllata",
            "intensity": "moderate",
        }

    if slot == 1:
        # Primary speed / VO2max / intervals day
        if phase == "Costruzione Base":
            reps = 6 + (week_idx % 3)
            return {
                "workout_type": "intervals",
                "title": f"Fartlek Aerobico ({reps}x2 min)",
                "description": (
                    f"2 km riscaldamento ({easy_p}) + {reps}x(2 min brillanti a {thresh_p} / "
                    f"2 min corsa facile) + 2 km defaticamento."
                ),
                "target_distance_km": 9.0,
                "target_pace_range": thresh_p,
                "target_hr_zone": "Z3 - Z4",
                "intensity": "moderate",
            }
        if distance_type in ("5k", "10k"):
            reps = 5 if distance_type == "5k" else 6
            return {
                "workout_type": "intervals",
                "title": f"Ripetute VO2max ({reps}x1000m)",
                "description": (
                    f"2 km riscaldamento + {reps}x1000m a {int_p} con 2'30\" di recupero in jogging + 1.5 km defaticamento."
                ),
                "target_distance_km": round(3.5 + reps * 1.2, 1),
                "target_pace_range": int_p,
                "target_hr_zone": "Z4 - Z5",
                "intensity": "hard",
            }
        else:
            reps = 4 if phase == "Sviluppo Specifico" else 5
            return {
                "workout_type": "intervals",
                "title": f"Ripetute Lunghe ({reps}x1600m Soglia)",
                "description": (
                    f"2 km riscaldamento + {reps}x1.6 km a ritmo soglia ({thresh_p}) "
                    f"con 90 sec di recupero lento + 2 km defaticamento."
                ),
                "target_distance_km": round(4.0 + reps * 1.8, 1),
                "target_pace_range": thresh_p,
                "target_hr_zone": "Z4",
                "intensity": "hard",
            }
    else:
        # Secondary threshold / race-pace tempo day
        if distance_type == "marathon":
            tempo_km = 8 if phase == "Costruzione Base" else (11 if phase == "Sviluppo Specifico" else 13)
            return {
                "workout_type": "tempo",
                "title": f"Medio a Ritmo Maratona ({tempo_km} km)",
                "description": (
                    f"2 km riscaldamento ({easy_p}) + {tempo_km} km continui a ritmo maratona ({mar_p}) "
                    "+ 1.5 km defaticamento."
                ),
                "target_distance_km": round(tempo_km + 3.5, 1),
                "target_pace_range": mar_p,
                "target_hr_zone": "Z3",
                "intensity": "moderate",
            }
        else:
            tempo_km = 5 if distance_type == "5k" else (7 if distance_type == "10k" else 9)
            return {
                "workout_type": "tempo",
                "title": f"Tempo Run / Soglia ({tempo_km} km)",
                "description": (
                    f"2 km riscaldamento ({easy_p}) + {tempo_km} km continui a ritmo soglia ({thresh_p}) "
                    "+ 2 km defaticamento. Cerca fluidità senza andare in affanno."
                ),
                "target_distance_km": round(tempo_km + 4.0, 1),
                "target_pace_range": thresh_p,
                "target_hr_zone": "Z4 (84-89% FC max)",
                "intensity": "hard",
            }


async def generate_race_plan(
    name: str,
    distance_type: str,
    race_date_str: str,
    target_time_sec: Optional[int],
    days_per_week: int,
    long_run_day: int,
    current_weekly_km: Optional[float],
    notes: str = "",
    use_ai: bool = True,
) -> Dict[str, Any]:
    """Creates a full week-by-week periodized training plan and persists it to SQLite."""
    distance_km = DISTANCE_MAP_KM[distance_type]
    today = date.today()
    race_date = datetime.strptime(race_date_str, "%Y-%m-%d").date()

    days_until_race = (race_date - today).days
    if days_until_race < 14:
        raise ValueError("La data della gara deve essere almeno tra 2 settimane per creare un piano efficace.")
    if days_until_race > 240:
        # Cap plan length to 24 weeks starting closer to the race if super far out, or start next Monday
        pass

    activities = db.get_activities(limit=200)
    garmin_days = db.get_garmin_daily(days=30)
    settings = db.get_settings()
    threshold_pace = float(settings.get("threshold_pace_sec") or 275)
    current_vdot, _ = estimate_athlete_vdot(activities, garmin_days, threshold_pace)

    # Auto-recommend target time if not provided (realistic 3-5% progression over current VDOT)
    if not target_time_sec:
        projected_vdot = min(75.0, current_vdot + min(2.5, max(0.8, days_until_race / 55.0)))
        target_time_sec = predict_race_time_sec(projected_vdot, distance_km * 1000.0)

    target_vdot = compute_vdot(distance_km * 1000.0, float(target_time_sec)) or current_vdot
    # Train primarily using a safe blend of current and target VDOT so paces don't cause injury
    training_vdot = round(current_vdot * 0.55 + target_vdot * 0.45, 1)
    paces = vdot_training_paces(training_vdot)
    race_pace_sec = target_time_sec / distance_km
    race_pace_str = f"{format_pace(race_pace_sec)} /km"

    # Estimate baseline weekly km from history if omitted
    if current_weekly_km is None:
        summary = build_dashboard_summary(activities, garmin_days, settings)
        vols = [w["km"] for w in summary["load"]["weekly_volumes"][-4:] if w["km"] > 0]
        base_km = (sum(vols) / len(vols)) if vols else float(settings.get("weekly_goal_km") or 32)
        base_km = max(18.0, min(90.0, base_km))
    else:
        base_km = float(current_weekly_km)

    # Plan spans from Monday of current week (or today) up to race_date
    monday_this_week = today - timedelta(days=today.weekday())
    monday_race_week = race_date - timedelta(days=race_date.weekday())
    total_weeks = max(3, min(24, ((monday_race_week - monday_this_week).days // 7) + 1))
    plan_start_monday = monday_race_week - timedelta(days=(total_weeks - 1) * 7)

    peak_weekly_km = min(
        110.0,
        max(base_km * 1.15, min(base_km * PEAK_WEEKLY_MULTIPLIER[distance_type], PEAK_LONG_RUN_KM[distance_type] * 2.4)),
    )
    day_roles = _select_training_days(days_per_week, long_run_day)
    role_by_day = {wd: role for role, wd in day_roles.items()}

    workouts: List[Dict[str, Any]] = []
    for w_idx in range(1, total_weeks + 1):
        week_monday = plan_start_monday + timedelta(days=(w_idx - 1) * 7)
        phase = _phase_for_week(w_idx, total_weeks)
        is_cutback = (w_idx % 4 == 0) and (w_idx < total_weeks - 1)

        # Compute weekly target volume progression
        if phase == "Settimana Gara":
            week_km = round(peak_weekly_km * 0.48, 1)
        elif phase == "Scarico / Taper":
            week_km = round(peak_weekly_km * 0.72, 1)
        else:
            build_ratio = min(1.0, w_idx / max(1, total_weeks - 2))
            week_km = base_km + (peak_weekly_km - base_km) * build_ratio
            if is_cutback:
                week_km *= 0.80
            week_km = round(week_km, 1)

        # Long run distance progression (never exceed 48% of weekly volume)
        max_lr = min(PEAK_LONG_RUN_KM[distance_type], round(week_km * 0.48, 1))
        min_lr = max(6.0, min(base_km * 0.34, max_lr * 0.65))
        if phase == "Settimana Gara":
            lr_km = distance_km
        elif phase == "Scarico / Taper":
            lr_km = round(max(6.0, max_lr * 0.62), 1)
        else:
            lr_ratio = min(1.0, w_idx / max(1, total_weeks - 2))
            lr_km = min_lr + (max_lr - min_lr) * lr_ratio
            if is_cutback:
                lr_km *= 0.80
            lr_km = round(max(6.0, min(max_lr, lr_km)), 1)

        # Precompute weekly quality distances so easy days fill the true remaining volume
        q1_spec = _build_quality_session(distance_type, phase, w_idx, 1, paces, race_pace_str, is_cutback)
        q2_spec = _build_quality_session(distance_type, phase, w_idx, 2, paces, race_pace_str, is_cutback)
        quality_total_km = float(q1_spec["target_distance_km"]) + float(q2_spec["target_distance_km"])

        for dow in range(7):
            d = week_monday + timedelta(days=dow)
            if d < today or d > race_date:
                continue

            days_before = (race_date - d).days
            if days_before == 0:
                workouts.append(
                    {
                        "week_number": w_idx,
                        "phase": "Settimana Gara",
                        "scheduled_date": d.isoformat(),
                        "day_of_week": dow,
                        "workout_type": "race",
                        "title": f"GARA: {name} ({DISTANCE_LABELS[distance_type]})",
                        "description": (
                            f"Obiettivo: {format_race_time(target_time_sec)} (passo medio {race_pace_str}). "
                            "Parti controllato nei primi 2 km, idratati ai ristori e accelera nel finale!"
                        ),
                        "target_distance_km": round(distance_km, 1),
                        "target_duration_min": int(round(target_time_sec / 60.0)),
                        "target_pace_range": race_pace_str,
                        "target_hr_zone": "Ritmo Gara",
                        "intensity": "hard",
                    }
                )
                continue

            # Final 6 days before race ALWAYS follow pre-race taper (even if race is Monday/Tuesday!)
            if 1 <= days_before <= 6:
                if days_before == 1:
                    workouts.append(
                        {
                            "week_number": w_idx,
                            "phase": phase,
                            "scheduled_date": d.isoformat(),
                            "day_of_week": dow,
                            "workout_type": "recovery",
                            "title": "Shakeout Pre-Gara (20 min)",
                            "description": f"3-4 km facilissimi ({paces['recovery']['range']}) + 4 allunghi sciolti da 80m. Poi riposo e carboidrati!",
                            "target_distance_km": 4.0,
                            "target_duration_min": 22,
                            "target_pace_range": paces["recovery"]["range"],
                            "target_hr_zone": "Z1 - Z2",
                            "intensity": "easy",
                        }
                    )
                elif days_before == 3:
                    workouts.append(
                        {
                            "week_number": w_idx,
                            "phase": phase,
                            "scheduled_date": d.isoformat(),
                            "day_of_week": dow,
                            "workout_type": "tempo",
                            "title": "Richiamo Ritmo Gara (6 km)",
                            "description": f"2 km riscaldamento + 2 km a ritmo gara ({race_pace_str}) + 2 km facili per tenere vive le gambe.",
                            "target_distance_km": 6.0,
                            "target_duration_min": 32,
                            "target_pace_range": race_pace_str,
                            "target_hr_zone": "Z3",
                            "intensity": "moderate",
                        }
                    )
                elif days_before == 5:
                    workouts.append(
                        {
                            "week_number": w_idx,
                            "phase": phase,
                            "scheduled_date": d.isoformat(),
                            "day_of_week": dow,
                            "workout_type": "easy",
                            "title": "Corsa Facile Leggera",
                            "description": f"6 km in totale scioltezza ({paces['easy']['range']}).",
                            "target_distance_km": 6.0,
                            "target_duration_min": 34,
                            "target_pace_range": paces["easy"]["range"],
                            "target_hr_zone": "Z2",
                            "intensity": "easy",
                        }
                    )
                else:
                    workouts.append(
                        {
                            "week_number": w_idx,
                            "phase": phase,
                            "scheduled_date": d.isoformat(),
                            "day_of_week": dow,
                            "workout_type": "rest",
                            "title": "Riposo & Recupero",
                            "description": "Riposo completo, sonno 8h, idratazione e mobilità leggera.",
                            "target_distance_km": 0,
                            "target_duration_min": 0,
                            "target_pace_range": "-",
                            "target_hr_zone": "Riposo",
                            "intensity": "rest",
                        }
                    )
                continue

            role = role_by_day.get(dow)
            if not role:
                workouts.append(
                    {
                        "week_number": w_idx,
                        "phase": phase,
                        "scheduled_date": d.isoformat(),
                        "day_of_week": dow,
                        "workout_type": "rest",
                        "title": "Riposo o Mobilità / Core",
                        "description": "Giornata di recupero attivo: 15 min stretching, core o camminata leggera.",
                        "target_distance_km": 0,
                        "target_duration_min": 0,
                        "target_pace_range": "-",
                        "target_hr_zone": "Riposo",
                        "intensity": "rest",
                    }
                )
            elif role == "long":
                est_min = int(round((lr_km * paces["easy"]["max_sec"]) / 60.0))
                if phase == "Picco Gara" and distance_type in ("half_marathon", "marathon") and not is_cutback:
                    title = f"Lungo Specifico con Finale a Ritmo Gara ({lr_km} km)"
                    desc = (
                        f"Primi {round(lr_km * 0.72, 1)} km in controllo ({paces['easy']['range']}), "
                        f"ultimi {round(lr_km * 0.28, 1)} km in progressione a ritmo gara ({race_pace_str}). "
                        "Prova integrazione (gel/acqua) come in gara."
                    )
                else:
                    title = f"Lungo Aerobico ({lr_km} km)"
                    desc = (
                        f"Corri rilassato tra {paces['easy']['range']}. Mantieni FC in Zona 2 per massimizzare "
                        "capillarizzazione e resistenza lipidica."
                    )
                workouts.append(
                    {
                        "week_number": w_idx,
                        "phase": phase,
                        "scheduled_date": d.isoformat(),
                        "day_of_week": dow,
                        "workout_type": "long",
                        "title": title,
                        "description": desc,
                        "target_distance_km": lr_km,
                        "target_duration_min": est_min,
                        "target_pace_range": paces["easy"]["range"],
                        "target_hr_zone": "Z2 (68-78% FC max)",
                        "intensity": "moderate",
                    }
                )
            elif role in ("quality1", "quality2"):
                q = q1_spec if role == "quality1" else q2_spec
                est_min = int(round((q["target_distance_km"] * paces["threshold"]["max_sec"]) / 60.0))
                workouts.append(
                    {
                        "week_number": w_idx,
                        "phase": phase,
                        "scheduled_date": d.isoformat(),
                        "day_of_week": dow,
                        "workout_type": q["workout_type"],
                        "title": q["title"],
                        "description": q["description"],
                        "target_distance_km": q["target_distance_km"],
                        "target_duration_min": est_min,
                        "target_pace_range": q["target_pace_range"],
                        "target_hr_zone": q["target_hr_zone"],
                        "intensity": q["intensity"],
                    }
                )
            else:
                # Easy / recovery days split true remaining weekly volume
                easy_slots = max(1, days_per_week - 3)
                remaining = max(4.5, (week_km - lr_km - quality_total_km) / easy_slots)
                easy_km = round(max(4.5, min(14.0, remaining)), 1)
                is_rec = role == "easy1"
                p_info = paces["recovery"] if is_rec else paces["easy"]
                est_min = int(round((easy_km * p_info["max_sec"]) / 60.0))
                workouts.append(
                    {
                        "week_number": w_idx,
                        "phase": phase,
                        "scheduled_date": d.isoformat(),
                        "day_of_week": dow,
                        "workout_type": "recovery" if is_rec else "easy",
                        "title": f"Corsa Rigenerante ({easy_km} km)" if is_rec else f"Corsa Facile + Allunghi ({easy_km} km)",
                        "description": (
                            f"Ritmo molto facile ({p_info['range']}), respirazione sempre nasale/conversazionale."
                            if is_rec
                            else f"{easy_km} km facili ({p_info['range']}) + 4x100m allunghi fluidi alla fine con recupero camminando."
                        ),
                        "target_distance_km": easy_km,
                        "target_duration_min": est_min,
                        "target_pace_range": p_info["range"],
                        "target_hr_zone": "Z1 - Z2" if is_rec else "Z2",
                        "intensity": "easy",
                    }
                )

    # Optional Gemini strategic overview
    ai_summary = ""
    if use_ai and settings.get("gemini_api_key", "").strip():
        prompt = f"""Crea un breve riepilogo strategico (max 150 parole, in italiano) per questo piano di allenamento:
- Gara: {name} ({DISTANCE_LABELS[distance_type]}) il {race_date_str} (tra {total_weeks} settimane)
- Obiettivo tempo: {format_race_time(target_time_sec)} (passo gara {race_pace_str})
- VDOT attuale: {current_vdot} -> Target VDOT: {target_vdot}
- Volume settimanale iniziale: {base_km:.0f} km -> Picco: {peak_weekly_km:.0f} km ({days_per_week} gg/settimana)
- Note atleta: {notes or 'Nessuna'}

Dai 3 consigli chiave su: 1) gestione dei ritmi, 2) come usare Stress/HRV Garmin durante la preparazione, 3) strategia mentale/integrazione per il giorno gara."""
        ai_summary = (
            await _call_gemini(
                prompt,
                system_instruction="Sei RunPulse AI, allenatore esperto di corsa su strada. Rispondi in italiano chiaro ed essenziale.",
            )
            or ""
        )

    if not ai_summary:
        ai_summary = (
            f"Piano periodizzato di **{total_weeks} settimane** verso **{name}** "
            f"(target **{format_race_time(target_time_sec)}**, passo gara **{race_pace_str}**). "
            f"Basato sul tuo VDOT stimato (**{current_vdot} → {target_vdot}**) con progressione graduale "
            f"da ~{base_km:.0f} km a ~{peak_weekly_km:.0f} km/settimana, scarico ogni 4ª settimana e taper finale. "
            "Usa il pulsante **Adatta allo stress Garmin** ogni volta che HRV o Body Battery scendono."
        )

    goal_record = {
        "name": name,
        "distance_type": distance_type,
        "distance_km": distance_km,
        "race_date": race_date_str,
        "target_time_sec": int(target_time_sec),
        "current_vdot": current_vdot,
        "target_vdot": target_vdot,
        "days_per_week": days_per_week,
        "long_run_day": long_run_day,
        "current_weekly_km": round(base_km, 1),
        "notes": notes,
        "ai_summary": ai_summary,
        "paces": {**paces, "race_pace": race_pace_str},
    }
    goal_id = db.create_race_goal(goal_record, workouts)
    db.auto_link_workouts_to_activities(goal_id)
    return db.get_goal_with_workouts(goal_id) or {}


def adapt_plan_for_recovery(goal_id: int) -> Dict[str, Any]:
    """
    Inspects current Garmin stress / HRV / Body Battery / Readiness and dynamically
    adapts upcoming workouts in the next 4 days to prevent overtraining or injury.
    """
    goal = db.get_goal_with_workouts(goal_id)
    if not goal:
        raise ValueError("Piano gara non trovato.")

    activities = db.get_activities(limit=120)
    garmin_days = db.get_garmin_daily(days=14)
    settings = db.get_settings()
    summary = build_dashboard_summary(activities, garmin_days, settings)
    readiness = summary["readiness"]
    score = readiness["score"]
    latest_g = summary.get("latest_garmin") or {}
    stress = latest_g.get("stress_avg")
    acwr = float(summary["load"]["current"].get("acwr") or 1.0)
    paces = summary["paces"]

    today = date.today()
    horizon = today + timedelta(days=4)
    adapted_count = 0
    messages: List[str] = []

    if score >= 65 and acwr <= 1.32:
        return {
            "adapted_count": 0,
            "readiness_score": score,
            "message": f"Nessuna riduzione necessaria! Readiness ottima ({score}/100) e carico bilanciato (ACWR {acwr:.2f}). Segui il piano regolare.",
            "goal": goal,
        }

    reason_tag = f"Adattato automaticamente (Readiness {score}/100"
    if stress is not None:
        reason_tag += f", Stress Garmin {stress}"
    if acwr > 1.32:
        reason_tag += f", ACWR {acwr:.2f}"
    reason_tag += ")"

    for w in goal.get("workouts", []):
        if w["completed"] or w["workout_type"] in ("rest", "race") or w.get("adapted_reason"):
            continue
        w_date = datetime.strptime(w["scheduled_date"], "%Y-%m-%d").date()
        if not (today <= w_date <= horizon):
            continue

        if score < 42:
            if w["intensity"] in ("hard", "moderate") and w_date <= today + timedelta(days=1):
                db.update_plan_workout(
                    w["id"],
                    {
                        "workout_type": "rest",
                        "title": "Riposo Forzato (Recupero Garmin)",
                        "description": "Sostituito automaticamente per alto stress / bassa Body Battery. Priorità a sonno e idratazione.",
                        "target_distance_km": 0,
                        "target_duration_min": 0,
                        "target_pace_range": "-",
                        "target_hr_zone": "Riposo",
                        "intensity": "rest",
                        "adapted_reason": reason_tag,
                    },
                )
                adapted_count += 1
                messages.append(f"{w['scheduled_date']}: '{w['title']}' convertito in Riposo.")
            elif w["intensity"] == "hard":
                # Also downgrade hard sessions at +2..+4 days during severe fatigue
                new_km = round(max(5.0, float(w["target_distance_km"]) * 0.75), 1)
                new_min = int(round((new_km * paces["easy"]["max_sec"]) / 60.0))
                db.update_plan_workout(
                    w["id"],
                    {
                        "workout_type": "easy",
                        "title": f"Corsa Facile Z2 ({new_km} km — ex qualità)",
                        "description": f"Declassata a corsa aerobica controllata ({paces['easy']['range']}) per proteggere il recupero.",
                        "target_distance_km": new_km,
                        "target_duration_min": new_min,
                        "target_pace_range": paces["easy"]["range"],
                        "target_hr_zone": "Z2 (68-78% FC max)",
                        "intensity": "easy",
                        "adapted_reason": reason_tag,
                    },
                )
                adapted_count += 1
                messages.append(f"{w['scheduled_date']}: '{w['title']}' declassata a Corsa Facile Z2.")
            elif w["intensity"] == "easy":
                new_km = round(max(4.0, float(w["target_distance_km"]) * 0.65), 1)
                new_min = int(round((new_km * paces["recovery"]["max_sec"]) / 60.0))
                db.update_plan_workout(
                    w["id"],
                    {
                        "workout_type": "recovery",
                        "title": f"Rigenerante Ridotta ({new_km} km)",
                        "description": f"Volume ridotto del 35% per recupero. Corri lentissimo ({paces['recovery']['range']}).",
                        "target_distance_km": new_km,
                        "target_duration_min": new_min,
                        "target_pace_range": paces["recovery"]["range"],
                        "target_hr_zone": "Z1 - Z2 bassa",
                        "intensity": "easy",
                        "adapted_reason": reason_tag,
                    },
                )
                adapted_count += 1
                messages.append(f"{w['scheduled_date']}: volume ridotto a {new_km} km.")
        else:
            if w["intensity"] == "hard":
                new_km = round(max(6.0, float(w["target_distance_km"]) * 0.8), 1)
                new_min = int(round((new_km * paces["easy"]["max_sec"]) / 60.0))
                db.update_plan_workout(
                    w["id"],
                    {
                        "workout_type": "easy",
                        "title": f"Corsa Facile Z2 ({new_km} km — ex qualità)",
                        "description": (
                            f"Seduta di qualità convertita in corsa aerobica controllata ({paces['easy']['range']}) "
                            "per proteggere il recupero e prevenire sovraccarico."
                        ),
                        "target_distance_km": new_km,
                        "target_duration_min": new_min,
                        "target_pace_range": paces["easy"]["range"],
                        "target_hr_zone": "Z2 (68-78% FC max)",
                        "intensity": "easy",
                        "adapted_reason": reason_tag,
                    },
                )
                adapted_count += 1
                messages.append(f"{w['scheduled_date']}: '{w['title']}' declassata a Corsa Facile Z2.")

    updated_goal = db.get_goal_with_workouts(goal_id)
    summary_msg = (
        f"Adattati {adapted_count} allenamenti nei prossimi 4 giorni in base ai tuoi dati Apple Watch & recupero."
        if adapted_count > 0
        else f"Readiness {score}/100: nessun allenamento intenso previsto nei prossimi 4 giorni da modificare."
    )
    return {
        "adapted_count": adapted_count,
        "readiness_score": score,
        "message": summary_msg,
        "details": messages,
        "goal": updated_goal,
    }
