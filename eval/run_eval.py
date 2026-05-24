"""Evaluate the RAG system against the golden question set.

For each question we hit POST /api/chat and score four dimensions:

  1. Retrieval hit — did at least one citation match an expected doc title fragment?
  2. Keyword recall — what fraction of expected reply-keywords appear in the reply?
  3. Confidence band — did the model's confidence fall in the expected range?
  4. Groundedness — for "I don't know" probes, did the model honestly refuse?

The script prints a per-question table to stdout and writes a machine-readable
JSON report to `eval/results.json`.

Usage:
    python eval/run_eval.py [--api http://localhost:8000] [--out eval/results.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = EVAL_DIR / "golden_questions.json"
DEFAULT_OUT = EVAL_DIR / "results.json"
DEFAULT_API = "http://localhost:8000"


def _norm(s: str) -> str:
    return (s or "").lower()


def score_question(q: dict, response: dict) -> dict:
    """Return a per-question score dict."""
    reply = _norm(response.get("reply"))
    confidence = response.get("confidence", 0.0)
    citations = response.get("citations") or []
    expected_titles = q.get("expected_doc_title_contains") or []
    expected_kws = q.get("expected_reply_contains") or []
    is_groundedness = bool(q.get("is_groundedness_test"))

    # 1. Retrieval hit
    if expected_titles:
        cited_titles = [_norm(c.get("document_title")) for c in citations]
        retrieval_hit = any(
            _norm(t) in title
            for title in cited_titles
            for t in expected_titles
        )
    else:
        # For groundedness tests, retrieval_hit = "ok" if we DIDN'T fabricate citations
        retrieval_hit = len(citations) == 0

    # 2. Keyword recall — OR for groundedness (any refusal phrase is enough)
    matched_kws = [k for k in expected_kws if _norm(k) in reply]
    if is_groundedness:
        keyword_score = 1.0 if matched_kws else 0.0
    elif expected_kws:
        keyword_score = len(matched_kws) / len(expected_kws)
    else:
        keyword_score = 1.0

    # 3. Confidence band
    conf_min = q.get("expected_confidence_min")
    conf_max = q.get("expected_confidence_max")
    confidence_ok = True
    if conf_min is not None and confidence < conf_min:
        confidence_ok = False
    if conf_max is not None and confidence > conf_max:
        confidence_ok = False

    # 4. Groundedness probe: refused (no citations + appropriate phrase)
    groundedness_ok = None
    if is_groundedness:
        groundedness_ok = (len(citations) == 0) and bool(matched_kws)

    overall_pass = (
        retrieval_hit
        and keyword_score >= 0.5
        and confidence_ok
        and (groundedness_ok is None or groundedness_ok)
    )

    return {
        "id": q["id"],
        "question": q["question"],
        "language": q.get("language"),
        "is_groundedness_test": is_groundedness,
        "retrieval_hit": retrieval_hit,
        "keyword_score": round(keyword_score, 3),
        "matched_keywords": matched_kws,
        "missing_keywords": [k for k in expected_kws if k not in matched_kws],
        "confidence": confidence,
        "confidence_ok": confidence_ok,
        "groundedness_ok": groundedness_ok,
        "citations_count": len(citations),
        "cited_documents": list({c.get("document_title") for c in citations if c.get("document_title")}),
        "duration_ms": response.get("duration_ms"),
        "reply": response.get("reply"),
        "pass": overall_pass,
    }


def run_eval(api_base: str, questions_path: Path, timeout: float = 60.0) -> dict:
    with open(questions_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    questions = manifest.get("questions", [])
    print(f"Running eval against {api_base} — {len(questions)} questions\n")

    results = []
    started = time.time()
    with httpx.Client(timeout=timeout) as client:
        for i, q in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] {q['id']} — \"{q['question'][:70]}\"")
            try:
                resp = client.post(
                    f"{api_base}/api/chat",
                    json={"message": q["question"], "channel": "web"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"   ERROR: {e}")
                results.append({
                    "id": q["id"],
                    "question": q["question"],
                    "error": str(e),
                    "pass": False,
                })
                continue

            scored = score_question(q, data)
            results.append(scored)

            tick = "✓" if scored["pass"] else "✗"
            confidence_str = f"{scored['confidence']:.2f}"
            kw_str = f"{int(scored['keyword_score'] * 100)}%"
            cite_str = f"{scored['citations_count']} cites"
            print(
                f"   {tick} retrieval={'hit' if scored['retrieval_hit'] else 'miss'}  "
                f"kw={kw_str}  conf={confidence_str}  {cite_str}  ({scored['duration_ms']}ms)"
            )

    elapsed = time.time() - started

    # Aggregate
    passed = sum(1 for r in results if r.get("pass"))
    retrieval_hits = sum(1 for r in results if r.get("retrieval_hit"))
    grounded_tests = [r for r in results if r.get("is_groundedness_test")]
    grounded_ok = sum(1 for r in grounded_tests if r.get("groundedness_ok"))
    kw_scores = [r["keyword_score"] for r in results if "keyword_score" in r]
    avg_kw = sum(kw_scores) / len(kw_scores) if kw_scores else 0.0
    avg_conf = sum(r.get("confidence", 0) or 0 for r in results) / max(1, len(results))
    avg_duration = sum(r.get("duration_ms", 0) or 0 for r in results) / max(1, len(results))

    summary = {
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / max(1, len(results)), 3),
        "retrieval_hit_rate": round(retrieval_hits / max(1, len(results)), 3),
        "avg_keyword_recall": round(avg_kw, 3),
        "avg_confidence": round(avg_conf, 3),
        "avg_duration_ms": int(avg_duration),
        "groundedness_tests": len(grounded_tests),
        "groundedness_correct": grounded_ok,
        "wall_clock_seconds": round(elapsed, 1),
    }

    print("\n" + "─" * 60)
    print("SUMMARY")
    print("─" * 60)
    for k, v in summary.items():
        print(f"  {k:28s} {v}")

    return {"summary": summary, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=DEFAULT_API, help="API base URL")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.questions.exists():
        print(f"Question file not found: {args.questions}")
        sys.exit(1)

    report = run_eval(args.api, args.questions)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nDetailed report written to {args.out}")


if __name__ == "__main__":
    main()
