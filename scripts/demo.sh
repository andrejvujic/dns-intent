#!/usr/bin/env bash
#
# demo.sh - runs the DNS Intent app for review (judges, demos).
# Every run starts from a clean database with the same test data.
#
# HOW TO RUN
# ----------
# Windows, from PowerShell or cmd (in the dns-intent folder):
#
#     .\scripts\demo.cmd
#
# or double-click scripts\demo.cmd in Windows Explorer.
#
# Windows from Git Bash, or a Linux/macOS terminal:
#
#     bash scripts/demo.sh
#
# NOTE: "bash scripts/demo.sh" does NOT work in PowerShell (it starts WSL
# instead of Git Bash). In PowerShell use .\scripts\demo.cmd.
#
# Requires: git, Python 3.10+, Node.js 20.19+ or 22.12+.
#
# WHAT IT DOES, IN ORDER
# ----------------------
#   1. checks that git, python and npm are installed
#   2. backend: creates .venv if missing and installs requirements.txt
#   3. deletes the database (backend/app.db), creates a new one and seeds it
#   4. frontend: npm install
#   5. starts the backend (http://localhost:8000) and frontend (http://localhost:5173)
#      and prints the login details
#
# Unlike start.sh, it does NOT run git pull: it runs exactly the code in the folder.
# NOTE: any changes made in the app are erased on the next run.
#
# The app opens in the browser at http://localhost:5173
# Ctrl+C stops both frontend and backend.

TOTAL_STEPS=5
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

check_tools
setup_backend
reset_database
setup_frontend

# Login details are read from the seed so they always match
cd "$BACKEND_DIR"
SEED_EMAILS="$("$VENV_PYTHON" -c 'from app.db.seed import SEED_USERS; print("\n".join(u["email"] for u in SEED_USERS))' | tr -d '\r')"
SEED_PASSWORD="$("$VENV_PYTHON" -c 'from app.db.seed import SEED_PASSWORD; print(SEED_PASSWORD)' | tr -d '\r')"

LOGIN_INFO=$'\n   Log in with any of these users:'
while IFS= read -r email; do
    LOGIN_INFO+=$'\n     '"$email"
done <<< "$SEED_EMAILS"
LOGIN_INFO+=$'\n   Password (same for all users): '"$SEED_PASSWORD"$'\n'

run_app "$LOGIN_INFO"
