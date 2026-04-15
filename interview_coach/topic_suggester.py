"""
topic_suggester.py — Agent C: Topic Suggester

WHAT THIS AGENT DOES:
  Given the full all-time coaching history, identifies the topic the user
  most needs to practise and explains why. This is Agent C in the Week 3B
  multi-agent PM Interview Coach system.

WHY IT'S A SEPARATE AGENT (not the orchestrator):
  The orchestrator is a session manager — it decides the next move for the
  current turn. Agent C is a pattern analyser — it looks across all historical
  sessions to surface consistent weak spots. Different scope, different job.

  If topic suggestions are poor, you tune this system prompt without touching
  the orchestrator or any other agent.

HOW IT WORKS:
  One Haiku call. No tools. No loop. No memory.
  Input:  full coach_history.json as a formatted string
  Output: {suggested_topic, reason}

  Stateless — each suggestion is independent of previous calls.
"""

import json
import re
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

MODEL = "claude-haiku-4-5-20251001"

TOPICS = [
    "ReAct pattern",
    "Memory types",
    "Tool design",
    "Eval frameworks",
    "Orchestration",
    "Stopping conditions",
    "System prompt design",
]

# ── Agent C system prompt ──────────────────────────────────────────────────────
# Narrow brief: analyse history, return one topic recommendation.
# Strict output format mirrors Agent A and B — structured, parseable.
SYSTEM_PROMPT = """You are a learning coach analysing a student's interview practice history.

You will receive HISTORY: a log of all past practice sessions showing topics covered and scores.

Your job: identify the single topic the student most needs to practise next.

Decision criteria (in order of priority):
1. Topics never attempted — a gap is worse than a low score
2. Topics with consistently low scores (average below 3/5)
3. Topics attempted only once — need more repetition to confirm understanding

Available topics:
- ReAct pattern
- Memory types
- Tool design
- Eval frameworks
- Orchestration
- Stopping conditions
- System prompt design

Respond in exactly this format (two lines, nothing else):
TOPIC: <topic name, must match one of the available topics exactly>
REASON: <one sentence explaining why this topic needs the most attention>"""


def suggest_topic(history: list) -> dict:
    """
    Call Agent C to identify the topic the user most needs to practise.

    The orchestrator passes the full history — Agent C does not read the
    file itself. This follows the same context-passing pattern as Agent A:
    agents receive what they need, they don't fetch it.

    Returns a dict with 'suggested_topic' (str) and 'reason' (str).
    """
    client = anthropic.Anthropic()

    # Format history as a readable summary for the judge
    # Group by topic so Agent C can see score patterns clearly
    if not history:
        return {
            "suggested_topic": TOPICS[0],
            "reason": "No history yet — starting with the foundational topic.",
        }

    # Build a per-topic summary: attempts and average score
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
            lines.append(f"- {topic}: {len(scores)} attempt(s), avg score {avg:.1f}/5")
        else:
            lines.append(f"- {topic}: never attempted")

    history_summary = "\n".join(lines)

    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"HISTORY:\n{history_summary}"}
        ]
    )

    raw = response.content[0].text.strip()

    # Parse structured response — same pattern as Agent B
    suggested_topic = ""
    reason = ""
    for line in raw.splitlines():
        if line.startswith("TOPIC:"):
            suggested_topic = line.replace("TOPIC:", "").strip()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    # Fallback: if parsing fails, pick first untried topic
    if not suggested_topic:
        tried = set(topic_stats.keys())
        for topic in TOPICS:
            if topic not in tried:
                suggested_topic = topic
                reason = "Never attempted — starting here."
                break
        if not suggested_topic:
            suggested_topic = TOPICS[0]
            reason = "Defaulting to foundational topic."

    return {"suggested_topic": suggested_topic, "reason": reason}
