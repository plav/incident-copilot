"""Ingest runbooks into runbook_chunks.

Usage (from the repo root, venv active, DB running):
    python -m scripts.ingest            # embed new/changed chunks only
    python -m scripts.ingest --force    # re-embed everything (e.g. after switching embedder)

Each runbook is split on its "## " headings, one chunk per section. The text
that gets embedded is prefixed with the runbook title and section name, so a
chunk like "Escalation" still carries what incident it belongs to.
"""
import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from psycopg.types.json import Jsonb
except ImportError:  # lets the chunking functions be imported and tested without psycopg
    Jsonb = dict

RUNBOOKS_DIR = Path("runbooks")


@dataclass
class Chunk:
    source_file: str
    chunk_index: int
    section_heading: str
    content: str
    metadata: dict

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def chunk_runbook(path: Path) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")

    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()

    # re.split with a capture group gives [preamble, heading1, body1, heading2, body2, ...]
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    sections = [
        (heading.strip(), body.strip())
        for heading, body in zip(parts[1::2], parts[2::2])
        if body.strip()
    ]

    # A runbook with no "## " headings becomes a single chunk
    if not sections:
        body = re.sub(r"^# .+$", "", text, count=1, flags=re.MULTILINE).strip()
        sections = [("Overview", body)] if body else []

    metadata = {"title": title, "slug": path.stem}
    return [
        Chunk(
            source_file=path.as_posix(),
            chunk_index=i,
            section_heading=heading,
            content=f"{title} — {heading}\n\n{body}",
            metadata=metadata,
        )
        for i, (heading, body) in enumerate(sections)
    ]


def load_chunks(runbooks_dir: Path = RUNBOOKS_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(runbooks_dir.glob("*.md")):
        file_chunks = chunk_runbook(path)
        if not file_chunks:
            print(f"  ! {path.name}: no content, skipped")
        chunks.extend(file_chunks)
    return chunks


def ingest(conn, embedder, chunks: list[Chunk], force: bool = False) -> dict:
    stats = {"embedded": 0, "unchanged": 0, "removed": 0}

    existing = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            "SELECT source_file, chunk_index, content_hash FROM runbook_chunks"
        ).fetchall()
    }

    for chunk in chunks:
        key = (chunk.source_file, chunk.chunk_index)
        if not force and existing.get(key) == chunk.content_hash:
            stats["unchanged"] += 1
            continue

        embedding = embedder.embed(chunk.content)
        conn.execute(
            """
            INSERT INTO runbook_chunks
                (source_file, chunk_index, section_heading, content, content_hash, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_file, chunk_index) DO UPDATE SET
                section_heading = EXCLUDED.section_heading,
                content         = EXCLUDED.content,
                content_hash    = EXCLUDED.content_hash,
                embedding       = EXCLUDED.embedding,
                metadata        = EXCLUDED.metadata,
                updated_at      = now()
            """,
            (
                chunk.source_file,
                chunk.chunk_index,
                chunk.section_heading,
                chunk.content,
                chunk.content_hash,
                embedding,
                Jsonb(chunk.metadata),
            ),
        )
        stats["embedded"] += 1
        print(f"  + {chunk.source_file} [{chunk.chunk_index}] {chunk.section_heading}")

    # Remove chunks whose runbook was deleted, or that no longer exist because a runbook got shorter
    current = {(c.source_file, c.chunk_index) for c in chunks}
    for key in existing.keys() - current:
        conn.execute(
            "DELETE FROM runbook_chunks WHERE source_file = %s AND chunk_index = %s", key
        )
        stats["removed"] += 1
        print(f"  - {key[0]} [{key[1]}]")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest runbooks into pgvector")
    parser.add_argument("--force", action="store_true", help="re-embed every chunk")
    args = parser.parse_args()

    if not RUNBOOKS_DIR.is_dir():
        print(f"No {RUNBOOKS_DIR}/ folder here. Run this from the repo root.")
        return 1

    import psycopg
    from pgvector.psycopg import register_vector

    from app.config import settings
    from app.embeddings import get_embedder

    embedder = get_embedder()
    chunks = load_chunks()
    files = len({c.source_file for c in chunks})
    print(f"Embedder: {embedder.name} | {len(chunks)} chunks from {files} runbooks")

    with psycopg.connect(settings.database_url) as conn:  # commits on success, rolls back on error
        register_vector(conn)
        stats = ingest(conn, embedder, chunks, force=args.force)

    print(
        f"Done: {stats['embedded']} embedded, {stats['unchanged']} unchanged, "
        f"{stats['removed']} removed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
