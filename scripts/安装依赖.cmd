@echo off
cd /d "%~dp0.."
call npm.cmd ci --no-audit --no-fund
pause
