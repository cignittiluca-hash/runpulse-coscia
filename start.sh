#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "⚡ Avvio di RunPulse (Garmin + Whoop Edition)..."

if [ ! -d ".venv" ]; then
    echo "📦 Creazione ambiente virtuale Python (.venv)..."
    python3 -m venv .venv
fi

echo "🔄 Verifica dipendenze..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

PORT="${PORT:-${RUNPULSE_PORT:-8000}}"

echo "=========================================================="
echo "🏃 RunPulse + Calippo AI (Garmin + Whoop Edition) è attivo!"
echo "📍 Apri nel browser del Mac: http://localhost:$PORT"
echo "📱 Da iPhone nella stessa rete Wi-Fi: apri http://$(ipconfig getifaddr en0 2>/dev/null || echo 'IP-DEL-TUO-MAC'):$PORT"
echo "=========================================================="

exec .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
