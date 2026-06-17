@echo off
REM Launch the edgar_pipeline Streamlit UI on Windows.

cd /d "%~dp0"

if exist "secenv\Scripts\python.exe" (
    set PY=secenv\Scripts\python.exe
) else (
    set PY=python
)

"%PY%" -m streamlit run app\streamlit_app.py ^
    --server.port 8501 ^
    --server.headless false ^
    --theme.base dark ^
    --theme.primaryColor "#1D6FA4" ^
    --theme.backgroundColor "#0E1117" ^
    --theme.secondaryBackgroundColor "#1C2333" ^
    --theme.textColor "#FAFAFA" ^
    --browser.gatherUsageStats false
