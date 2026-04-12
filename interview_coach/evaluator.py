"""
evaluator.py — Agent B: Evaluator

WHAT THIS AGENT DOES:
  Given a question and a user's answer, scores the answer 1-5 and gives
  one sentence of specific feedback. This is Agent B in the multi-agent
  PM Interview Coach system.

THE RUBRIC (designed by Abhishek, Quiz 10):
  Criteria:
    1. Relevance  — is the answer about what was actually asked?
    2. Accuracy   — is the concept explained correctly?
    3. Clarity    — jargon-free, plain language, free-flowing
    4. Length     — focused; not too short (incomplete) or too long (point gets lost)

  Scale:
    1 — Off-topic or conceptually wrong
    2 — Correct topic but explanation is confused, wrong on mechanism, or jargon without understanding
    3 — Correct and clear but too brief to stand alone (right answer, not enough detail)
    4 — Correct, clear, at least one concrete detail or example anchors the explanation
    5 — All of 4, plus naturally accessible to a non-technical stakeholder

  Calibration: A brief but correct answer should score ≥ 3. Score 2 only if the explanation is wrong or
  confused — not merely short. Length alone is not grounds for a 2.

WHY IT'S A SEPARATE AGENT:
  Same reason as Agent A — single responsibility. If scoring is too harsh or
  too lenient, you tune this system prompt without touching anything else.
  The evaluator is also the natural place to add calibration (human review)
  if scores drift over time — same pattern as Eval 2's --human-review flag.

HOW IT WORKS:
  One Haiku call. No tools. No loop. No memory.
  Input: question + user's answer
  Output: dict with score, strength, improvement

  Stateless — each evaluation is independent of previous ones.
"""

import re
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

MODEL = "claude-haiku-4-5-20251001"

# ── Agent B system prompt ──────────────────────────────────────────────────────
# The rubric is embedded directly — the judge gets the full scoring criteria
# so it applies them consistently on every call.
# Strict output format (SCORE / STRENGTH / IMPROVEMENT) mirrors the pattern
# from Eval 2 and 3 — structured output is easier to parse reliably.
SYSTEM_PROMPT = """You are an interview coach evaluating answers about agentic AI systems.

You will be given:
- QUESTION: the interview question that was asked
- ANSWER: the candidate's response

Evaluate the answer against these four criteria:
1. Relevance  — is the answer about what was actually asked? Off-topic answers score 1 regardless of quality.
2. Accuracy   — is the concept explained correctly? A fluent answer that gets the concept wrong should not score above 3.
3. Clarity    — is it explained in plain terms, free of unnecessary jargon? Could a non-technical person follow it?
4. Length     — is it focused and appropriately concise? Too short = incomplete. Too long = the point gets lost.

Scoring scale:
1 — Off-topic or conceptually wrong
2 — Correct topic but explanation is confused, wrong on the mechanism, or uses jargon without understanding
3 — Correct and clear but too brief — identifies the right answer without enough detail to stand alone
4 — Correct, clear, and includes at least one concrete detail or example that anchors the explanation
5 — All of 4, plus naturally accessible to a non-technical stakeholder without losing accuracy

Calibration note: A brief answer that correctly names the right concept and mechanism should score at least 3.
Only score 2 if the explanation itself is wrong or confused — not merely short.

Respond in exactly this format (three lines, nothing else):
SCORE: <1|2|3|4|5>
STRENGTH: <one sentence on what was done well>
IMPROVEMENT: <one sentence on the single most important thing to strengthen>"""


def evaluate_answer(question: str, answer: str) -> dict:
    """
    Call Agent B to evaluate a user's answer against the rubric.

    The orchestrator passes both the question and the answer — Agent B
    needs both to judge whether the answer is relevant and accurate.
    This is the information-passing pattern from Quiz 9, Q2.

    Returns a dict with 'score' (int), 'strength' (str), 'improvement' (str).
    """
    client = anthropic.Anthropic()

    user_message = f"""QUESTION:
{question}

ANSWER:
{answer}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    raw = response.content[0].text.strip()

    # ── Parse the structured response ─────────────────────────────────────────
    # Same parsing pattern as the eval judges — look for labelled lines.
    # Safe defaults if parsing fails — better to show something than crash.
    score = 0
    strength = ""
    improvement = ""

    for line in raw.splitlines():
        if line.startswith("SCORE:"):
            raw_score = line.replace("SCORE:", "").strip()
            # Extract just the digit — handles "4/5" or "4" equally
            digits = re.findall(r'\d', raw_score)
            if digits:
                score = int(digits[0])
        elif line.startswith("STRENGTH:"):
            strength = line.replace("STRENGTH:", "").strip()
        elif line.startswith("IMPROVEMENT:"):
            improvement = line.replace("IMPROVEMENT:", "").strip()

    return {
        "score": score,
        "strength": strength,
        "improvement": improvement,
        "raw_response": raw,   # kept for debugging — same pattern as eval judges
    }
