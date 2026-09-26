"""Embedding backends. Pick one with EMBEDDER=fake|bedrock in .env."""
import hashlib
import json
from typing import Protocol

import numpy as np

from app.config import settings


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Deterministic, offline vectors from a hash of the text.

    Same text -> same vector, so the pipeline (chunking, upserts, change
    detection) can be tested end to end. Search results are meaningless.
    """

    name = "fake"

    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vec = np.random.default_rng(seed).standard_normal(self.dim)
        return (vec / np.linalg.norm(vec)).tolist()


class BedrockEmbedder:
    """Amazon Titan Text Embeddings v2 via Bedrock."""

    name = "bedrock"

    def __init__(self, model_id: str, region: str, dim: int):
        import boto3  # imported here so the fake embedder works without AWS set up

        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())["embedding"]


def get_embedder() -> Embedder:
    if settings.embedder == "bedrock":
        return BedrockEmbedder(
            settings.embedding_model_id, settings.aws_region, settings.embedding_dim
        )
    if settings.embedder == "fake":
        return FakeEmbedder(settings.embedding_dim)
    raise ValueError(f"Unknown EMBEDDER {settings.embedder!r} (expected 'fake' or 'bedrock')")
