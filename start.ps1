# PowerShell launcher for Event Attendance System
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "  EVENT ATTENDANCE SYSTEM - POWER SHELL LAUNCHER" -ForegroundColor Green
Write-Host "  Dark Cyberpunk // Futuristic Event Check-in" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green

if (-not (Test-Path "attendance.db")) {
    Write-Host "[INFO] First run detected. Seeding sample TECHSTAR 2026 data..." -ForegroundColor Cyan
    python seed_data.py
}

Write-Host "[INFO] Starting Event Attendance Server on http://localhost:5000 ..." -ForegroundColor Cyan
Write-Host "[INFO] Admin Dashboard:      http://localhost:5000/admin" -ForegroundColor Yellow
Write-Host "[INFO] Venue Projector View: http://localhost:5000/projector" -ForegroundColor Yellow
Write-Host "[INFO] Participant Check-in: http://localhost:5000/checkin" -ForegroundColor Yellow
Write-Host "[INFO] Participant Portal:   http://localhost:5000/participant" -ForegroundColor Yellow

python app.py
