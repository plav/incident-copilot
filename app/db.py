"""Postgres connection pool with pgvector registered."""
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(
    settings.database_url,
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
