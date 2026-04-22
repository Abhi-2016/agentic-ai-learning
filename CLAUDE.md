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
| `system_prompt.txt` | ✅ Live | Written by Abhishek — goal, stopping condition, ReAct reasoning, tools, 5 uncertainty modes, LANGUAGE DISCIPLINE verbatim constraint |
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

# API keys live in .env — copy the template and fill in your keys
cp .env.example .env
# edit .env: add ANTHROPIC_API_KEY and TAVILY_API_KEY
# Keys are loaded automatically via python-dotenv — no export needed

python agent.py "your topic"
```

### Full Eval Pipeline (run after agent produces a paper)
```bash
python agent.py "your topic" > last_paper.txt  # produce the paper + run_metrics.json
python evals/eval_efficiency.py                 # runs all 4 evals in sequence
# or run individually:
python evals/eval_grounding.py                  # Eval 1: citation coverage
python evals/eval_factuality.py                 # Eval 2: LLM-as-judge
python evals/eval_factuality.py --human-review  # Eval 2 with calibration spot-check
python evals/eval_completeness.py               # Eval 3: rubric-based section + coverage check
python evals/eval_efficiency.py                 # Eval 4: quality per tool call (runs 1–3 internally)
```

### What's Built (Week 2 — Evals ✅)
| Eval | Status | Method |
|---|---|---|
| Grounding | ✅ Built | Rule-based citation checker |
| Factuality | ✅ Built | LLM-as-judge (claude-haiku) + `--human-review` calibration |
| Completeness | ✅ Built | Rubric-based section coverage (3 Haiku calls, one per criterion) |
| Efficiency | ✅ Built | Composite quality / (external calls / baseline 6) |

### What's Built (Week 3 — Agent 2: PM Interview Coach ✅)

**Multi-agent system, verified working end-to-end.**

| File | Role | Notes |
|---|---|---|
| `interview_coach/coach.py` | Orchestrator | Python router — coordinates Agent A + B, owns all state and file I/O |
| `interview_coach/question_generator.py` | Agent A | Single Haiku call — generates one question calibrated to learner's study scope |
| `interview_coach/evaluator.py` | Agent B | Single Haiku call — scores answer 1–5 with strength + improvement feedback |
| `interview_coach/coach_history.json` | Persistent memory | Every question, answer, and score — written by orchestrator only |

**Run the coach:**
```bash
python3 interview_coach/coach.py
```

---

## Architecture

### Agent 2 — Multi-Agent PM Interview Coach

```
coach.py (Orchestrator)
    │
    ├── load_learner_context()     # reads CLAUDE.md once at startup
    │       └── extracts: weeks complete, quizzes passed, PM background
    │
    ├── generate_question(topic, learner_context)  → Agent A (Haiku)
    │       └── returns: one calibrated question string
    │
    ├── [user answers in terminal]
    │
    ├── evaluate_answer(question, answer)  → Agent B (Haiku)
    │       └── returns: {score, strength, improvement}
    │
    └── save_to_history(entry)     # orchestrator owns all writes
            └── coach_history.json
```

Key architecture decisions:
- Agent A and Agent B have **separate context windows** — neither knows the other exists
- The orchestrator passes only what each agent needs — nothing bleeds between them
- Agent A does **not** read files itself — it receives context from the orchestrator
- All persistent state (history) is written by the orchestrator, never by agents

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
├── requirements.txt    # anthropic, requests, beautifulsoup4, python-dotenv
├── .env                # API keys — gitignored, never committed
├── .env.example        # Key template — committed, safe (no real values)
├── .venv/              # Python virtual environment (gitignored)
├── README.md           # Public-facing project showcase
├── CLAUDE.md           # This file — internal context for Claude Code
├── evals/
│   ├── eval_grounding.py     # ✅ Eval 1: rule-based citation checker
│   ├── eval_factuality.py    # ✅ Eval 2: LLM-as-judge + human-review calibration
│   ├── eval_completeness.py  # ✅ Eval 3: rubric-based section + coverage check (3 Haiku calls)
│   └── eval_efficiency.py    # ✅ Eval 4: composite quality / (external calls / baseline 6)
└── interview_coach/
    ├── coach.py              # ✅ Orchestrator — Python router, owns all state
    ├── question_generator.py # ✅ Agent A — generates calibrated questions (Haiku)
    ├── evaluator.py          # ✅ Agent B — scores answers 1-5 with feedback (Haiku)
    └── coach_history.json    # Persistent memory — every session saved here
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

### Why `.env` via python-dotenv instead of `export`
Exporting keys per session is error-prone and easy to forget. `python-dotenv` reads `.env` at import time, injecting values into `os.environ` before any tool or API call. The `.env` file is gitignored by `*.env` pattern. `.env.example` is committed so any future collaborator knows exactly what keys are needed.

### Why citation format is enforced in the system prompt (not the eval)
The agent generated 3+ citation styles in the same paper — named attribution, footnote-style, end-of-paragraph grouping. Each new format required a regex patch in the eval. That is the wrong layer to fix.

Rule: fix the generation layer (system prompt), not the inspection layer (eval). One citation standard upstream means both evals work without code changes. Every patch in the eval is a symptom of a missing standard upstream.

The enforced format: `([Author, Year](URL))` inline at the end of every cited sentence.

### Why Eval 4 only counts search + read calls (not save_note) against efficiency
`save_note` is only called when the agent determines a source is strong — it is the desired outcome, not overhead. Penalising it would punish quality. `search_web` and `read_page_contents` are the exploration calls where waste actually shows up (duplicate searches, pages that yield nothing saved).

Baseline = 6: 3 searches + 3 reads. Formula: `efficiency = composite_quality / (external_calls / 6)`.

### Why the Week 3B orchestrator is an LLM, not Python
The Python router in Week 3 works because the flow is fixed: question → answer → evaluate → save → repeat. No reasoning needed to decide that sequence.

Week 3B adds history-aware routing — the orchestrator reads all past sessions and decides what topic to focus on next. Python can read the JSON file, but it can only apply fixed rules ("if score < 3, repeat"). An LLM orchestrator reasons about patterns: "ReAct scores are improving but stopping conditions are consistently weak — target that gap." That's the distinction:

> **Python routes by rules. An LLM orchestrator routes by reasoning.**

### Why Agent C (Topic Suggester) is separate from the orchestrator
The orchestrator is a session manager — it sees the current turn and decides the next move. Agent C is a pattern analyser — it looks across all historical sessions to find consistent weak spots. Different scope, different job.

The orchestrator delegates to Agent C when it decides deep analysis is needed, rather than doing pattern analysis itself every turn. This keeps each agent's responsibility narrow:

| Agent | Scope | Input | Output |
|---|---|---|---|
| Orchestrator (LLM) | Session manager | Current turn + recent history | action, topic, reason |
| Agent A | Question generator | Topic + learner context | One question |
| Agent B | Answer evaluator | Question + answer | Score + feedback |
| Agent C | Pattern analyser | Full all-time history | Suggested topic + reason |

### Why the orchestrator reads CLAUDE.md, not Agent A
Agent A's job is to generate questions — not fetch context. If Agent A read the plan file, it would violate single responsibility and make the system harder to debug (you wouldn't know what context each agent actually received). The orchestrator reads CLAUDE.md once at startup, extracts the Learning Progress Tracker section, and passes it as a parameter to every `generate_question()` call. This keeps Agent A stateless and the context chain inspectable.

### Why the evaluator rubric has explicit calibration notes
LLM judges default to the harshest interpretation of ambiguous rubric boundaries. "Incomplete" meant "wrong" to the judge even when an answer was correct but brief. Calibration notes attached to the rubric resolve the ambiguity at the source — same principle as fixing the generation layer instead of patching the eval. The 4→5 boundary now requires an explicit "without X, you'd lose Y" framing — a structural signal rather than a vague tone criterion.

### Why the system prompt has a LANGUAGE DISCIPLINE section (verbatim constraint)
The agent produced fluent, readable prose that paraphrased and elaborated beyond what sources actually said. "Only state facts from your notes" was insufficient — the agent still synthesised plausible language. Adding "use the exact language from your notes" improved the factuality eval from 67% WARN to 100% PASS.

The tradeoff is **synthesis vs. attribution**:
- **Attribution** — model repeats source language. Low risk. Eval-verifiable.
- **Synthesis** — model connects ideas to form new claims. Higher risk. Cannot be verified against any scratchpad entry. Every fluent transition ("taken together, these findings suggest...") is synthesis.

For this research accuracy tool, attribution > synthesis. The eval is the instrument that measures where you land. This is a deliberate PM decision, not an engineering one.

---

## Conventions for This Project

- **Quiz before code**: If resuming and a new concept is up next, quiz Abhishek before writing anything
- **Branch + PR for every feature**: No direct commits to main
- **Wait for explicit approval**: Never merge without Abhishek saying "merge PR X"
- **Comments are teaching tools**: Every non-trivial line has a comment mapping to a concept — preserve this
- **Plan file is source of truth**: `~/.claude/plans/graceful-seeking-lecun.md`
- **Evals go in `evals/`**: One file per eval, named `eval_<name>.py`
- **System prompts are always written by Abhishek first**: Claude reviews, suggests improvements, and flags gaps — but never generates a system prompt from scratch. This applies to every agent in the project: `system_prompt.txt`, evaluator prompts, orchestrator prompts, Agent A, Agent B, Agent C. If a new agent needs a system prompt, Abhishek writes a first draft, Claude reviews it. No exceptions.
- **Run commands belong to Abhishek**: After building a feature, provide the commands to run — do NOT run them. Wait for Abhishek to share the output, then discuss results together.
- **Quizzes gate all code**: Never build a new feature or eval without first quizzing the concept — no exceptions

---

## Learning Progress Tracker

| Week | Focus | Status |
|---|---|---|
| 1 | Agent foundations (ReAct, tools, memory, logging) | ✅ Complete |
| 2 | Evals (grounding, factuality, completeness, efficiency) | ✅ Complete |
| 3 | Agent 2: Multi-agent PM Interview Coach | ✅ Complete |
| 3B | LLM orchestrator with dynamic routing | ✅ Complete |
| 4 | Meta-evals + Agent Design Doc + interview story | ⏳ In progress |

**Quizzes passed:**
- Quiz 0: Chatbot vs. agent ✅
- Quiz 1: System prompt design ✅
- Quiz 2: Tool description quality ✅
- Quiz 3: ReAct pattern ✅
- Quiz 4: Memory types ✅
- Quiz 5: Grounding vs. factuality ✅
- Quiz 6: LLM-as-judge risk + human-in-the-loop mitigation ✅
- Quiz 7: Rubric design (3-point completeness rubric) ✅
- Quiz 8: Efficiency metric selection — PM dashboard vs. engineer dashboard ✅
- Quiz 9: Multi-agent architecture (orchestrator, context separation, shared memory ownership) ✅
- Quiz 10: Evaluator rubric design (4 criteria, 1–5 scale, calibration notes) ✅
- Quiz 11: Python router vs. LLM orchestrator — when to use each, latency/cost/failure modes ✅
- Quiz 12: Inter-rater reliability — LLM variance, temperature, consistency vs. accuracy ✅
- Quiz 13: Orchestrator accuracy test design — synthetic scenarios, ground truth, pass threshold ✅

**What's Built (Week 3B ✅)**
| File | Role |
|---|---|
| `interview_coach/coach.py` | Rewritten — LLM orchestrator replaces Python router |
| `interview_coach/topic_suggester.py` | New — Agent C, pattern analyser across all-time history |
| `interview_coach/evaluator.py` | Rubric scores 4–5 rewritten by Abhishek in behaviour-based language |

**What's Built (Week 4 — in progress)**
| File | Role | Status |
|---|---|---|
| `interview_coach/evaluator.py` | `temperature=0` added — deterministic scoring | ✅ |
| `interview_coach/eval_consistency.py` | Meta-eval: Agent B consistency test (5 runs, variance check) | ✅ |
| `interview_coach/eval_orchestrator.py` | Meta-eval: orchestrator accuracy test (5 scenarios, 80% threshold) | ✅ |
| `interview_coach/coach.py` | Orchestrator system prompt tightened by Abhishek (suggest_topic rule) | ✅ |

**Key findings so far:**
- Agent B consistency: PASS (variance=0, all 5 runs scored 3/5 — temperature=0 confirmed working)
- Score drift: rubric rewrite caused same answer to drop from 4→3 — rubrics must be versioned
- Orchestrator accuracy: 80% PASS but Scenario C failed — `suggest_topic` condition was too vague
- Fix: Abhishek rewrote the condition to "5+ history entries → always delegate to Agent C"

**Known debt:** System prompts in all 4 agents still need to be rewritten by Abhishek before Week 4 is fully complete.

**Known debt:** System prompts in all 4 agents were generated by Claude — to be rewritten by Abhishek before Week 4 meta-evals.

**Merged PRs:**
- PR #1: `feature/wire-real-tools` — live Tavily + BeautifulSoup ✅
- PR #2: `feature/richer-agent-logging` — Thought traces + human-readable logs ✅
- PR #4: `feature/week2-eval-factuality` — Eval 2 (factuality) + .env setup ✅
- PR #5: `feature/week2-verbatim-system-prompt-eval-fix` — verbatim system prompt + eval multi-source fix ✅
- PR #6: `feature/week2-docs-synthesis-attribution` — CLAUDE.md + README.md sync ✅
- PR #7: `feature/week2-eval-completeness` — Eval 3 (completeness) built ✅
- PR #8: `feature/week2-eval-factuality-extraction-fix` — bold references + slash separator + bibliography skip ✅
- PR #9: `feature/week2-completeness-full-paper` — remove 1500-char truncation in Eval 3 ✅
- PR #10: `feature/week2-docs-update-completeness` — CLAUDE.md + README.md sync through PR #9 ✅
- PR #11: `feature/repo-topics-badges` — GitHub topics + shields.io badges ✅
- PR #12: `feature/week2-eval-efficiency` — Eval 4 (efficiency) + run_metrics.json logging ✅
- PR #13: `feature/week2-citation-format-standard` — single citation format enforced in system prompt ✅
- PR #14: `feature/week2-grounding-sentence-split-fix` — grounding eval sentence splitter fix ✅
- PR #15: `feature/week2-grounding-split-fix-v2` — handle multi-split citation fragments ✅
- PR #16: `feature/week2-docs-final` — CLAUDE.md + README.md sync through PR #15 ✅
- PR #17: `feature/week3-interview-coach` — Agent 2: multi-agent PM Interview Coach ✅
- PR #18: `feature/week3-docs-update` — CLAUDE.md + README.md sync through Week 3 ✅
- PR #19: `feature/week5-9-roadmap-docs` — Weeks 5–9 added to roadmap ✅
- PR #20: `feature/week3b-llm-orchestrator` — Week 3B: LLM orchestrator + Agent C ✅
