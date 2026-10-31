from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate_panic_schema() -> None:
    """Small POC migration for databases created before the panic workflow UI."""
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "panic_requests" not in inspector.get_table_names():
        return
    request_columns = {item["name"] for item in inspector.get_columns("panic_requests")}
    signature_columns = {item["name"] for item in inspector.get_columns("panic_signatures")}
    with engine.begin() as connection:
        if "change_json" not in request_columns:
            connection.execute(text("ALTER TABLE panic_requests ADD COLUMN change_json JSON"))
        if "hash" not in request_columns:
            connection.execute(text("ALTER TABLE panic_requests ADD COLUMN hash VARCHAR(44)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_panic_requests_hash ON panic_requests (hash)"))
        if "creator_signature" not in request_columns:
            connection.execute(text("ALTER TABLE panic_requests ADD COLUMN creator_signature VARCHAR(88)"))
        if "decision" not in signature_columns:
            connection.execute(text("ALTER TABLE panic_signatures ADD COLUMN decision VARCHAR(6)"))


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
