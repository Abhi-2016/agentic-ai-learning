"""
eval_factuality.py — Eval 2: Factuality

WHAT THIS EVAL MEASURES:
  Does the paper accurately represent what its sources actually say?

WHY IT EXISTS (from Quiz 6):
  Grounding (Eval 1) only checks that a URL is present — not that the claim
  near that URL is faithful to the source. An agent can be fully grounded
  and still misquote, exaggerate, or hallucinate details. Factuality catches
  that second failure mode by comparing what the paper says to what the agent
  actually saved in the scratchpad.

HOW IT WORKS:
  1. Load the paper (agent output)
  2. Load the scratchpad (the findings the agent saved — this is ground truth)
  3. For each scratchpad source, extract the sentences in the paper that
     cite that source (the 3 sentences surrounding the URL)
  4. Send source finding + paper claim to a judge LLM with a strict rubric
  5. Judge returns: SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED + reason
  6. Report a factuality score: weighted average of verdicts

WHY THE SCRATCHPAD IS GROUND TRUTH:
  The scratchpad is what the agent actually read and chose to save. If the
  agent saved "34% improvement" but wrote "64% improvement" in the paper,
  the discrepancy is caught here — without re-fetching the original page.

THE JUDGE LLM RISK (Quiz 6 answer):
  The judge LLM can itself be wrong — inconsistent verdicts, hallucinated
  reasoning, or systematic leniency/harshness. Mitigation: human-in-the-loop
  spot-checking via --human-review flag. Run a sample of verdicts past a
  human reviewer and record agreement rate. If human agreement < 80%, the
  judge is not calibrated and its signal can't be trusted.

WHAT IT CATCHES:
  - Agent that changed numbers when writing the paper ("34%" → "64%")
  - Agent that generalized too aggressively ("some improvement" → "major breakthrough")
  - Agent that attributed a claim to the wrong source

WHAT IT DOES NOT CATCH:
  - A source that is itself factually wrong (the scratchpad finding could be wrong)
  - Missing claims (no citation at all) — that's Eval 1: Grounding

Run with:
  python evals/eval_factuality.py
  python evals/eval_factuality.py --paper <path> --scratchpad <path>
  python evals/eval_factuality.py --human-review   # enables interactive spot-check
"""

import json
import re
import random
import argparse
import anthropic
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root into os.environ

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PAPER_PATH = PROJECT_ROOT / "last_paper.txt"
DEFAULT_SCRATCHPAD_PATH = PROJECT_ROOT / "scratchpad.json"

# Judge model: Haiku is cheaper + faster than the agent model.
# For eval tasks, speed and cost matter more than reasoning depth.
# The same anthropic client — no new dependency.
JUDGE_MODEL = "claude-haiku-4-5-20251001"

# Verdict weights for scoring
VERDICT_SCORES = {
    "SUPPORTED": 1.0,
    "PARTIALLY_SUPPORTED": 0.5,
    "NOT_SUPPORTED": 0.0,
}

# Judge system prompt — strict rubric, no wiggle room
JUDGE_SYSTEM_PROMPT = """You are a factuality judge evaluating whether a research paper accurately represents its sources.

You will be given:
1. SOURCE: the key finding from the original source (ground truth — what the source actually says)
2. PAPER_CLAIM: a paragraph from the paper that cites this source

IMPORTANT: A paragraph often cites multiple sources. Your job is narrow and specific:
- Only evaluate claims that are explicitly attributed to THIS source (e.g. "(Voltage Control, 2025)", "according to Voltage Control...")
- Completely ignore claims in the paragraph that are attributed to other sources — those are not your responsibility to judge
- If the paragraph contains no claims explicitly attributed to this source, return SUPPORTED with reason "No claims explicitly attributed to this source in the paragraph"

Your job: decide if the claims attributed to THIS SOURCE accurately represent what SOURCE says.

Verdicts:
- SUPPORTED: the attributed claims faithfully represent the source — numbers match, scope is accurate, no added detail
- PARTIALLY_SUPPORTED: the attributed claims are related but overstate, understate, change a number, or add unsupported detail
- NOT_SUPPORTED: the attributed claims contradict the source or cannot be derived from it

Be critical, not charitable. If a number was changed even slightly, that is PARTIALLY_SUPPORTED at best.

Respond in this exact format (two lines, nothing else):
VERDICT: <SUPPORTED|PARTIALLY_SUPPORTED|NOT_SUPPORTED>
REASON: <one sentence explaining your verdict>"""


# ── Core functions ────────────────────────────────────────────────────────────

def load_scratchpad(path: Path) -> list[dict]:
    """Load saved sources from the scratchpad."""
    if not path.exists():
        raise FileNotFoundError(f"Scratchpad not found at {path}")
    with open(path) as f:
        return json.load(f)


def load_paper(path: Path) -> str:
    """Load the agent's output paper."""
    if not path.exists():
        raise FileNotFoundError(
            f"Paper not found at {path}.\n"
            "Run the agent first and save the output:\n"
            "  python agent.py 'your topic' > last_paper.txt"
        )
    return path.read_text()


def extract_body(paper: str) -> str:
    """Return only the body of the paper, stripping the references section.

    Claims are made in the body. The references section is just citation
    metadata — URLs there are not claims and should not be judged.
    """
    ref_match = re.search(r'\n#{1,3}\s*(References|Bibliography|Sources)', paper, re.IGNORECASE)
    if ref_match:
        return paper[:ref_match.start()]
    return paper


def extract_author_keyword(author: str) -> str:
    """Extract the most searchable keyword from a scratchpad author/org string.

    The paper cites sources by org name in prose ("According to Voltage Control..."),
    not by URL. We need a keyword to find those prose sentences.

    Examples:
      "Voltage Control (2025)"                               → "Voltage Control"
      "Tucker J. Marion — MIT Sloan Management Review (2024)" → "MIT Sloan"
      "Productboard (in partnership with UserEvidence) (2025)" → "Productboard"
    """
    # Remove year patterns like (2024), (2025)
    clean = re.sub(r'\(\d{4}\)', '', author).strip()
    # Remove parenthetical asides like "(in partnership with UserEvidence)"
    clean = re.sub(r'\(.*?\)', '', clean).strip()
    # If there's a dash separator (lastname — OrgName), take the org part
    if ' — ' in clean:
        clean = clean.split(' — ')[-1].strip()
    # If "Firstname Lastname, Org Name" pattern: extract surname only.
    # Papers cite individuals by surname ("Cagan, 2024"), not full name or org.
    if ',' in clean:
        first_segment = clean.split(',')[0].strip()
        words = first_segment.split()
        return words[-1] if words else ''  # e.g., "Marty Cagan, SVPG" → "Cagan"
    # Return up to 3 words — enough to be distinctive without over-constraining
    words = clean.split()
    return ' '.join(words[:3]) if words else ''


def extract_context_for_source(paper: str, source_url: str, author: str = "") -> str:
    """
    Find the paragraph in the paper body that discusses a given source.

    Strategy (two-pass, paragraph-level):
    1. Strip the references section — claims are in the body, not the citations list
    2. Split the body into paragraphs (double newlines = semantic boundaries)
    3. Search paragraphs for the source by author/org keyword
    4. Fall back to URL search if author search finds nothing

    Why paragraphs, not ±1 sentences:
    Sentence-level windows bleed across paragraph boundaries. If Voltage Control
    is cited at the end of one paragraph and Productboard numbers appear at the
    start of the next, ±1 captures both — the judge then penalises Voltage Control
    for Productboard's numbers. Paragraphs are the natural semantic unit: one
    source, one paragraph.

    Returns an empty string if no relevant context is found.
    """
    body = extract_body(paper)
    url_clean = source_url.rstrip(".,;)")

    # Split into paragraphs — double newlines delimit semantic blocks
    paragraphs = [p.strip() for p in re.split(r'\n\n+', body) if p.strip()]

    # Primary: collect ALL paragraphs mentioning the author/org keyword.
    # A source may be cited in multiple paragraphs — returning only the first
    # means the judge misses later citations. Joining all gives full picture.
    keyword = extract_author_keyword(author)
    if keyword:
        matching = [p for p in paragraphs if keyword.lower() in p.lower()]
        if matching:
            combined = '\n\n'.join(matching)
            return combined[:800]  # cap at 800 chars — full context, not overwhelming

    # Fallback: find the last paragraph containing the URL (reversed = body, not references)
    for para in reversed(paragraphs):
        if url_clean in para or source_url in para:
            return para[:800]

    return ""


def judge_claim(source_finding: str, paper_context: str) -> dict:
    """
    Send a source finding + paper claim to the judge LLM.

    The judge reads the strict rubric in the system prompt and returns
    a verdict (SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED) plus
    a one-sentence reason.

    Returns a dict with 'verdict', 'reason', and 'raw_response'.
    """
    client = anthropic.Anthropic()

    user_message = f"""SOURCE:
{source_finding}

PAPER_CLAIM:
{paper_context}"""

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=200,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text.strip()

    # Parse the two-line response
    verdict = "NOT_SUPPORTED"  # safe default if parsing fails
    reason = raw

    for line in raw.splitlines():
        if line.startswith("VERDICT:"):
            raw_verdict = line.replace("VERDICT:", "").strip()
            if raw_verdict in VERDICT_SCORES:
                verdict = raw_verdict
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    return {
        "verdict": verdict,
        "reason": reason,
        "raw_response": raw
    }


def run_human_review(judgments: list[dict]) -> dict:
    """
    Human-in-the-loop spot-check: show 1-2 judge decisions and ask the
    human reviewer to confirm or challenge them.

    This is the calibration mechanism from Quiz 6 — if the judge is
    systematically wrong, human agreement < 80% reveals it. No abstraction
    needed: the calibration signal comes directly from this terminal prompt.

    Returns a dict with human_agreement_rate and reviewer responses.
    """
    print("\n── Human Review (Calibration Check) ──────────────────────")
    print("  You're about to spot-check the judge's verdicts.")
    print("  This is how you calibrate an LLM-as-judge: compare its")
    print("  decisions to human judgment on a random sample.\n")

    # Sample up to 2 judgments at random — enough to spot systematic issues
    sample_size = min(2, len(judgments))
    sample = random.sample(judgments, sample_size)

    agreements = []

    for i, j in enumerate(sample, 1):
        print(f"  Sample {i}/{sample_size}")
        print(f"  Source: {j['author']} ({j['year']})")
        print(f"  Source finding: \"{j['source_finding'][:100]}...\"" if len(j['source_finding']) > 100 else f"  Source finding: \"{j['source_finding']}\"")
        print(f"  Paper claim:    \"{j['paper_context'][:100]}...\"" if len(j['paper_context']) > 100 else f"  Paper claim:    \"{j['paper_context']}\"")
        print(f"  Judge verdict:  {j['verdict']}")
        print(f"  Judge reason:   {j['reason']}")

        while True:
            response = input("\n  Do you agree with this verdict? [y/n/skip]: ").strip().lower()
            if response in ("y", "n", "skip"):
                break
            print("  Please enter y, n, or skip.")

        if response == "skip":
            print("  Skipped.\n")
            continue

        agreed = response == "y"
        agreements.append(agreed)

        if agreed:
            print("  ✅ Agreed — judge and human aligned.\n")
        else:
            print("  ❌ Disagreed — judge may be miscalibrated for this type of claim.\n")

    if not agreements:
        return {"human_agreement_rate": None, "samples_reviewed": 0}

    agreement_rate = sum(agreements) / len(agreements)
    return {
        "human_agreement_rate": round(agreement_rate, 2),
        "samples_reviewed": len(agreements)
    }


def score_factuality(judgments: list[dict]) -> dict:
    """
    Produce a final factuality score and verdict.

    Scoring:
      - SUPPORTED = 1.0 per source
      - PARTIALLY_SUPPORTED = 0.5
      - NOT_SUPPORTED = 0.0
      - final_score = average across all sources

    Verdict:
      PASS  → score >= 0.8 (claims are largely faithful to sources)
      WARN  → score 0.5–0.8 (some misrepresentation, worth reviewing)
      FAIL  → score < 0.5 (significant factuality failures)
    """
    if not judgments:
        return {"final_score": 0.0, "verdict": "FAIL", "supported": 0, "partially": 0, "unsupported": 0}

    scores = [VERDICT_SCORES[j["verdict"]] for j in judgments]
    final_score = sum(scores) / len(scores)

    supported = sum(1 for j in judgments if j["verdict"] == "SUPPORTED")
    partially = sum(1 for j in judgments if j["verdict"] == "PARTIALLY_SUPPORTED")
    unsupported = sum(1 for j in judgments if j["verdict"] == "NOT_SUPPORTED")

    if final_score >= 0.8:
        verdict = "PASS"
    elif final_score >= 0.5:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return {
        "final_score": round(final_score, 3),
        "verdict": verdict,
        "supported": supported,
        "partially_supported": partially,
        "not_supported": unsupported
    }


# ── Report printer ─────────────────────────────────────────────────────────────

def print_report(judgments: list[dict], score: dict, human_review: Optional[dict]) -> None:
    """Print a human-readable factuality eval report."""

    print("\n" + "="*60)
    print("EVAL 2: FACTUALITY REPORT")
    print("="*60)

    # Per-source verdict table
    print("\n── Source Verdicts ───────────────────────────────────────")
    for j in judgments:
        if j["verdict"] == "SUPPORTED":
            icon = "✅"
        elif j["verdict"] == "PARTIALLY_SUPPORTED":
            icon = "⚠️ "
        else:
            icon = "❌"

        print(f"  {icon} {j['verdict']}")
        print(f"    Source: {j['author']} ({j['year']})")
        print(f"    URL:    {j['source_url']}")

        # Show what the source said vs what the paper said
        src_preview = j['source_finding'][:90] + "..." if len(j['source_finding']) > 90 else j['source_finding']
        claim_preview = j['paper_context'][:90] + "..." if len(j['paper_context']) > 90 else j['paper_context']
        print(f"    Source says:  \"{src_preview}\"")
        print(f"    Paper claims: \"{claim_preview}\"")
        print(f"    Judge reason: {j['reason']}")

        if not j['paper_context']:
            print("    ⚠️  Note: URL not found in paper — claim context could not be extracted.")
        print()

    # Verdict summary
    print(f"  Supported:          {score['supported']}")
    print(f"  Partially supported:{score['partially_supported']}")
    print(f"  Not supported:      {score['not_supported']}")

    # Human review results (if run)
    if human_review and human_review.get("samples_reviewed", 0) > 0:
        agreement = human_review["human_agreement_rate"]
        reviewed = human_review["samples_reviewed"]
        print(f"\n── Human Review Results ──────────────────────────────────")
        print(f"  Samples reviewed:   {reviewed}")
        print(f"  Human agreement:    {agreement*100:.0f}%")
        if agreement >= 0.8:
            print("  ✅ Judge appears well-calibrated — human and judge aligned.")
        else:
            print("  ⚠️  Judge may be miscalibrated. Consider refining the judge prompt.")

    # Final score
    print("\n── Final Score ───────────────────────────────────────────")
    print(f"  Final score:  {score['final_score']*100:.0f}%")
    print(f"  Verdict:      {score['verdict']}")

    if score['verdict'] == "FAIL":
        print("\n  ❌ The paper significantly misrepresents its sources.")
        print("     Review NOT_SUPPORTED claims before trusting any output.")
    elif score['verdict'] == "WARN":
        print("\n  ⚠️  Some claims are overstated or imprecise.")
        print("     Review PARTIALLY_SUPPORTED claims — they may mislead readers.")
    else:
        print("\n  ✅ Claims are faithful to sources. Proceed to Eval 3 (Completeness).")

    # PM insight
    print("\n── PM Insight ────────────────────────────────────────────")
    print("  A PASS here means the paper accurately represents what it saved.")
    print("  It does NOT mean the sources themselves are correct.")
    print("  The judge LLM can also be wrong — run --human-review to calibrate it.")
    print("  If human agreement < 80%, the judge's signal can't be trusted.")
    print("="*60 + "\n")


# ── Entry point ────────────────────────────────────────────────────────────────

def run_eval(paper_path: Path, scratchpad_path: Path, human_review: bool = False) -> dict:
    """Run the full factuality eval and return the score dict."""
    paper = load_paper(paper_path)
    scratchpad = load_scratchpad(scratchpad_path)

    # Group scratchpad entries by source URL.
    # A single source often contributes multiple findings — evaluating them
    # separately would give the judge the same paragraph 3 times and produce
    # redundant (often wrong) verdicts. One source → one verdict is the right
    # granularity: "does the paper faithfully represent Voltage Control?"
    sources: dict = {}
    for note in scratchpad:
        url = note.get("source_url", "")
        if url not in sources:
            sources[url] = {
                "source_url": url,
                "author": note.get("author_or_org", "Unknown"),
                "year": note.get("year", "Unknown"),
                "findings": []
            }
        sources[url]["findings"].append(note.get("finding", ""))

    unique_sources = list(sources.values())
    print(f"\nRunning Eval 2 (Factuality) — judge model: {JUDGE_MODEL}")
    print(f"Checking {len(unique_sources)} unique sources ({len(scratchpad)} scratchpad entries)...\n")

    judgments = []
    for i, src in enumerate(unique_sources, 1):
        source_url = src["source_url"]
        author = src["author"]
        year = src["year"]
        # Combine all findings for this source into one SOURCE block
        combined_finding = "\n\n".join(
            f"Finding {j+1}: {f}" for j, f in enumerate(src["findings"])
        )

        print(f"  [{i}/{len(unique_sources)}] Judging: {author} ({year})...", end=" ", flush=True)

        paper_context = extract_context_for_source(paper, source_url, author)

        if not paper_context:
            # URL not found in paper — Eval 1 (grounding) would catch this,
            # but we still record it here as NOT_SUPPORTED for completeness
            print("not found in paper — skipping judge call")
            judgments.append({
                "source_url": source_url,
                "author": author,
                "year": year,
                "source_finding": combined_finding,
                "paper_context": "",
                "verdict": "NOT_SUPPORTED",
                "reason": "Source not found in paper — claim context could not be extracted.",
                "raw_response": ""
            })
            continue

        result = judge_claim(combined_finding, paper_context)
        print(result["verdict"])

        judgments.append({
            "source_url": source_url,
            "author": author,
            "year": year,
            "source_finding": combined_finding,
            "paper_context": paper_context,
            **result
        })

    score = score_factuality(judgments)

    # Human-in-the-loop spot-check (opt-in via --human-review flag)
    human_review_results = None
    if human_review:
        human_review_results = run_human_review(judgments)

    print_report(judgments, score, human_review_results)
    return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eval 2: Factuality — LLM-as-judge claim checker")
    parser.add_argument("--paper", type=Path, default=DEFAULT_PAPER_PATH,
                        help=f"Path to the paper text file (default: {DEFAULT_PAPER_PATH})")
    parser.add_argument("--scratchpad", type=Path, default=DEFAULT_SCRATCHPAD_PATH,
                        help=f"Path to scratchpad.json (default: {DEFAULT_SCRATCHPAD_PATH})")
    parser.add_argument("--human-review", action="store_true",
                        help="Enable interactive human spot-check to calibrate the judge")
    args = parser.parse_args()

    run_eval(args.paper, args.scratchpad, human_review=args.human_review)
