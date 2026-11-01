from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.domains import router as domains_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, migrate_membership_schema, migrate_panic_schema
import app.models  # noqa: F401


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(domains_router)


@app.on_event("startup")
def prepare_database() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_panic_schema()
    migrate_membership_schema()


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
