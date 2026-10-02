---
description: Create a new research task log HTML file for the current week
---

# Research Task Log 作成プロンプト

新しいリサーチ作業を記録する HTML ファイルを作成します。

## ルール

- **ファイルは必ず HTML で作成する。** Markdown (.md) は使わない。
- 保存先: `research/weekly/YYYY-WNN/YYYY-MM-DD/HHMM_task-name.html`
  - `HHMM` は現在時刻の概算（例: `1430`）
  - `task-name` は英語またはローマ字の短いケバブケース（例: `spg-gain-analysis`）
- 作成後、必ず同じ週の `research/weekly/YYYY-WNN/RESEARCH_LOG.md` に1行追記する。
- `<meta name="role">` と `<meta name="tags">` を必ず書く。`tags` には status + phase + topic(s) + corpus を入れる。
- 既存ログとの因果関係が明確な場合だけ、`<meta name="relations">` を追加する。
- `research/threads/` は日次ログのコピー置き場ではない。通常のタスクログ作成時には更新しない。
- その作業でトピックの current state / open question / next read が変わる場合だけ、該当 thread の更新を提案または実施する。

## デザインシステム（ダークテーマ）

このプロジェクトの既存ドキュメントと統一したスタイルを使うこと。

**スタイルは共有CSSファイルを参照する。インラインで `<style>` を書かない。**

- タスクログ（`research/weekly/YYYY-WNN/YYYY-MM-DD/*.html`）:
  ```html
  <link rel="stylesheet" href="../../../research.css">
  ```
- 週次 README（`research/weekly/YYYY-WNN/README.html`）:
  ```html
  <link rel="stylesheet" href="../../research.css">
  ```

CSS 変数・コンポーネントの定義は `research/research.css` を参照。

### コンポーネント早見表

| 目的 | クラス / 要素 | 使用シーン |
|------|-------------|-----------|
| 指標をカード表示 | `.kpi` > `.v` + `.l` + `.d` | 数値KPIを強調したいとき |
| パネル（色付き左ボーダー） | `.panel.accent/.good/.warn/.bad` | 結論・注意・ブロッカーの強調 |
| 横棒グラフ | `.bar-row` > `.bar-track` > `.bar.blue/.green/.warn` | 手法比較・比率 |
| 積み上げ棒グラフ | `.stack-bar-track` > `.seg.blue/.green/.warn/.purple` | 構成比の比較 |
| 2/3カラムグリッド | `.grid-2` / `.grid-3` | KPI並列・対比 |
| テーブル | `table > th,td` / `td.num` / `td.good/.bad/.warn` | 定量比較 |
| コードブロック | `<pre><code>` | コマンド・出力・スニペット |
| バッジ | `.pill.blue/.green/.warn/.purple` | ラベル・タグ・状態 |
| メモ・補足 | `.note` | 小さい注釈 |
| フロー図 | `.flow` > `.flow-step` + `.arrow` | パイプライン・手順 |

### KPI カード例

```html
<div class="grid-3">
  <div class="kpi">
    <div class="v">1,841,174</div>
    <div class="l">Total Gain</div>
    <div class="d">+21,848 vs Baseline</div>
  </div>
</div>
```

### パネル例

```html
<div class="panel good">
  <h3>結論</h3>
  <p>...</p>
</div>
```

### 棒グラフ例

```html
<div class="bar-row">
  <div class="bar-label">① ベースライン</div>
  <div class="bar-track">
    <div class="bar blue" style="width:52%;">256</div>
  </div>
  <div class="bar-val">256</div>
</div>
```

## HTML 全体テンプレート

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<!-- タグ分類: status + phase + topic(s) + corpus -->
<!-- Phase: design | experiment | analysis | investigation -->
<!-- Topic: readability | gain-formula | spg | stream-refactor | variant-design | metric -->
<!-- Corpus: treasuredata | tpch -->
<!-- Status: done | doing | blocked | parked -->
<meta name="role" content="experiment"><!-- experiment | analysis | design | investigation | hypothesis -->
<meta name="tags" content="doing, experiment, gain-formula, treasuredata">
<!-- Optional: typed links for graph/thread reconstruction -->
<!-- <meta name="relations" content="implements:previous-task.html, motivated-by:../../2026-W20/README.html"> -->
<title>タスク名</title>
<!-- タスクログは 3 階層深い: weekly/YYYY-WNN/YYYY-MM-DD/ -->
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

<h2>What was done</h2>
<ul>
  <li><!-- 実行したこと・書いたコード・試した設定 --></li>
</ul>
<pre><code>python compute_metrics.py --dataset tpch</code></pre>

<h2>Results &amp; Observations</h2>
<!-- 数値があれば KPI カードや棒グラフで表示する -->
<ul>
  <li><!-- 出力、数値、グラフの挙動 --></li>
</ul>

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

## HTML を豊かにするヒント（ @trq212 の記事より）

- **Markdown より HTML を使う理由**: 色・表・図・インタラクションで情報密度が高い。100行超のドキュメントは Markdown では読まれない。
- **数値は必ず KPI カードか棒グラフで視覚化する**。テキストで羅列するだけにしない。
- **比較は表 + 色付きセル**（`td.good` / `td.bad`）で一目でわかるようにする。
- **結論・注意・ブロッカーは `.panel.good/.warn/.bad`** で目立たせる。
- **コマンドや出力は `<pre><code>`** にそのままペーストしてよい。完璧に書こうとしない。
- **SVG でフロー図**を描くと、パイプラインや手順の説明が格段にわかりやすくなる。

## LLM が後で追いやすくするための最小メタ情報

- `role` はページの主目的を表す。複数の目的があっても主目的を1つ選ぶ。
- `tags` は検索・グラフ・thread map の入口になるため、topic tag を省略しない。
- `relations` は本文リンクより重要。研究の流れが明確なときだけ使う。
- 使える relation: `implements`, `motivated-by`, `validates`, `refutes`, `extends`, `open-question`。
- `threads/` は週次クローズやトピック整理時に更新する。日次ファイル作成のたびに更新しない。

## threads/ の更新（`threads-update` エージェント呼び出し）

タスクログ作成後、そのタスクでトピックの **current state / open questions / next frontier** が変化したと判断した場合、`threads-update` カスタムエージェントを呼び出す。

**通常の呼び出しタイミング**: 週次クローズ時（デフォルト）。日次ルーティンログでは呼び出さない。

**例外的に即時呼び出す条件**:
- 長らく open だった core question が解決されたとき
- 実験結果で設計方針が大きく変わったとき（`validates` / `refutes` が確定したとき）

**呼び出し方**:

`runSubagent` ツールを使って `threads-update` エージェントを呼び出してください。

- `agentName`: `"threads-update"`
- `prompt`: `"topic: {topic名}。{変化の概要を1文で}"`
- `description`: `"threads/{topic}.md を更新"`

> `chat.customAgentInSubagent.enabled: true` が VS Code settings.json に必要（VS Code v1.107+）。
