@echo off
cd /d "%~dp0"
pythonw src/app.py
if errorlevel 1 (
  echo Application failed to start. Trying console mode...
  python src/app.py
  pause
)
