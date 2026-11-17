@echo off
chcp 65001 >nul
title Zee Retail
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not running.
    echo Open Docker Desktop, wait until it says "running", then try again.
    pause
    exit /b 1
)

docker compose up -d
if errorlevel 1 (
    echo Could not start Zee Retail. See the messages above.
    pause
    exit /b 1
)

echo Waiting for Odoo to start...
timeout /t 25 /nobreak >nul
start "" http://localhost:8069
echo Zee Retail is running at http://localhost:8069
echo You can close this window. Use stop-zee.bat to stop it.
timeout /t 5 /nobreak >nul
