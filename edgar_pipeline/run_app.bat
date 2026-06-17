@echo off
REM Launch the edgar_pipeline Streamlit UI on Windows.
REM Usage:  run_app.bat                              (default port 8501)
REM         set PORT=8600 ^&^& run_app.bat           (custom port)
REM         set EDGAR_UI_LOG_LEVEL=DEBUG ^&^& run_app.bat

cd /d "%~dp0"
set HERE=%CD%

echo ========================================================
echo   Edgar Pipeline - Streamlit UI
echo ========================================================
echo   Working dir : %HERE%

if exist "secenv\Scripts\python.exe" (
    set PY=secenv\Scripts\python.exe
    echo   Interpreter : secenv\Scripts\python.exe
) else (
    set PY=python
    echo   Interpreter : system python ^(no venv detected^)
    echo   WARN        : create a venv with "python -m venv secenv" for isolation
)

"%PY%" -c "import streamlit" 2>NUL
if errorlevel 1 (
    echo   ERROR: streamlit is not installed in %PY%
    echo          install it with:  %PY% -m pip install -r requirements.txt
    exit /b 1
)

if not exist "app\streamlit_app.py" (
    echo   ERROR: app\streamlit_app.py not found under %HERE%
    exit /b 1
)

if "%PORT%"=="" set PORT=8501
if "%EDGAR_UI_LOG_LEVEL%"=="" set EDGAR_UI_LOG_LEVEL=INFO

echo   Port        : %PORT%
echo   Log level   : %EDGAR_UI_LOG_LEVEL%
echo   UI log file : outputs\streamlit_ui.log
echo   Backend log : outputs\pipeline.log
echo   Open in browser: http://localhost:%PORT%
echo ========================================================

"%PY%" -m streamlit run app\streamlit_app.py ^
    --server.port %PORT% ^
    --server.headless false ^
    --theme.base light ^
    --theme.primaryColor "#1D6FA4" ^
    --theme.backgroundColor "#F4F6FA" ^
    --theme.secondaryBackgroundColor "#FFFFFF" ^
    --theme.textColor "#1B2030" ^
    --browser.gatherUsageStats false
