"""
agent.py — The ReAct loop for the Research Synthesizer.

This is the heart of Agent 1. Every line maps to a concept you've learned:

  - The `while` loop        → the agentic loop (Perception → Reasoning → Action → Observation)
  - `messages`              → the context window (Quiz 4: temporary memory, gone on restart)
  - `dispatch_tool()`       → tool use (Quiz 2: description shapes behavior, function executes it)
  - `scratchpad.json`       → persistent memory (Quiz 4: survives restarts)
  - Thought in the output   → ReAct reasoning (Quiz 3: rationale before every action)
  - `get_saved_notes()`     → stopping condition check (Quiz 1: done when 3 notes saved)

Run with:
  python agent.py "Impact of AI on healthcare"
"""

import anthropic
import json
import sys
from pathlib import Path

from tools import TOOLS, dispatch_tool, get_saved_notes, clear_scratchpad

# ── Config ───────────────────────────────────────────────────────────────────

MODEL = "claude-opus-4-6"          # The LLM powering the agent
MAX_ITERATIONS = 20                 # Safety ceiling — prevents infinite loops
REQUIRED_SOURCES = 3                # Stopping condition from your system prompt


def load_system_prompt() -> str:
    """Reads your system prompt from system_prompt.txt."""
    path = Path(__file__).parent / "system_prompt.txt"
    return path.read_text()


# ── The ReAct loop ────────────────────────────────────────────────────────────

def run_agent(topic: str) -> str:
    """
    Runs the Research Synthesizer agent on a given topic.
    Returns the final research paper as a string.

    The loop structure:
      1. Send messages to the LLM (context window)
      2. LLM either: (a) calls a tool, or (b) produces final text
      3. If tool call → execute it, append result to context, loop again
      4. If final text → check stopping condition, return if met
    """

    client = anthropic.Anthropic()
    system_prompt = load_system_prompt()

    # ── Context window (temporary memory) ────────────────────────────────────
    # This list IS the agent's short-term memory.
    # Every Thought, Action, and Observation gets appended here.
    # It grows with each iteration. If the topic is complex, it can get long.
    messages = [
        {
            "role": "user",
            "content": f"Please research and write a paper on: {topic}"
        }
    ]

    print(f"\n{'='*60}")
    print(f"Research Synthesizer — Topic: {topic}")
    print(f"{'='*60}\n")

    # ── Main agentic loop ─────────────────────────────────────────────────────
    # This loop is the difference between a chatbot and an agent.
    # A chatbot sends one message, gets one reply, done.
    # An agent keeps looping until it decides it's done.
    for iteration in range(MAX_ITERATIONS):

        print(f"[Iteration {iteration + 1}/{MAX_ITERATIONS}]")

        # ── Step 1: Send context window to the LLM ───────────────────────────
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,           # The LLM sees tool descriptions — not the functions
            messages=messages
        )

        print(f"Stop reason: {response.stop_reason}")

        # ── Step 2: Process the LLM's response ───────────────────────────────
        # The LLM can respond in two ways:
        #   (a) stop_reason="tool_use" → it wants to call a tool
        #   (b) stop_reason="end_turn" → it's done reasoning, producing text

        # Append LLM response to context window (it needs to see its own output
        # in subsequent turns — that's how the Thought trace builds up)
        messages.append({"role": "assistant", "content": response.content})

        # ── Path A: Tool call ─────────────────────────────────────────────────
        if response.stop_reason == "tool_use":

            # The LLM may request multiple tool calls in one turn
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":

                    tool_name = block.name
                    tool_input = block.input

                    print(f"\n  → Tool call: {tool_name}")
                    print(f"    Input: {json.dumps(tool_input, indent=6)}")

                    # ── Execute the tool (calls tools.py dispatch_tool) ───────
                    result = dispatch_tool(tool_name, tool_input)

                    print(f"    Result preview: {str(result)[:120]}...")

                    # ── Append Observation to context window ──────────────────
                    # This is the "O" in ReAct: Reason → Act → Observe → (loop)
                    # The LLM will read this result in the next iteration.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)
                    })

            # Add all tool results as a single user turn
            messages.append({"role": "user", "content": tool_results})

            # ── Check scratchpad (stopping condition) ─────────────────────────
            # After every save_note call, check if we've hit 3 confirmed sources.
            # This is the stopping condition from your system prompt.
            saved_notes = get_saved_notes()
            print(f"\n  Scratchpad: {len(saved_notes)}/{REQUIRED_SOURCES} sources saved")

            # Loop continues — agent will reason about what to do next

        # ── Path B: Final answer ──────────────────────────────────────────────
        elif response.stop_reason == "end_turn":

            # Extract the text content from the response
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            # ── Hard stopping condition check ─────────────────────────────────
            # Even if the agent says it's done, we verify the scratchpad.
            # This is the difference between trusting the agent's self-report
            # and verifying against ground truth. In production, you'd always verify.
            saved_notes = get_saved_notes()

            if len(saved_notes) >= REQUIRED_SOURCES:
                print(f"\n{'='*60}")
                print("Stopping condition met. Final paper below.")
                print(f"{'='*60}\n")
                return final_text
            else:
                # Agent said it was done but didn't meet the stopping condition.
                # This is a common failure mode — the agent gets overconfident.
                # We send it back to keep researching.
                print(f"\n  [Warning] Agent tried to stop with only {len(saved_notes)} sources.")
                print(f"  Sending back to find more sources...\n")

                messages.append({
                    "role": "user",
                    "content": (
                        f"You have only saved {len(saved_notes)} source(s) to your scratchpad, "
                        f"but the stopping condition requires {REQUIRED_SOURCES}. "
                        "Please continue researching before writing the final paper."
                    )
                })

        else:
            # Unexpected stop reason — surface it for debugging
            print(f"[Unexpected stop reason: {response.stop_reason}]")
            break

    # If we exit the loop without returning, we hit the iteration ceiling
    return (
        f"[Agent reached max iterations ({MAX_ITERATIONS}) without completing the task. "
        f"Saved {len(get_saved_notes())} of {REQUIRED_SOURCES} required sources. "
        "Try a more specific topic or increase MAX_ITERATIONS.]"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py \"<research topic>\"")
        print("Example: python agent.py \"Impact of AI on healthcare\"")
        sys.exit(1)

    topic = " ".join(sys.argv[1:])

    # Clear scratchpad for a fresh session
    # Remove this line if you want notes to carry over from a previous run
    clear_scratchpad()

    result = run_agent(topic)
    print(result)
