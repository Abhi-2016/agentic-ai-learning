"""
eval_efficiency.py — Eval 4: Efficiency

WHAT THIS EVAL MEASURES:
  Quality per tool call — did the agent produce good output efficiently,
  or did it wander (redundant searches, unused page reads, over-iteration)?

WHY IT EXISTS:
  Evals 1–3 measure the output. Eval 4 measures the process.
  Two agents can produce identical quality papers — one using 10 tool calls,
  one using 30. The first is efficient. The second is wasteful and fragile:
  at scale, that waste is latency, API cost, and a signal that something
  in the system prompt or tools is not well-defined.

THE FORMULA:
  efficiency_score = min(composite_quality / (num_tool_calls / BASELINE), 1.0)

  Where:
    composite_quality = average of Eval 1, 2, 3 final scores
    num_tool_calls    = total tool dispatches logged in run_metrics.json
    BASELINE          = 10 (ideal: 3 search + 3 read + 3 save + 1 margin)

  Interpretation:
    penalty_factor = num_tool_calls / BASELINE
    - penalty = 1.0  → used exactly baseline calls → no penalty
    - penalty = 2.0  → used 2× baseline → efficiency halved
    - penalty = 0.5  → used half baseline → score capped at 1.0

WHY THIS IS THE PM DASHBOARD METRIC:
  A single number that captures both quality and process health.
  If efficiency drops over time (same quality, more calls), something
  is degrading — before it shows up in the output evals. Leading indicator.

Run with:
  python evals/eval_efficiency.py
  python evals/eval_efficiency.py --paper <path> --scratchpad <path> --metrics <path>
"""

import json
import argparse
import sys
from pathlib import Path

# ── Load .env before importing sub-evals ─────────────────────────────────────
# override=True: use .env even if ANTHROPIC_API_KEY is already set as empty string
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# ── Import the three existing eval runners ────────────────────────────────────
# All three expose run_eval(paper_path, scratchpad_path) → dict with "final_score".
# We alias them so they can live in the same namespace without name collisions.
sys.path.insert(0, str(Path(__file__).parent))  # make evals/ importable
from eval_grounding import run_eval as run_grounding        # Eval 1: rule-based
from eval_factuality import run_eval as run_factuality      # Eval 2: LLM-as-judge
from eval_completeness import run_eval as run_completeness  # Eval 3: rubric

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PAPER_PATH = PROJECT_ROOT / "last_paper.txt"
DEFAULT_SCRATCHPAD_PATH = PROJECT_ROOT / "scratchpad.json"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "run_metrics.json"

# ── Constants ─────────────────────────────────────────────────────────────────
# BASELINE: the ideal tool call count for a minimal correct run.
# 3 × search_web  +  3 × read_page_contents  +  3 × save_note  +  1 margin = 10
# A run using exactly 10 calls for perfect quality scores 1.0 efficiency.
BASELINE_TOOL_CALLS = 10

# Verdict thresholds — same PASS / WARN / FAIL scale as Evals 1–3
PASS_THRESHOLD = 0.70   # good quality, call count reasonable
WARN_THRESHOLD = 0.40   # quality or efficiency needs improvement


# ── Core functions ────────────────────────────────────────────────────────────

def load_metrics(metrics_path: Path) -> dict:
    """
    Load run_metrics.json written by agent.py on a successful run.

    Expected shape: { "topic": str, "num_tool_calls": int, "num_iterations": int }

    Raises FileNotFoundError with a helpful message if the file is missing —
    which usually means the agent hasn't been run yet this session.
    """
    if not metrics_path.exists():
        raise FileNotFoundError(
            f"run_metrics.json not found at {metrics_path}\n"
            "Run the agent first to generate metrics:\n"
            "  python agent.py \"<your topic>\" > last_paper.txt"
        )
    return json.loads(metrics_path.read_text())


def score_to_verdict(score: float) -> str:
    """Map a 0.0–1.0 score to a PASS / WARN / FAIL string."""
    if score >= PASS_THRESHOLD:
        return "PASS"
    elif score >= WARN_THRESHOLD:
        return "WARN"
    else:
        return "FAIL"


def verdict_emoji(verdict: str) -> str:
    """Return the display emoji for a verdict string."""
    return {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}.get(verdict, "❓")


def run_eval(
    paper_path: Path,
    scratchpad_path: Path,
    metrics_path: Path,
) -> dict:
    """
    Orchestrate all four eval components and compute the efficiency score.

    Steps:
      1. Load run_metrics.json for the tool call count.
      2. Run Eval 1 (Grounding), Eval 2 (Factuality), Eval 3 (Completeness).
         Each prints its own report — the user sees the full picture before
         the efficiency summary appears.
      3. Compute composite_quality = mean of the three final_scores.
      4. Apply efficiency formula: min(quality / (calls / BASELINE), 1.0)
      5. Return results dict.
    """
    # ── Step 1: Load metrics ──────────────────────────────────────────────────
    metrics = load_metrics(metrics_path)
    num_tool_calls = metrics["num_tool_calls"]
    topic = metrics.get("topic", "Unknown")
    num_iterations = metrics.get("num_iterations", "Unknown")

    # ── Step 2: Run all three sub-evals ──────────────────────────────────────
    # Each call prints its own full report to stdout as it runs.
    # We only need the final_score from the returned dict.
    grounding_result = run_grounding(paper_path, scratchpad_path)
    factuality_result = run_factuality(paper_path, scratchpad_path)
    completeness_result = run_completeness(paper_path, scratchpad_path)

    # ── Step 3: Composite quality ─────────────────────────────────────────────
    # Simple equal-weight average across all three evals.
    # A PM could adjust weights later — e.g. factuality × 2 if accuracy is critical.
    g_score = grounding_result["final_score"]
    f_score = factuality_result["final_score"]
    c_score = completeness_result["final_score"]
    composite_quality = round((g_score + f_score + c_score) / 3, 3)

    # ── Step 4: Efficiency score ──────────────────────────────────────────────
    # penalty_factor = how many "ideal runs" worth of calls were used.
    # 1.0 = exactly baseline (no penalty). 2.0 = double baseline (halves score).
    penalty_factor = num_tool_calls / BASELINE_TOOL_CALLS
    raw_efficiency = composite_quality / penalty_factor
    efficiency_score = round(min(raw_efficiency, 1.0), 3)  # cap at 1.0

    verdict = score_to_verdict(efficiency_score)

    return {
        "topic": topic,
        "num_tool_calls": num_tool_calls,
        "num_iterations": num_iterations,
        "baseline_tool_calls": BASELINE_TOOL_CALLS,
        "penalty_factor": round(penalty_factor, 2),
        "grounding_score": g_score,
        "factuality_score": f_score,
        "completeness_score": c_score,
        "composite_quality": composite_quality,
        "efficiency_score": efficiency_score,
        "verdict": verdict,
    }


def print_report(results: dict) -> None:
    """
    Print the Eval 4 summary report — appears after the three sub-eval reports.

    Shows each quality sub-score, the tool call penalty, and the final
    efficiency score + verdict.
    """
    verdict = results["verdict"]
    emoji = verdict_emoji(verdict)

    print("\n")
    print("=" * 60)
    print("EVAL 4: EFFICIENCY REPORT")
    print("=" * 60)

    print(f"\n  Topic:      {results['topic']}")
    print(f"  Iterations: {results['num_iterations']}")

    # ── Quality sub-scores ────────────────────────────────────────────────────
    print("\n── Quality sub-scores ────────────────────────────────────────")
    for label, key in [
        ("Grounding   (Eval 1)", "grounding_score"),
        ("Factuality  (Eval 2)", "factuality_score"),
        ("Completeness (Eval 3)", "completeness_score"),
    ]:
        score = results[key]
        sub_verdict = score_to_verdict(score)
        sub_emoji = verdict_emoji(sub_verdict)
        print(f"  {sub_emoji} {label:<26} {score * 100:.1f}%  ({sub_verdict})")

    print(f"\n  {'Composite quality':<30} {results['composite_quality'] * 100:.1f}%")

    # ── Tool call breakdown ───────────────────────────────────────────────────
    print("\n── Tool call efficiency ──────────────────────────────────────")
    print(f"  Tool calls used:   {results['num_tool_calls']}")
    print(f"  Baseline:          {results['baseline_tool_calls']}")
    print(f"  Penalty factor:    {results['penalty_factor']:.1f}×")

    # Plain-English interpretation of the penalty
    pf = results["penalty_factor"]
    if pf <= 1.0:
        print("  (Used ≤ baseline calls — maximum efficiency)")
    elif pf <= 1.5:
        print("  (Slightly above baseline — acceptable)")
    elif pf <= 2.5:
        print("  (Above baseline — some redundant calls)")
    else:
        print("  (Well above baseline — agent is wandering)")

    # ── Final score ───────────────────────────────────────────────────────────
    print("\n── Final Score ───────────────────────────────────────────────")
    print(f"  Composite quality:  {results['composite_quality'] * 100:.1f}%")
    print(f"  Efficiency score:   {results['efficiency_score'] * 100:.1f}%")
    print(f"  Verdict:            {emoji} {verdict}")

    if verdict == "FAIL":
        print("\n  ❌ Poor quality and/or excessive tool calls.")
        print("     Review sub-eval scores — identify the weakest link.")
    elif verdict == "WARN":
        print("\n  ⚠️  Quality is acceptable but the agent is over-calling tools.")
        print("     Check the system prompt — tighten stopping conditions.")
    else:
        print("\n  ✅ Good quality, efficient process. Agent is working well.")

    # PM insight
    print("\n── PM Insight ────────────────────────────────────────────────")
    print("  This is your dashboard metric — one number for stakeholders.")
    print("  If this score drops run-over-run with stable quality,")
    print("  the agent is drifting. Tighten the system prompt before")
    print("  quality scores start to follow.")
    print("=" * 60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point — parse args, run eval, print report, exit with status."""
    parser = argparse.ArgumentParser(
        description="Eval 4: Efficiency — quality per tool call"
    )
    parser.add_argument(
        "--paper", type=Path, default=DEFAULT_PAPER_PATH,
        help="Path to the paper (default: last_paper.txt)"
    )
    parser.add_argument(
        "--scratchpad", type=Path, default=DEFAULT_SCRATCHPAD_PATH,
        help="Path to scratchpad.json (default: scratchpad.json)"
    )
    parser.add_argument(
        "--metrics", type=Path, default=DEFAULT_METRICS_PATH,
        help="Path to run_metrics.json written by agent.py (default: run_metrics.json)"
    )
    args = parser.parse_args()

    try:
        results = run_eval(args.paper, args.scratchpad, args.metrics)
    except FileNotFoundError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        sys.exit(1)

    print_report(results)

    # Non-zero exit on FAIL so CI pipelines can catch it automatically
    if results["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
