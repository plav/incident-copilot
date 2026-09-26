"""Vector search over runbook_chunks."""
from functools import lru_cache

import numpy as np

from app.db import get_conn
from app.embeddings import Embedder, get_embedder


@lru_cache(maxsize=1)
def embedder() -> Embedder:
    return get_embedder()


def search_runbooks(query: str, k: int = 5) -> list[dict]:
    query_vec = np.array(embedder().embed(query))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source_file, section_heading, content, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM runbook_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec, query_vec, k),
        ).fetchall()
    return [
        {
            "source_file": r[0],
            "section": r[1],
            "title": r[3].get("title"),
            "score": round(float(r[4]), 4),
            "content": r[2],
        }
        for r in rows
    ]
