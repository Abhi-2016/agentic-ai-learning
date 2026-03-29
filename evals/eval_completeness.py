"""
eval_completeness.py — Eval 3: Completeness

WHAT THIS EVAL MEASURES:
  Did the paper cover everything it was supposed to?

WHY IT EXISTS:
  Grounding (Eval 1) checks citations are present.
  Factuality (Eval 2) checks citations are accurate.
  Completeness checks something different: is the output structurally and
  topically whole? A paper can be fully grounded, 100% factual, and still
  be incomplete — missing a conclusion, drifting off-topic, or sourced from
  weak or irrelevant material.

HOW IT WORKS:
  1. Load the paper and scratchpad
  2. Extract the topic from the paper's H1 heading (automatic — no CLI arg needed)
  3. For each of 3 rubric criteria, ask a judge LLM: does the paper satisfy this?
  4. Judge returns: YES / PARTIAL / NO + one sentence reason
  5. Score: 1.0 / 0.5 / 0.0 per criterion → average → PASS / WARN / FAIL

THE RUBRIC (written by Abhishek, Quiz 7):
  Criterion 1 — Topic coverage: Does the paper stay on topic and cover it accurately?
  Criterion 2 — Structure: Does the paper have a well-formed intro, body, and conclusion?
  Criterion 3 — Source adherence: Did the agent use 3 strong, relevant sources?

WHY ONE CALL PER CRITERION:
  Each criterion is independent. Separate calls give cleaner verdicts and easier
  debugging — if Criterion 2 (structure) fails but Criterion 1 passes, you know
  exactly what to fix. A single call for all 3 risks the judge conflating them.

THE TOPIC EXTRACTION:
  The paper always starts with a Markdown H1 heading (# <topic>). We extract this
  automatically rather than requiring a --topic CLI arg — fewer moving parts and
  the heading reliably mirrors the original query.

Run with:
  python evals/eval_completeness.py
  python evals/eval_completeness.py --paper <path> --scratchpad <path>
"""

import re
import json
import argparse
import anthropic
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)  # override=True: always use .env, even if var is already set (e.g. set to empty string)

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PAPER_PATH = PROJECT_ROOT / "last_paper.txt"
DEFAULT_SCRATCHPAD_PATH = PROJECT_ROOT / "scratchpad.json"

# Judge model — same as Eval 2. Haiku is cheaper and fast enough for rubric checks.
JUDGE_MODEL = "claude-haiku-4-5-20251001"

# Verdict weights — same scale as Eval 1 + 2 for consistency
VERDICT_SCORES = {
    "YES": 1.0,
    "PARTIAL": 0.5,
    "NO": 0.0,
}

# ── Rubric criteria (written by Abhishek, Quiz 7) ────────────────────────────
# These are the exact strings passed to the judge for each call.
# The topic and paper/scratchpad context are injected at call time.
CRITERIA = [
    (
        "Topic coverage",
        "Does the paper stay on topic and cover the subject accurately? "
        "Check whether the paper addresses the key dimensions of the topic provided, "
        "or whether it drifts into unrelated areas or treats the topic too superficially."
    ),
    (
        "Structure",
        "Does the paper have a well-formed introduction, body, and conclusion? "
        "The introduction should set context for the topic, the body should develop "
        "the argument with cited evidence, and the conclusion should synthesise the findings."
    ),
    (
        "Source adherence",
        "Did the agent use 3 strong, relevant sources? "
        "Check the scratchpad summary provided: are there 3 saved sources? "
        "Do the findings look substantive and directly relevant to the topic, "
        "or are they generic, off-topic, or low-quality?"
    ),
]

# ── Judge system prompt ───────────────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """You are a completeness judge evaluating a research paper against a single criterion.

You will be given:
- TOPIC: the intended subject of the paper
- CRITERION: one specific quality criterion to evaluate
- PAPER: the full paper text (or as much as fits)
- SCRATCHPAD: a summary of the sources the agent saved (for source-related criteria)

Your job: decide if the paper satisfies the criterion.

Verdicts:
- YES: the paper clearly satisfies this criterion
- PARTIAL: the paper partially satisfies it — present but weak, incomplete, or borderline
- NO: the paper does not satisfy this criterion

Be direct. One criterion, one verdict.

Respond in exactly this format (two lines, nothing else):
VERDICT: <YES|PARTIAL|NO>
REASON: <one sentence explaining your verdict>"""


# ── Core functions ────────────────────────────────────────────────────────────

def load_paper(path: Path) -> str:
    """Load the agent's output paper."""
    if not path.exists():
        raise FileNotFoundError(
            f"Paper not found at {path}.\n"
            "Run the agent first:\n"
            "  python agent.py 'your topic' > last_paper.txt"
        )
    return path.read_text()


def load_scratchpad(path: Path) -> list:
    """Load saved sources from the scratchpad."""
    if not path.exists():
        raise FileNotFoundError(f"Scratchpad not found at {path}")
    with open(path) as f:
        return json.load(f)


def extract_topic(paper: str) -> str:
    """Extract the topic from the paper's H1 Markdown heading.

    The agent always begins the paper with a # heading that mirrors the
    original query. Using it means we don't need a --topic CLI flag.

    Example:
      '# How Generative AI is Changing Product Management\n\n...'
      → 'How Generative AI is Changing Product Management'
    """
    match = re.search(r'^#\s+(.+)', paper, re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Fallback: return first non-empty line
    for line in paper.splitlines():
        if line.strip():
            return line.strip()
    return "Unknown topic"


def build_scratchpad_summary(scratchpad: list) -> str:
    """Summarise the scratchpad for the judge.

    The judge only needs to know: how many sources, who they are, and a
    short preview of each finding. Enough to evaluate source quality and
    relevance without overwhelming the context.
    """
    if not scratchpad:
        return "No sources saved (scratchpad is empty)."

    # Group by unique source URL to avoid double-counting multi-finding sources
    seen_urls = set()
    unique_sources = []
    for note in scratchpad:
        url = note.get("source_url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(note)

    lines = [f"{len(unique_sources)} unique source(s) saved:\n"]
    for i, note in enumerate(unique_sources, 1):
        author = note.get("author_or_org", "Unknown")
        finding = note.get("finding", "")
        preview = finding[:120] + "..." if len(finding) > 120 else finding
        lines.append(f"  {i}. {author}")
        lines.append(f"     Finding: \"{preview}\"")
    return "\n".join(lines)


def judge_criterion(
    criterion_name: str,
    criterion_text: str,
    topic: str,
    paper: str,
    scratchpad_summary: str
) -> dict:
    """Ask the judge LLM whether the paper satisfies one criterion.

    Each criterion gets its own call — clean separation, easier debugging.
    Returns a dict with 'verdict', 'score', 'reason', and 'raw_response'.
    """
    client = anthropic.Anthropic()

    # Cap paper at 1500 chars — enough for the judge to evaluate structure
    # and topic coverage without exhausting the context window on a single call
    paper_excerpt = paper[:1500] + "\n[...truncated...]" if len(paper) > 1500 else paper

    user_message = f"""TOPIC: {topic}

CRITERION: {criterion_text}

PAPER:
{paper_excerpt}

SCRATCHPAD SUMMARY:
{scratchpad_summary}"""

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=150,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text.strip()

    # Parse the two-line response
    verdict = "NO"   # safe default if parsing fails
    reason = raw

    for line in raw.splitlines():
        if line.startswith("VERDICT:"):
            raw_verdict = line.replace("VERDICT:", "").strip()
            if raw_verdict in VERDICT_SCORES:
                verdict = raw_verdict
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    return {
        "criterion_name": criterion_name,
        "verdict": verdict,
        "score": VERDICT_SCORES[verdict],
        "reason": reason,
        "raw_response": raw,
    }


def score_completeness(results: list) -> dict:
    """Average criterion scores → final PASS / WARN / FAIL verdict.

    Scoring mirrors Eval 1 + 2:
    - PASS  ≥ 0.8  (paper is complete and well-structured)
    - WARN  0.5–0.8 (some gaps, worth reviewing)
    - FAIL  < 0.5  (significant structural or coverage failures)
    """
    if not results:
        return {"final_score": 0.0, "verdict": "FAIL", "yes": 0, "partial": 0, "no": 0}

    scores = [r["score"] for r in results]
    final_score = sum(scores) / len(scores)

    yes_count = sum(1 for r in results if r["verdict"] == "YES")
    partial_count = sum(1 for r in results if r["verdict"] == "PARTIAL")
    no_count = sum(1 for r in results if r["verdict"] == "NO")

    if final_score >= 0.8:
        verdict = "PASS"
    elif final_score >= 0.5:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return {
        "final_score": round(final_score, 3),
        "verdict": verdict,
        "yes": yes_count,
        "partial": partial_count,
        "no": no_count,
    }


def print_report(
    topic: str,
    results: list,
    score: dict
) -> None:
    """Print a human-readable completeness eval report."""

    print("\n" + "=" * 60)
    print("EVAL 3: COMPLETENESS REPORT")
    print("=" * 60)
    print(f"\n  Topic: {topic}")

    # Per-criterion verdict table
    print("\n── Criterion Verdicts ────────────────────────────────────")
    for r in results:
        if r["verdict"] == "YES":
            icon = "✅"
        elif r["verdict"] == "PARTIAL":
            icon = "⚠️ "
        else:
            icon = "❌"

        print(f"\n  {icon} {r['verdict']} — {r['criterion_name']}")
        print(f"     {r['reason']}")

    # Summary counts
    print(f"\n── Summary ───────────────────────────────────────────────")
    print(f"  Yes (full):     {score['yes']}")
    print(f"  Partial:        {score['partial']}")
    print(f"  No:             {score['no']}")

    # Final score
    print(f"\n── Final Score ───────────────────────────────────────────")
    print(f"  Final score:  {score['final_score'] * 100:.0f}%")
    print(f"  Verdict:      {score['verdict']}")

    if score["verdict"] == "FAIL":
        print("\n  ❌ The paper has significant structural or coverage gaps.")
        print("     Review NO criteria — these are the paper's weak points.")
    elif score["verdict"] == "WARN":
        print("\n  ⚠️  The paper is partially complete.")
        print("     Review PARTIAL criteria — they indicate areas to strengthen.")
    else:
        print("\n  ✅ Paper is complete. Proceed to Eval 4 (Efficiency).")

    # PM insight
    print("\n── PM Insight ────────────────────────────────────────────")
    print("  Completeness is about structure and coverage — not accuracy.")
    print("  A complete paper can still fail Eval 2 (Factuality).")
    print("  The rubric you define here is your product's 'definition of done'.")
    print("  Without it, 'complete' is just a feeling.")
    print("=" * 60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_eval(paper_path: Path, scratchpad_path: Path) -> dict:
    """Run the full completeness eval and return the score dict."""
    paper = load_paper(paper_path)
    scratchpad = load_scratchpad(scratchpad_path)

    topic = extract_topic(paper)
    scratchpad_summary = build_scratchpad_summary(scratchpad)

    print(f"\nRunning Eval 3 (Completeness) — judge model: {JUDGE_MODEL}")
    print(f"Topic: {topic}")
    print(f"Checking {len(CRITERIA)} criteria...\n")

    results = []
    for i, (criterion_name, criterion_text) in enumerate(CRITERIA, 1):
        print(f"  [{i}/{len(CRITERIA)}] {criterion_name}...", end=" ", flush=True)
        result = judge_criterion(
            criterion_name,
            criterion_text,
            topic,
            paper,
            scratchpad_summary
        )
        print(result["verdict"])
        results.append(result)

    score = score_completeness(results)
    print_report(topic, results, score)
    return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Eval 3: Completeness — rubric-based section and coverage checker"
    )
    parser.add_argument(
        "--paper", type=Path, default=DEFAULT_PAPER_PATH,
        help=f"Path to the paper text file (default: {DEFAULT_PAPER_PATH})"
    )
    parser.add_argument(
        "--scratchpad", type=Path, default=DEFAULT_SCRATCHPAD_PATH,
        help=f"Path to scratchpad.json (default: {DEFAULT_SCRATCHPAD_PATH})"
    )
    args = parser.parse_args()

    run_eval(args.paper, args.scratchpad)
