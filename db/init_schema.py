"""Create all tables (idempotent — safe to run multiple times)."""
from __future__ import annotations

from db import engine
from db.models import Base  # noqa: F401 — registers all models


def main() -> None:
    Base.metadata.create_all(engine)
    print("Schema created (or already up to date).")


if __name__ == "__main__":
    main()
