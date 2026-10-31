# DNS Intent

## Tehnologije

- Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic i Uvicorn
- Frontend: React, Vite i JavaScript

## Pokretanje backenda

Potrebni su Python 3.10 ili noviji.

Priprema virtuelnog okruženja i zavisnosti:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pokretanje backenda:

```bash
uvicorn app.main:app --reload
```

Na Windows PowerShell-u virtuelno okruženje se aktivira komandom:

```powershell
.venv\Scripts\Activate.ps1
```

Backend je dostupan na `http://localhost:8000`, a health endpoint na
`http://localhost:8000/api/health`.

`backend/.env.example` dokumentuje dostupne promenljive okruženja. Njihovo
podešavanje nije obavezno jer podrazumevane vrednosti već rade lokalno.

## Pokretanje frontenda

Potreban je Node.js 20.19+ ili 22.12+.

U drugom terminalu pokrenite:

```bash
cd frontend
npm install
npm run dev
```

Frontend je dostupan na `http://localhost:5173`.

## Struktura

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
└── README.md
```
