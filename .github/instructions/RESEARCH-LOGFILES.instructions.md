---
applyTo: "research/**/*.md"
description: "Use when creating or updating RESEARCH_LOG.md (weekly or root), TASKS.md, INSIGHTS.md, INDEX.md, or threads/ files. Covers format specs and LLM operation instructions for all Markdown research files."
---

# Research Markdown File Specifications

## Weekly Index Log `weekly/YYYY-WNN/RESEARCH_LOG.md`

Chronological index of task logs created during the week. **Append new entries at the bottom.**

One line per task log — not for details, just "when, what, which file."

```markdown
# 2026-W01 RESEARCH_LOG

## 2026-01-06
- 09:00 Set up environment. → [0900_env-setup.html](2026-01-06/0900_env-setup.html)
- 13:30 Investigated parser failure. → [1330_parser-investigation.html](2026-01-06/1330_parser-investigation.html)

## 2026-01-07
- 10:15 Organized experiment conditions. → [1015_experiment-conditions.html](2026-01-07/1015_experiment-conditions.html)
```

---

## Root Progress Narrative `RESEARCH_LOG.md`

Records the overall chronological flow of research. 3–5 lines per week.

**How to append:** Insert the new week's entry immediately **after** the `# RESEARCH_LOG` header line (latest entry stays at top).

```markdown
# RESEARCH_LOG

## 2026-W03 > Halstead metric integration
Integrated Halstead-style metrics into the core pipeline. Confirmed correlation with SN on TPC-H queries.
Variance higher than expected for nested CTEs — needs further investigation.
→ [Details](weekly/2026-W03_halstead-integration/README.html)

## 2026-W02 > Baseline metric evaluation
Established baseline readability scores for the Treasure Data corpus.
Overfitting to SQL style detected; normalization strategy needed.
→ [Details](weekly/2026-W02_baseline-eval/README.html)
```

Do not add fine-grained daily work here. That belongs in `weekly/YYYY-WNN/RESEARCH_LOG.md`.

---

## Active Task Queue `TASKS.md`

Lean, always-current queue. **Done tasks are deleted, not archived.**

```markdown
# Research Tasks

## Active
| ID | P | Topic | Status | Next Action |
|---|---|---|---|---|
| RQ-WNN-001 | P0 | stream-refactor | ready | implement stream-apply |
| RQ-WNN-002 | P1 | gain-formula | blocked | run R_core evaluation |

## Ticket: RQ-WNN-001 — short title

    Status:      ready | wip | blocked
    Topic:       topic-name
    Question:    What does this task answer?
    Why:         Why is it needed now?
    Next action: Concrete next step.
    Acceptance:
      - Condition 1
      - Condition 2
    Evidence:
      - weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task-name.html
```

**LLM rules:**
- Done task: delete the Active table row AND the full ticket block.
- New task: append a row to the Active table AND a new ticket block.
- If Active rows exceed ~10, something is wrong — escalate to user.

---

## Key Insights `INSIGHTS.md`

Only findings that remain valid across weeks. No obligation to write every week — only append when "I'll want to reference this later."

```markdown
# INSIGHTS

## [2026-W03] Low Halstead volume does not always mean high readability
Queries with low operator/operand count can still be hard to read due to deep nesting.
Readability requires structural metrics (SN, DRY) in addition to surface-level counts.
Source: [1030_halstead-analysis.html](weekly/2026-W03_halstead-integration/2026-01-20/1030_halstead-analysis.html)
Confidence: medium — observed on TPC-H (N=22); not yet validated on larger corpora.
Falsifiable by: <!-- 反証となる条件・実験（例: Halstead 低でも R_core 低いクエリ群が大量出現） -->
```

**LLM rules for INSIGHTS.md entries:**
- `Source:` is required — link to the task log where this was observed.
- `Confidence:` is required — `high` (replicated, N>50), `medium` (limited data), `low` (single observation or hypothesis).
- `Falsifiable by:` is required — describe what result would disprove this insight. If you can't state it, the insight is too vague to record.

---

## Cross-topic Map `INDEX.md`

Create when 5–6 weeks have accumulated. For searching "where is what" across topics, methods, and datasets. `RESEARCH_LOG` is for reading the flow; `INDEX` is for finding things.

```markdown
# INDEX

## By method
- Halstead metrics: W01, W03, W05 → [W03 details](weekly/2026-W03_.../README.html)
- Core 5-metric model: W02

## By dataset
- TPC-H: W01–W04
- Treasure Data: W05–

## Unresolved issues
- [ ] Optimal normalization strategy for Halstead volume (open since W03)
- [ ] Criteria for SN threshold selection (hypothesis in W03, needs validation)
```

---

## Topic Thread Maps `threads/INDEX.md` and `threads/{topic}.md`

LLM reading maps — not daily logs, not full summaries. Route LLMs to the right task logs without loading everything.

Create `research/threads/` only when topic-specific review becomes useful (not required for the first few weeks).

`threads/INDEX.md`:
```markdown
# Research Threads

## Topics
- gain-formula: Gain score design, tokenCount, W_T/GAMMA tuning → [gain-formula.md](gain-formula.md)
- spg: Slot-Pattern Grouping and multi-cluster variant selection → [spg.md](spg.md)

## Current Frontiers
- gain-formula: W_T scaling needs external R_core validation.
- spg: occurrence-level selection works; downstream readability impact remains open.
```

`threads/{topic}.md`:
```markdown
# Thread: gain-formula

## Current State
1–4 bullets: what is currently known and what is still open.

## Core Questions
- [done] Resolved question.
- [doing] Currently being tested.
- [open] Not yet answered.

## Research Flow
- Short causal step. Relation: motivated-by / implements / extends / validates / refutes.
  Source: ../weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task.html

## Evidence Ledger
| Claim | Status | Evidence |
|---|---|---|
| A reusable claim | supported / tentative / refuted / open | linked task log |

## Next Reads
- For formula design: [list of logs in order]
- For external validation: [list of logs in order]

## Neighbor Threads
- related-topic: why it matters for this thread.
```

**Update timing:** Weekly close, or when a task changes a topic's current state/frontier. Do NOT update for every routine task log. If no topic-level state changed, leave `threads/` untouched.

---

## LLM Instructions

### Updating the weekly index log
Append one linked line to the date section of `weekly/YYYY-WNN/RESEARCH_LOG.md`. If the date section does not yet exist, create `## YYYY-MM-DD` first, then append. Use a relative path ending in `.html`.

### Starting a new week
Calculate the week number from the current date. Create `weekly/YYYY-WNN/` folder and the weekly `RESEARCH_LOG.md`. The week number can be adjusted to be sequential with existing folders.

### Assisting with review
For "what did I do last week?": start from root `RESEARCH_LOG.md` → relevant week's `README.html` → weekly `RESEARCH_LOG.md` → task logs as needed.

For topic-specific questions (gain-formula, SPG, stream-refactor, readability, variant-design, metrics): check `research/threads/INDEX.md` → relevant `threads/{topic}.md` → follow `Next Reads` into task logs. Do not read every thread file at once.

### Managing TASKS.md
When a task completes:
1. Delete the row from the `## Active` table.
2. Delete the corresponding ticket block.
3. Update the HTML task log status to `done`.
4. Propose an INSIGHTS.md entry if the result is a reusable finding.

When starting a new task: append a row to the Active table and a new ticket block.

### Extracting to INSIGHTS.md
While writing task logs or weekly summaries, if a finding is valid across weeks, propose appending it to `INSIGHTS.md`.

### Updating root RESEARCH_LOG.md
Read the week's `README.html` and weekly `RESEARCH_LOG.md`. Compress to 3–5 lines. Insert immediately **after** the `# RESEARCH_LOG` header line in root `RESEARCH_LOG.md` (before existing entries — latest stays at top).

### Updating topic thread maps
Use the `threads-update` custom agent for affected topics when closing a week.

If `runSubagent` is not available, update files directly:
1. Read `research/threads/INDEX.md`; create only when the user asks or enough topic history exists.
2. Identify affected topics from task log tags and typed relations.
3. Update `Current State`, `Core Questions`, `Research Flow`, `Evidence Ledger`, `Next Reads` only where understanding changed.
4. Link to source task logs — do not copy their full contents.
5. Keep thread files short enough to serve as routing maps for LLM context selection.
