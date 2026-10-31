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
