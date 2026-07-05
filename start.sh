#!/bin/bash
# Chrona — Full Stack Start Script
# Usage: bash start.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║        Chrona Stock Dashboard         ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# ── 1. Install frontend deps ────────────────────────────────────────────────
echo "📦 Installing frontend dependencies..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  npm install --legacy-peer-deps
fi

# ── 2. Check Python deps ────────────────────────────────────────────────────
echo "🐍 Checking Python dependencies..."
cd "$SCRIPT_DIR/backend"
pip install -q fastapi uvicorn pydantic pandas numpy requests textblob \
  scikit-learn yfinance supabase google-generativeai --break-system-packages 2>/dev/null || true

# ── 3. Start backend ────────────────────────────────────────────────────────
echo ""
echo "🚀 Starting FastAPI backend on http://localhost:8000 ..."
cd "$SCRIPT_DIR/backend"
uvicorn backend:app --reload --port 8000 &
BACKEND_PID=$!

sleep 2

# ── 4. Start frontend ───────────────────────────────────────────────────────
echo "⚡ Starting Next.js frontend on http://localhost:3000 ..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Chrona is running!"
echo "   Frontend → http://localhost:3000"
echo "   Backend  → http://localhost:8000"
echo "   API Docs → http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
