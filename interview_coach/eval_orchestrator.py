"""
eval_orchestrator.py — Meta-eval: Orchestrator Accuracy Test

WHAT THIS TESTS:
  Runs the LLM orchestrator against 5 synthetic history scenarios,
  each with a clearly correct expected routing decision.
  Measures whether the orchestrator routes correctly.

WHY THIS MATTERS (Week 4 learning):
  The orchestrator decides what the user practises next. If it routes
  incorrectly — sending the user to a strong topic instead of a weak one,
  or ending the session too early — the coach loses its value.
  Accuracy is different from consistency: consistency = same input, same output.
  Accuracy = correct input, correct decision.

SCENARIOS:
  A — Empty history, 0 questions → ask_on_topic (nothing to analyse)
  B — One weak topic (avg 2/5), others never tried, 0 questions → ask_on_topic
  C — Rich history (6 entries), one clear weak spot, 0 questions → suggest_topic
  D — 5 questions this session, all topics strong → end_session
  E — 3 questions this session, mixed scores → ask_on_topic (keep going)

VERDICT:
  PASS  ≥ 80% correct (4 or 5 out of 5)
  WARN  60–79% correct (3 out of 5)
  FAIL  < 60% correct (2 or fewer out of 5)

Run with:
  python3 interview_coach/eval_orchestrator.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from coach import orchestrate   # LLM orchestrator

# ── Synthetic test scenarios ───────────────────────────────────────────────────
# Each scenario has: a name, synthetic history, questions_this_session count,
# and the expected action. History format matches coach_history.json exactly
# so the orchestrator receives realistic input.

SCENARIOS = [
    {
        "name": "A — Empty history",
        "description": "No sessions yet. Orchestrator should start a question.",
        "history": [],
        "questions_this_session": 0,
        "expected_action": "ask_on_topic",
    },
    {
        "name": "B — One weak topic, others never tried",
        "description": "ReAct pattern has low scores. Others not attempted. Should ask on a topic.",
        "history": [
            {"topic": "ReAct pattern", "score": 2},
            {"topic": "ReAct pattern", "score": 2},
        ],
        "questions_this_session": 0,
        "expected_action": "ask_on_topic",
    },
    {
        "name": "C — Rich history, one clear weak spot",
        "description": "6 entries across topics. Stopping conditions is weakest. Should delegate to Agent C.",
        "history": [
            {"topic": "ReAct pattern", "score": 4},
            {"topic": "ReAct pattern", "score": 4},
            {"topic": "Memory types", "score": 4},
            {"topic": "Tool design", "score": 3},
            {"topic": "Eval frameworks", "score": 4},
            {"topic": "Stopping conditions", "score": 2},
        ],
        "questions_this_session": 0,
        "expected_action": "suggest_topic",
    },
    {
        "name": "D — Session complete, all topics strong",
        "description": "5 questions asked, all scoring 4+. Orchestrator should end the session.",
        "history": [
            {"topic": "ReAct pattern", "score": 4},
            {"topic": "Memory types", "score": 5},
            {"topic": "Tool design", "score": 4},
            {"topic": "Eval frameworks", "score": 4},
            {"topic": "Orchestration", "score": 4},
        ],
        "questions_this_session": 5,
        "expected_action": "end_session",
    },
    {
        "name": "E — Mid-session, mixed scores",
        "description": "3 questions asked this session, scores mixed. Should continue asking.",
        "history": [
            {"topic": "ReAct pattern", "score": 3},
            {"topic": "Memory types", "score": 2},
            {"topic": "Tool design", "score": 4},
        ],
        "questions_this_session": 3,
        "expected_action": "ask_on_topic",
    },
]


# ── Accuracy test ──────────────────────────────────────────────────────────────

def run_eval() -> dict:
    """
    Run each scenario through the orchestrator and compare actual vs expected action.

    The orchestrator is an LLM call — it may not be deterministic even at
    default temperature. This test catches systematic routing failures,
    not run-to-run variance (that's eval_consistency.py's job).
    """
    print(f"\n{'='*60}")
    print("Orchestrator — Accuracy Test (Meta-eval)")
    print(f"{'='*60}\n")

    results = []

    for scenario in SCENARIOS:
        print(f"  Scenario {scenario['name']}")
        print(f"  {scenario['description']}")

        decision = orchestrate(scenario["history"], scenario["questions_this_session"])
        actual_action = decision["action"]
        expected_action = scenario["expected_action"]
        correct = actual_action == expected_action

        status = "✅ CORRECT" if correct else "❌ WRONG"
        print(f"  Expected: {expected_action} | Got: {actual_action} | {status}")
        if not correct:
            print(f"  ⚠️  Orchestrator routed incorrectly — review system prompt or history summary format")
        print()

        results.append({
            "scenario": scenario["name"],
            "expected": expected_action,
            "actual": actual_action,
            "correct": correct,
        })

    # ── Score ──────────────────────────────────────────────────────────────────
    correct_count = sum(1 for r in results if r["correct"])
    total = len(results)
    accuracy = correct_count / total

    if accuracy >= 0.80:
        verdict = "PASS"
        note = "Orchestrator is routing correctly across all key scenarios."
    elif accuracy >= 0.60:
        verdict = "WARN"
        note = "Routing has gaps — review failing scenarios and tighten system prompt."
    else:
        verdict = "FAIL"
        note = "Orchestrator is unreliable — routing logic needs significant revision."

    print(f"── Results ───────────────────────────────────────────────")
    print(f"  Correct:  {correct_count}/{total}")
    print(f"  Accuracy: {accuracy*100:.0f}%")
    print(f"  Verdict:  {verdict}")
    print(f"  Note:     {note}")

    return {
        "results": results,
        "correct_count": correct_count,
        "total": total,
        "accuracy": accuracy,
        "verdict": verdict,
    }


if __name__ == "__main__":
    run_eval()
