---
applyTo: "research/**"
description: "Use when creating, updating, or referencing any file under research/. Covers folder structure, naming conventions, weekly workflow, and efficiency rules. For HTML task logs and design system, see RESEARCH-HTML.instructions.md. For RESEARCH_LOG.md, TASKS.md, INSIGHTS.md, INDEX.md, and threads/ formats, see RESEARCH-LOGFILES.instructions.md."
---

# Research Document Management System

This file defines the specification for the research logging system.
Read this file and follow the rules below when creating, updating, or referencing research records.

---

## Purpose

- Organize research progress in weekly units and accumulate logs at the task level.
- Keep multiple experiments, investigations, and implementations that happen on the same day separate so they can be referenced later.
- Accumulate important insights and findings across weeks.
- Allow LLMs to understand research context and assist with recording, referencing, and summarizing.

---

## Folder Structure

```
# System spec: .github/instructions/RESEARCH.instructions.md
research/
├── RESEARCH_LOG.md        # Weekly progress narrative (starting point for overall review)
├── INSIGHTS.md            # Accumulated insights (knowledge valid across weeks)
├── TASKS.md               # Active task queue (lean; done tasks removed; details in task logs)
├── INDEX.md               # Cross-topic map (create when 5–6 weeks have accumulated)
├── threads/               # Topic-level reading maps for LLMs (optional, lightweight)
│   ├── INDEX.md           # Topic list and current frontiers
│   ├── gain-formula.md    # Route map for one topic, not a duplicate summary of all logs
│   ├── spg.md
│   └── stream-refactor.md
└── weekly/
    ├── 2026-W01/                           # Created with number only at the start of a period
    │   ├── RESEARCH_LOG.md                 # Chronological log and file index for the week (Markdown)
    │   ├── 2026-01-06/                     # Date folder
    │   │   ├── 0900_env-setup.html         # Task-level log (HTML)
    │   │   ├── 1330_parser-investigation.html
    │   │   └── 1700_next-steps.html
    │   ├── 2026-01-07/
    │   │   └── 1015_experiment-conditions.html
    │   └── README.html                     # Weekly summary (HTML, created when closing the week)
    ├── 2026-W01_parser-behavior-study/     # Renamed when closing the week
    └── ...
```

---

## Workflow

> **"Week" does not need to align with the calendar week.** A period can be 7 days, 10 days, or any length. Create a new week folder when the user says to start a new week.

### Starting a week (triggered by user)
1. Create `weekly/YYYY-WNN/` folder (no theme name yet)
2. Create `RESEARCH_LOG.md` directly inside the week folder
3. Create a date folder `YYYY-MM-DD/` when needed
4. Create the first task log `HHMM_task-name.html` and start recording

### During the week
- Create or update `YYYY-MM-DD/HHMM_task-name.html` for each work unit
- After creating a new task log, add one line to the weekly `RESEARCH_LOG.md`
- Add `<meta name="relations">` when the task clearly implements, extends, validates, refutes, or is motivated by another log
- Do not update `threads/` during routine logging unless the new work changes a topic frontier or resolves/opens a core question
- No need to write perfectly — pasting raw commands, results, and questions is sufficient
- If resuming the same task, append to the existing file in principle; if the purpose has changed, create a new file

### Closing a week (triggered by user)
1. Review the weekly `RESEARCH_LOG.md` and key task logs
2. Write `README.html` (the theme will naturally emerge)
3. Rename the folder to `YYYY-WNN_theme-name/`
4. Insert a 3–5 line entry immediately after the `# RESEARCH_LOG` header in the root `RESEARCH_LOG.md`
5. Append to `INSIGHTS.md` if there are important insights
6. Update `threads/INDEX.md` and affected `threads/{topic}.md` files only for topics whose current state, evidence, or next reads changed

---

## Efficiency Rules

- Name task logs `HHMM_short-task-name.html`. They sort naturally by time and do not conflict when multiple are created on the same day.
- Keep task names short. Put details inside the file under `Goal` and `Results & Observations`.
- The weekly `RESEARCH_LOG.md` must always be a one-line summary with a link. This allows both LLMs and humans to navigate to detail files immediately.
- The root `RESEARCH_LOG.md` covers weekly units only. Do not add fine-grained work; that causes bloat and breaks the separation of roles.
- Use `README.html` for weekly summaries, weekly `RESEARCH_LOG.md` as a working index, and task logs as primary records.
- Use `threads/` as a lightweight topic map only. Do not duplicate daily logs or full weekly summaries there.
- For topic-specific questions, prefer `threads/INDEX.md` → relevant `threads/{topic}.md` → only the listed source logs. Do not read every thread file at once.
- Use `doing`, `done`, `blocked`, or `parked` for task log `Status`. This makes it easy to pick up incomplete tasks during weekly review.
- Only move insights that are valid across weeks into `INSIGHTS.md`. Do not transcribe every observation.

---

## Related Instructions

- **HTML task logs, README.html, design system, tag taxonomy** → `RESEARCH-HTML.instructions.md`
- **RESEARCH_LOG.md, TASKS.md, INSIGHTS.md, INDEX.md, threads/** → `RESEARCH-LOGFILES.instructions.md`

---

## Naming Conventions

| Target | Format | Example |
|--------|--------|---------|
| Week folder (at creation) | `YYYY-WNN` | `2026-W03` |
| Week folder (after rename) | `YYYY-WNN_theme-name` | `2026-W03_halstead-integration` |
| Date folder | `YYYY-MM-DD` | `2026-01-20` |
| Task log | `HHMM_task-name.html` | `0930_join-metric-recalculation.html` |
| Weekly summary | `README.html` | `README.html` |
| Thread index | `threads/INDEX.md` | `threads/INDEX.md` |
| Topic thread | `threads/{topic}.md` | `threads/gain-formula.md` |
| Theme name | English or Japanese, no spaces | `halstead-integration` |

Keep task names in file names short and use no spaces. Use `_` or `-` as separators if needed.
