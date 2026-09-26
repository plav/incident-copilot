"""LLM backends. Pick one with LLM=ollama|fake in .env."""
import json
import urllib.request
from typing import Protocol

from app.config import settings


class LLM(Protocol):
    name: str

    def generate_json(self, system: str, user: str, schema: dict) -> str: ...


class OllamaLLM:
    """Local chat model via Ollama, constrained to a JSON schema."""

    name = "ollama"

    def __init__(self, model: str, base_url: str):
        self.model = model
        self.url = f"{base_url.rstrip('/')}/api/chat"
        self.name = f"ollama/{model}"

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,  # Ollama constrains output to this JSON schema
            "stream": False,
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read())["message"]["content"]


class FakeLLM:
    """Returns a fixed, schema-valid answer. For tests and running without a model."""

    name = "fake"

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        return json.dumps(
            {
                "summary": "Stub triage: no real model was called.",
                "likely_causes": [],
                "diagnostic_steps": ["Set LLM=ollama in .env to get a real analysis"],
                "resolution_steps": [],
                "escalate": False,
                "escalation_reason": None,
            }
        )


def get_llm() -> LLM:
    if settings.llm == "ollama":
        return OllamaLLM(settings.ollama_chat_model, settings.ollama_url)
    if settings.llm == "fake":
        return FakeLLM()
    raise ValueError(f"Unknown LLM {settings.llm!r} (expected 'ollama' or 'fake')")
