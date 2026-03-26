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
3. Searches the web for peer-reviewed and credible sources
4. Reads and evaluates each source for relevance
5. Saves confirmed findings to persistent memory
6. Synthesizes a grounded, cited research paper — and stops when its own stopping criteria are met

It does this in a loop, without human input between steps. That loop is the difference between a chatbot and an agent.

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
│  ┌─────────┐    Thought (rationale + next action)   │
│  │   LLM   │ ──────────────────────────────────►   │
│  │ (Claude)│                                        │
│  └─────────┘ ◄── Observation (tool result)          │
│      │                                              │
│      ▼                                              │
│  Tool Dispatcher                                    │
│  ├── search_web       → web search API              │
│  ├── read_page_contents → page scraper              │
│  └── save_note        → scratchpad.json             │
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
search_web          → discovers sources (returns URLs + snippets)
       │
       ▼ (only if snippet looks promising)
read_page_contents  → reads full content of a URL
       │
       ▼ (only if content is relevant and credible)
save_note           → writes confirmed finding to scratchpad.json
```

Critically, each tool description explicitly states **when NOT to use it**. Without this, the LLM defaults to the most familiar tool for every task.

---

## Key Concepts Demonstrated

### 1. System Prompt as a Product Spec
The system prompt is the agent's job description, operating constraints, and uncertainty-handling playbook — all in one. A vague system prompt produces a vague agent. Key elements:
- Specific, measurable stopping condition (not "do a good job")
- Explicit tool boundaries (when to use each, and when not to)
- Defined behaviour for every failure mode (no results, gibberish input, errors)
- Mandatory reasoning step before every action

### 2. The Stopping Problem
When does an agent know it's done? This is one of the hardest unsolved problems in agentic AI. This agent implements two-layer stopping:
- The LLM decides it's done (self-report via `end_turn`)
- The system *verifies* against the scratchpad (ground truth check)

If the LLM stops early, it gets sent back. Trust but verify.

### 3. Flow Types
| Flow | Where It Appears |
|---|---|
| **Sequential** | Search → Read → Save → Synthesise |
| **Conditional** | Only read a URL if the snippet looks relevant |
| **Loop** | Keep searching until 3 sources are saved |
| **Parallel** | (Week 2) Fan-out to multiple sources simultaneously |

### 4. Evals (Week 2)
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
├── agent.py            # The ReAct loop — the heart of the agent
├── tools.py            # Tool schemas (LLM-facing) + execution functions (Python-facing)
├── system_prompt.txt   # The agent's operating instructions (written by hand, not generated)
├── scratchpad.json     # Persistent memory — survives restarts
├── requirements.txt    # anthropic SDK only
└── evals/              # (Week 2) Evaluation suite
    ├── eval_grounding.py
    ├── eval_factuality.py
    ├── eval_completeness.py
    └── eval_efficiency.py
```

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# 3. (Optional) Add Tavily for live web search
pip install tavily-python
export TAVILY_API_KEY=your_key_here

# 4. Run the agent
python agent.py "Impact of AI on healthcare"
```

The agent will print every iteration — tool calls, inputs, results, and scratchpad count — so you can watch the ReAct loop in action.

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

### Week 2 — Evals 🔄
- [ ] Grounding eval (rule-based citation checker)
- [ ] Factuality eval (LLM-as-judge)
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

## Technical Stack

| Component | Technology | Why |
|---|---|---|
| LLM | Claude (Anthropic) | Native tool use, strong reasoning, Anthropic SDK |
| Web search | Tavily API | Clean structured results, free tier |
| Persistent memory | JSON file (`scratchpad.json`) | Simple, inspectable, no infrastructure |
| Language | Python 3.11+ | Standard for AI/ML tooling |

---

## About This Project

Built as part of a structured AI PM learning curriculum, mentored by an experienced PM who worked on Claude Code at Anthropic. Every concept was earned through quizzes before any code was written — because understanding why something is built the way it is matters more than being able to copy it.

This is not a tutorial project. It is a learning artefact.

---

*Author: Abhishek Venkatesh*
*Co-authored with Claude (Anthropic)*
