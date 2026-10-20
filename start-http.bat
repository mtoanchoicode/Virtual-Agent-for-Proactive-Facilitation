@echo off
echo ===================================================
echo Starting IAcine Virtual Avatar Services (HTTP only)
echo ===================================================

set HTTP_ONLY=1

echo Starting Backend Server...
start "Backend Server" cmd /k "set HTTP_ONLY=1&& cd back && call ..\.venv\Scripts\activate && python -m app.main"

echo Starting Frontend Server...
start "Frontend Server" cmd /k "set HTTP_ONLY=1&& cd front && npm run dev"

echo.
echo Open http://localhost:5173
echo NOTE: browsers only allow microphone on http://localhost, not on a LAN IP.
echo ===================================================
