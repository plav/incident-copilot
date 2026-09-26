"""Postgres connection pool with pgvector registered."""
import os
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://copilot:copilot@localhost:5432/incident_copilot",
)

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    configure=register_vector,
    open=False,
)


def open_pool() -> None:
    pool.open(wait=True)


def close_pool() -> None:
    pool.close()


@contextmanager
def get_conn():
    with pool.connection() as conn:
        yield conn


def db_healthy() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1 FROM runbook_chunks LIMIT 1")
        return True
    except Exception:
        return False
