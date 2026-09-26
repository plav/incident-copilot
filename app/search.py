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


def fetch_runbooks(source_files: list[str]) -> dict[str, list[dict]]:
    """All sections of the given runbooks, in document order, keyed by source_file."""
    if not source_files:
        return {}
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source_file, section_heading, content, metadata
            FROM runbook_chunks
            WHERE source_file = ANY(%s)
            ORDER BY source_file, chunk_index
            """,
            (source_files,),
        ).fetchall()
    runbooks: dict[str, list[dict]] = {f: [] for f in source_files}
    for source_file, section, content, metadata in rows:
        runbooks[source_file].append(
            {"title": metadata.get("title"), "section": section, "content": content}
        )
    return runbooks
