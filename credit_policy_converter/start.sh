#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Credit Policy Converter — start backend + frontend dev servers
# ─────────────────────────────────────────────────────────────────────────────
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Verify .env ────────────────────────────────────────────────────────────
ENV_FILE="$ROOT/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "⚠  $ENV_FILE not found — copying from .env.example"
  cp "$ROOT/backend/.env.example" "$ENV_FILE"
  echo "👉 Edit $ENV_FILE and add your ANTHROPIC_API_KEY, then re-run this script."
  exit 1
fi

if grep -q "sk-ant-your-key-here" "$ENV_FILE"; then
  echo "⚠  ANTHROPIC_API_KEY is still the placeholder value in $ENV_FILE"
  echo "👉 Replace it with your real key and re-run."
  exit 1
fi

# ── 2. Backend ────────────────────────────────────────────────────────────────
echo "▶  Starting backend (FastAPI on :8000)..."
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
  echo "   Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# ── 3. Frontend ───────────────────────────────────────────────────────────────
echo "▶  Starting frontend (Vite on :5173)..."
cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "   Installing npm dependencies..."
  npm install
fi

npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"

# ── 4. Open browser (macOS) ───────────────────────────────────────────────────
sleep 2
if command -v open &>/dev/null; then
  open "http://localhost:5173"
fi

echo ""
echo "✅  App running at http://localhost:5173"
echo "   Backend API at http://localhost:8000"
echo "   Press Ctrl+C to stop both servers."

# ── 5. Wait and cleanup ───────────────────────────────────────────────────────
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
