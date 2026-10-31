# DNS Intent

## Quick start (for reviewers)

Requires Git, Python 3.10+ and Node.js 20.19+ or 22.12+.

Windows: double-click `scripts\demo.cmd`, or run from PowerShell in this folder:

```powershell
.\scripts\demo.cmd
```

Linux/macOS or Git Bash:

```bash
bash scripts/demo.sh
```

- Installs dependencies.
- Deletes the database and creates a fresh one with test data.
- Starts the backend and frontend.
- App: `http://localhost:5173`. Login details are printed in the terminal.
- `Ctrl+C` stops the app.

For day-to-day team work, use `scripts\start.cmd` / `scripts/start.sh`: runs
`git pull` on `main` and starts the app without deleting the database. Shared
steps for both scripts live in `scripts/common.sh`.

## Tech stack

- Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic, Uvicorn
- Frontend: React, Vite, JavaScript

## Running the backend

Requires Python 3.10+.

Create the virtual environment and install dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Activate the virtual environment on Windows PowerShell (instead of `source`):

```powershell
.venv\Scripts\Activate.ps1
```

Start the backend:

```bash
uvicorn app.main:app --reload
```

- Backend: `http://localhost:8000`
- Health endpoint: `http://localhost:8000/api/health`
- Environment variables are listed in `backend/.env.example` (optional; defaults work locally).

### Email notifications

When a signed intent is scheduled, every active member of that domain receives a
personalized notification. Email is sent in the background, so a temporary SMTP
failure does not undo a successfully scheduled intent.

For Gmail, fill in these values in `backend/.env`:

```dotenv
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-16-character-google-app-password
SMTP_FROM_EMAIL=your-address@gmail.com
```

`backend/.env` is ignored by Git. Use the Google app password rather than the
regular password for the Gmail account. The remaining SMTP defaults already
target Gmail on port 587 with STARTTLS.

Enabling DNS Intent generates an Ed25519 intent and panic key pair for every active
domain member in the browser. Public keys are stored by the backend; private keys
are downloaded as an organized JSON file and never uploaded.

When DNS Intent is enabled, a member can schedule a change by submitting its
Base64 SHA-256 commitment hash and Ed25519 signature. The backend verifies the
signature and starts the configured hold period. All domain members can review
scheduled commits and their creation/maturity times in the domain UI.

The nonce is generated once by the client and used to calculate
`SHA-256(canonical_intent || nonce)`. It is deliberately not sent while scheduling
the commit; the same nonce is sent only with the intent during the later reveal
phase, allowing the server to reproduce the hash without exposing the intended
change during the hold period.

After the hold period, applying a commit requires both the original Intent JSON
and that same Base64 nonce. The reveal endpoint recalculates the commitment,
checks the intent validity window and domain, applies the protected add/update/
delete operation, and marks the commit `CONSUMED` to prevent replay.

The domain UI can generate the Intent JSON without manual editing. Sign the
downloaded file locally and save a bundle with:

```bash
cd backend
python -m scripts.create_commit /path/to/intent.json \
  --private-key 'BASE64_PRIVATE_KEY' \
  --output signing-bundle.json
```

Upload `signing-bundle.json` in the commit form. Keep both the original Intent
file and the bundle secure: the bundle contains the nonce needed later. During
reveal, upload the original Intent JSON and paste `reveal_secret.nonce` from the
bundle.

For a panic change, enable the red **Panic change** checkbox in the same Intent
builder. Sign the downloaded JSON with the member's panic private key:

```bash
cd backend
python -m scripts.create_panic_signature /path/to/panic.json \
  --private-key 'BASE64_PANIC_PRIVATE_KEY' \
  --output panic-signature.json
```

The requester uploads both files. Other members review and download the exact
JSON from **Pending Panic Changes**, sign it, validate their signature, and vote
ACCEPT or REJECT. Either counter reaching the configured panic quorum closes the
request; accepted changes execute immediately. Panic changes can also cancel an
active scheduled commit.

## Running the frontend

Requires Node.js 20.19+ or 22.12+.

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── common.sh
│   ├── demo.cmd
│   ├── demo.sh
│   ├── start.cmd
│   └── start.sh
└── README.md
```
