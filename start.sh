#!/usr/bin/env bash
#
# start.sh - povlači najnoviji kod sa main grane i pokreće ceo DNS Intent
# (backend + frontend) jednom komandom.
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
# Aplikacija se otvara u browseru na http://localhost:5173
# Ctrl+C gasi i frontend i backend.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
TOTAL_STEPS=5

# Boje samo kad se ispisuje u terminal
if [ -t 1 ]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; CYAN=$'\e[36m'; RESET=$'\e[0m'
else
    BOLD=''; GREEN=''; RED=''; YELLOW=''; CYAN=''; RESET=''
fi

step() { echo; echo "${BOLD}${CYAN}[$1/$TOTAL_STEPS] $2${RESET}"; }
ok()   { echo "${GREEN}    ✔ $1${RESET}"; }
info() { echo "      $1"; }

# Poruka i savet koji se ispisuju ako trenutni korak pukne
HINT=""
fail() {
    echo
    echo "${BOLD}${RED}    ✘ GREŠKA: $1${RESET}"
    if [ -n "$HINT" ]; then
        echo "${YELLOW}      Šta uraditi: $HINT${RESET}"
    fi
    exit 1
}
CURRENT=""
trap 'fail "$CURRENT nije uspelo (pogledajte poruku iznad)."' ERR

# 1. Provera alata
step 1 "Proveravam da li su potrebni programi instalirani"
command -v git >/dev/null 2>&1 \
    || { HINT="instalirajte Git sa https://git-scm.com"; fail "git nije pronađen."; }
if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    PYTHON=python
else
    HINT="instalirajte Python 3.10+ sa https://www.python.org i štiklirajte \"Add python to PATH\"."
    fail "Python nije pronađen."
fi
command -v npm >/dev/null 2>&1 \
    || { HINT="instalirajte Node.js (LTS) sa https://nodejs.org"; fail "npm (Node.js) nije pronađen."; }
ok "git:    $(git --version)"
ok "python: $("$PYTHON" --version 2>&1)"
ok "node:   $(node --version)"

# 2. Najnoviji kod sa main grane
step 2 "Preuzimam najnoviji kod sa GitHub-a (main grana)"
cd "$ROOT_DIR"
CURRENT="Prebacivanje na main granu"
HINT="imate izmene koje nisu commit-ovane. Commit-ujte ih ili pokrenite: git stash"
git checkout main -q
CURRENT="git pull"
HINT="proverite internet konekciju, ili imate lokalne izmene koje se sukobljavaju sa novim kodom (git status)."
git pull -q origin main
ok "Kod je ažuran: $(git log -1 --format='%h %s')"

# 3. Backend: virtuelno okruženje i zavisnosti
step 3 "Pripremam backend (Python zavisnosti)"
cd "$BACKEND_DIR"
CURRENT="Pravljenje virtuelnog okruženja (.venv)"
HINT="obrišite backend/.venv folder i pokrenite skriptu ponovo."
if [ ! -d .venv ]; then
    info "Pravim virtuelno okruženje backend/.venv (samo prvi put)..."
    "$PYTHON" -m venv .venv
fi
# Windows venv ima Scripts/, Linux/macOS ima bin/
if [ -f .venv/Scripts/python.exe ]; then
    VENV_PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
else
    VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
fi
CURRENT="Instalacija Python paketa (pip install)"
HINT="proverite internet konekciju, ili obrišite backend/.venv i pokrenite ponovo."
info "Instaliram pakete iz requirements.txt..."
"$VENV_PYTHON" -m pip install -q --disable-pip-version-check -r requirements.txt
ok "Backend je spreman"

# 4. Frontend: npm zavisnosti
step 4 "Pripremam frontend (npm install)"
cd "$FRONTEND_DIR"
CURRENT="npm install"
HINT="proverite internet konekciju i verziju Node.js-a (treba 20.19+ ili 22.12+)."
info "Instaliram npm pakete (prvi put može potrajati)..."
npm install --no-audit --no-fund --loglevel=error
ok "Frontend je spreman"

# 5. Pokretanje
step 5 "Pokrećem aplikaciju"
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn app.main:app --reload --log-level warning &
BACKEND_PID=$!
trap - ERR
trap 'echo; echo "${YELLOW}Gasim backend i frontend...${RESET}"; kill "$BACKEND_PID" 2>/dev/null || true' EXIT

echo
echo "${BOLD}${GREEN}  ============================================${RESET}"
echo "${BOLD}${GREEN}   Aplikacija je pokrenuta!${RESET}"
echo "${BOLD}${GREEN}   Otvorite u browseru:  http://localhost:5173${RESET}"
echo "${GREEN}   Backend (API):         http://localhost:8000${RESET}"
echo "${GREEN}   Za gašenje pritisnite Ctrl+C${RESET}"
echo "${BOLD}${GREEN}  ============================================${RESET}"
echo

cd "$FRONTEND_DIR"
npm run dev --silent
