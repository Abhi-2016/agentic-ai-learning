# Agentic AI Learning — Research Synthesizer

> A hands-on learning project built to deeply understand Agentic AI architecture, memory systems, flow types, and evaluation frameworks — from the perspective of an AI Product Manager.

---

## Why This Project Exists

Most AI PM candidates can talk about agents. Few have built one. This project exists to close that gap.

Rather than working through tutorials, I built a production-pattern AI agent from scratch — making the same architectural decisions a real PM would face: how to define the system prompt, how to describe tools so the LLM uses them correctly, how to design stopping conditions, and — most critically — how to evaluate whether the agent is actually working.

This repository documents that learning journey, with every concept earned before the code was written.

---

## What This Agent Does

The **Research Synthesizer** is a single autonomous agent that:

1. Takes any research topic as input
2. Plans its own research strategy (without user intervention)
3. Searches the web for peer-reviewed and credible sources via the Tavily API
4. Reads and evaluates each source for relevance using BeautifulSoup
5. Saves confirmed findings to persistent memory (`scratchpad.json`)
6. Synthesizes a grounded, cited research paper — and stops only when its own stopping criteria are met

It does this in a loop, without human input between steps. That loop is the difference between a chatbot and an agent.

---

## Live Agent Output

Every iteration prints the agent's full reasoning trace — the Thought before every action, and a human-readable description of what it's doing:

```
============================================================
Research Synthesizer — Topic: Impact of AI on social media
============================================================

[Iteration 1/20]
────────────────────────────────────────────────────────────
  💭 Agent Thought:

     I have the topic but no sources yet. My first step should be to
     search for peer-reviewed research on AI's impact on social media.
     Rationale: I need credible sources before I can read or save anything.
     Tool: search_web
     Expected outcome: A list of URLs I can evaluate for relevance.
────────────────────────────────────────────────────────────

  🔍 Searching the web for: "impact of AI on social media peer-reviewed 2024"

  ✅ Result preview: Search results for '...' 1. The Impact of AI on S...

[Iteration 2/20]

  📄 Reading page: https://ijraset.com/research-paper/...

  💾 Saving finding to scratchpad:
     Source: https://ijraset.com/...
     Author: Soni et al. (IJRASET) (2025)
     Finding: AI technologies like machine learning, deep learning...

  Scratchpad: 1/3 sources saved
```

The Thought trace is the agent's audit log — every decision is visible and debuggable.

---

## Architecture

### The ReAct Pattern (Reason + Act)

Every action the agent takes is preceded by a written Thought. This is not optional — it is the mechanism that makes the agent debuggable, auditable, and self-correcting.

```
┌─────────────────────────────────────────────────────┐
│                   REACT LOOP                        │
│                                                     │
│  User Input                                         │
│      │                                              │
│      ▼                                              │
│  ┌─────────┐    💭 Thought (rationale + next action) │
│  │   LLM   │ ──────────────────────────────────►   │
│  │ (Claude)│                                        │
│  └─────────┘ ◄── Observation (tool result)          │
│      │                                              │
│      ▼                                              │
│  Tool Dispatcher                                    │
│  ├── 🔍 search_web       → Tavily Search API        │
│  ├── 📄 read_page_contents → requests + BS4         │
│  └── 💾 save_note        → scratchpad.json          │
│                                                     │
│  Loop continues until stopping condition is met     │
└─────────────────────────────────────────────────────┘
```

### Memory Architecture

Two distinct memory types — a design decision with real tradeoffs:

| Memory Type | Implementation | Scope | Capacity |
|---|---|---|---|
| **Context window** (temporary) | `messages[]` list in Python | Current session only | Limited by model's token limit |
| **Scratchpad** (persistent) | `scratchpad.json` on disk | Survives restarts + sessions | Limited by disk (effectively unlimited) |

The agent saves confirmed findings to the scratchpad. On restart, those findings are still there. The context window forgets everything — the scratchpad does not.

### Tool Architecture

Tools are the agent's hands — how it reaches outside itself to act on the world. Each tool has two parts:

1. **The description** (what the LLM reads to decide when to call it) — a product decision
2. **The function** (what Python executes when called) — an engineering decision

The three tools and their boundaries:

```
🔍 search_web          → Tavily API (discovers sources, returns URLs + snippets)
       │
       ▼ (only if snippet looks promising)
📄 read_page_contents  → requests + BeautifulSoup (reads full page, strips noise,
       │                  truncates to 8000 chars to protect context window)
       ▼ (only if content is relevant and credible)
💾 save_note           → writes confirmed finding to scratchpad.json
```

Critically, each tool description explicitly states **when NOT to use it**. Without this, the LLM defaults to the most familiar tool for every task.

---

## Key Concepts Demonstrated

### 1. System Prompt as a Product Spec
The system prompt is the agent's job description, operating constraints, and uncertainty-handling playbook — all in one. Written by hand (not generated) to force real architectural decisions:
- Specific, measurable stopping condition (3 sources + structured paper ≤ 1000 words)
- Explicit tool boundaries (when to use each, and when not to)
- Defined behaviour for 5 distinct failure modes
- Mandatory reasoning step (Thought) before every action

### 2. The Stopping Problem
When does an agent know it's done? This is one of the hardest unsolved problems in agentic AI. This agent implements two-layer stopping:
- The LLM decides it's done (self-report via `end_turn`)
- The system *verifies* against the scratchpad (ground truth check)

If the LLM stops early, it gets sent back. Trust but verify.

### 3. Thought Traces as Audit Logs
Every action is preceded by a printed Thought showing rationale, chosen tool, and expected outcome. This is the ReAct pattern made visible. In production, this trace is how you debug failures — without it, you're flying blind.

### 4. Flow Types
| Flow | Where It Appears |
|---|---|
| **Sequential** | Search → Read → Save → Synthesise |
| **Conditional** | Only read a URL if the snippet looks relevant |
| **Loop** | Keep searching until 3 sources are saved |
| **Parallel** | (Week 2) Fan-out to multiple sources simultaneously |

### 5. Evals (Week 2 — in progress)
Four evaluation dimensions, each taught before built:

| Eval | What It Measures | Method |
|---|---|---|
| **Grounding** | Does every claim have a traceable source? | Rule-based (citation check) |
| **Factuality** | Are the claims actually true? | LLM-as-judge against ground truth |
| **Completeness** | Did it cover all required sections? | Rubric-based scoring |
| **Efficiency** | Quality per tool call | Ratio metric |

**The key PM insight:** Grounding and factuality are not the same thing. An agent can cite a source that is itself wrong. Attribution ≠ truth. This distinction shapes every production deployment decision.

---

## Project Structure

```
research-synthesizer/
├── agent.py              # The ReAct loop — the heart of the agent
├── tools.py              # Tool schemas (LLM-facing) + live execution functions
├── system_prompt.txt     # The agent's operating instructions (written by hand, not generated)
├── scratchpad.json       # Persistent memory — survives restarts
├── requirements.txt      # anthropic, requests, beautifulsoup4, python-dotenv
├── .env.example          # API key template — copy to .env and fill in values
└── evals/
    ├── eval_grounding.py   # ✅ Eval 1: rule-based citation checker
    ├── eval_factuality.py  # ✅ Eval 2: LLM-as-judge + --human-review calibration
    ├── eval_completeness.py  # ⏳ Eval 3: rubric-based (coming soon)
    └── eval_efficiency.py    # ⏳ Eval 4: quality per tool call (coming soon)
```

---

## How to Run

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set API keys — copy the template and fill in your keys
cp .env.example .env
# Edit .env and add your keys (never committed — gitignored automatically)
# ANTHROPIC_API_KEY=...
# TAVILY_API_KEY=...     # Free tier at app.tavily.com

# 4. Run the agent
python agent.py "Impact of AI on healthcare" > last_paper.txt
```

Watch the terminal — every iteration shows the agent's Thought, the tool it chose, and the result. The scratchpad count climbs to 3, then the paper is written.

### Run the Eval Suite

```bash
# Eval 1: Grounding — does every claim have a citation?
python evals/eval_grounding.py

# Eval 2: Factuality — do claims accurately represent their sources?
python evals/eval_factuality.py

# Eval 2 with human calibration spot-check
python evals/eval_factuality.py --human-review
```

---

## Learning Roadmap

This project is being built incrementally, with each concept quizzed and understood before the code is written.

### Week 1 — Agent Foundations ✅
- [x] Chatbot vs. agent distinction
- [x] System prompt design (goal, tools, uncertainty handling)
- [x] Tool description quality (what, when, when NOT to use)
- [x] ReAct pattern (Thought → Action → Observation loop)
- [x] Memory types (context window vs. persistent scratchpad)
- [x] ReAct scaffold + tool dispatcher built
- [x] Live tool wiring (Tavily search + BeautifulSoup scraper)
- [x] Agent Thought traces surfaced in terminal output
- [x] Agent verified working end-to-end ✅

### Week 2 — Evals 🔄
- [x] Grounding eval (rule-based citation checker) ✅
- [x] Factuality eval (LLM-as-judge + human calibration) ✅
- [ ] Completeness eval (rubric-based)
- [ ] Efficiency eval (quality per tool call)

### Week 3 — Agent 2: Multi-Agent PM Interview Coach
- [ ] Multi-agent architecture (Orchestrator + Questioner + Evaluator)
- [ ] Persistent memory across sessions
- [ ] Inter-agent handoff protocol design
- [ ] Conditional routing + feedback loops

### Week 4 — Meta-Evals + Agent Design Doc
- [ ] Evaluating the evaluator (calibration + consistency)
- [ ] Orchestrator accuracy testing
- [ ] Agent Design Doc (PRD equivalent for agents)
- [ ] End-to-end interview story

---

## Git Workflow

Every feature is developed on a branch, reviewed as a PR, and merged only after explicit approval:

```
main (stable — always working)
  └── feature/<name>
        └── commit, commit
              └── PR → review → approved → merge
```

| PR | Branch | What It Delivered |
|---|---|---|
| #1 | `feature/wire-real-tools` | Live Tavily + BeautifulSoup implementations |
| #2 | `feature/richer-agent-logging` | Agent Thought traces + human-readable action logs |
| #4 | `feature/week2-eval-factuality` | Eval 2 (factuality) + .env setup via python-dotenv |

---

## Technical Stack

| Component | Technology | Why |
|---|---|---|
| LLM | Claude (Anthropic) | Native tool use, strong reasoning, transparent Thought traces |
| Web search | Tavily API | Purpose-built for LLM agents, structured results, free tier |
| Page reading | requests + BeautifulSoup | No JS rendering needed for research papers; lightweight |
| Persistent memory | `scratchpad.json` | Simple, inspectable, no infrastructure — open it and read it |
| Language | Python 3.9+ | Standard for AI/ML tooling |

---

## About This Project

Built as part of a structured AI PM learning curriculum, mentored by an experienced PM who worked on Claude Code at Anthropic. Every concept was earned through quizzes before any code was written — because understanding why something is built the way it is matters more than being able to copy it.

This is not a tutorial project. It is a learning artefact.

---

*Author: Abhishek Venkatesh*
*Co-authored with Claude (Anthropic)*
