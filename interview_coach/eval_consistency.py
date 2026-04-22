"""
eval_consistency.py — Meta-eval: Agent B Consistency Test

WHAT THIS TESTS:
  Runs the same real question + answer through Agent B N times and
  measures whether the score is consistent across runs.

  A reliable evaluator must return the same score on identical input.
  Variance reveals whether Agent B can be trusted as a product metric.

WHY THIS MATTERS (Week 4 learning):
  Inconsistent scores destroy the signal you use to make decisions.
  If Agent B scores the same answer 3 one time and 4 another, you
  can't tell whether a score change reflects genuine improvement
  or judge noise. This is called inter-rater reliability.

TEST CASE — real question + answer from coach_history.json:
  Topic:    ReAct pattern
  Score:    4/5 (sits on the 3/4 boundary — most sensitive to variance)
  Chosen because boundary cases are where variance hurts most.

VERDICT:
  Variance 0 → PASS  — evaluator is deterministic, scores are trustworthy
  Variance 1 → WARN  — minor drift, monitor across more runs
  Variance 2+ → FAIL — evaluator is unreliable, fix before trusting scores

Run with:
  python3 interview_coach/eval_consistency.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evaluator import evaluate_answer   # Agent B

# ── Fixed test case — pulled directly from coach_history.json ─────────────────
# This is Abhishek's real answer that scored 4/5.
# Keeping it verbatim: typos and all — the eval should score the content,
# not the spelling.

TEST_QUESTION = (
    "Explain why the ReAct pattern separates an agent's thinking from its "
    "action, and what problem does that separation solve for a PM trying to "
    "evaluate whether an agent is working correctly?"
)

TEST_ANSWER = (
    "the ReAct pattern shows clearly what the agent was thinkning when it "
    "took an action. This is an important pattern to figure out the reasoning "
    "behind the actions that agents take. This separation helps with evalutions. "
    "A PM trying to figure out whether an agent is complying with the system "
    "prompt can check the ReAct step to see what the reasoning is to make needed "
    "changes. The ReAct pattern also helps an Agent figure out what next steps "
    "to take when the reasoning is laid out clearly for each step."
)

NUM_RUNS = 5


# ── Consistency test ───────────────────────────────────────────────────────────

def run_eval() -> dict:
    """
    Run Agent B NUM_RUNS times on identical input and measure score variance.

    temperature=0 is set in evaluator.py — this test confirms whether that
    setting is holding. If variance > 0, something changed upstream.
    """
    print(f"\n{'='*60}")
    print("Agent B — Consistency Test (Meta-eval)")
    print(f"{'='*60}")
    print(f"\nTest case: ReAct pattern answer (expected: 4/5)")
    print(f"Runs: {NUM_RUNS}\n")

    scores = []

    for i in range(1, NUM_RUNS + 1):
        print(f"  Run {i}/{NUM_RUNS}...", end=" ", flush=True)
        result = evaluate_answer(TEST_QUESTION, TEST_ANSWER)
        score = result["score"]
        scores.append(score)
        print(f"Score: {score}/5")

    # ── Calculate stats ────────────────────────────────────────────────────────
    variance = max(scores) - min(scores)
    avg = sum(scores) / len(scores)
    all_same = len(set(scores)) == 1

    # ── Verdict ───────────────────────────────────────────────────────────────
    if variance == 0:
        verdict = "PASS"
        verdict_note = "Evaluator is fully consistent — scores are trustworthy."
    elif variance == 1:
        verdict = "WARN"
        verdict_note = "Minor variance detected. Monitor across more runs before trusting scores."
    else:
        verdict = "FAIL"
        verdict_note = "Evaluator is unreliable. Review temperature setting and rubric clarity."

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n── Results ───────────────────────────────────────────────")
    print(f"  Scores:   {scores}")
    print(f"  Average:  {avg:.1f}/5")
    print(f"  Variance: {variance} point(s)  (max - min)")
    print(f"  Verdict:  {verdict}")
    print(f"  Note:     {verdict_note}")

    return {
        "scores": scores,
        "average": avg,
        "variance": variance,
        "verdict": verdict,
    }


if __name__ == "__main__":
    run_eval()
