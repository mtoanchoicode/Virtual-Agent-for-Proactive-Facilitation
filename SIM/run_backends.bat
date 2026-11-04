@echo off
REM Start N extra backend processes for parallel simulation (one room each).
REM Usage: run_backends.bat [count=2] [first_port=3001]
REM Then list them under backend_urls in config\experiment.yaml.
REM File logging is off so parallel sessions don't write into the same log files
REM (the simulator records everything it needs itself).
setlocal
set COUNT=%1
if "%COUNT%"=="" set COUNT=2
set FIRST=%2
if "%FIRST%"=="" set FIRST=3001
set /a LAST=%FIRST%+%COUNT%-1

for /L %%P in (%FIRST%,1,%LAST%) do (
  echo Starting backend on port %%P
  start "SIM backend %%P" cmd /k "set HTTP_ONLY=1&& set PORT=%%P&& set ENABLE_FILE_LOGGING=false&& set PYTHONIOENCODING=utf-8&& cd /d %~dp0..\back && call ..\.venv\Scripts\activate && python -m app.main"
)
endlocal
