@echo off
cd /d "%~dp0"
pythonw app.py
if errorlevel 1 (
  echo Application failed to start. Trying console mode...
  python app.py
  pause
)
