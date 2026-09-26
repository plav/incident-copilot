"""Incident triage: retrieve relevant runbooks, then have the LLM analyse them."""
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLM, get_llm
from app.search import fetch_runbooks, search_runbooks


class LikelyCause(BaseModel):
    cause: str
    confidence: Literal["low", "medium", "high"]
    runbook: str = Field(description="Title of the runbook this cause comes from")


class TriageAnalysis(BaseModel):
    """What the LLM must return."""

    summary: str = Field(description="One or two sentences on what is probably happening")
    likely_causes: list[LikelyCause]
    diagnostic_steps: list[str]
    resolution_steps: list[str]
    escalate: bool
    escalation_reason: str | None


class Source(BaseModel):
    runbook: str
    section: str
    source_file: str
    score: float


class TriageResponse(TriageAnalysis):
    """What the API returns: the analysis plus the sources we actually retrieved."""

    incident: str
    sources: list[Source]
    model: str


SYSTEM_PROMPT = """You are an incident triage assistant for an on-call engineer.
You are given an incident description and the team's most relevant runbooks.

How to answer:
1. Decide which runbook best matches the incident. Compare the incident's
   symptoms against each runbook's Symptoms section, and use every clue given
   (timing, recent deploys, which metrics look normal or abnormal).
2. summary: your diagnosis in one or two sentences, e.g. "Most likely X because Y."
   Do NOT just repeat the incident text.
3. likely_causes: 1-3 causes, most likely first, taken from the runbooks'
   Likely Causes sections. "runbook" must be the title of the runbook the cause
   comes from. Use "high" confidence only when the clues clearly point to it.
4. diagnostic_steps and resolution_steps: take them from the best-matching
   runbook, adapted to this incident. Only add steps from another runbook if
   it is also a plausible cause.
5. escalate: follow the best-matching runbook's Escalation section.

Use ONLY the runbooks provided. If none of them fit, say so in the summary,
leave likely_causes empty and set escalate to true."""


@lru_cache(maxsize=1)
def llm() -> LLM:
    return get_llm()


def section_body(content: str) -> str:
    """Strip the 'Title — Section' prefix added at ingestion."""
    return content.split("\n\n", 1)[-1]


def top_runbooks(chunks: list[dict], max_runbooks: int) -> list[str]:
    """Source files ranked by their best-scoring chunk (chunks arrive best first)."""
    ranked: list[str] = []
    for c in chunks:
        if c["source_file"] not in ranked:
            ranked.append(c["source_file"])
    return ranked[:max_runbooks]


def build_prompt(incident: str, runbooks: dict[str, list[dict]]) -> str:
    blocks = []
    for sections in runbooks.values():
        if not sections:
            continue
        body = "\n\n".join(f"## {s['section']}\n{section_body(s['content'])}" for s in sections)
        blocks.append(f"=== RUNBOOK: {sections[0]['title']} ===\n{body}")
    return f"INCIDENT:\n{incident}\n\n" + "\n\n".join(blocks)


def schema_for(titles: list[str]) -> dict:
    """Triage schema with 'runbook' restricted to the retrieved titles, so citations can't be invented."""
    schema = TriageAnalysis.model_json_schema()
    if titles:
        schema["$defs"]["LikelyCause"]["properties"]["runbook"]["enum"] = titles
    return schema


def triage(incident: str, k: int = 8, max_runbooks: int = 3) -> TriageResponse:
    chunks = search_runbooks(incident, k)
    runbooks = fetch_runbooks(top_runbooks(chunks, max_runbooks))
    titles = [sections[0]["title"] for sections in runbooks.values() if sections]
    model = llm()

    raw = model.generate_json(SYSTEM_PROMPT, build_prompt(incident, runbooks), schema_for(titles))
    try:
        analysis = TriageAnalysis.model_validate_json(raw)
    except ValidationError as e:
        raise ValueError(f"LLM returned invalid JSON for the triage schema: {e}") from e

    # Safety net: drop any cause citing a runbook we didn't give the model
    analysis.likely_causes = [c for c in analysis.likely_causes if c.runbook in titles]

    return TriageResponse(
        **analysis.model_dump(),
        incident=incident,
        sources=[
            Source(runbook=c["title"], section=c["section"], source_file=c["source_file"], score=c["score"])
            for c in chunks
        ],
        model=model.name,
    )
