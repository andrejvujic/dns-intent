import argparse

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import engine


def drop_database() -> None:
    Base.metadata.drop_all(bind=engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop all DNSIntent database tables")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation",
    )
    args = parser.parse_args()

    database = engine.url.render_as_string(hide_password=True)
    if not args.yes:
        confirmation = input(
            f"This will drop every table in {database}. Type DROP to continue: "
        )
        if confirmation != "DROP":
            print("Drop cancelled.")
            return

    drop_database()
    print(f"Dropped all tables in {database}.")


if __name__ == "__main__":
    main()
