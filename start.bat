@echo off
echo ===================================================
echo Starting IAcine Virtual Avatar Services
echo ===================================================

echo Starting Backend Server...
start "Backend Server" cmd /k "cd back && call ..\.venv\Scripts\activate && python -m app.main"

echo Starting Frontend Server...
start "Frontend Server" cmd /k "cd front && npm run dev"

echo.
echo Both services are launching in separate windows!
echo You can see the logs in those newly opened command prompts.
echo ===================================================
