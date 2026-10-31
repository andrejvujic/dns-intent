import app.models  # noqa: F401
from app.db.base import Base
from app.db.seed import SEED_PASSWORD, seed_database
from app.db.session import SessionLocal, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)

    print("Seed data inserted successfully.")
    print("Users: 5 | Domains: 1 | DNS records: 5 | IE records: 0")
    print(f"Development password for every seed user: {SEED_PASSWORD}")


if __name__ == "__main__":
    main()
