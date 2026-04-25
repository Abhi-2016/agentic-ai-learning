# Agent Design Doc — PM Interview Coach

**System:** PM Interview Coach (Agent 2)
**Branch:** feature/week4-meta-evals
**Status:** Week 4 complete — meta-evals passing

---

## 1. Purpose

**Problem:** A PM preparing for AI interviews needs to practice explaining agentic AI concepts clearly and consistently. Reading about agents is not enough — fluency requires repeated retrieval practice with calibrated feedback.

**What the system does:** A multi-agent coaching loop that generates PM interview questions calibrated to the learner's weak spots, evaluates answers on a structured rubric, and decides what to practice next based on all-time history. It remembers across sessions and improves its targeting over time.

**Who it's for:** A single learner (PM, not engineer) building interview fluency in agentic AI concepts.

**What it is not:** A production coaching product. A grader. A replacement for human feedback. It is a learning artefact — every design decision is made to be inspectable and debuggable by the person using it.

---

## 2. Architecture

```
coach.py (Orchestrator — LLM)
    │
    ├── load_learner_context()          reads CLAUDE.md once at startup
    │       └── extracts: weeks complete, quizzes passed, PM background
    │
    ├── orchestrate(history, q_count)   LLM call → routing decision
    │       └── returns: {action, topic}
    │           action ∈ {ask_on_topic, suggest_topic, end_session}
    │
    ├── [suggest_topic path]
    │       └── suggest_topic(history)  → Agent C (topic_suggester.py)
    │               └── returns: {suggested_topic, reason}
    │
    ├── generate_question(topic, ctx)   → Agent A (question_generator.py)
    │       └── returns: one question string
    │
    ├── [user answers in terminal]
    │
    ├── evaluate_answer(question, ans)  → Agent B (evaluator.py)
    │       └── returns: {score, strength, improvement}
    │
    └── save_to_history(entry)          orchestrator owns all writes
            └── coach_history.json
```

**Four agents, four jobs:**

| Agent | File | Model | Input | Output |
|---|---|---|---|---|
| Orchestrator | coach.py | Haiku | History + session count | action, topic |
| Agent A — Questioner | question_generator.py | Haiku | Topic + learner context | One question |
| Agent B — Evaluator | evaluator.py | Haiku | Question + answer | Score 1–5, feedback |
| Agent C — Pattern Analyser | topic_suggester.py | Haiku | Full all-time history | Suggested topic + reason |

**Key architectural decision — Haiku for all agents:**
Each agent handles a structured, narrow task. Deep reasoning is not required. Haiku is cheaper and faster; the quality bar for these tasks does not justify Sonnet or Opus.

---

## 3. Memory Model

| Type | Location | Written by | Read by | Persistence |
|---|---|---|---|---|
| All-time history | `coach_history.json` | Orchestrator only | Orchestrator, Agent C | Permanent — survives restarts |
| Learner context | `CLAUDE.md` (read-only) | Human (Abhishek) | Orchestrator at startup | Permanent |
| Session state | Python variables in `run_coach()` | Orchestrator | Orchestrator | Session only — wiped on restart |
| Agent context windows | `messages[]` per call | Per-call construction | That call's LLM only | Single call — wiped immediately |

**Ownership rule:** No agent writes to `coach_history.json` directly. All writes go through `save_to_history()` in coach.py. This is the same pattern as the Research Synthesizer's scratchpad — orchestrator owns shared state, agents only receive what they need.

**Why Agent A and Agent B don't read history:**
Agent A's job is to generate a question, not fetch context — the orchestrator passes exactly what Agent A needs. Agent B's job is to evaluate one answer — it has no use for past sessions. Centralising reads in the orchestrator keeps each agent's input inspectable and reproducible.

---

## 4. Decision Logic (Orchestrator)

The orchestrator runs one LLM call per turn. It receives:
- `HISTORY_SUMMARY` — per-topic attempt counts and average scores
- `TOTAL_HISTORY_ENTRIES` — pre-computed raw count (prevents LLM arithmetic errors)
- `QUESTIONS_THIS_SESSION` — count of questions asked this session

**Priority rules (checked in order, stop at first match):**

```
Priority 1: IF questions_this_session >= 5  →  end_session
Priority 2: IF total_history_entries >= 5   →  suggest_topic
Priority 3: (default)                       →  ask_on_topic
```

**Why explicit priority order, not independent conditions:**
The first version of the system prompt listed three conditions as parallel alternatives ("Use when: ..."). When two conditions were simultaneously true (Scenario C: 6 entries + 0 session questions), the LLM used judgment to pick — and chose incorrectly. Rewriting as a sequential decision tree removed the ambiguity. The LLM's job is now comparison, not conflict resolution.

**Why `TOTAL_HISTORY_ENTRIES` is passed explicitly:**
The history summary groups attempts by topic (e.g. "ReAct pattern: 2 attempts, avg 4.0/5"). To check Priority 2, the LLM would need to sum all the per-topic counts. That arithmetic is where Scenario E failed — the LLM miscounted and triggered `suggest_topic` with only 3 entries. Passing `len(history)` directly reduces the check to a single integer comparison.

**Fallback:** If the LLM response can't be parsed, the orchestrator defaults to `ask_on_topic` on the first topic in the list. The session never crashes.

---

## 5. Evaluation Framework

Two meta-evals measure the agents that do the evaluating.

### Eval 1 — Agent B Consistency (`eval_consistency.py`)

**What it measures:** Does Agent B score the same answer identically across multiple runs?

**Method:** Run the same (question, answer) pair through `evaluate_answer()` five times. Record the score each time. Calculate variance.

**Pass condition:** Zero variance across all 5 runs — identical score every time.

**Why this matters:** An inconsistent evaluator produces noise, not signal. If the same answer scores 3 one run and 5 the next, no learning is happening — the score reflects randomness, not quality. Consistency is the minimum bar before trusting any eval output.

**Result:** PASS. Variance = 0. All 5 runs scored 3/5.
**Fix applied:** `temperature=0` in Agent B — deterministic sampling eliminates run-to-run score drift.

**What consistency does NOT guarantee:** A consistent evaluator can be consistently wrong. Consistency = same answer every time. Accuracy = correct answer. You need both — consistency first, then calibration.

---

### Eval 2 — Orchestrator Accuracy (`eval_orchestrator.py`)

**What it measures:** Does the orchestrator route to the correct action across key decision scenarios?

**Method:** 5 synthetic history scenarios, each with a clearly correct expected action. Run the orchestrator against each. Compare actual vs expected.

**Scenarios:**

| Scenario | History | Session Q's | Expected action | Tests |
|---|---|---|---|---|
| A | Empty | 0 | ask_on_topic | Cold start behaviour |
| B | 2 entries, one weak topic | 0 | ask_on_topic | Doesn't over-trigger suggest_topic |
| C | 6 entries, one clear weak spot | 0 | suggest_topic | Delegates when history is rich |
| D | 5 entries, all strong | 5 | end_session | Wraps up correctly |
| E | 3 entries, mixed | 3 | ask_on_topic | Doesn't miscount entries |

**Pass condition:** ≥ 80% (4/5 correct). WARN at 60–79%. FAIL below 60%.

**Result (after fix):** PASS. 5/5 correct. 100% accuracy.

**What failed before the fix:** Scenarios C and E both failed at 60% (WARN).
- Scenario C: overlapping conditions — both `ask_on_topic` and `suggest_topic` applied. LLM chose wrong.
- Scenario E: LLM miscounted history entries from the summary, triggering `suggest_topic` with only 3 entries.
**Fix:** Explicit priority order in system prompt + `TOTAL_HISTORY_ENTRIES` injected as a pre-computed integer.

---

## 6. Failure Modes

| Failure | Trigger | What happens | Mitigation |
|---|---|---|---|
| Orchestrator misroutes | Ambiguous conditions, LLM miscounts | Wrong topic, wrong action | Explicit priority order; pre-computed counts passed as integers |
| Orchestrator response unparseable | LLM ignores format instructions | Falls back to `ask_on_topic` on first topic | Hardcoded fallback in `orchestrate()` — session never crashes |
| Agent B scores inconsistently | Temperature > 0 | Score variance makes feedback unreliable | `temperature=0` enforced in evaluator.py |
| Agent B rubric drift | Rubric language is vague or pattern-matching | Same answer scores differently across rubric versions | Behaviour-based rubric language; rubric changes must be versioned |
| Agent A generates wrong difficulty | Learner context not passed | Questions framed for engineers, not PMs | Orchestrator reads CLAUDE.md at startup, injects learner profile into every Agent A call |
| History file missing | First run, or file deleted | `load_history()` returns empty list | Explicitly handled — empty list is a valid starting state |
| Score drift across rubric versions | Rubric rewritten mid-project | Historical scores not comparable | Known debt — rubrics should be versioned and scores tagged with rubric version |

---

## 7. Known Limitations

**System prompts were Claude-generated (not Abhishek-written):**
All four agents — orchestrator, Agent A, Agent B, Agent C — have system prompts that were generated by Claude during initial scaffolding. The project convention is that Abhishek writes every system prompt first. This debt means the prompts haven't been through the deliberate design process that catches boundary failures and rubric ambiguities. Scheduled for rewrite before Week 5.

**No rubric versioning:**
The evaluator rubric was rewritten in Week 3B (calibration pass). The same answer that scored 4/5 under the original rubric scored 3/5 under the revised rubric. Scores in `coach_history.json` are not tagged with a rubric version, so historical trends are not meaningful across the rewrite boundary. In a production system, rubric changes would be versioned and scores would carry a rubric ID.

**Single learner, no auth:**
The system is designed for one user. `coach_history.json` is a flat file with no user ID. Multi-user deployment would require a keyed store.

**No question deduplication:**
Agent A can generate the same question twice across sessions. There is no check against `coach_history.json` before generating. A production system would pass recent questions to Agent A as context to avoid repetition.

**Orchestrator is not idempotent:**
If the session crashes mid-turn (after the question is generated but before the answer is saved), the history entry is lost. The next session picks up cleanly, but the turn is not recoverable.

---

## 8. The PM Decision Trail

Key decisions made during this build, and why:

| Decision | Rationale |
|---|---|
| Python router → LLM orchestrator (Week 3B) | Fixed flows don't need LLM reasoning. History-aware routing does. Python routes by rules; an LLM orchestrator routes by reasoning. |
| Agent C separate from orchestrator | Session manager (current turn) and pattern analyser (all-time history) are different jobs. Separating them keeps each agent's scope narrow and swappable. |
| Orchestrator owns all file I/O | If agents wrote to `coach_history.json` directly, you couldn't know what any agent actually received. Centralised writes make the system inspectable. |
| `temperature=0` for Agent B | Consistency before accuracy. A noisy evaluator produces no signal. Temperature=0 is the minimum viable setting for a judge. |
| Explicit priority order in orchestrator prompt | Parallel conditions let the LLM resolve conflicts via judgment. Judgment introduced errors. Sequential rules make the decision deterministic. |
| `TOTAL_HISTORY_ENTRIES` passed explicitly | LLM arithmetic on summary text failed (Scenario E). Pre-computed integers are more reliable than derived counts. Fix the input, not the reasoning. |
