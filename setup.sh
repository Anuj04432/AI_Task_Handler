#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-command setup for AI To-Do System
# Usage:  chmod +x setup.sh && ./setup.sh
# =============================================================================

set -e

PYTHON=${PYTHON:-python3}
VENV_DIR="venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       AI To-Do System — Setup            ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Check Python version ───────────────────────────────────────────────────
PYVER=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PYVER" -lt 11 ]; then
  echo "❌ Python 3.11+ required. Found: $($PYTHON --version)"
  exit 1
fi
echo "✅ Python $($PYTHON --version) found"

# ── 2. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Creating virtual environment..."
  $PYTHON -m venv $VENV_DIR
fi
source $VENV_DIR/bin/activate
echo "✅ Virtual environment activated"

# ── 3. Install deps ───────────────────────────────────────────────────────────
echo "📦 Installing dependencies..."

# Platform-specific PyAudio
OS="$(uname -s)"
if [ "$OS" = "Linux" ]; then
  echo "   Detected Linux — installing portaudio..."
  sudo apt-get install -y python3-pyaudio portaudio19-dev 2>/dev/null || true
elif [ "$OS" = "Darwin" ]; then
  echo "   Detected macOS — installing portaudio via brew..."
  brew install portaudio 2>/dev/null || true
fi

pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"

# ── 4. Create data dir ────────────────────────────────────────────────────────
mkdir -p data
echo "✅ Data directory ready"

# ── 5. Optional: Ollama ───────────────────────────────────────────────────────
if command -v ollama &> /dev/null; then
  echo "✅ Ollama detected — enhanced AI available"
  echo "   To pull a model: ollama pull llama3"
else
  echo "ℹ️  Ollama not found — rule-based NLU will be used (works great offline)"
  echo "   Optional install: https://ollama.com"
fi

# ── 6. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ Setup complete! Start the app with:  ║"
echo "║                                          ║"
echo "║     streamlit run ui/app.py              ║"
echo "║                                          ║"
echo "║  Then open: http://localhost:8501        ║"
echo "╚══════════════════════════════════════════╝"
echo ""
