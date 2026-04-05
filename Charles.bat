@echo off
title Charles AI Assistant
cd /d "%~dp0launcher"

:: First run: install Electron and dependencies if node_modules is missing
if not exist "node_modules" (
    echo [Charles] First run -- installing dependencies, this may take a minute...
    npm install
    if errorlevel 1 (
        echo [Charles] ERROR: npm install failed. Make sure Node.js is installed.
        pause
        exit /b 1
    )
)

:: Launch the Electron app (it handles spawning the Python API internally)
echo [Charles] Starting...
npx electron .
