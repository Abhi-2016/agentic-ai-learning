"""
coach.py — PM Interview Coach: LLM Orchestrator (Week 3B)

WHAT THIS IS:
  The orchestrator for Agent 2 — the PM Interview Coach.
  Week 3B upgrade: replaces the Python router with an LLM orchestrator
  that reads session history and decides what to do next each turn.

THE DIFFERENCE FROM WEEK 3:
  Week 3 (Python router): flow was fixed — question → answer → evaluate → save.
  Python decided nothing; it just followed a hardcoded sequence.

  Week 3B (LLM orchestrator): Claude reads history and chooses the next action:
    - ask_on_topic: pick a specific topic and generate a question
    - suggest_topic: delegate to Agent C to find the user's weakest area
    - end_session: enough practice — wrap up

  Python routes by rules. An LLM orchestrator routes by reasoning.

FOUR AGENTS:
  Orchestrator (Claude) — session manager: reads history, decides next action
  Agent A (question_generator.py) — generates one calibrated question
  Agent B (evaluator.py) — scores the answer 1-5 with feedback
  Agent C (topic_suggester.py) — pattern analyser: finds the weakest topic

PERSISTENT MEMORY:
  coach_history.json stores every question, answer, and score.
  Orchestrator owns all reads and writes — no agent touches it directly.

Run with:
  python3 interview_coach/coach.py
"""

import json
import re
import sys
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# ── Import agents ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from question_generator import generate_question   # Agent A
from evaluator import evaluate_answer              # Agent B
from topic_suggester import suggest_topic          # Agent C

# ── Constants ─────────────────────────────────────────────────────────────────
TOPICS = [
    "ReAct pattern",
    "Memory types",
    "Tool design",
    "Eval frameworks",
    "Orchestration",
    "Stopping conditions",
    "System prompt design",
]

HISTORY_PATH = Path(__file__).parent / "coach_history.json"
CLAUDE_MD_PATH = Path(__file__).parent.parent / "CLAUDE.md"

# Model for the orchestrator — Haiku is enough for structured routing decisions
ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"

# ── Orchestrator system prompt ─────────────────────────────────────────────────
# The orchestrator sees history + context and decides the next action.
# Strict output format — parsed by the Python loop below.
ORCHESTRATOR_SYSTEM_PROMPT = """You are a session manager for a PM Interview Coach.

Each turn you will receive:
- HISTORY_SUMMARY: topics the learner has practised and their scores
- TOTAL_HISTORY_ENTRIES: exact count of all attempts across all topics
- QUESTIONS_THIS_SESSION: how many questions asked so far this session

Follow these priorities in order. Check Priority 1 first, then Priority 2, then Priority 3.
Stop at the first one that applies.

Priority 1 — check this first.
  If QUESTIONS_THIS_SESSION is greater than or equal to 5: ACTION is end_session.
  Wrap the session up.

Priority 2 — check this next.
  If TOTAL_HISTORY_ENTRIES is greater than or equal to 5: ACTION is suggest_topic.
  Delegate topic selection to a specialist analyser.
  Do not analyse topics yourself — always delegate to the specialist.

Priority 3 — default, only if neither Priority 1 nor Priority 2 applied.
  ACTION is ask_on_topic.
  Pick a topic that has never been attempted, or has the lowest average score.

Respond in exactly this format (two lines, nothing else):
ACTION: <ask_on_topic|suggest_topic|end_session>
TOPIC: <topic name if ACTION is ask_on_topic, otherwise omit this line>"""


# ── Learner context ────────────────────────────────────────────────────────────

def load_learner_context() -> str:
    """Read CLAUDE.md and extract learning progress — passed to Agent A."""
    if not CLAUDE_MD_PATH.exists():
        return ""
    content = CLAUDE_MD_PATH.read_text()
    start = content.find("## Learning Progress Tracker")
    if start == -1:
        return ""
    section = content[start:]
    next_section = re.search(r'\n## ', section[1:])
    if next_section:
        section = section[:next_section.start() + 1]
    return f"""Learner profile:
- Role: Product Manager (not an engineer) learning Agentic AI
- Goal: Speak credibly about agentic AI in a PM interview
- Has built: 2 agents in a learning context (not production systems)

{section.strip()}

Question calibration:
- Only ask about concepts listed under "Quizzes passed" above
- Frame as "explain X", "why does X matter", or "what tradeoff does X create"
- Do NOT use war-story framing — learner has built 2 agents in a structured course
- Difficulty: foundational to intermediate — not senior engineer level"""


# ── Memory functions ───────────────────────────────────────────────────────────

def load_history() -> list:
    """Load all-time history from disk."""
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return []


def save_to_history(entry: dict) -> None:
    """Append one entry — orchestrator owns all writes, agents never write here."""
    history = load_history()
    history.append(entry)
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def build_history_summary(history: list) -> str:
    """
    Summarise all-time history as a readable string for the orchestrator.
    Groups by topic so the orchestrator can spot patterns at a glance.
    """
    if not history:
        return "No history yet — this is the learner's first session."

    topic_stats: dict[str, list[int]] = {}
    for entry in history:
        topic = entry.get("topic", "")
        score = entry.get("score", 0)
        if topic:
            topic_stats.setdefault(topic, []).append(score)

    lines = []
    for topic in TOPICS:
        if topic in topic_stats:
            scores = topic_stats[topic]
            avg = sum(scores) / len(scores)
            lines.append(f"- {topic}: {len(scores)} attempt(s), avg {avg:.1f}/5")
        else:
            lines.append(f"- {topic}: never attempted")
    return "\n".join(lines)


# ── LLM Orchestrator ───────────────────────────────────────────────────────────

def orchestrate(history: list, questions_this_session: int) -> dict:
    """
    Call the LLM orchestrator to decide the next action.

    This is the core of Week 3B — a Claude call that reads history and
    reasons about what to do next, rather than following hardcoded Python logic.

    Returns: {action: str, topic: str|None}
    """
    client = anthropic.Anthropic()

    history_summary = build_history_summary(history)
    total_entries = len(history)  # raw count — passed explicitly so LLM doesn't have to sum the summary

    user_message = f"""HISTORY_SUMMARY:
{history_summary}

TOTAL_HISTORY_ENTRIES: {total_entries}
QUESTIONS_THIS_SESSION: {questions_this_session}"""

    response = client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=80,
        system=ORCHESTRATOR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = response.content[0].text.strip()

    # Parse the structured response
    action = ""
    topic = None
    for line in raw.splitlines():
        if line.startswith("ACTION:"):
            action = line.replace("ACTION:", "").strip()
        elif line.startswith("TOPIC:"):
            topic = line.replace("TOPIC:", "").strip()

    # Fallback if parsing fails
    if action not in ("ask_on_topic", "suggest_topic", "end_session"):
        action = "ask_on_topic"
        topic = TOPICS[0]

    return {"action": action, "topic": topic}


# ── Display helpers ────────────────────────────────────────────────────────────

def show_score(result: dict) -> None:
    """Print Agent B's evaluation."""
    score = result["score"]
    indicator = "🟢" if score >= 5 else "🟡" if score >= 4 else "🟠" if score >= 3 else "🔴"
    print(f"\n── Evaluation ────────────────────────────────────────────")
    print(f"  {indicator} Score:       {score}/5")
    print(f"  ✅ Strength:    {result['strength']}")
    print(f"  📈 Improve:     {result['improvement']}")


def show_session_summary(history: list, session_count: int) -> None:
    """Print progress summary at start and end of session."""
    if not history:
        return
    scores = [e["score"] for e in history if e.get("score")]
    avg = sum(scores) / len(scores) if scores else 0
    print(f"\n── Your progress ─────────────────────────────────────────")
    print(f"  Total sessions completed: {len(history)}")
    print(f"  All-time average score:   {avg:.1f}/5")
    if session_count > 0:
        print(f"  Questions this session:   {session_count}")
    if len(history) >= 2:
        print(f"\n  Last 3 sessions:")
        for entry in history[-3:]:
            print(f"    [{entry['score']}/5] {entry['topic']} — {entry['question'][:50]}...")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_coach() -> None:
    """
    Main loop — now driven by the LLM orchestrator.

    Each turn:
      1. Load history (all-time)
      2. Call orchestrator → get action + topic
      3. If suggest_topic → call Agent C → get topic
      4. Call Agent A → get question on that topic
      5. User answers
      6. Call Agent B → score + feedback
      7. Save to history
      8. Repeat until orchestrator says end_session or user quits
    """
    print("\n" + "=" * 60)
    print("PM Interview Coach — Agentic AI (Week 3B: LLM Orchestrator)")
    print("=" * 60)
    print("\nThe coach now decides what to ask based on your history.")
    print("Each answer is scored 1–5 with specific feedback.")
    print("Type 'q' at any time to quit.\n")

    # Load once at startup — orchestrator owns context, agents receive it
    learner_context = load_learner_context()
    history = load_history()
    show_session_summary(history, session_count=0)

    questions_this_session = 0

    while True:
        # ── Step 1: LLM orchestrator decides next action ──────────────────────
        print("\n  Thinking about what to ask next...")
        decision = orchestrate(history, questions_this_session)
        action = decision["action"]
        topic = decision["topic"]

        # ── Step 2: Handle end_session ────────────────────────────────────────
        if action == "end_session":
            print("\n── Session complete ──────────────────────────────────────")
            print("  Good work. The coach has decided you've covered enough for now.")
            history = load_history()
            show_session_summary(history, questions_this_session)
            print("\nGood luck in your interview. 🎯")
            break

        # ── Step 3: If suggest_topic, call Agent C ────────────────────────────
        if action == "suggest_topic":
            print("  Analysing your history for weak spots...")
            suggestion = suggest_topic(history)
            topic = suggestion["suggested_topic"]
            print(f"  💡 Coach suggests: {topic}")
            print(f"     Reason: {suggestion['reason']}")

        # Allow user to override or quit
        print(f"\n── Next topic: {topic} ───────────────────────────────────")
        override = input("  Press Enter to continue, type a number to pick your own topic, or 'q' to quit: ").strip().lower()

        if override == "q":
            print("\nGood luck in your interview. 🎯")
            break

        if override.isdigit():
            idx = int(override) - 1
            if 0 <= idx < len(TOPICS):
                topic = TOPICS[idx]
                print(f"  → Switching to: {topic}")
            else:
                print("  Invalid choice — continuing with coach's suggestion.")

        # ── Step 4: Agent A generates question ───────────────────────────────
        print(f"\n  Generating question on: {topic}...")
        question = generate_question(topic, learner_context)

        print(f"\n── Question ──────────────────────────────────────────────")
        print(f"  {question}")
        print(f"─────────────────────────────────────────────────────────")

        # ── Step 5: Collect answer ────────────────────────────────────────────
        print("\nYour answer (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if line == "" and lines:
                break
            if line.lower() == "q":
                print("\nGood luck in your interview. 🎯")
                sys.exit(0)
            lines.append(line)
        answer = " ".join(lines).strip()

        if not answer:
            print("  No answer provided — skipping.")
            continue

        # ── Step 6: Agent B evaluates ─────────────────────────────────────────
        print("\n  Evaluating...")
        result = evaluate_answer(question, answer)
        show_score(result)

        # ── Step 7: Save (orchestrator owns all writes) ───────────────────────
        save_to_history({
            "topic": topic,
            "question": question,
            "answer": answer,
            "score": result["score"],
            "strength": result["strength"],
            "improvement": result["improvement"],
        })

        # Reload history so orchestrator sees the latest entry next turn
        history = load_history()
        questions_this_session += 1

        input("\n  Press Enter to continue...")


if __name__ == "__main__":
    run_coach()
