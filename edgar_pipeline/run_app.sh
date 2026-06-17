#!/bin/bash
# Launch the edgar_pipeline Streamlit UI.
# Usage:  bash run_app.sh                            # default port 8501
#         EDGAR_UI_LOG_LEVEL=DEBUG bash run_app.sh   # verbose logging
#         PORT=8600 bash run_app.sh                  # custom port
set -e

cd "$(dirname "$0")"
HERE="$(pwd)"

echo "========================================================"
echo "  Edgar Pipeline - Streamlit UI"
echo "========================================================"
echo "  Working dir : $HERE"

# ---- Locate Python ----
if [ -x "./secenv/Scripts/python.exe" ]; then
    PY="./secenv/Scripts/python.exe"
    echo "  Interpreter : ./secenv/Scripts/python.exe (Windows venv)"
elif [ -x "./secenv/bin/python" ]; then
    PY="./secenv/bin/python"
    echo "  Interpreter : ./secenv/bin/python (POSIX venv)"
elif command -v python >/dev/null 2>&1; then
    PY="python"
    echo "  Interpreter : system python (no venv detected)"
    echo "  WARN        : create a venv with 'python -m venv secenv' for isolation"
else
    echo "  ERROR: no Python interpreter found." >&2
    exit 1
fi

# ---- Verify streamlit is importable ----
if ! "$PY" -c "import streamlit" >/dev/null 2>&1; then
    echo "  ERROR: streamlit is not installed in $PY" >&2
    echo "         install it with:  $PY -m pip install -r requirements.txt" >&2
    exit 1
fi

# ---- Verify the entry script exists ----
if [ ! -f "app/streamlit_app.py" ]; then
    echo "  ERROR: app/streamlit_app.py not found under $HERE" >&2
    exit 1
fi

PORT="${PORT:-8501}"
LOG_LEVEL="${EDGAR_UI_LOG_LEVEL:-INFO}"

echo "  Port        : $PORT"
echo "  Log level   : $LOG_LEVEL"
echo "  UI log file : outputs/streamlit_ui.log"
echo "  Backend log : outputs/pipeline.log"
echo "  Open in browser: http://localhost:$PORT"
echo "========================================================"

export EDGAR_UI_LOG_LEVEL="$LOG_LEVEL"

exec "$PY" -m streamlit run app/streamlit_app.py \
    --server.port "$PORT" \
    --server.headless false \
    --theme.base dark \
    --theme.primaryColor "#1D6FA4" \
    --theme.backgroundColor "#0E1117" \
    --theme.secondaryBackgroundColor "#1C2333" \
    --theme.textColor "#FAFAFA" \
    --browser.gatherUsageStats false
