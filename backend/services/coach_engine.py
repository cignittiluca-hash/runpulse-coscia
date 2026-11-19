"""Hybrid AI + Sports-Science Running Coach Engine."""
import asyncio
import hashlib
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from backend.database import db
from backend.services.analytics import (
    build_dashboard_summary,
    format_duration,
    format_hm,
    format_pace,
)


async def _call_gemini(prompt: str, system_instruction: str = "", thinking_budget: int = 1024) -> Optional[str]:
    """Calls Gemini REST API directly via httpx (100% Python 3.9 compatible)."""
    text, _ = await _call_gemini_chat(
        [{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction=system_instruction,
        thinking_budget=thinking_budget,
    )
    return text


_cached_discovered_models: Dict[str, List[str]] = {}


def _sanitize_error(msg: str, api_key: str) -> str:
    if api_key and api_key in msg:
        return msg.replace(api_key, "***")
    return msg


def _normalize_gemini_contents(contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensures Gemini multi-turn contents always start with 'user' and strictly alternate user/model."""
    cleaned: List[Dict[str, Any]] = []
    for item in contents:
        role = item.get("role")
        parts = item.get("parts") or []
        text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
        if not text:
            continue
        # Skip previous error notices from polluting AI history
        if role == "model" and (text.startswith("⚠️") or text.startswith("⏳")):
            continue
        if not cleaned and role != "user":
            continue
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            cleaned.append({"role": role, "parts": [{"text": text}]})
    return cleaned


async def _discover_gemini_models(client: httpx.AsyncClient, api_key: str) -> List[str]:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    if key_hash in _cached_discovered_models:
        return _cached_discovered_models[key_hash]
    try:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return []
        models = resp.json().get("models") or []
        valid = []
        for m in models:
            methods = m.get("supportedGenerationMethods") or []
            name = str(m.get("name") or "").replace("models/", "")
            if "generateContent" in methods and "gemini" in name and "embedding" not in name and "tts" not in name and "image" not in name:
                if "flash" in name:
                    valid.append(name)
        valid.sort(key=lambda n: ("3." not in n, "lite" in n, n))
        _cached_discovered_models[key_hash] = valid[:5]
        return _cached_discovered_models[key_hash]
    except Exception:
        return []


async def _call_gemini_chat(
    contents: List[Dict[str, Any]],
    system_instruction: str = "",
    thinking_budget: int = 2048,
) -> tuple:
    """Multi-turn Gemini REST API call with x-goog-api-key header, turn normalization, thinking, and 503 fallback."""
    settings = db.get_settings()
    api_key = settings.get("gemini_api_key", "").strip()
    if not api_key:
        return None, "Chiave API Gemini non configurata."
    norm_contents = _normalize_gemini_contents(contents)
    if not norm_contents:
        return None, "Messaggio vuoto."

    primary_model = settings.get("gemini_model", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    if primary_model in ("gemini-2.5-flash", "gemini-2.0-flash"):
        primary_model = "gemini-3.8-flash"

    candidate_models = [primary_model]
    for fb in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
        if fb not in candidate_models:
            candidate_models.append(fb)

    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    last_error = "Nessuna risposta da Gemini."
    async with httpx.AsyncClient(timeout=60.0) as client:
        discovered_loaded = False
        idx = 0
        while idx < len(candidate_models):
            model = candidate_models[idx]
            idx += 1
            attempts = 2 if idx == 1 else 1
            for _ in range(attempts):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                gen_config: Dict[str, Any] = {
                    "temperature": 0.65,
                    "maxOutputTokens": 4096,
                }
                if ("2.5" in model or "3." in model) and "lite" not in model and thinking_budget > 0:
                    gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

                payload: Dict[str, Any] = {
                    "contents": norm_contents,
                    "generationConfig": gen_config,
                }
                if system_instruction:
                    payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 400 and "thinking" in resp.text.lower() and "thinkingConfig" in gen_config:
                        gen_config.pop("thinkingConfig", None)
                        resp = await client.post(url, headers=headers, json=payload)

                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates") or []
                        if candidates:
                            parts = (candidates[0].get("content") or {}).get("parts") or []
                            answer_parts = [p.get("text", "") for p in parts if p.get("text") and not p.get("thought")]
                            text = "\n".join(answer_parts).strip()
                            if text:
                                return text, None
                        last_error = "Risposta vuota da Gemini."
                        continue

                    try:
                        err_obj = resp.json().get("error", {})
                        err_msg = err_obj.get("message") or resp.text[:240]
                    except Exception:
                        err_msg = resp.text[:240]
                    last_error = _sanitize_error(f"Errore Gemini API ({resp.status_code}): {err_msg}", api_key)

                    if resp.status_code in (500, 502, 503, 504):
                        await asyncio.sleep(1.5)
                        continue
                    if resp.status_code == 404:
                        if not discovered_loaded:
                            discovered_loaded = True
                            for dm in await _discover_gemini_models(client, api_key):
                                if dm not in candidate_models:
                                    candidate_models.append(dm)
                        break
                    return None, last_error
                except httpx.TimeoutException:
                    last_error = "Timeout nella richiesta a Gemini (riprova tra qualche secondo)."
                    await asyncio.sleep(1.0)
                except Exception as exc:
                    return None, _sanitize_error(f"Errore di rete verso Gemini: {exc}", api_key)

            if idx == len(candidate_models) and not discovered_loaded:
                discovered_loaded = True
                for dm in await _discover_gemini_models(client, api_key):
                    if dm not in candidate_models:
                        candidate_models.append(dm)

    return None, last_error


async def test_gemini_connection() -> Dict[str, Any]:
    text, err = await _call_gemini_chat(
        [{"role": "user", "parts": [{"text": "Rispondi solo con: OK Calippo connesso a Gemini!"}]}],
        thinking_budget=0,
    )
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "reply": text, "model": db.get_setting("gemini_model", "gemini-3.8-flash")}


def _build_deterministic_daily_advice(
    summary: Dict[str, Any],
    today_plan_workout: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    readiness = summary["readiness"]
    score = readiness["score"]
    latest_g = summary.get("latest_garmin") or {}
    load = summary["load"]["current"]
    paces = summary["paces"]

    stress = latest_g.get("stress_avg")
    bb_max = latest_g.get("body_battery_max")
    bb_cur = latest_g.get("body_battery_current")
    bb = bb_max if bb_max is not None else bb_cur
    hrv = latest_g.get("hrv_avg")
    sleep_sec = latest_g.get("sleep_seconds")
    sleep_h = (float(sleep_sec) / 3600.0) if sleep_sec else None
    sleep_str = format_hm(sleep_sec) if sleep_sec else None
    acwr = float(load.get("acwr") or 1.0)
    tsb = float(load.get("tsb") or 0.0)

    reasons: List[str] = []
    warnings: List[str] = []

    if stress is not None:
        if stress >= 48:
            warnings.append(f"Stress Garmin alto ({stress}/100): il sistema nervoso è affaticato.")
        elif stress <= 28:
            reasons.append(f"Stress Garmin molto basso ({stress}/100): ottimo recupero autonomico.")
        else:
            reasons.append(f"Stress Garmin nella norma ({stress}/100).")

    if bb is not None:
        bb_note = f"{bb_cur}/100 (picco {bb_max})" if (bb_cur is not None and bb_max is not None and bb_cur != bb_max) else f"{bb}/100"
        if bb < 50:
            warnings.append(f"Body Battery bassa ({bb_note}): riserva energetica ridotta.")
        elif bb >= 75:
            reasons.append(f"Body Battery alta ({bb_note}): ottima carica per allenarti.")

    if sleep_h is not None and sleep_str:
        if sleep_h < 6.3:
            warnings.append(f"Sonno breve ({sleep_str}): evita sedute lattacide o ad alto impatto.")
        elif sleep_h >= 7.2:
            reasons.append(f"Buon riposo notturno ({sleep_str}).")

    if hrv is not None:
        reasons.append(f"HRV notturna a {round(hrv)} ms ({latest_g.get('hrv_status') or 'monitorata'}).")

    if acwr > 1.35:
        warnings.append(f"Rapporto carico acuto/cronico elevato (ACWR {acwr:.2f}): rischio sovraccarico.")
    elif tsb < -18:
        warnings.append(f"Fatica cumulata significativa (TSB {tsb:+.0f}): serve una giornata più leggera.")
    else:
        reasons.append(f"Equilibrio carico buono (Fitness {load.get('ctl', 0):.0f}, Forma {tsb:+.0f}).")

    # Decide recommended session
    if score >= 78 and acwr <= 1.32:
        action = "Allenamento di Qualità Consigliato"
        badge = "VIA LIBERA"
        workout_suggestion = (
            f"Ottimo giorno per una seduta chiave: Tempo Run a {paces['threshold']['range']} "
            f"oppure ripetute VO2max a {paces['interval']['range']}."
        )
        target_zone = "Z3 - Z4 (o Z5 per ripetute)"
        target_pace = paces["threshold"]["range"]
    elif score >= 58 and acwr <= 1.40:
        action = "Corsa Aerobica Facile (Zona 2)"
        badge = "MODERATO"
        workout_suggestion = (
            f"Mantieni il ritmo controllato tra {paces['easy']['range']} per 40-55 minuti. "
            "Costruisci base aerobica senza aggiungere stress."
        )
        target_zone = "Z2 (68-78% FC max)"
        target_pace = paces["easy"]["range"]
    elif score >= 40:
        action = "Corsa Rigenerante Breve o Cross-Training"
        badge = "SCARICO"
        workout_suggestion = (
            f"Riduci intensità e volume: massimo 25-35 min lentissimi ({paces['recovery']['range']}) "
            "oppure 30 min di bici/camminata + stretching."
        )
        target_zone = "Z1 - Z2 bassa (<72% FC max)"
        target_pace = paces["recovery"]["range"]
    else:
        action = "Riposo Completo & Recupero"
        badge = "STOP / RECUPERO"
        workout_suggestion = (
            "Oggi il corpo chiede recupero. Salta la corsa, punta a idratazione, mobilità leggera "
            "e almeno 8 ore di sonno per riportare su HRV e Body Battery."
        )
        target_zone = "Riposo"
        target_pace = "Nessuna corsa"

    # Cross-check with today's planned race workout if any
    plan_note = ""
    if today_plan_workout:
        w_title = today_plan_workout["title"]
        w_int = today_plan_workout.get("intensity", "easy")
        if w_int in ("hard", "moderate") and score < 55:
            plan_note = (
                f"Nel tuo piano gara oggi avresti '{w_title}', ma visti i dati Garmin ti consiglio di "
                "declassarla a corsa rigenerante o spostarla di 24-48 ore (puoi usare 'Adatta Piano')."
            )
        elif w_int == "rest":
            plan_note = f"Il tuo piano gara prevede già '{w_title}': scelta perfetta oggi."
        else:
            plan_note = f"In linea con il tuo piano gara di oggi: '{w_title}' ({today_plan_workout.get('target_pace_range') or target_pace})."

    return {
        "headline": action,
        "badge": badge,
        "readiness_score": score,
        "readiness_zone": readiness["zone"],
        "workout_suggestion": workout_suggestion,
        "target_zone": target_zone,
        "target_pace": target_pace,
        "plan_note": plan_note,
        "reasons": reasons,
        "warnings": warnings,
        "ai_narrative": "",
        "ai_powered": False,
    }


async def generate_daily_coach_advice(
    use_ai: bool = True,
    summary: Optional[Dict[str, Any]] = None,
    activities: Optional[List[Dict[str, Any]]] = None,
    active_goal: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = db.get_settings()
    if activities is None:
        activities = db.get_activities(limit=250)
    if summary is None:
        wellness_days = db.get_wellness_daily(days=30)
        summary = build_dashboard_summary(activities, wellness_days, settings)

    today_str = date.today().isoformat()
    today_workout = None
    if active_goal is None:
        active_goal = db.get_active_goal_with_workouts()
    if active_goal:
        today_workout = next(
            (w for w in active_goal.get("workouts", []) if w["scheduled_date"] == today_str),
            None,
        )

    advice = _build_deterministic_daily_advice(summary, today_workout)

    if use_ai and settings.get("gemini_api_key", "").strip():
        latest_w = summary.get("latest_wellness") or {}
        load = summary["load"]["current"]
        recent_runs = [a for a in activities if "run" in str(a.get("sport_type", "")).lower()][:5]
        runs_text = "\n".join(
            f"- {r['date_key']}: {r['name']} ({r['distance_m']/1000:.1f} km, passo {format_pace(r['avg_pace_sec_km'])}/km, FC {r.get('avg_hr') or 'N/D'}, tipo {r['workout_category']})"
            for r in recent_runs
        ) or "Nessuna corsa recente."

        prompt = f"""Sei un coach di corsa su strada esperto e basato sui dati. Rispondi in italiano, in modo diretto, pratico e motivante (max 140 parole).

Dati di oggi ({today_str}) per {settings.get('athlete_name', 'Runner')}:
- Readiness calcolata: {advice['readiness_score']}/100 ({advice['badge']})
- Dispositivo salute: Apple Watch (Apple Health)
- HRV notturna: {latest_w.get('hrv_avg', 'N/D')} ms ({latest_w.get('hrv_status', 'N/D')}) | FC riposo: {latest_w.get('resting_hr', 'N/D')} bpm
- Sonno: {format_hm(latest_w.get('sleep_seconds')) if latest_w.get('sleep_seconds') else 'N/D'} (score {latest_w.get('sleep_score', 'N/D')})
- Anelli Movimento/Esercizio: {latest_w.get('active_calories', 'N/D')} kcal attive | {latest_w.get('exercise_min', 'N/D')} min esercizio | Passi: {latest_w.get('steps', 'N/D')}
- Cardio Fitness (VO2 Max): {latest_w.get('vo2_max', 'N/D')}
- Carico allenamento: CTL {load.get('ctl', 0)}, ATL {load.get('atl', 0)}, TSB {load.get('tsb', 0)}, ACWR {load.get('acwr', 1.0)}
- VDOT stimato: {summary['vdot']} | Passo Facile: {summary['paces']['easy']['range']} | Soglia: {summary['paces']['threshold']['range']}
- Allenamento previsto dal piano oggi: {today_workout['title'] + ' - ' + today_workout['description'] if today_workout else 'Nessuno'}

Ultime 5 corse:
{runs_text}

Fornisci un consiglio operativo chiaro per oggi (cosa fare, a che passo/FC, un suggerimento pratico sul recupero)."""

        ai_text = await _call_gemini(
            prompt,
            system_instruction="Sei RunPulse AI, un allenatore di running scientifico e conciso specializzato per runner con Apple Watch e Strava. Scrivi in italiano naturale, senza preamboli inutili.",
        )
        if ai_text:
            advice["ai_narrative"] = ai_text
            advice["ai_powered"] = True

    return advice


async def analyze_single_run(activity_id: str, force_ai: bool = True) -> Dict[str, Any]:
    act = db.get_activity(activity_id)
    if not act:
        raise ValueError("Attività non trovata.")

    settings = db.get_settings()
    max_hr = float(settings.get("max_hr") or 190)
    dist_km = round(float(act.get("distance_m") or 0) / 1000.0, 2)
    pace_str = format_pace(act.get("avg_pace_sec_km"))
    dur_str = format_duration(act.get("moving_time_s"))
    avg_hr = act.get("avg_hr")
    drift = act.get("cardiac_drift_pct")
    ef = act.get("efficiency_factor")
    cadence = act.get("avg_cadence")

    # Deterministic structured breakdown
    bullets: List[str] = []
    if avg_hr and max_hr > 0:
        hr_pct = round((avg_hr / max_hr) * 100)
        if hr_pct <= 77:
            bullets.append(f"**Sforzo cardiovascolare controllato ({int(avg_hr)} bpm, {hr_pct}% FC max)**: ottimo lavoro aerobico sostenibile.")
        elif hr_pct <= 86:
            bullets.append(f"**Intensità medio-alta ({int(avg_hr)} bpm, {hr_pct}% FC max)**: zona soglia/ritmo gara, utile ma richiede recupero adeguato.")
        else:
            bullets.append(f"**Sforzo intenso ({int(avg_hr)} bpm, {hr_pct}% FC max)**: stimolo anaerobico/VO2max elevato, programma almeno 48h prima del prossimo lavoro di qualità.")

    if drift is not None:
        if drift <= 5.0:
            bullets.append(f"**Deriva cardiaca eccellente ({drift:+.1f}%)**: ottima tenuta aerobica e idratazione per tutta la corsa.")
        elif drift <= 9.0:
            bullets.append(f"**Deriva cardiaca moderata ({drift:+.1f}%)**: leggero aumento FC nella seconda metà, normale su corse lunghe o calde.")
        else:
            bullets.append(f"**Deriva cardiaca alta ({drift:+.1f}%)**: possibile partenza troppo veloce, disidratazione o fatica pregressa.")

    if cadence:
        if cadence >= 172:
            bullets.append(f"**Cadenza efficiente ({cadence:.0f} spm)**: passo reattivo che riduce l'impatto articolare.")
        else:
            bullets.append(f"**Cadenza migliorabile ({cadence:.0f} spm)**: lavorare su passi più brevi e frequenti può migliorare l'economia di corsa.")

    if ef:
        bullets.append(f"**Efficiency Factor (EF {ef:.2f})**: monitora questo valore nel tempo nelle corse facili — più sale, più diventi veloce a parità di battiti.")

    fallback_text = (
        f"### Analisi Tecnica: {act['name']}\n"
        f"Hai percorso **{dist_km} km** in **{dur_str}** al passo medio di **{pace_str}/km** "
        f"(categoria: *{act['workout_category']}*, carico TRIMP: **{act.get('trimp', 0)}**).\n\n"
        + "\n".join(f"- {b}" for b in bullets)
    )

    ai_text = None
    if force_ai and settings.get("gemini_api_key", "").strip():
        splits_preview = ", ".join(
            f"Km {i+1}: {format_pace((s.get('moving_time',0)/(s.get('distance',1000)/1000.0)) if s.get('distance') else 0)} ({int(s['average_heartrate']) if s.get('average_heartrate') else '--'}bpm)"
            for i, s in enumerate((act.get("splits") or [])[:15])
        )
        prompt = f"""Analizza in modo professionale ma sintetico (in italiano, max 180 parole) questa corsa su strada:
- Nome: {act['name']} ({act['date_key']})
- Distanza: {dist_km} km | Durata: {dur_str} | Passo medio: {pace_str}/km | Dislivello: {act.get('elevation_gain_m', 0)} m
- FC media: {avg_hr or 'N/D'} bpm | FC max: {act.get('max_hr') or 'N/D'} bpm (FC max atleta: {int(max_hr)})
- Cadenza: {cadence or 'N/D'} spm | TRIMP: {act.get('trimp', 0)} | Deriva cardiaca: {drift if drift is not None else 'N/D'}% | EF: {ef or 'N/D'}
- Zone FC: {act.get('hr_zones') or 'N/D'}
- Parziali km: {splits_preview or 'Non disponibili'}

Evidenzia: 1) Punti di forza, 2) Aspetti migliorabili (pacing, gestione FC, deriva), 3) Cosa fare nel prossimo allenamento."""
        ai_text = await _call_gemini(
            prompt,
            system_instruction="Sei un coach di running esperto in analisi dati Strava/Garmin. Scrivi in italiano con elenchi puntati puliti.",
        )

    final_analysis = ai_text or fallback_text
    db.save_activity_ai_analysis(activity_id, final_analysis)
    return {
        "activity_id": activity_id,
        "analysis": final_analysis,
        "ai_powered": bool(ai_text),
    }


def _build_athlete_data_snapshot() -> Dict[str, Any]:
    """Collects a deep, complete real-time snapshot of Strava, Apple Watch & Apple Health, VDOT, and Race Plan data."""
    activities = db.get_activities(limit=5000)
    wellness_days = db.get_wellness_daily(days=30)
    settings = db.get_settings()
    summary = build_dashboard_summary(activities, wellness_days, settings)
    active_goal = db.get_active_goal_with_workouts()
    today_str = date.today().isoformat()

    # Global career / archive stats across ALL synced runs since day 1
    runs_only = [a for a in activities if "run" in str(a.get("sport_type", "")).lower()]
    total_runs = len(runs_only)
    total_km = round(sum(float(a.get("distance_m") or 0) for a in runs_only) / 1000.0, 1)
    first_date = activities[-1]["date_key"] if activities else "N/D"
    km_by_year: Dict[str, float] = {}
    runs_by_year: Dict[str, int] = {}
    for a in runs_only:
        yr = str(a.get("date_key", ""))[:4]
        if yr:
            km_by_year[yr] = km_by_year.get(yr, 0.0) + float(a.get("distance_m") or 0) / 1000.0
            runs_by_year[yr] = runs_by_year.get(yr, 0) + 1
    yearly_summary = " | ".join(
        f"{yr}: {round(km_by_year[yr], 1)} km ({runs_by_year[yr]} corse)"
        for yr in sorted(km_by_year.keys(), reverse=True)
    ) or "N/D"
    longest_run = max(runs_only, key=lambda a: float(a.get("distance_m") or 0), default=None)
    fastest_5k_plus = min(
        [a for a in runs_only if float(a.get("distance_m") or 0) >= 4800 and float(a.get("avg_pace_sec_km") or 0) > 150],
        key=lambda a: float(a.get("avg_pace_sec_km") or 9999),
        default=None,
    )
    efs = [float(a["efficiency_factor"]) for a in runs_only[:20] if a.get("efficiency_factor")]
    drifts = [float(a["cardiac_drift_pct"]) for a in runs_only[:20] if a.get("cardiac_drift_pct") is not None]
    avg_ef = round(sum(efs) / len(efs), 2) if efs else "N/D"
    avg_drift = f"{sum(drifts)/len(drifts):+.1f}%" if drifts else "N/D"

    weekly_vol_lines = [
        f"Sett {w['week_label']}: {w['km']} km ({w['runs']} corse, carico {w['load']})"
        for w in summary["load"]["weekly_volumes"]
    ]

    recent_runs_lines = []
    for idx_r, r in enumerate(activities[:25]):
        km = round(float(r.get("distance_m") or 0) / 1000.0, 2)
        pace = format_pace(r.get("avg_pace_sec_km"))
        hr = f"{int(r['avg_hr'])} bpm" if r.get("avg_hr") else "N/D"
        max_hr_s = f" (max {int(r['max_hr'])})" if r.get("max_hr") else ""
        cad_s = f", cad {round(r['avg_cadence'])}" if r.get("avg_cadence") else ""
        elev = f"D+{int(r.get('elevation_gain_m') or 0)}m"
        drift = f", deriva {r['cardiac_drift_pct']:+.1f}%" if r.get("cardiac_drift_pct") is not None else ""
        ef = f", EF {r['efficiency_factor']}" if r.get("efficiency_factor") else ""
        zones_s = ""
        if idx_r < 10 and r.get("hr_zones"):
            z_parts = [f"{zk}:{zv}%" for zk, zv in r["hr_zones"].items() if zv and zv >= 5]
            if z_parts:
                zones_s = f", zone [{' '.join(z_parts)}]"
        recent_runs_lines.append(
            f"- {r['date_key']} | {r['name']} [{r['sport_type']}/{r['workout_category']}]: {km} km a {pace}/km, {elev}, FC {hr}{max_hr_s}{cad_s}, TRIMP {round(r.get('trimp') or 0)}{ef}{drift}{zones_s}"
        )

    apple_health_lines = []
    for g in wellness_days[-14:]:
        slp = format_hm(g["sleep_seconds"]) if g.get("sleep_seconds") else "N/D"
        stages = ""
        if g.get("sleep_deep_sec") or g.get("sleep_rem_sec"):
            stages = f" [Prof {format_hm(g.get('sleep_deep_sec'))}, REM {format_hm(g.get('sleep_rem_sec'))}, Base {format_hm(g.get('sleep_light_sec'))}]"
        rhr = f"RHR {g['resting_hr']} bpm" if g.get("resting_hr") else "RHR N/D"
        hrv = f"HRV {round(g['hrv_avg'])} ms ({g.get('hrv_status') or '-'})" if g.get("hrv_avg") else "HRV N/D"
        readiness = f"Readiness {g['training_readiness']}/100" if g.get("training_readiness") else "Readiness N/D"
        vo2 = f", Cardio Fitness VO2 {g['vo2_max']}" if g.get("vo2_max") else ""
        cals = f", Movimento {g['active_calories']} kcal" if g.get("active_calories") else ""
        ex_min = f", Esercizio {g['exercise_min']} min" if g.get("exercise_min") else ""
        steps_s = f", Passi {g['steps']}" if g.get("steps") else ""
        spo2 = f", SpO2 {g['spo2_avg']}%" if g.get("spo2_avg") else ""
        resp = f", Resp {g['respiration_avg']} bpm" if g.get("respiration_avg") else ""
        apple_health_lines.append(
            f"- {g['date_key']}: {hrv}, {rhr}, Sonno {slp}{stages} (score {g.get('sleep_score', 'N/D')}), {readiness}{vo2}{cals}{ex_min}{steps_s}{spo2}{resp}"
        )

    upcoming_plan_lines = []
    goal_header = "Nessun obiettivo gara attivo al momento."
    if active_goal:
        goal_header = (
            f"{active_goal['name']} ({active_goal['distance_km']} km il {active_goal['race_date']}, "
            f"target {format_duration(active_goal['target_time_sec'])}, passo gara {active_goal.get('paces', {}).get('race_pace', 'N/D')})"
        )
        upcoming = [w for w in active_goal.get("workouts", []) if w["scheduled_date"] >= today_str][:10]
        for w in upcoming:
            status = "FATTO" if w["completed"] else "DA FARE"
            upcoming_plan_lines.append(
                f"- {w['scheduled_date']} ({w['phase']}): {w['title']} — {w['target_distance_km']} km @ {w['target_pace_range']} [{status}]"
            )

    load = summary["load"]["current"]
    mix = summary["stats_30d"]["workout_mix"]
    longest_str = f"{longest_run['distance_m']/1000:.1f} km ({longest_run['name']}, {longest_run['date_key']})" if longest_run else "N/D"
    fastest_str = f"{format_pace(fastest_5k_plus['avg_pace_sec_km'])}/km su {fastest_5k_plus['distance_m']/1000:.1f} km ({fastest_5k_plus['name']}, {fastest_5k_plus['date_key']})" if fastest_5k_plus else "N/D"

    context_text = f"""DATA DI OGGI: {today_str}
ATLETA: {settings.get('athlete_name', 'Runner')} (FC max {settings.get('max_hr', 190)}, FC riposo {settings.get('resting_hr', 52)}, obiettivo settimanale {settings.get('weekly_goal_km', 40)} km)
DISPOSITIVO DI MONITORAGGIO SALUTE: Apple Watch & Apple Health

PANORAMICA ARCHIVIO STRAVA (dal {first_date}: {len(activities)} attività totali, {total_runs} corse, {total_km} km totali):
- Storico annuale corsa: {yearly_summary}
- Corsa più lunga in archivio: {longest_str}
- Corsa più veloce (>=5 km): {fastest_str}
- Ultimi 30 giorni: {summary['stats_30d']['km']} km in {summary['stats_30d']['runs']} corse (passo medio {summary['stats_30d']['avg_pace']}/km)
- Distribuzione intensità 30g: Facili {mix.get('easy',0)}, Rigeneranti {mix.get('recovery',0)}, Tempo/Soglia {mix.get('tempo',0)}, Ripetute {mix.get('intervals',0)}, Lunghi {mix.get('long',0)}, Gare {mix.get('race',0)}
- Efficiency Factor medio (ultime 20 corse): {avg_ef} | Deriva cardiaca media: {avg_drift}

PROGRESSIONE ULTIME 8 SETTIMANE:
{' | '.join(weekly_vol_lines)}

READINESS & CARICO OGGI:
- Readiness: {summary['readiness']['score']}/100 ({summary['readiness']['zone_label']})
- Fitness (CTL): {load.get('ctl', 0)} | Fatica (ATL): {load.get('atl', 0)} | Forma (TSB): {load.get('tsb', 0)} | ACWR: {load.get('acwr', 1.0)}
- Settimana corrente: {summary['load']['this_week_km']} km ({summary['load']['this_week_runs']} corse)
- VDOT stimato: {summary['vdot']} (da {summary['vdot_source']})
- Ritmi VDOT: Rigenerante {summary['paces']['recovery']['range']} | Facile {summary['paces']['easy']['range']} | Maratona {summary['paces']['marathon']['range']} | Soglia {summary['paces']['threshold']['range']} | VO2max {summary['paces']['interval']['range']}
- Proiezioni gara: 5K {summary['race_predictions']['5k']}, 10K {summary['race_predictions']['10k']}, Mezza {summary['race_predictions']['half_marathon']}, Maratona {summary['race_predictions']['marathon']}

APPLE HEALTH / APPLE WATCH ULTIMI 14 GIORNI:
{chr(10).join(apple_health_lines) if apple_health_lines else 'Nessun dato Apple Health ancora sincronizzato.'}

ULTIME 25 ATTIVITÀ STRAVA:
{chr(10).join(recent_runs_lines) if recent_runs_lines else 'Nessuna corsa Strava sincronizzata.'}

OBIETTIVO GARA ATTIVO:
{goal_header}
Prossimi allenamenti in tabella:
{chr(10).join(upcoming_plan_lines) if upcoming_plan_lines else 'Nessuno.'}"""

    return {
        "activities": activities,
        "wellness_days": wellness_days,
        "settings": settings,
        "summary": summary,
        "active_goal": active_goal,
        "context_text": context_text,
    }


def _calippo_local_reply(user_message: str, snap: Dict[str, Any]) -> str:
    """Smart local data-driven Calippo response when Gemini API key is not configured."""
    q = user_message.lower()
    summary = snap["summary"]
    latest_w = summary.get("latest_wellness") or {}
    load = summary["load"]["current"]
    paces = summary["paces"]
    acts = snap["activities"]
    active_goal = snap["active_goal"]
    advice = _build_deterministic_daily_advice(summary)

    if any(w in q for w in ["ciao", "ehi", "salve", "buongiorno", "buonasera", "chi sei"]):
        return (
            f"Ciao! Sono **Calippo**, il tuo coach personale di corsa per Apple Watch & Strava 😎\n\n"
            f"Ho già sott'occhio i tuoi numeri di oggi: Readiness **{summary['readiness']['score']}/100** "
            f"({summary['readiness']['zone_label']}), Fitness CTL **{load.get('ctl', 0)}**, "
            f"Frequenza a Riposo **{latest_w.get('resting_hr', 'N/D')} bpm**. "
            "Chiedimi pure come stai recuperando, che allenamento fare oggi, com'è andata l'ultima corsa o come va il piano gara!"
        )

    if any(w in q for w in ["apple", "salute", "hrv", "sonno", "dormit", "recuper", "stanco", "stanc"]):
        if not latest_w:
            return (
                "Non vedo ancora dati Apple Health sincronizzati! Configura il comando rapido nella scheda **Apple Watch** "
                "(oppure carica i dati demo) così posso analizzarti HRV, sonno e battito a riposo."
            )
        slp_h = format_hm(latest_w["sleep_seconds"]) if latest_w.get("sleep_seconds") else "N/D"
        stages = []
        if latest_w.get("sleep_deep_sec"):
            stages.append(f"Profondo {format_hm(latest_w['sleep_deep_sec'])}")
        if latest_w.get("sleep_rem_sec"):
            stages.append(f"REM {format_hm(latest_w['sleep_rem_sec'])}")
        stage_txt = f" ({', '.join(stages)})" if stages else ""
        return (
            f"Ecco il check-up Apple Watch di oggi ({latest_w['date_key']}):\n"
            f"- **HRV notturna**: {round(latest_w['hrv_avg']) if latest_w.get('hrv_avg') else 'N/D'} ms ({latest_w.get('hrv_status') or 'N/D'})\n"
            f"- **FC riposo**: {latest_w.get('resting_hr', 'N/D')} bpm\n"
            f"- **Sonno**: {slp_h}{stage_txt} (score {latest_w.get('sleep_score', 'N/D')}/100)\n"
            f"- **Attività**: {latest_w.get('active_calories', 'N/D')} kcal · {latest_w.get('steps', 'N/D')} passi\n\n"
            f"👉 **Consiglio di Calippo**: {advice['headline']} — {advice['workout_suggestion']}"
        )

    if any(w in q for w in ["corsa", "corse", "ultim", "strava", "allenament", "km", "volume"]):
        if not acts:
            return "Non ho ancora corse Strava in memoria. Collega Strava in **Connessioni** e sincronizza i tuoi allenamenti!"
        top3 = acts[:3]
        lines = [
            f"- **{a['date_key']} · {a['name']}**: {(a['distance_m']/1000):.2f} km a **{format_pace(a['avg_pace_sec_km'])}/km** "
            f"(FC {int(a['avg_hr']) if a.get('avg_hr') else 'N/D'} bpm, TRIMP {round(a.get('trimp') or 0)})"
            for a in top3
        ]
        return (
            f"Negli ultimi 30 giorni hai macinato **{summary['stats_30d']['km']} km** in **{summary['stats_30d']['runs']} corse** "
            f"(passo medio {summary['stats_30d']['avg_pace']}/km, settimana attuale **{summary['load']['this_week_km']} km**).\n\n"
            f"Le tue ultime uscite:\n" + "\n".join(lines) +
            f"\n\nCarico attuale: Fitness **{load.get('ctl', 0)}**, Fatica **{load.get('atl', 0)}**, ACWR **{load.get('acwr', 1.0)}**."
        )

    if any(w in q for w in ["gara", "piano", "tabella", "maratona", "mezza", "10k", "5k", "tempo", "ritm", "vdot", "passo"]):
        preds = summary["race_predictions"]
        goal_txt = (
            f"\n\n🎯 **Piano attivo**: *{active_goal['name']}* il **{active_goal['race_date']}** "
            f"(passo gara target **{active_goal.get('paces', {}).get('race_pace', 'N/D')}**)."
            if active_goal
            else "\n\nNon hai ancora un piano gara attivo: vai su **Obiettivo Gara** e lo creiamo in 10 secondi!"
        )
        return (
            f"Con il tuo **VDOT stimato di {summary['vdot']}**, ecco i tuoi ritmi ideali:\n"
            f"- **Facile Z2**: {paces['easy']['range']}\n"
            f"- **Soglia / Tempo**: {paces['threshold']['range']}\n"
            f"- **Ripetute VO2max**: {paces['interval']['range']}\n\n"
            f"⏱️ **Proiezioni gara attuali**: 5K **{preds['5k']}** · 10K **{preds['10k']}** · Mezza **{preds['half_marathon']}** · Maratona **{preds['marathon']}**"
            + goal_txt
        )

    return (
        f"Ho controllato tutti i tuoi dati di oggi (Readiness **{summary['readiness']['score']}/100**, "
        f"Stress Garmin **{latest_g.get('stress_avg', 'N/D')}**, Forma TSB **{load.get('tsb', 0):+.0f}**, ACWR **{load.get('acwr', 1.0)}**).\n\n"
        f"👉 **{advice['headline']}**: {advice['workout_suggestion']}\n"
        f"Passo consigliato: **{advice['target_pace']}** · Zona: **{advice['target_zone']}**.\n\n"
        "*(Tip: se inserisci una chiave gratuita **Google Gemini API** in Connessioni, posso chiacchierare con te liberamente su qualsiasi domanda complessa!)*"
    )


async def chat_with_calippo(user_message: str) -> Dict[str, Any]:
    """Persistent multi-turn conversation with Calippo using real Strava/Garmin/Plan data."""
    msg = user_message.strip()
    if not msg:
        raise ValueError("Scrivi un messaggio per Calippo.")

    # Save user message first
    user_row = db.add_chat_message("user", msg, ai_powered=False)
    snap = _build_athlete_data_snapshot()

    ai_reply = None
    ai_error = None
    if snap["settings"].get("gemini_api_key", "").strip():
        history = db.get_chat_messages(limit=16)
        contents: List[Dict[str, Any]] = []
        for h in history:
            g_role = "user" if h["role"] == "user" else "model"
            contents.append({"role": g_role, "parts": [{"text": h["content"]}]})

        system_prompt = f"""Sei Calippo, il personal running coach e data analyst AI dell'atleta dentro l'app RunPulse (Apple Watch & Strava Edition).
Stile e metodo di ragionamento:
- Rifletti a fondo sui dati prima di rispondere: confronta volumi, intensità (polarizzazione 80/20 vs zona grigia), trend di FC, deriva cardiaca, Efficiency Factor, dati di salute Apple Watch (HRV SDNN, sonno con fasi, anelli attività, FC riposo), CTL/ATL/TSB e ACWR.
- Parla in italiano naturale, umano, diretto e coinvolgente (dai del "tu", tono da vero coach preparatissimo e complice, mai generico o da template).
- Adatta la profondità alla domanda: se l'atleta chiede una panoramica completa di sé o un'analisi delle sue corse, fai un'analisi ricca, strutturata per sezioni chiare (es. Profilo & Punti di Forza, Cosa Migliorare, Recupero Apple Watch & Sonno, Prossimi Passi Concreti) citando date, km, passi e numeri reali. Se fa una domanda rapida, rispondi in modo agile ma ragionato.
- Non inventare MAI numeri che non sono presenti nei dati qui sotto.

DATI REALI COMPLETI E AGGIORNATI DELL'ATLETA:
{snap['context_text']}"""

        ai_reply, ai_error = await _call_gemini_chat(
            contents,
            system_instruction=system_prompt,
            thinking_budget=2048,
        )

    if ai_reply:
        final_text = ai_reply
    elif ai_error:
        if "503" in ai_error or "high demand" in ai_error.lower():
            final_text = (
                "⏳ **I server gratuiti di Gemini hanno un picco momentaneo di traffico** (errore temporaneo 503). "
                "La tua chiave è ok! Riprova a mandare il messaggio tra 10–15 secondi."
            )
        else:
            final_text = (
                f"⚠️ **Problema temporaneo con Gemini**: `{ai_error}`\n\n"
                "Se il problema persiste, puoi fare il test della chiave in **Connessioni**."
            )
    else:
        final_text = _calippo_local_reply(msg, snap)

    bot_row = db.add_chat_message("assistant", final_text, ai_powered=bool(ai_reply))
    return {
        "user_message": user_row,
        "reply": bot_row,
        "ai_powered": bool(ai_reply),
        "ai_error": ai_error,
    }


async def ask_coach_question(question: str) -> Dict[str, Any]:
    res = await chat_with_calippo(question)
    return {"answer": res["reply"]["content"], "ai_powered": res["ai_powered"]}
