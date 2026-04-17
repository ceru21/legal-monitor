from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection as PGConnection


DEFAULT_DATABASE_URL = "postgresql://legal_monitor:legal_monitor@127.0.0.1:5432/legal_monitor"


def get_database_url(explicit_url: str | None = None) -> str:
    return explicit_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


@contextmanager
def get_connection(database_url: str | None = None) -> Iterator[PGConnection]:
    conn = psycopg2.connect(get_database_url(database_url))
    try:
        yield conn
    finally:
        conn.close()
