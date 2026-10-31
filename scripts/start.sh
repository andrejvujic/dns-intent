#!/usr/bin/env bash
#
# start.sh - pulls the latest code from main and starts the whole DNS Intent
# app (backend + frontend) with one command. The existing database is NOT deleted.
#
# HOW TO RUN
# ----------
# Windows, from PowerShell or cmd (in the dns-intent folder):
#
#     .\scripts\start.cmd
#
# Windows from Git Bash (right-click the folder -> "Open Git Bash here"),
# or a Linux/macOS terminal:
#
#     bash scripts/start.sh
#
# NOTE: "bash scripts/start.sh" does NOT work in PowerShell. There "bash"
# starts WSL and prints "Windows Subsystem for Linux has no installed
# distributions". In PowerShell use .\scripts\start.cmd.
#
# Requires: git, Python 3.10+, Node.js 20.19+ or 22.12+.
#
# WHAT IT DOES, IN ORDER
# ----------------------
#   1. checks that git, python and npm are installed
#   2. git checkout main  +  git pull origin main
#   3. backend: creates .venv if missing and installs requirements.txt
#   4. frontend: npm install
#   5. starts the backend (uvicorn, http://localhost:8000) in the background
#      and the frontend (vite, http://localhost:5173)
#
# For a clean database with test data (e.g. for judges) use demo.sh / demo.cmd.
#
# The app opens in the browser at http://localhost:5173
# Ctrl+C stops both frontend and backend.

TOTAL_STEPS=5
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_tools
git_pull_main
setup_backend
setup_frontend
run_app
