@echo off
echo =========================================================
echo   EVENT ATTENDANCE SYSTEM - STARTUP LAUNCHER
echo   Dark Cyberpunk // Futuristic Event Check-in
echo =========================================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

REM Initialize and seed demo data if database does not exist
if not exist "attendance.db" (
    echo [INFO] First run detected. Seeding sample TECHSTAR 2026 data...
    python seed_data.py
)

echo [INFO] Starting Event Attendance Server on http://localhost:5000 ...
echo [INFO] Staff Login (Admin):  http://localhost:5000/login  [default: admin / admin123]
echo [INFO] Venue Projector View: http://localhost:5000/projector [staff only]
echo [INFO] Participant Check-in: http://localhost:5000/checkin
echo [INFO] Participant Portal:   http://localhost:5000/participant
echo.
python app.py
pause
