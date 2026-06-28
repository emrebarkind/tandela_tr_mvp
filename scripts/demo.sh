#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "backend/.env bulunamadı. backend/.env.example dosyasından oluşturup GEMINI_API_KEY ekleyin."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export TANDELA_AUDIO_PROVIDER="${TANDELA_AUDIO_PROVIDER:-gemini_audio}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:8000}"

if [[ "$TANDELA_AUDIO_PROVIDER" == "gemini_audio" && -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY yok. Gerçek ASR/analiz demosu için backend/.env içine ekleyin."
  exit 1
fi

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "8000 portu kullanımda. Çalışan backend'i kapatıp tekrar deneyin."
  exit 1
fi

if lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "3000 portu kullanımda. Çalışan frontend'i kapatıp tekrar deneyin."
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
PNPM_BIN="${PNPM_BIN:-pnpm}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python bulunamadı. PYTHON_BIN ile Python yolunu belirtin."
  exit 1
fi

if ! command -v "$PNPM_BIN" >/dev/null 2>&1; then
  echo "pnpm bulunamadı. PNPM_BIN ile pnpm yolunu belirtin."
  exit 1
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "Backend başlıyor: http://127.0.0.1:8000"
(
  cd "$BACKEND_DIR"
  "$PYTHON_BIN" -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

sleep 2

echo "Frontend başlıyor: http://127.0.0.1:3000"
cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
  "$PNPM_BIN" install
fi
"$PNPM_BIN" dev
