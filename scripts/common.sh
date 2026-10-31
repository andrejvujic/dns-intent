# common.sh - shared steps for start.sh and demo.sh.
#
# Not meant to be run directly; the scripts in this folder load it with
# "source common.sh". Set TOTAL_STEPS before loading it.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
STEP=0

# Colors only when writing to a terminal
if [ -t 1 ]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; CYAN=$'\e[36m'; RESET=$'\e[0m'
else
    BOLD=''; GREEN=''; RED=''; YELLOW=''; CYAN=''; RESET=''
fi

step() { STEP=$((STEP + 1)); echo; echo "${BOLD}${CYAN}[$STEP/$TOTAL_STEPS] $1${RESET}"; }
ok()   { echo "${GREEN}    ✔ $1${RESET}"; }
info() { echo "      $1"; }

# Message and hint printed if the current step fails
CURRENT=""
HINT=""
fail() {
    echo
    echo "${BOLD}${RED}    ✘ ERROR: $1${RESET}"
    if [ -n "$HINT" ]; then
        echo "${YELLOW}      What to do: $HINT${RESET}"
    fi
    exit 1
}
trap 'fail "$CURRENT failed (see the message above)."' ERR

check_tools() {
    step "Checking required programs"
    command -v git >/dev/null 2>&1 \
        || { HINT="install Git from https://git-scm.com"; fail "git not found."; }
    if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
        PYTHON=python
    else
        HINT="install Python 3.10+ from https://www.python.org and check \"Add python to PATH\"."
        fail "Python not found."
    fi
    command -v npm >/dev/null 2>&1 \
        || { HINT="install Node.js (LTS) from https://nodejs.org"; fail "npm (Node.js) not found."; }
    ok "git:    $(git --version)"
    ok "python: $("$PYTHON" --version 2>&1)"
    ok "node:   $(node --version)"
}

git_pull_main() {
    step "Pulling the latest code from GitHub (main branch)"
    cd "$ROOT_DIR"
    CURRENT="Switching to the main branch"
    HINT="you have uncommitted changes. Commit them or run: git stash"
    git checkout main -q
    CURRENT="git pull"
    HINT="check your internet connection, or local changes conflict with the new code (git status)."
    git pull -q origin main
    ok "Code is up to date: $(git log -1 --format='%h %s')"
}

setup_backend() {
    step "Preparing the backend (Python dependencies)"
    cd "$BACKEND_DIR"
    CURRENT="Creating the virtual environment (.venv)"
    HINT="delete the backend/.venv folder and run the script again."
    if [ ! -d .venv ]; then
        info "Creating virtual environment backend/.venv (first run only)..."
        "$PYTHON" -m venv .venv
    fi
    # Windows venvs use Scripts/, Linux/macOS use bin/
    if [ -f .venv/Scripts/python.exe ]; then
        VENV_PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
    else
        VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
    fi
    CURRENT="Installing Python packages (pip install)"
    HINT="check your internet connection, or delete backend/.venv and run again."
    info "Installing packages from requirements.txt..."
    "$VENV_PYTHON" -m pip install -q --disable-pip-version-check -r requirements.txt
    ok "Backend is ready"
}

reset_database() {
    step "Deleting the old database and creating a new one with test data"
    cd "$BACKEND_DIR"
    CURRENT="Deleting the old database (backend/app.db)"
    HINT="the app is probably already running in another window. Stop it (Ctrl+C) and run again."
    rm -f app.db
    ok "Old database deleted"
    CURRENT="Creating and seeding the new database"
    HINT="see the error above; if it is a Python package issue, delete backend/.venv and run again."
    "$VENV_PYTHON" -m scripts.seed_database >/dev/null
    ok "New database created and filled with test data"
}

setup_frontend() {
    step "Preparing the frontend (npm install)"
    cd "$FRONTEND_DIR"
    CURRENT="npm install"
    HINT="check your internet connection and Node.js version (20.19+ or 22.12+ required)."
    info "Installing npm packages (the first run may take a while)..."
    npm install --no-audit --no-fund --loglevel=error
    ok "Frontend is ready"
}

# Starts the backend in the background and the frontend in the foreground.
# Argument: extra lines to print inside the banner (e.g. login details).
run_app() {
    step "Starting the app"
    cd "$BACKEND_DIR"
    if "$VENV_PYTHON" -c 'import socket, sys; sock = socket.socket(); sock.settimeout(0.3); result = sock.connect_ex(("127.0.0.1", 8000)); sock.close(); sys.exit(0 if result == 0 else 1)' >/dev/null 2>&1; then
        HINT="stop the process already using port 8000, then run the script again."
        fail "Port 8000 is already in use."
    fi
    "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level warning &
    BACKEND_PID=$!
    trap - ERR
    trap 'echo; echo "${YELLOW}Stopping backend and frontend...${RESET}"; kill "$BACKEND_PID" 2>/dev/null || true' EXIT

    # Do not start Vite until the API is actually accepting connections. Without
    # this check, the browser can issue its first /api request while Uvicorn is
    # still importing the app, which Vite reports as ECONNREFUSED.
    info "Waiting for the backend health check..."
    BACKEND_ATTEMPTS=0
    until "$VENV_PYTHON" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1).read()' >/dev/null 2>&1; do
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            HINT="read the backend error above; if port 8000 is already used, stop the other process and run again."
            fail "Backend stopped before it became ready."
        fi
        BACKEND_ATTEMPTS=$((BACKEND_ATTEMPTS + 1))
        if [ "$BACKEND_ATTEMPTS" -ge 50 ]; then
            HINT="check whether another process is using port 8000, then run the script again."
            fail "Backend did not become ready within 15 seconds."
        fi
        sleep 0.3
    done
    ok "Backend health check passed"

    echo
    echo "${BOLD}${GREEN}  ============================================${RESET}"
    echo "${BOLD}${GREEN}   The app is running!${RESET}"
    echo "${BOLD}${GREEN}   Open in your browser: http://localhost:5173${RESET}"
    echo "${GREEN}   Backend (API):        http://localhost:8000${RESET}"
    if [ -n "${1:-}" ]; then
        echo "${GREEN}$1${RESET}"
    fi
    echo "${GREEN}   Press Ctrl+C to stop${RESET}"
    echo "${BOLD}${GREEN}  ============================================${RESET}"
    echo

    cd "$FRONTEND_DIR"
    npm run dev --silent
}
