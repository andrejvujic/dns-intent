@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m scripts.signature_app
) else (
    python -m scripts.signature_app
)

if errorlevel 1 pause
