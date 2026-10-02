---
applyTo: "research/**/*.html"
description: "Use when creating or editing research HTML task logs (HHMM_task-name.html) or weekly summary files (README.html). Covers HTML templates, design system components, CSS classes, tag taxonomy, meta tag requirements, and threads-update agent invocation."
---

# Research HTML File Specification

## Task Log: `weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task-name.html`

### Creation Rules

- **Use HTML only.** Never Markdown (.md) for task logs.
- File path: `research/weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task-name.html`
  - `HHMM`: approximate current time (e.g. `1430`)
  - `task-name`: short kebab-case in English (e.g. `spg-gain-analysis`)
- After creating, add one linked line to the same week's `RESEARCH_LOG.md`.
- `<meta name="role">` and `<meta name="tags">` are required in every task log.
- Add `<meta name="relations">` only when causal links to other logs are clear.
- Do not update `threads/` as a routine after each task log. Update only when the topic's current state / open questions / next frontier changes.

### HTML Template

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="role" content="experiment"><!-- experiment | analysis | design | investigation | hypothesis -->
<meta name="tags" content="doing, experiment, gain-formula, treasuredata">
<!-- <meta name="relations" content="implements:../2026-05-19/previous-task.html, motivated-by:../../2026-W20/README.html"> -->
<title>タスク名</title>
<!-- Task logs are 3 levels deep: weekly/YYYY-WNN/YYYY-MM-DD/ -->
<link rel="stylesheet" href="../../../research.css">
</head>
<body>
<div class="container">

<nav>
  <a href="../README.html">↑ Weekly Summary</a> ·
  <a href="../RESEARCH_LOG.md">Weekly Log</a>
</nav>

<h1>タスク名</h1>
<p class="sub">
  YYYY-MM-DD ·
  <span class="pill blue">doing</span><!-- doing | done | blocked | parked -->
</p>

<h2>Goal</h2>
<div class="panel accent">
  <ul>
    <li><!-- 確認したいこと・達成したいこと --></li>
  </ul>
</div>
<p class="note">Rationale: <!-- なぜこの手法・アプローチを選んだか。検討した代替案があれば --></p>

<h2>What was done</h2>
<ul>
  <li><!-- 実行したこと・書いたコード・試した設定 --></li>
</ul>
<pre><code>python compute_metrics.py --dataset tpch</code></pre>

<h2>Results &amp; Observations</h2>
<h3>実験条件 / Conditions</h3>
<!-- 再現に必要な設定を必ず記録する -->
<table>
  <tr><th>Item</th><th>Value</th></tr>
  <tr><td>データセット</td><td><!-- tpch / treasuredata / sample --></td></tr>
  <tr><td>件数</td><td><!-- N=? --></td></tr>
  <tr><td>主なパラメータ</td><td><!-- key=value --></td></tr>
</table>

<h3>結果</h3>
<!-- 数値があれば KPI カードや棒グラフで表示する -->
<ul>
  <li><!-- 出力、数値、グラフの挙動 --></li>
</ul>
<p class="note">Confidence: <span class="pill blue">preliminary</span><!-- preliminary | supported | strong --></p>

<h2>Blockers &amp; Solutions</h2>
<ul>
  <li><!-- エラーの詳細と解決方法 --></li>
</ul>

<h2>Open Questions</h2>
<ul>
  <li><!-- 次に調べること、まだわからないこと --></li>
</ul>

<h2>Next Actions</h2>
<ul>
  <li><!-- 具体的な次のステップ --></li>
</ul>

<h2>Related Files &amp; Outputs</h2>
<ul>
  <li><a href=""><!-- コード・CSV・図・ログへの相対パス --></a></li>
</ul>

</div>
</body>
</html>
```

### Role-specific sections

The template includes all sections by default. Adjust based on `role`:

| Role | Conditions table | Notes |
|------|-----------------|-------|
| `experiment` | **Required**: dataset, n=, key parameters | Core reproducibility baseline |
| `analysis` | **Include** when data-driven; describe data source and scope | |
| `investigation` | **Skip** — list source material in "What was done" instead | Paper reading, exploratory research |
| `design` | **Skip** — use a rationale/scope table instead | |
| `hypothesis` | **Skip** — use a supporting evidence list instead | |

---

## Weekly Summary: `weekly/YYYY-WNN_theme-name/README.html`

Created when closing a week. Weekly summaries are 2 levels deep.

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>WNN: テーマ名</title>
<!-- Weekly summaries are 2 levels deep: weekly/YYYY-WNN/ -->
<link rel="stylesheet" href="../../research.css">
</head>
<body>
<div class="container">

<nav><a href="RESEARCH_LOG.md">Weekly Log (Markdown)</a></nav>

<h1>WNN: テーマ名</h1>
<p class="sub">Period: YYYY-MM-DD – YYYY-MM-DD</p>

<h2>What was done</h2>
<p><!-- 3行以内で要約 --></p>

<h2>Key findings &amp; insights</h2>
<div class="panel good">
  <ul>
    <li><!-- 実験から学んだこと --></li>
    <li><!-- 予想外の結果 --></li>
  </ul>
</div>

<h2>What did not work</h2>
<ul>
  <li><!-- 失敗・行き詰まり・原因の仮説 --></li>
</ul>

<h2>Handoff to next week</h2>
<div class="panel warn">
  <ul>
    <li><!-- 未完了タスク・次に試すこと --></li>
  </ul>
</div>

<h2>Key task logs</h2>
<table>
  <thead>
    <tr><th>ファイル</th><th>概要</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="YYYY-MM-DD/HHMM_task-name.html">YYYY-MM-DD / HHMM_task-name</a></td>
      <td><!-- 1行説明 --></td>
    </tr>
  </tbody>
</table>

</div>
</body>
</html>
```

---

## Design System

**Do not write inline `<style>`. Always reference `research/research.css` via relative `<link>`.**

### Component Reference

| Purpose | Class / Element | When to use |
|---------|-----------------|-------------|
| KPI card | `.kpi` > `.v` + `.l` + `.d` | Highlight numeric results |
| Panel (colored left border) | `.panel.accent/.good/.warn/.bad` | Conclusion, warning, blocker |
| Horizontal bar chart | `.bar-row` > `.bar-track` > `.bar.blue/.green/.warn` | Method comparison, ratios |
| Stacked bar chart | `.stack-bar-track` > `.seg.blue/.green/.warn/.purple` | Composition comparison |
| 2/3-column grid | `.grid-2` / `.grid-3` | Parallel KPIs |
| Table | `table > th,td` / `td.num` / `td.good/.bad/.warn` | Quantitative comparison |
| Code block | `<pre><code>` | Commands, output, snippets |
| Badge | `.pill.blue/.green/.warn/.purple` | Labels, tags, status |
| Note | `.note` | Small annotations |
| Flow diagram | `.flow` > `.flow-step` + `.arrow` | Pipelines, procedures |

### Examples

**KPI card:**
```html
<div class="grid-3">
  <div class="kpi">
    <div class="v">1,841,174</div>
    <div class="l">Total Gain</div>
    <div class="d">+21,848 vs Baseline</div>
  </div>
</div>
```

**Panel:**
```html
<div class="panel good">
  <h3>結論</h3>
  <p>...</p>
</div>
```

**Bar chart:**
```html
<div class="bar-row">
  <div class="bar-label">① ベースライン</div>
  <div class="bar-track">
    <div class="bar blue" style="width:52%;">256</div>
  </div>
  <div class="bar-val">256</div>
</div>
```

### Tips for Rich HTML

- **Visualize numbers**: always use KPI cards or bar charts, not plain text lists.
- **Comparison**: table + colored cells (`td.good` / `td.bad`) for at-a-glance reading.
- **Conclusion / warning / blocker**: `.panel.good/.warn/.bad` to stand out.
- **Commands and output**: paste raw into `<pre><code>`. No need to write perfectly.
- **Flow diagrams**: use `.flow` + `.flow-step` + `.arrow` to explain pipelines and procedures.

---

## Meta Tags and Research Index

`research/index.html` is auto-generated by `research/generate_index.py`.  
Auto-rebuild on save requires the *emeraldwalk.RunOnSave* extension.  
Manual: `python3 research/generate_index.py`

### Required meta tags (every task log)

```html
<meta name="role" content="experiment">
<!-- experiment | analysis | design | investigation | hypothesis -->

<meta name="tags" content="done, experiment, gain-formula, treasuredata">
<!-- comma-separated list: status + phase + topic(s) + corpus -->
```

`<meta name="tags">` must include the status word. Do **not** rely on `.pill` elements for tag extraction — body pills are intentionally excluded from the graph.

### Tag Taxonomy

**Phase** — choose the primary phase:

| Tag | When |
|-----|------|
| `design` | Designing metrics, formulas, or architecture |
| `experiment` | Running measurements or validation |
| `analysis` | Interpreting results, breakdowns |
| `investigation` | Exploratory reading, open-ended research |

**Topic** — choose all that apply:

| Tag | Scope |
|-----|-------|
| `readability` | Query readability evaluation (SQL/Wvlet comparison, user study) |
| `gain-formula` | Gain score formula design and calibration |
| `spg` | Slot-Pattern Grouping — multi-cluster variant selection |
| `stream-refactor` | Stream refactoring pipeline optimisation |
| `variant-design` | Variant candidate generation / ILP optimisation |
| `metric` | Generic metric design (DRY, SN, SSOA, Halstead, etc.) |

**Corpus** — add when relevant:

| Tag | Meaning |
|-----|---------|
| `treasuredata` | Treasure Data real-world corpus (≈ 139k files) |
| `tpch` | TPC-H benchmark queries |

**Status** — exactly one per page:

| Tag | Meaning |
|-----|---------|
| `done` | Work complete |
| `doing` | In progress |
| `blocked` | Blocked on external dependency |
| `parked` | Deferred |

**Examples:**
```
done, experiment, gain-formula, treasuredata
doing, design, spg, variant-design
done, analysis, stream-refactor
```

### Typed Relations (optional)

```html
<meta name="relations" content="implements:../2026-05-19/task.html, motivated-by:../../2026-W20/README.html">
<!-- Edge types: implements | motivated-by | validates | refutes | extends | open-question -->
```

If omitted, edges are inferred from `<a href="...html">` links in the body.

> **`investigation` tasks triggered by current research**: if a paper reading or exploratory investigation was motivated by an open question in ongoing work, add `motivated-by:` pointing to the log or README that raised the question. If no specific log applies, link to the current week's `README.html` (even if it does not yet exist).

---

## LLM Instructions for HTML Files

### Writing a task log
Split work into task units. Create `weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task-name.html` using the task log template above. After creating, add one linked line to the weekly `RESEARCH_LOG.md` for the same week.

When the task clearly implements, extends, validates, refutes, or is motivated by another log, add `<meta name="relations">`.

### Writing a weekly summary
Read the week's `RESEARCH_LOG.md` and key task logs. Create `README.html` using the weekly summary template above. Propose theme name candidates for the folder rename.

### Updating threads after a task log
After creating a task log, assess whether the topic's **current state / open questions / next frontier** changed. If yes, invoke the `threads-update` agent:

```
runSubagent:
  agentName:   "threads-update"
  prompt:      "topic: {topic名}。{変化の概要を1文で}"
  description: "threads/{topic}.md を更新"
```

Default timing: **weekly close only**. Invoke immediately only when:
- A long-standing core question is resolved
- A design direction changes significantly (`validates` / `refutes` confirmed)
