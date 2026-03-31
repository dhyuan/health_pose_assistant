#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_PYTHON="$BACKEND_DIR/hpa_backend_env/bin/python"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${GREEN}[INFO]${NC} Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo -e "${GREEN}[INFO]${NC} Done."
}

# --- Pre-flight checks ---
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo -e "${RED}[ERROR]${NC} Backend venv not found at $VENV_PYTHON"
    echo "       Run: bash scripts/setup_dev.sh"
    exit 1
fi

if ! command -v node &>/dev/null; then
    echo -e "${RED}[ERROR]${NC} Node.js not found. Install Node >= 22."
    exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo -e "${RED}[ERROR]${NC} Frontend node_modules not found."
    echo "       Run: cd frontend && npm install"
    exit 1
fi

# --- Start backend ---
echo -e "${GREEN}[INFO]${NC} Starting backend (uvicorn) on :8000 ..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# --- Start frontend ---
echo -e "${GREEN}[INFO]${NC} Starting frontend (next dev) on :3000 ..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

trap cleanup EXIT INT TERM

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Backend:  http://localhost:8000${NC}"
echo -e "${GREEN}  Frontend: http://localhost:3000${NC}"
echo -e "${GREEN}  Press Ctrl+C to stop both${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

wait
