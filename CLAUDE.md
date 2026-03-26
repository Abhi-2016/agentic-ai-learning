# CLAUDE.md — Research Synthesizer

This file gives Claude Code full context on the project so every session picks up exactly where the last one left off.

---

## Project Purpose

This is an **AI learning project** built by Abhishek Venkatesh, with Claude as co-author and mentor. The goal is to learn Agentic AI deeply enough to speak credibly as an AI PM — covering architecture, memory systems, flow types, and evaluation frameworks.

**This is not a production app.** It is a structured learning artefact. Every piece of code maps to a concept that was quizzed and understood before it was written.

---

## How This Project Is Built (The Teaching Contract)

Every concept follows this rhythm — no exceptions:
1. Claude explains the concept
2. Claude asks a quiz question
3. Abhishek answers
4. Claude gives feedback (right / partially right / wrong + why)
5. Then the code gets written

**No code is written until the quiz is passed.** This is non-negotiable and must be maintained across all sessions.

The learning progress is tracked in:
`~/.claude/plans/graceful-seeking-lecun.md`

Always read that file at the start of a new session to know where we are.

---

## Current State

### What's Built (Week 1 ✅)
- `system_prompt.txt` — written by Abhishek (not generated), covers: goal, stopping condition, ReAct reasoning step, tool definitions, uncertainty handling
- `tools.py` — three tools with full schemas + stub execution functions + `dispatch_tool()` router
- `agent.py` — the ReAct loop: context window management, tool dispatch, scratchpad verification, stopping condition enforcement
- `scratchpad.json` — persistent memory (empty, ready for use)

### What's Next (Week 2 — Evals)
Four evals to build, each gated by a quiz:
1. **Grounding eval** — does every claim have a traceable citation? (rule-based)
2. **Factuality eval** — are the claims true? (LLM-as-judge)
3. **Completeness eval** — did it cover all required sections? (rubric-based)
4. **Efficiency eval** — quality per tool call (ratio metric)

Evals go in an `evals/` directory.

---

## Architecture

### Agent Loop (`agent.py`)
```
User input
    → messages[] (context window / temporary memory)
    → LLM call (claude-opus-4-6, with TOOLS schema)
    → stop_reason == "tool_use"  → dispatch_tool() → append observation → loop
    → stop_reason == "end_turn"  → verify scratchpad count → return paper OR send back
```

### Memory
| Type | Location | Persistence |
|---|---|---|
| Context window | `messages[]` list in Python | Session only — wiped on restart |
| Scratchpad | `scratchpad.json` | Permanent — survives restarts |

### Tools (`tools.py`)
| Tool | Purpose | Returns |
|---|---|---|
| `search_web` | Discover sources | List of URLs + snippets (STUB — needs Tavily) |
| `read_page_contents` | Read full URL content | Full page text (STUB — needs scraper) |
| `save_note` | Save finding to scratchpad | Boolean (REAL — writes to disk) |

**The stubs are intentional.** `save_note` is fully functional. `search_web` and `read_page_contents` need real API wiring before the agent runs live.

### To wire live search (Tavily):
```python
# In tools.py → execute_search_web():
from tavily import TavilyClient
client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
results = client.search(query)
return json.dumps(results["results"])
```

---

## File Map

```
research-synthesizer/
├── agent.py            # ReAct loop — READ THIS FIRST to understand the architecture
├── tools.py            # Tool schemas (LLM-facing) + dispatcher + execution stubs
├── system_prompt.txt   # Agent's operating instructions — written by Abhishek
├── scratchpad.json     # Persistent memory store — do not delete between sessions
├── requirements.txt    # anthropic>=0.40.0
├── README.md           # Public-facing project showcase
└── CLAUDE.md           # This file — internal context for Claude Code
```

---

## Key Design Decisions (and Why)

### Why the system prompt is a `.txt` file, not hardcoded in `agent.py`
Abhishek wrote this prompt himself as a learning exercise (not generated). Keeping it as a separate file means it can be iterated on without touching Python code — the same way a PM would own the prompt without owning the engineering.

### Why `scratchpad.json` instead of a vector DB
Simplicity and inspectability. At this stage of learning, being able to `cat scratchpad.json` and see exactly what the agent saved matters more than retrieval performance. A vector DB is Week 3+ territory.

### Why stubs for search and scraper
The ReAct loop, tool dispatch, and memory architecture are the learning targets for Week 1 — not API integration. Stubs let the loop be tested structurally without needing API keys. They are clearly marked with `# TODO` comments.

### Why `MAX_ITERATIONS = 20`
Hard ceiling to prevent runaway loops during development. In production this would be configurable per-use-case. The value is intentionally conservative.

### Why the agent gets sent back if it stops early
The stopping condition in `agent.py` verifies the scratchpad independently of the LLM's self-report. This is the "trust but verify" pattern. LLMs can become overconfident and stop early — the system catches it.

---

## Running the Agent

```bash
# Install
pip install -r requirements.txt
pip install tavily-python  # for live search

# Set keys
export ANTHROPIC_API_KEY=your_key
export TAVILY_API_KEY=your_key  # optional until stubs are wired

# Run
python agent.py "Impact of AI on climate change"
```

Expected output per iteration:
```
[Iteration 1/20]
Stop reason: tool_use
  → Tool call: search_web
    Input: {"query": "AI impact climate change peer reviewed 2024"}
    Result preview: [STUB] search_web called with query...
  Scratchpad: 0/3 sources saved
```

---

## Conventions for This Project

- **Quiz before code**: If resuming and a new concept is up next, quiz Abhishek before writing anything
- **Comments are teaching tools**: Every non-trivial line in `agent.py` and `tools.py` has a comment that maps to a concept. Preserve this when editing.
- **Stubs stay stubs** until Abhishek explicitly asks to wire them live
- **Plan file is the source of truth** for learning progress: `~/.claude/plans/graceful-seeking-lecun.md`
- **Evals go in `evals/`** — one file per eval, named `eval_<name>.py`
- **No generated system prompts** — `system_prompt.txt` is always written/edited by Abhishek

---

## Learning Progress Tracker

| Week | Focus | Status |
|---|---|---|
| 1 | Agent foundations (ReAct, tools, memory) | ✅ Complete |
| 2 | Evals (grounding, factuality, completeness, efficiency) | 🔄 Next |
| 3 | Agent 2: Multi-agent PM Interview Coach | ⏳ Pending |
| 4 | Meta-evals + Agent Design Doc + interview story | ⏳ Pending |

Quizzes passed: 0 (chatbot vs agent), 1 (system prompt), 2 (tool descriptions), 3 (ReAct pattern), 4 (memory types)
