#!/bin/bash
# Launch the edgar_pipeline Streamlit UI.
# Usage:  bash run_app.sh
set -e

cd "$(dirname "$0")"

# Prefer the project's virtualenv if present
if [ -x "./secenv/Scripts/python.exe" ]; then
    PY="./secenv/Scripts/python.exe"
elif [ -x "./secenv/bin/python" ]; then
    PY="./secenv/bin/python"
else
    PY="python"
fi

"$PY" -m streamlit run app/streamlit_app.py \
    --server.port 8501 \
    --server.headless false \
    --theme.base dark \
    --theme.primaryColor "#1D6FA4" \
    --theme.backgroundColor "#0E1117" \
    --theme.secondaryBackgroundColor "#1C2333" \
    --theme.textColor "#FAFAFA" \
    --browser.gatherUsageStats false
