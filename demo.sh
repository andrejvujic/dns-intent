#!/usr/bin/env bash
#
# demo.sh - pokretanje DNS Intent aplikacije za pregled (komisija, demo).
# Svaki put počinje od čiste baze sa istim test podacima.
#
# KAKO SE POKREĆE
# ---------------
# Windows, iz PowerShell-a ili cmd-a (u dns-intent folderu):
#
#     .\demo.cmd
#
# ili dvoklikom na demo.cmd u Windows Explorer-u.
#
# Windows, iz Git Bash-a, ili Linux/macOS terminal:
#
#     bash demo.sh
#
# PAŽNJA: "bash demo.sh" u PowerShell-u NE radi (pokreće WSL umesto Git
# Bash-a). U PowerShell-u koristite .\demo.cmd.
#
# Potrebno: git, Python 3.10+, Node.js 20.19+ ili 22.12+.
#
# ŠTA RADI, REDOM
# ---------------
#   1. proverava da su git, python i npm instalirani
#   2. backend: pravi .venv ako ne postoji i instalira requirements.txt
#   3. briše bazu (backend/app.db), pravi novu i puni je test podacima (seed)
#   4. frontend: npm install
#   5. pokreće backend (http://localhost:8000) i frontend (http://localhost:5173)
#      i ispisuje podatke za prijavu
#
# Za razliku od start.sh, NE radi git pull: pokreće tačno kod koji je u folderu.
# PAŽNJA: sve izmene napravljene u aplikaciji brišu se pri sledećem pokretanju.
#
# Aplikacija se otvara u browseru na http://localhost:5173
# Ctrl+C gasi i frontend i backend.

TOTAL_STEPS=5
source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

check_tools
setup_backend
reset_database
setup_frontend

# Podaci za prijavu se čitaju iz seed-a, da uvek budu tačni
cd "$BACKEND_DIR"
SEED_EMAILS="$("$VENV_PYTHON" -c 'from app.db.seed import SEED_USERS; print("\n".join(u["email"] for u in SEED_USERS))' | tr -d '\r')"
SEED_PASSWORD="$("$VENV_PYTHON" -c 'from app.db.seed import SEED_PASSWORD; print(SEED_PASSWORD)' | tr -d '\r')"

LOGIN_INFO=$'\n   Prijava (bilo koji od korisnika):'
while IFS= read -r email; do
    LOGIN_INFO+=$'\n     '"$email"
done <<< "$SEED_EMAILS"
LOGIN_INFO+=$'\n   Šifra za sve korisnike: '"$SEED_PASSWORD"$'\n'

run_app "$LOGIN_INFO"
