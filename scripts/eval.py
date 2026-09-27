"""Evaluate retrieval and triage against labelled incidents.

Usage (from the repo root, venv active, DB + Ollama running):
    python -m scripts.eval                     # retrieval + triage
    python -m scripts.eval --retrieval-only    # fast: skips the LLM
    OLLAMA_CHAT_MODEL=llama3.2 python -m scripts.eval   # compare another model
    python -m scripts.eval --cases private/incidents.json   # a different test set

Metrics:
    retrieval hit@1 / hit@3: is the expected runbook the best / in the top 3
        runbooks found by vector search? (in-scope cases only)
    triage accuracy: in-scope -> the top likely cause cites the expected runbook;
        out-of-scope -> no cause is given with medium/high confidence.

Results are saved to evals/results/ so runs can be compared over time.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

CASES_FILE = Path("evals/incidents.json")
RESULTS_DIR = Path("evals/results")


def ranked_runbooks(chunks: list[dict]) -> list[str]:
    """Runbook titles ranked by their best-scoring chunk (chunks arrive best first)."""
    titles: list[str] = []
    for c in chunks:
        if c["title"] not in titles:
            titles.append(c["title"])
    return titles


def triage_is_correct(expected: str | None, likely_causes: list[dict]) -> bool:
    if expected is None:
        return not any(c["confidence"] in ("medium", "high") for c in likely_causes)
    return bool(likely_causes) and likely_causes[0]["runbook"] == expected


def evaluate_case(case: dict, search_fn, triage_fn=None, k: int = 8) -> dict:
    chunks = search_fn(case["incident"], k)
    ranked = ranked_runbooks(chunks)
    expected = case["expected"]
    result = {
        "id": case["id"],
        "difficulty": case["difficulty"],
        "expected": expected,
        "retrieved": ranked[:3],
        "top_score": chunks[0]["score"] if chunks else None,
        "hit_at_1": (ranked[:1] == [expected]) if expected else None,
        "hit_at_3": (expected in ranked[:3]) if expected else None,
    }
    if triage_fn:
        start = time.perf_counter()
        try:
            response = triage_fn(case["incident"], k).model_dump()
            causes = response["likely_causes"]
            result.update(
                predicted=causes[0]["runbook"] if causes else None,
                confidence=causes[0]["confidence"] if causes else None,
                escalate=response["escalate"],
                triage_correct=triage_is_correct(expected, causes),
                error=None,
            )
        except Exception as e:  # a bad LLM response counts as a miss, not a crash
            result.update(predicted=None, triage_correct=False, error=str(e)[:200])
        result["latency_s"] = round(time.perf_counter() - start, 2)
    return result


def summarise(results: list[dict]) -> dict:
    in_scope = [r for r in results if r["expected"] is not None]
    summary = {
        "cases": len(results),
        "hit_at_1": sum(r["hit_at_1"] for r in in_scope),
        "hit_at_3": sum(r["hit_at_3"] for r in in_scope),
        "in_scope": len(in_scope),
    }
    if "triage_correct" in results[0]:
        summary["triage_correct"] = sum(r["triage_correct"] for r in results)
        summary["avg_latency_s"] = round(sum(r["latency_s"] for r in results) / len(results), 2)
        summary["by_difficulty"] = {}
        for d in dict.fromkeys(r["difficulty"] for r in results):
            group = [r for r in results if r["difficulty"] == d]
            summary["by_difficulty"][d] = f"{sum(r['triage_correct'] for r in group)}/{len(group)}"
    return summary


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def print_report(results: list[dict], summary: dict, label: str) -> None:
    triage = "triage_correct" in results[0]
    print(f"\n{label}\n")
    header = f"{'case':<10} {'expected':<38} {'retrieval top-1':<38} {'r@1':<4}"
    if triage:
        header += f" {'triage predicted':<38} {'ok':<3} {'secs':>5}"
    print(header)
    print("-" * len(header))
    for r in results:
        expected = r["expected"] or "(none)"
        top = r["retrieved"][0] if r["retrieved"] else "-"
        r1 = "-" if r["hit_at_1"] is None else ("✓" if r["hit_at_1"] else "✗")
        line = f"{r['id']:<10} {expected[:37]:<38} {top[:37]:<38} {r1:<4}"
        if triage:
            predicted = r["predicted"] or ("ERROR" if r.get("error") else "(none)")
            ok = "✓" if r["triage_correct"] else "✗"
            line += f" {predicted[:37]:<38} {ok:<3} {r['latency_s']:>5}"
        print(line)

    print(f"\nRetrieval hit@1:  {pct(summary['hit_at_1'], summary['in_scope'])}")
    print(f"Retrieval hit@3:  {pct(summary['hit_at_3'], summary['in_scope'])}")
    if triage:
        print(f"Triage accuracy:  {pct(summary['triage_correct'], summary['cases'])}")
        print(f"  by difficulty:  " + ", ".join(f"{d} {s}" for d, s in summary["by_difficulty"].items()))
        print(f"Avg triage time:  {summary['avg_latency_s']}s")
        errors = [r for r in results if r.get("error")]
        for r in errors:
            print(f"  ! {r['id']}: {r['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval and triage")
    parser.add_argument("--retrieval-only", action="store_true", help="skip the LLM (fast)")
    parser.add_argument("--k", type=int, default=8, help="chunks to retrieve per case")
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="JSON file of test incidents")
    args = parser.parse_args()

    from app.config import settings
    from app.db import close_pool, open_pool
    from app.search import search_runbooks

    triage_fn = None
    if not args.retrieval_only:
        from app.triage import triage as triage_fn

    cases = json.loads(args.cases.read_text())
    label = f"embedder={settings.embedder}/{settings.ollama_embed_model}"
    if triage_fn:
        label += f"  llm={settings.llm}/{settings.ollama_chat_model}"
    print(f"Running {len(cases)} cases from {args.cases}  |  {label}")

    open_pool()
    try:
        results = []
        for i, case in enumerate(cases, 1):
            print(f"  [{i}/{len(cases)}] {case['id']}", flush=True)
            results.append(evaluate_case(case, search_runbooks, triage_fn, args.k))
    finally:
        close_pool()

    summary = summarise(results)
    print_report(results, summary, label)

    # Results go next to the cases file, so private runs stay in the private folder
    results_dir = RESULTS_DIR if args.cases == CASES_FILE else args.cases.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    model = settings.ollama_chat_model if triage_fn else "retrieval-only"
    out = results_dir / f"{datetime.now():%Y%m%d-%H%M}-{model.replace(':', '-')}.json"
    out.write_text(json.dumps({"label": label, "summary": summary, "results": results}, indent=2))
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
