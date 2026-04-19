# Agentic AI Learning — Research Synthesizer

> A hands-on learning project built to deeply understand Agentic AI architecture, memory systems, flow types, and evaluation frameworks — from the perspective of an AI Product Manager.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Powered%20by-Claude%20Sonnet-D97706?logoColor=white)
![Tavily](https://img.shields.io/badge/Search-Tavily%20API-10B981?logoColor=white)
![PRs Merged](https://img.shields.io/badge/PRs%20Merged-20-brightgreen)
![Evals](https://img.shields.io/badge/Evals-4%20of%204%20Built-3B82F6?logoColor=white)
![Week](https://img.shields.io/badge/Week-3B%20Complete-8B5CF6?logoColor=white)

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
The system prompt is the agent's job description, operating constraints, and uncertainty-handling playbook — all in one. Written by hand (not generated) to force real architectural decisions.

**Ground rule — system prompts are always written by Abhishek first.** Claude reviews, suggests improvements, and flags gaps — but never generates a system prompt from scratch. Writing it yourself forces the architectural decisions that matter: what is the agent's goal, what are its boundaries, how does it handle failure? Reading someone else's prompt (or a generated one) skips exactly the thinking a PM needs to do.
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

### 5. Evals (Week 2 — Complete ✅)
Four evaluation dimensions, each taught before built:

| Eval | What It Measures | Method | Status |
|---|---|---|---|
| **Grounding** | Does every claim have a traceable source? | Rule-based (citation check) | ✅ |
| **Factuality** | Are the claims accurately represented from their sources? | LLM-as-judge against scratchpad ground truth | ✅ |
| **Completeness** | Does the paper cover the topic, have good structure, and use 3 strong sources? | Rubric-based scoring (3 independent judge calls) | ✅ |
| **Efficiency** | Quality per tool call | Composite quality / (external calls / baseline) | ✅ |

**The key PM insights:**
- **Attribution ≠ truth**: Grounding checks that a URL is present. Factuality checks what's actually said near that URL. An agent can be fully grounded and still misrepresent its sources.
- **Synthesis vs. attribution**: Attribution is the model repeating source language — low risk, eval-verifiable. Synthesis is the model connecting ideas to form new claims — higher risk, unverifiable against any single source. Fluent, eloquent writing requires synthesis. Every "taken together, these findings suggest..." is a claim no scratchpad entry contains. As a PM, you must deliberately decide how much synthesis you authorise — and use the factuality eval to measure where you actually land.

### 6. Multi-Agent Architecture (Week 3 — Complete ✅)

**Agent 2: PM Interview Coach** — a three-component multi-agent system:

```
coach.py (Orchestrator)
    ├── Reads CLAUDE.md → extracts learner context (quizzes passed, study scope)
    ├── Agent A: question_generator.py → one calibrated Haiku call per question
    ├── Agent B: evaluator.py → one Haiku call to score + give feedback
    └── Writes all session history to coach_history.json
```

**Key architectural decisions made:**
- **Python router, not LLM orchestrator** — the flow is fixed (question → answer → evaluate → save), so Python logic handles routing. No LLM reasoning needed for a deterministic sequence.
- **Separate context windows** — Agent A and Agent B are independent, stateless Haiku calls. Neither knows the other exists.
- **Orchestrator owns all context** — Agent A does not read files itself. The orchestrator reads CLAUDE.md once at startup and passes the relevant section as a parameter. This makes context ownership inspectable and debuggable.
- **Evaluator rubric is calibrated, not just defined** — calibration notes prevent the LLM judge from defaulting to the harshest reading of ambiguous boundaries. Brief ≠ wrong. Complete ≠ perfect.

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
├── evals/
│   ├── eval_grounding.py      # ✅ Eval 1: rule-based citation checker
│   ├── eval_factuality.py     # ✅ Eval 2: LLM-as-judge + --human-review calibration
│   ├── eval_completeness.py   # ✅ Eval 3: rubric-based section + coverage check
│   └── eval_efficiency.py     # ✅ Eval 4: composite quality / (external calls / baseline)
└── interview_coach/
    ├── coach.py               # ✅ Orchestrator — Python router, owns all state
    ├── question_generator.py  # ✅ Agent A — calibrated question generator (Haiku)
    └── evaluator.py           # ✅ Agent B — 1–5 answer scorer with feedback (Haiku)
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
# Run all 4 evals in one command (recommended)
python evals/eval_efficiency.py

# Or run individually:
python evals/eval_grounding.py      # Eval 1: citation coverage
python evals/eval_factuality.py     # Eval 2: LLM-as-judge
python evals/eval_factuality.py --human-review  # Eval 2 with human calibration
python evals/eval_completeness.py   # Eval 3: rubric-based coverage
python evals/eval_efficiency.py     # Eval 4: quality per tool call (runs 1–3 internally)
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

### Week 2 — Evals ✅
- [x] Grounding eval (rule-based citation checker) ✅
- [x] Factuality eval (LLM-as-judge + human calibration) ✅
- [x] Completeness eval (rubric-based, 3-criterion, 3 independent Haiku judge calls) ✅
- [x] Efficiency eval (composite quality / external call ratio, PM dashboard metric) ✅

### Week 3 — Agent 2: Multi-Agent PM Interview Coach ✅
- [x] Multi-agent architecture (Orchestrator + Agent A + Agent B)
- [x] Persistent memory across sessions (coach_history.json)
- [x] Orchestrator-owned context injection (CLAUDE.md → Agent A)
- [x] Evaluator rubric design + iterative calibration (3 sessions)
- [x] Python router orchestration

### Week 3B — LLM Orchestrator with Dynamic Routing ✅

**The key insight:** Python routes by rules. An LLM orchestrator routes by reasoning.

**Architecture:**
```
Orchestrator (Claude) reads history + context → decides next action
    ├── "ask_on_topic: X"  → Agent A → question
    ├── "suggest_topic"    → Agent C (pattern analyser) → Agent A → question
    └── "end_session"      → summary → exit
```

**Four agents, clear scope boundaries:**

| Agent | Role | Input | Output |
|---|---|---|---|
| Orchestrator | Session manager | History + learner context | action, topic, reason |
| Agent A | Question generator | Topic + context | One question |
| Agent B | Answer evaluator | Question + answer | Score + feedback |
| Agent C | Pattern analyser | Full all-time history | Suggested topic + reason |

**Python router vs. LLM orchestrator:**

| Dimension | Python router | LLM orchestrator |
|---|---|---|
| Latency | ~0ms | 300–800ms per routing decision |
| Cost | Free | One Haiku call per turn |
| Failure mode | Predictable — wrong `if/else` branch | Unpredictable — bad reasoning on context |
| Debugging | Read the code | Read the reasoning trace |
| Fix | Change the condition | Change the system prompt |

- [x] Quiz: Python router vs. LLM orchestrator — when to use each ✅
- [x] Build: `topic_suggester.py` — Agent C ✅
- [x] Build: LLM orchestrator in `coach.py` ✅
- [x] Evaluator rubric scores 4–5 rewritten by Abhishek in behaviour-based language ✅

### Week 4 — Meta-Evals + Agent Design Doc ⏳
- [ ] Evaluator calibration: does Agent B's score match a human's?
- [ ] Evaluator consistency: same answer → same score twice?
- [ ] Orchestrator accuracy: does it route to the right agent?
- [ ] Agent Design Doc (PRD equivalent for agents)
- [ ] End-to-end interview story

### Week 5 — MCP: The New Integration Standard (and Its Limits) ⏳
Model Context Protocol — Anthropic's open standard for connecting agents to tools. Becoming the "USB-C for agent tools" as major SaaS providers publish MCP servers. But it comes with a real tradeoff: loading a large tool catalogue burns thousands of tokens before the agent does anything useful, and model performance degrades with 50+ tools in context.
- [ ] What MCP is and why it matters as a product governance decision
- [ ] The token problem: tool sprawl and context cost
- [ ] Mitigation approaches: tool filtering, namespacing, A2A delegation, minimal tool sets
- [ ] Add MCP-connected tools to Research Synthesizer; measure token cost vs. custom tools
- [ ] Tool call accuracy as a new eval dimension

### Week 6 — Production Reliability & Trajectory Evals ⏳
The "reliability cliff" — agents that pass testing degrade in production. Output evals catch wrong answers; trajectory evals catch wrong reasoning paths.
- [ ] Trajectory evaluation vs. output evaluation
- [ ] What to instrument: every agent call logged with inputs, outputs, latency, cost
- [ ] Build trajectory evaluator for the PM Interview Coach
- [ ] Evals as a CI/CD gate: failing evals = bugs, not warnings

### Week 7 — Agent Economics & Async Product Design ⏳
How do you design a product around something that costs money, takes minutes, and sometimes fails mid-task?
- [ ] Cost per task modeling (not per token) — the PM unit that matters at scale
- [ ] Latency UX patterns: async execution, progress indicators, partial results, cancellation
- [ ] Human-in-the-loop as deliberate product design — not a fallback
- [ ] Add cost tracker to Research Synthesizer; add human approval checkpoint to Interview Coach

### Week 8 — Enterprise Safety & Governance ⏳
What breaks when agents go to production at scale — and what does a PM own in that?
- [ ] Prompt injection: the new CSRF — malicious tool results that hijack agent behaviour
- [ ] Agent scope definition: permissions, boundaries, guardrails
- [ ] Data governance: what can an agent read/write, and under what conditions?
- [ ] Write an Agent Specification doc for the Research Synthesizer as an enterprise deployment

### Week 9 — Beyond MCP: Tool Access Alternatives ⏳
MCP is not the only answer. Understanding the alternatives is what separates a PM who evaluates vendor claims from one who follows trends.

| Alternative | When it wins over MCP |
|---|---|
| Direct API integration | Stable, well-documented APIs; small tool sets |
| A2A (Agent-to-Agent) | Large tool catalogues; keeps tools out of orchestrator context |
| RAG over tool descriptions | Solves token problem without A2A overhead; adds retrieval latency |
| Workflow engines (n8n, Zapier) | Fixed flows that don't require LLM reasoning to pick tools |

- [ ] The PM decision framework: how many tools, how stable, who owns them, what's the token budget?
- [ ] Replace one MCP tool with a direct API integration; measure the token difference
- [ ] Implement RAG-over-tools: embed tool descriptions, retrieve top-3 at query time

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
| #5 | `feature/week2-verbatim-system-prompt-eval-fix` | Verbatim system prompt rule + eval multi-source grouping fix |
| #6 | `feature/week2-docs-synthesis-attribution` | CLAUDE.md + README.md sync; synthesis vs. attribution PM insight |
| #7 | `feature/week2-eval-completeness` | Eval 3 (completeness) built — 3-criterion rubric, topic auto-extraction |
| #8 | `feature/week2-eval-factuality-extraction-fix` | Eval 2 extraction fixes: bold references, slash separator, bibliography skip |
| #9 | `feature/week2-completeness-full-paper` | Eval 3 fix: send full paper to judge (remove 1500-char truncation) |
| #10 | `feature/week2-docs-update-completeness` | CLAUDE.md + README.md sync through PR #9 |
| #11 | `feature/repo-topics-badges` | GitHub topics + shields.io badges |
| #12 | `feature/week2-eval-efficiency` | Eval 4 (efficiency) + run_metrics.json per-tool logging |
| #13 | `feature/week2-citation-format-standard` | Single citation format enforced in system prompt |
| #14 | `feature/week2-grounding-sentence-split-fix` | Grounding eval: peek at next fragment for citation |
| #15 | `feature/week2-grounding-split-fix-v2` | Grounding eval: handle multi-split citation fragments |
| #16 | `feature/week2-docs-final` | CLAUDE.md + README.md sync through PR #15 |
| #17 | `feature/week3-interview-coach` | Agent 2: multi-agent PM Interview Coach (3 files) |
| #18 | `feature/week3-docs-update` | CLAUDE.md + README.md sync through Week 3 |
| #19 | `feature/week5-9-roadmap-docs` | Weeks 5–9 added to learning roadmap |
| #20 | `feature/week3b-llm-orchestrator` | Week 3B: LLM orchestrator + Agent C + rubric rewrite |

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
