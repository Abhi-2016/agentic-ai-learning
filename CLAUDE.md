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

## Git Workflow (must follow every session)

1. **Branch first** — `git checkout -b feature/<name>` before any new code
2. **Commit on the branch** — never commit directly to `main`
3. **Push + open PR** — `git push -u origin feature/<name>` then `gh pr create`
4. **Share PR link and STOP** — wait for Abhishek's explicit approval
5. **Merge only on approval** — `gh pr merge <number> --merge --delete-branch`

Branch naming: `feature/week2-evals`, `feature/week3-multi-agent`, `feature/week4-meta-evals`

---

## Current State

### What's Built and Working (Week 1 ✅)

**Agent is verified working end-to-end.** Tested on "Impact of AI on social media" — completed 3 sources, saved to scratchpad, produced paper.

| File | Status | Notes |
|---|---|---|
| `system_prompt.txt` | ✅ Live | Written by Abhishek — goal, stopping condition, ReAct reasoning, tools, 5 uncertainty modes |
| `tools.py` | ✅ Live | All 3 tools fully wired — no stubs remaining |
| `agent.py` | ✅ Live | ReAct loop + Thought trace logging + trust-but-verify stopping |
| `scratchpad.json` | ✅ Live | Persistent memory — contains results from last run |

### Tools — All Live (no stubs)
| Tool | Implementation | Returns |
|---|---|---|
| `search_web` | Tavily API via `requests.post` to `api.tavily.com/search` | Formatted list of URLs + snippets |
| `read_page_contents` | `requests.get` + BeautifulSoup, noise-stripped, truncated to 8000 chars | Clean page text |
| `save_note` | Writes to `scratchpad.json` | Boolean success |

### Environment Setup
```bash
cd ~/Documents/research-synthesizer
source .venv/bin/activate    # venv lives at .venv/ — already created
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export TAVILY_API_KEY=...     # free at app.tavily.com
python agent.py "your topic"
```

### What's Next (Week 2 — Evals)
Four evals to build, each gated by a quiz:
1. **Grounding eval** — does every claim have a traceable citation? (rule-based)
2. **Factuality eval** — are the claims true? (LLM-as-judge)
3. **Completeness eval** — did it cover all required sections? (rubric-based)
4. **Efficiency eval** — quality per tool call (ratio metric)

Evals go in an `evals/` directory. Branch: `feature/week2-evals`.

---

## Architecture

### Agent Loop (`agent.py`)
```
User input
    → messages[] (context window / temporary memory)
    → LLM call (claude-opus-4-6, with TOOLS schema)
    → stop_reason == "tool_use"
        → print 💭 Thought (text blocks before tool_use)
        → print human-readable action (🔍 / 📄 / 💾)
        → dispatch_tool() → execute → append observation → loop
    → stop_reason == "end_turn"
        → verify scratchpad count ≥ 3
        → if yes: return final paper
        → if no: send agent back with explicit instruction
```

### Memory
| Type | Location | Persistence |
|---|---|---|
| Context window | `messages[]` list in Python | Session only — wiped on restart |
| Scratchpad | `scratchpad.json` | Permanent — survives restarts |

### Output Format (what the terminal looks like)
```
[Iteration N/20]
────────────────────────────────────────────────
  💭 Agent Thought:
     <full reasoning block from LLM>
────────────────────────────────────────────────

  🔍 Searching the web for: "<query>"
  ✅ Result preview: ...

  📄 Reading page: https://...
  ✅ Result preview: ...

  💾 Saving finding to scratchpad:
     Source: https://...
     Author: ... (year)
     Finding: ...

  Scratchpad: N/3 sources saved
```

---

## File Map

```
research-synthesizer/
├── agent.py            # ReAct loop — READ THIS FIRST to understand the architecture
├── tools.py            # Tool schemas (LLM-facing) + live execution functions
├── system_prompt.txt   # Agent's operating instructions — written by Abhishek
├── scratchpad.json     # Persistent memory store — contains findings from last run
├── requirements.txt    # anthropic, requests, beautifulsoup4
├── .venv/              # Python virtual environment (gitignored)
├── README.md           # Public-facing project showcase
└── CLAUDE.md           # This file — internal context for Claude Code
```

---

## Key Design Decisions (and Why)

### Why the system prompt is a `.txt` file, not hardcoded
Abhishek wrote this prompt himself as a learning exercise (not generated). Keeping it as a separate file means it can be iterated on without touching Python — the same way a PM would own the prompt without owning the engineering.

### Why `scratchpad.json` instead of a vector DB
Simplicity and inspectability. At this stage of learning, being able to open `scratchpad.json` and read exactly what the agent saved matters more than retrieval performance. A vector DB is Week 3+ territory.

### Why Tavily via `requests` not the Tavily SDK
Transparency. Direct HTTP calls make the API contract explicit — you can see exactly what's sent and returned. SDK abstractions hide this, which is the opposite of what a learning project needs.

### Why truncate `read_page_contents` to 8000 chars
Full pages can be 50,000–200,000 characters. Feeding that raw into the context window consumes most of the agent's token budget on a single page. 8000 chars (~2000 tokens) is enough to evaluate relevance and extract key findings.

### Why `MAX_ITERATIONS = 20`
Hard ceiling to prevent runaway loops during development. The agent completed its first real run in ~6 iterations.

### Why the agent gets sent back if it stops early
The stopping condition in `agent.py` verifies the scratchpad independently of the LLM's self-report. LLMs can become overconfident and stop early — the system catches it. This is the "trust but verify" pattern.

---

## Conventions for This Project

- **Quiz before code**: If resuming and a new concept is up next, quiz Abhishek before writing anything
- **Branch + PR for every feature**: No direct commits to main
- **Wait for explicit approval**: Never merge without Abhishek saying "merge PR X"
- **Comments are teaching tools**: Every non-trivial line has a comment mapping to a concept — preserve this
- **Plan file is source of truth**: `~/.claude/plans/graceful-seeking-lecun.md`
- **Evals go in `evals/`**: One file per eval, named `eval_<name>.py`
- **No generated system prompts**: `system_prompt.txt` is always written/edited by Abhishek

---

## Learning Progress Tracker

| Week | Focus | Status |
|---|---|---|
| 1 | Agent foundations (ReAct, tools, memory, logging) | ✅ Complete |
| 2 | Evals (grounding, factuality, completeness, efficiency) | 🔄 Next |
| 3 | Agent 2: Multi-agent PM Interview Coach | ⏳ Pending |
| 4 | Meta-evals + Agent Design Doc + interview story | ⏳ Pending |

**Quizzes passed:**
- Quiz 0: Chatbot vs. agent ✅
- Quiz 1: System prompt design ✅
- Quiz 2: Tool description quality ✅
- Quiz 3: ReAct pattern ✅
- Quiz 4: Memory types ✅

**Merged PRs:**
- PR #1: `feature/wire-real-tools` — live Tavily + BeautifulSoup ✅
- PR #2: `feature/richer-agent-logging` — Thought traces + human-readable logs ✅
