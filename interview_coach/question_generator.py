"""
question_generator.py — Agent A: Question Generator

WHAT THIS AGENT DOES:
  Given a topic, generates exactly one focused interview question on that topic.
  This is Agent A in the multi-agent PM Interview Coach system.

WHY IT'S A SEPARATE AGENT (not part of the orchestrator):
  Single responsibility — this agent has one job and one system prompt.
  If question quality degrades, you know exactly where to fix it.
  If you want to swap to a stronger model for harder topics, you change one file.

HOW IT WORKS:
  One Haiku call. No tools. No loop. No memory.
  Input: topic string
  Output: question string

  This is the simplest possible agent — a single LLM call with a focused
  system prompt. Stateless: call it, get a question, done.
"""

import anthropic
from pathlib import Path
from dotenv import load_dotenv

# override=True: use .env even if ANTHROPIC_API_KEY is already set as empty string
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Haiku is sufficient — generating a structured question is not a reasoning-heavy task.
# Save Sonnet for tasks that require deeper judgement (e.g. evaluating nuanced answers).
MODEL = "claude-haiku-4-5-20251001"

# ── Agent A system prompt ──────────────────────────────────────────────────────
# Narrow brief: one question, no preamble, no follow-ups.
# The question should test genuine understanding — not just definitions.
# "Answerable in 2-4 sentences" keeps the interview loop tight.
SYSTEM_PROMPT = """You are an AI interviewer specialising in agentic AI systems.

Your job: generate exactly ONE sharp, focused interview question on the topic provided.

Rules:
- One question only — no preamble, no follow-up questions, no explanation
- The question should test genuine understanding, not just the ability to recall a definition
- The question should be answerable in 2-4 sentences by someone who has built an agent
- Write in plain English — no academic or overly technical framing
- Output the question and nothing else"""


def generate_question(topic: str) -> str:
    """
    Call Agent A to generate one interview question on the given topic.

    This is a single, stateless LLM call — no context window carried over
    from previous calls. Each question is generated fresh.

    Returns the question as a plain string.
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=200,           # questions are short — 200 tokens is generous
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Generate an interview question on: {topic}"}
        ]
    )

    # Extract the text from the response
    # No tool calls here — Agent A only produces text
    return response.content[0].text.strip()
