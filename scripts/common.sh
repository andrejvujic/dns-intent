# common.sh - zajednički koraci za start.sh i demo.sh.
#
# Ne pokreće se direktno; skripte iz korenskog foldera ga učitavaju sa
# "source scripts/common.sh". Pre učitavanja treba postaviti TOTAL_STEPS.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
STEP=0

# Boje samo kad se ispisuje u terminal
if [ -t 1 ]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; CYAN=$'\e[36m'; RESET=$'\e[0m'
else
    BOLD=''; GREEN=''; RED=''; YELLOW=''; CYAN=''; RESET=''
fi

step() { STEP=$((STEP + 1)); echo; echo "${BOLD}${CYAN}[$STEP/$TOTAL_STEPS] $1${RESET}"; }
ok()   { echo "${GREEN}    ✔ $1${RESET}"; }
info() { echo "      $1"; }

# Poruka i savet koji se ispisuju ako trenutni korak pukne
CURRENT=""
HINT=""
fail() {
    echo
    echo "${BOLD}${RED}    ✘ GREŠKA: $1${RESET}"
    if [ -n "$HINT" ]; then
        echo "${YELLOW}      Šta uraditi: $HINT${RESET}"
    fi
    exit 1
}
trap 'fail "$CURRENT nije uspelo (pogledajte poruku iznad)."' ERR

check_tools() {
    step "Proveravam da li su potrebni programi instalirani"
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
}

git_pull_main() {
    step "Preuzimam najnoviji kod sa GitHub-a (main grana)"
    cd "$ROOT_DIR"
    CURRENT="Prebacivanje na main granu"
    HINT="imate izmene koje nisu commit-ovane. Commit-ujte ih ili pokrenite: git stash"
    git checkout main -q
    CURRENT="git pull"
    HINT="proverite internet konekciju, ili imate lokalne izmene koje se sukobljavaju sa novim kodom (git status)."
    git pull -q origin main
    ok "Kod je ažuran: $(git log -1 --format='%h %s')"
}

setup_backend() {
    step "Pripremam backend (Python zavisnosti)"
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
}

reset_database() {
    step "Brišem staru bazu i pravim novu sa test podacima"
    cd "$BACKEND_DIR"
    CURRENT="Brisanje stare baze (backend/app.db)"
    HINT="aplikacija je verovatno već pokrenuta u drugom prozoru. Ugasite je (Ctrl+C) i pokrenite ponovo."
    rm -f app.db
    ok "Stara baza je obrisana"
    CURRENT="Pravljenje nove baze i seed"
    HINT="pogledajte grešku iznad; ako je u pitanju Python paket, obrišite backend/.venv i pokrenite ponovo."
    "$VENV_PYTHON" -m scripts.seed_database >/dev/null
    ok "Nova baza je napravljena i popunjena test podacima"
}

setup_frontend() {
    step "Pripremam frontend (npm install)"
    cd "$FRONTEND_DIR"
    CURRENT="npm install"
    HINT="proverite internet konekciju i verziju Node.js-a (treba 20.19+ ili 22.12+)."
    info "Instaliram npm pakete (prvi put može potrajati)..."
    npm install --no-audit --no-fund --loglevel=error
    ok "Frontend je spreman"
}

# Pokreće backend u pozadini i frontend u prvom planu.
# Argument: dodatne linije koje se ispisuju u okviru (npr. podaci za login).
run_app() {
    step "Pokrećem aplikaciju"
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
    if [ -n "${1:-}" ]; then
        echo "${GREEN}$1${RESET}"
    fi
    echo "${GREEN}   Za gašenje pritisnite Ctrl+C${RESET}"
    echo "${BOLD}${GREEN}  ============================================${RESET}"
    echo

    cd "$FRONTEND_DIR"
    npm run dev --silent
}
