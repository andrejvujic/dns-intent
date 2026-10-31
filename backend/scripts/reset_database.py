import argparse

from app.db.seed import SEED_PASSWORD, seed_database
from app.db.session import SessionLocal, engine
from app.db.base import Base
import app.models  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drop, recreate, and seed the DNSIntent database"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation",
    )
    args = parser.parse_args()

    database = engine.url.render_as_string(hide_password=True)
    if not args.yes:
        confirmation = input(
            f"This will erase and reseed {database}. Type RESET to continue: "
        )
        if confirmation != "RESET":
            print("Reset cancelled.")
            return

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)

    print(f"Reset and seeded {database} successfully.")
    print("Users: 5 | Domains: 1 | DNS records: 5 | IE records: 0")
    print(f"Development password for every seed user: {SEED_PASSWORD}")


if __name__ == "__main__":
    main()
