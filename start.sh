#!/usr/bin/env bash
#
# start.sh - povlači najnoviji kod sa main grane i pokreće ceo DNS Intent
# (backend + frontend) jednom komandom. Postojeća baza se NE briše.
#
# KAKO SE POKREĆE
# ---------------
# Windows, iz PowerShell-a ili cmd-a (u dns-intent folderu):
#
#     .\start.cmd
#
# Windows, iz Git Bash-a (desni klik u folderu -> "Open Git Bash here"),
# ili Linux/macOS terminal:
#
#     bash start.sh
#
# PAŽNJA: "bash start.sh" u PowerShell-u NE radi. Tamo "bash" pokreće WSL
# i ispisuje "Windows Subsystem for Linux has no installed distributions".
# U PowerShell-u koristite .\start.cmd.
#
# Potrebno: git, Python 3.10+, Node.js 20.19+ ili 22.12+.
#
# ŠTA RADI, REDOM
# ---------------
#   1. proverava da su git, python i npm instalirani
#   2. git checkout main  +  git pull origin main
#   3. backend: pravi .venv ako ne postoji i instalira requirements.txt
#   4. frontend: npm install
#   5. pokreće backend (uvicorn, http://localhost:8000) u pozadini
#      i frontend (vite, http://localhost:5173)
#
# Za čistu bazu sa test podacima (npr. za komisiju) koristite demo.sh / demo.cmd.
#
# Aplikacija se otvara u browseru na http://localhost:5173
# Ctrl+C gasi i frontend i backend.

TOTAL_STEPS=5
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

check_tools
git_pull_main
setup_backend
setup_frontend
run_app
