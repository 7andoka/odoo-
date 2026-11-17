@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker compose stop
echo Zee Retail stopped. Your data is kept.
pause
