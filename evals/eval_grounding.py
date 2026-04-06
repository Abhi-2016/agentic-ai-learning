"""
eval_grounding.py — Eval 1: Grounding

WHAT THIS EVAL MEASURES:
  Does every claim in the paper have a traceable citation?

WHY IT EXISTS (from Quiz 5):
  Grounding checks attribution — not truth. A paper can be fully grounded
  (every claim has a URL) and still be factually wrong if the cited source
  is itself wrong. Grounding is the CHEAPEST eval to run because it requires
  no LLM — it's a mechanical check using regex and string matching.

HOW IT WORKS:
  1. Load the paper (agent output)
  2. Load the scratchpad (the URLs the agent saved)
  3. Check how many scratchpad URLs appear in the paper
  4. Scan for sentences that look like claims but have no URL nearby
  5. Report a grounding score: citations_present / total_saved_sources

WHAT IT CATCHES:
  - Agent that wrote the paper without referencing its saved sources
  - Agent that hallucinated claims with no citation
  - Agent that cited a URL that wasn't in its scratchpad (fabricated URL)

WHAT IT DOES NOT CATCH:
  - A cited source that is itself wrong (→ that's Eval 2: Factuality)
  - A citation present but misquoted (→ that's also Eval 2)

Run with:
  python evals/eval_grounding.py --paper <path_to_paper.txt> --scratchpad scratchpad.json
  python evals/eval_grounding.py  # uses defaults: last_paper.txt + scratchpad.json
"""

import json
import re
import argparse
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PAPER_PATH = PROJECT_ROOT / "last_paper.txt"
DEFAULT_SCRATCHPAD_PATH = PROJECT_ROOT / "scratchpad.json"


# ── Core grounding check functions ───────────────────────────────────────────

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


def extract_urls_from_text(text: str) -> set[str]:
    """
    Extract all URLs from a block of text using regex.
    This is the rule-based core of the grounding eval —
    no LLM needed, just pattern matching.
    """
    url_pattern = r'https?://[^\s\)\]\'"<>]+'
    return set(re.findall(url_pattern, text))


def check_source_citations(paper: str, scratchpad: list[dict]) -> dict:
    """
    For each URL saved to the scratchpad, check if it appears in the paper.

    This answers: did the agent actually USE its saved sources, or did it
    write the paper from memory/hallucination?

    Returns a dict with per-source results and an overall citation rate.
    """
    paper_urls = extract_urls_from_text(paper)
    results = []

    for note in scratchpad:
        source_url = note.get("source_url", "")
        # Strip trailing punctuation that might appear after a URL in text
        url_clean = source_url.rstrip(".,;)")

        cited = url_clean in paper_urls or any(
            url_clean in paper_url for paper_url in paper_urls
        )

        results.append({
            "source_url": source_url,
            "author": note.get("author_or_org", "Unknown"),
            "year": note.get("year", "Unknown"),
            "cited_in_paper": cited,
            "finding_preview": note.get("finding", "")[:80] + "..."
        })

    cited_count = sum(1 for r in results if r["cited_in_paper"])
    citation_rate = cited_count / len(scratchpad) if scratchpad else 0.0

    return {
        "sources": results,
        "cited_count": cited_count,
        "total_sources": len(scratchpad),
        "citation_rate": citation_rate
    }


def scan_uncited_claims(paper: str) -> list[str]:
    """
    Scan the paper for sentences that look like factual claims
    but have no URL in or immediately after them.

    This is a heuristic — not perfect, but effective at catching
    paragraphs where the agent made statements without citing anything.

    Claim indicators: numbers, percentages, "research shows", "studies found",
    "according to", comparative language ("more than", "higher than"), etc.
    """
    claim_patterns = [
        r'\d+%',                          # percentages
        r'\d+\s*(million|billion|thousand)', # large numbers
        r'research (shows|found|suggests|indicates)',
        r'stud(y|ies) (show|found|suggest)',
        r'according to',
        r'(significantly|substantially) (more|less|higher|lower)',
        r'(increased|decreased|improved|declined) by',
    ]
    combined = re.compile('|'.join(claim_patterns), re.IGNORECASE)

    sentences = re.split(r'(?<=[.!?])\s+', paper)
    uncited = []

    for i, sentence in enumerate(sentences):
        if combined.search(sentence):
            # Check this sentence for a URL
            if re.search(r'https?://', sentence):
                continue

            # Also check the immediately following fragment.
            # Our citation format ([Author, Year](URL)) follows the sentence
            # period as a separate fragment after splitting. A period inside a
            # quoted string (e.g. "Not 99%. 100%.") can cause multiple splits,
            # leaving the citation fragment starting with tail text rather than "([".
            # We check for ](https:// — the markdown hyperlink opener — which is
            # specific to our citation format and won't false-positive on
            # unrelated URLs in the next sentence.
            next_fragment = sentences[i + 1] if i + 1 < len(sentences) else ""
            if re.search(r'\]\(https?://', next_fragment[:300]):
                continue  # citation is in the immediately following fragment — not uncited

            uncited.append(sentence.strip())

    return uncited


def score_grounding(citation_rate: float, uncited_claims: list[str]) -> dict:
    """
    Produce a final grounding score and verdict.

    Scoring:
      - citation_rate: % of scratchpad sources that appear in the paper
      - uncited_claim_penalty: deducted for every flagged uncited claim
      - final_score: 0.0 to 1.0

    Verdict:
      PASS  → score >= 0.8 (most sources cited, few uncited claims)
      WARN  → score 0.5–0.8 (some gaps, worth reviewing)
      FAIL  → score < 0.5 (significant grounding failures)
    """
    # Penalty: each uncited claim reduces score by 0.05, capped at 0.4
    uncited_penalty = min(len(uncited_claims) * 0.05, 0.4)
    final_score = max(0.0, citation_rate - uncited_penalty)

    if final_score >= 0.8:
        verdict = "PASS"
    elif final_score >= 0.5:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return {
        "citation_rate": round(citation_rate, 3),
        "uncited_claim_count": len(uncited_claims),
        "uncited_penalty": round(uncited_penalty, 3),
        "final_score": round(final_score, 3),
        "verdict": verdict
    }


# ── Report printer ────────────────────────────────────────────────────────────

def print_report(citation_check: dict, uncited_claims: list[str], score: dict) -> None:
    """Print a human-readable grounding eval report."""

    print("\n" + "="*60)
    print("EVAL 1: GROUNDING REPORT")
    print("="*60)

    # Source citation table
    print("\n── Source Citations ──────────────────────────────────────")
    for r in citation_check["sources"]:
        status = "✅ CITED" if r["cited_in_paper"] else "❌ NOT CITED"
        print(f"  {status}")
        print(f"    URL: {r['source_url']}")
        print(f"    Author: {r['author']} ({r['year']})")
        print(f"    Finding: {r['finding_preview']}")
        print()

    print(f"  Citation rate: {citation_check['cited_count']}/{citation_check['total_sources']} "
          f"sources referenced in paper ({score['citation_rate']*100:.0f}%)")

    # Uncited claims
    if uncited_claims:
        print("\n── Flagged Uncited Claims ────────────────────────────────")
        print("  These sentences contain factual language but no URL:\n")
        for i, claim in enumerate(uncited_claims[:5], 1):  # show max 5
            print(f"  {i}. \"{claim[:120]}...\"" if len(claim) > 120 else f"  {i}. \"{claim}\"")
        if len(uncited_claims) > 5:
            print(f"  ... and {len(uncited_claims) - 5} more")
    else:
        print("\n── Flagged Uncited Claims ────────────────────────────────")
        print("  ✅ No uncited factual claims detected")

    # Final score
    print("\n── Final Score ───────────────────────────────────────────")
    print(f"  Citation rate:       {score['citation_rate']*100:.0f}%")
    print(f"  Uncited claims:      {score['uncited_claim_count']} (penalty: -{score['uncited_penalty']*100:.0f}%)")
    print(f"  Final score:         {score['final_score']*100:.0f}%")
    print(f"  Verdict:             {score['verdict']}")

    if score['verdict'] == "FAIL":
        print("\n  ⚠️  The paper has significant grounding failures.")
        print("     Run Eval 2 (Factuality) only after fixing grounding.")
    elif score['verdict'] == "WARN":
        print("\n  ⚠️  Some claims are not clearly traceable to sources.")
        print("     Review flagged sentences before trusting the paper.")
    else:
        print("\n  ✅ Paper is well-grounded. Proceed to Eval 2 (Factuality).")

    # PM insight
    print("\n── PM Insight ────────────────────────────────────────────")
    print("  A PASS here means every claim has a URL attached.")
    print("  It does NOT mean those URLs contain true information.")
    print("  That's what Eval 2 (Factuality) checks.")
    print("="*60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_eval(paper_path: Path, scratchpad_path: Path) -> dict:
    """Run the full grounding eval and return the score dict."""
    paper = load_paper(paper_path)
    scratchpad = load_scratchpad(scratchpad_path)

    citation_check = check_source_citations(paper, scratchpad)
    uncited_claims = scan_uncited_claims(paper)
    score = score_grounding(citation_check["citation_rate"], uncited_claims)

    print_report(citation_check, uncited_claims, score)
    return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eval 1: Grounding — checks citation coverage")
    parser.add_argument("--paper", type=Path, default=DEFAULT_PAPER_PATH,
                        help=f"Path to the paper text file (default: {DEFAULT_PAPER_PATH})")
    parser.add_argument("--scratchpad", type=Path, default=DEFAULT_SCRATCHPAD_PATH,
                        help=f"Path to scratchpad.json (default: {DEFAULT_SCRATCHPAD_PATH})")
    args = parser.parse_args()

    run_eval(args.paper, args.scratchpad)
