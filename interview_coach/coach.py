"""
coach.py — PM Interview Coach: Orchestrator

WHAT THIS IS:
  The orchestrator for Agent 2 — the PM Interview Coach.
  It coordinates Agent A (question generator) and Agent B (evaluator),
  manages the conversation loop, and owns all persistent state.

THE ORCHESTRATOR PATTERN (from Quiz 9):
  The orchestrator is the only component that sees the full picture.
  Agent A only knows the topic. Agent B only knows the question + answer.
  Neither agent knows about the other — the orchestrator holds the state
  between calls and passes exactly what each agent needs.

WHY A PYTHON ROUTER (not an LLM orchestrator):
  The flow here is fixed and predictable:
    generate question → get answer → evaluate → save → repeat
  No LLM reasoning is needed to decide that sequence. Python logic is
  cheaper, faster, and more reliable for deterministic flows.
  Week 3B will replace this with an LLM orchestrator for dynamic routing.

PERSISTENT MEMORY:
  coach_history.json stores every question, answer, and score.
  This is the same pattern as scratchpad.json in Agent 1 — simple,
  inspectable, no infrastructure. Open it and read it.

Run with:
  python interview_coach/coach.py
"""

import json
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# ── Import agents ──────────────────────────────────────────────────────────────
# Each agent is a separate module — single responsibility, easy to swap.
# Adding a new agent in Week 3B means adding one import and one function call.
sys.path.insert(0, str(Path(__file__).parent))
from question_generator import generate_question   # Agent A
from evaluator import evaluate_answer              # Agent B

# ── Constants ─────────────────────────────────────────────────────────────────
# Topics drawn from Week 1 + 2 concepts — Abhishek has built all of these.
# Questions will test understanding of systems he actually built, not theory.
TOPICS = [
    "ReAct pattern",
    "Memory types",
    "Tool design",
    "Eval frameworks",
    "Orchestration",
    "Stopping conditions",
    "System prompt design",
]

# Persistent memory — same directory as this file
HISTORY_PATH = Path(__file__).parent / "coach_history.json"


# ── Memory functions ───────────────────────────────────────────────────────────

def load_history() -> list:
    """Load conversation history from disk. Returns empty list if file doesn't exist."""
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return []


def save_to_history(entry: dict) -> None:
    """
    Append one session entry to coach_history.json.

    The orchestrator owns all writes to shared state — neither agent
    writes here directly. This is the memory ownership pattern from Quiz 9, Q3.
    """
    history = load_history()
    history.append(entry)
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


# ── Display helpers ────────────────────────────────────────────────────────────

def show_topics() -> None:
    """Print the topic menu."""
    print("\n── Available topics ──────────────────────────────────────")
    for i, topic in enumerate(TOPICS, 1):
        print(f"  {i}. {topic}")
    print("  q. Quit")


def show_score(result: dict) -> None:
    """Print Agent B's evaluation in a readable format."""
    score = result["score"]

    # Visual indicator for score level
    if score >= 5:
        indicator = "🟢"
    elif score >= 4:
        indicator = "🟡"
    elif score >= 3:
        indicator = "🟠"
    else:
        indicator = "🔴"

    print(f"\n── Evaluation ────────────────────────────────────────────")
    print(f"  {indicator} Score:       {score}/5")
    print(f"  ✅ Strength:    {result['strength']}")
    print(f"  📈 Improve:     {result['improvement']}")


def show_session_summary() -> None:
    """Print a summary of scores from this session and all time."""
    history = load_history()
    if not history:
        return

    # All-time stats
    scores = [e["score"] for e in history if e.get("score")]
    avg = sum(scores) / len(scores) if scores else 0

    print(f"\n── Your progress ─────────────────────────────────────────")
    print(f"  Sessions completed: {len(history)}")
    print(f"  Average score:      {avg:.1f}/5")

    # Last 3 sessions
    if len(history) >= 2:
        print(f"\n  Last {min(3, len(history))} sessions:")
        for entry in history[-3:]:
            print(f"    [{entry['score']}/5] {entry['topic']} — {entry['question'][:50]}...")


# ── Main orchestrator loop ─────────────────────────────────────────────────────

def run_coach() -> None:
    """
    Main orchestration loop — the Python router.

    This is where the orchestrator pattern from Quiz 9 is implemented:
    - Orchestrator decides what to call and when
    - Passes only what each agent needs
    - Owns all state between agent calls

    Flow per iteration:
      1. User picks a topic
      2. Call Agent A → get question
      3. Show question → get user's answer
      4. Call Agent B with question + answer → get score + feedback
      5. Save to history (orchestrator writes, agents don't)
      6. Loop or quit
    """
    print("\n" + "=" * 60)
    print("PM Interview Coach — Agentic AI")
    print("=" * 60)
    print("\nPractice explaining agentic AI concepts in plain language.")
    print("Each answer is scored 1–5 with specific feedback.")

    show_session_summary()

    while True:
        show_topics()
        choice = input("\nChoose a topic: ").strip().lower()

        if choice == "q":
            print("\nGood luck in your interview. 🎯")
            break

        # ── Validate topic choice ─────────────────────────────────────────────
        try:
            topic_index = int(choice) - 1
            if topic_index < 0 or topic_index >= len(TOPICS):
                print("  Please enter a number from the list.")
                continue
            topic = TOPICS[topic_index]
        except ValueError:
            print("  Please enter a number or 'q' to quit.")
            continue

        # ── Step 1: Agent A generates the question ────────────────────────────
        print(f"\n  Generating question on: {topic}...")
        question = generate_question(topic)

        print(f"\n── Question ──────────────────────────────────────────────")
        print(f"  {question}")
        print(f"─────────────────────────────────────────────────────────")

        # ── Step 2: Collect user's answer ─────────────────────────────────────
        print("\nYour answer (press Enter twice when done):")

        # Multi-line input: user presses Enter twice to submit
        # This gives space for a full 2-4 sentence answer
        lines = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        answer = " ".join(lines).strip()

        if not answer:
            print("  No answer provided — skipping.")
            continue

        # ── Step 3: Agent B evaluates the answer ─────────────────────────────
        # The orchestrator passes BOTH question and answer to Agent B.
        # Agent B has no memory — it only knows what we explicitly pass.
        # This is the information-passing pattern from Quiz 9, Q2.
        print("\n  Evaluating...")
        result = evaluate_answer(question, answer)

        # ── Step 4: Show result ───────────────────────────────────────────────
        show_score(result)

        # ── Step 5: Save to history (orchestrator owns all writes) ────────────
        save_to_history({
            "topic": topic,
            "question": question,
            "answer": answer,
            "score": result["score"],
            "strength": result["strength"],
            "improvement": result["improvement"],
        })

        input("\n  Press Enter to continue...")


if __name__ == "__main__":
    run_coach()
