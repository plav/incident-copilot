CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS runbook_chunks (
    id              BIGSERIAL PRIMARY KEY,
    source_file     TEXT        NOT NULL,
    chunk_index     INT         NOT NULL,
    section_heading TEXT,
    content         TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    embedding       VECTOR(1024),
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_file, chunk_index)
);

CREATE INDEX IF NOT EXISTS runbook_chunks_embedding_hnsw
    ON runbook_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS runbook_chunks_metadata_gin
    ON runbook_chunks USING gin (metadata);
