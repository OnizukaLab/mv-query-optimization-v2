# Streamlit Dashboard Implementation Plan

## 📋 概要

このドキュメントは、MV Query Optimization プロジェクトのための Streamlit ベースの Web ダッシュボードの実装計画を定義します。

### 目的
- 実験実行の GUI 化（CLI からの脱却）
- フェーズごとの実行制御
- リアルタイムな実行進捗の可視化
- 実験結果の包括的な視覚化と分析
- 複数アルゴリズムの比較分析

### 対象ユーザー
- 研究者・開発者
- データベース管理者
- 実験結果を確認したいステークホルダー

---

## 🏗️ システムアーキテクチャ

### 技術スタック

```yaml
Frontend:
  - Streamlit 1.32.0+
  - Plotly 5.18.0+ (インタラクティブグラフ)
  - Graphviz 0.20.1+ (実行プラン可視化)
  - Pandas 2.2.3+ (データ処理)

Backend:
  - 既存のsrc/モジュール群
  - scripts/run_experiment.py をラップ

Styling:
  - Custom CSS (st.markdown)
  - Streamlit Theme Configuration
  - カスタムHTMLコンポーネント
```

### ディレクトリ構造

```
mv-query-optimization/
├── dashboard/
│   ├── __init__.py
│   ├── app.py                      # メインアプリケーション
│   ├── pages/
│   │   ├── 1_🏠_Home.py           # ホーム・実験実行
│   │   ├── 2_📊_Results.py        # 結果分析
│   │   ├── 3_🔍_Query_Analysis.py # クエリ詳細分析
│   │   ├── 4_📦_MV_Explorer.py    # MV詳細
│   │   └── 5_⚙️_Settings.py      # 設定管理
│   ├── components/
│   │   ├── __init__.py
│   │   ├── experiment_runner.py   # 実験実行ロジック
│   │   ├── progress_tracker.py    # 進行状況トラッキング
│   │   ├── result_loader.py       # 結果読み込み
│   │   └── visualizations.py      # 可視化コンポーネント
│   ├── styles/
│   │   ├── main.css              # メインスタイル
│   │   └── theme.toml            # Streamlitテーマ
│   └── utils/
│       ├── __init__.py
│       ├── session_state.py      # セッション状態管理
│       ├── data_processor.py     # データ処理ユーティリティ
│       └── file_manager.py       # ファイル管理
├── .streamlit/
│   └── config.toml               # Streamlit設定
└── requirements-dashboard.txt    # Dashboard専用の依存関係
```

---

## 🎨 ユーザーインターフェース設計

### メイン画面レイアウト

```
┌─────────────────────────────────────────────────────────────────┐
│  🚀 MV Query Optimization Dashboard                             │
├─────────────┬───────────────────────────────────────────────────┤
│             │  📍 Navigation                                    │
│  Sidebar    │  ├─ 🏠 Home                                      │
│  (Settings) │  ├─ 📊 Results                                   │
│             │  ├─ 🔍 Query Analysis                            │
│             │  ├─ 📦 MV Explorer                               │
│             │  └─ ⚙️ Settings                                  │
│             │                                                   │
│             │  [Current Page Content]                          │
│             │                                                   │
└─────────────┴───────────────────────────────────────────────────┘
```

### 1. ホーム画面（実験実行）

**レイアウト:**
```
┌─────────────────────────────────────────────────────────────┐
│  🏠 Experiment Configuration                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📋 Select Algorithms                                       │
│  ☑ Normal    ☑ BigSubs    ☑ Frequency                      │
│  ☐ Utility   ☐ Utility+Capacity                            │
│                                                             │
│  💾 Storage Configuration                                   │
│  [=============================] 50 MB                      │
│                                                             │
│  🔧 Execution Phases                                        │
│  ☑ Query Parsing          ☑ Optimization                   │
│  ☑ SQL Generation         ☑ MV Creation                    │
│  ☑ Query Rewriting        ☑ Benchmark                      │
│                                                             │
│  ⚙️ Advanced Settings                                       │
│  ▼ Show Advanced Options                                    │
│     Insert Queries: [1000]                                  │
│     Benchmark Type: [JOB ▼]                                 │
│     Query Selection: [redbench ▼]                           │
│                                                             │
│  [🚀 Run Experiment]  [💾 Save Config]  [📂 Load Config]   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  📊 Execution Status                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Current Algorithm: Frequency (2/3)                         │
│  Current Phase: Optimization                                │
│                                                             │
│  [████████░░░░░░░░░░░░░░] 40% Complete                     │
│                                                             │
│  ✅ Query Parsing (12.3s)                                   │
│  🔄 Optimization (running... 8.5s elapsed)                  │
│  ⏳ SQL Generation (pending)                                │
│  ⏳ MV Creation (pending)                                   │
│  ⏳ Query Rewriting (pending)                               │
│  ⏳ Benchmark (pending)                                     │
│                                                             │
│  📝 Live Log:                                               │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ [INFO] Building ILP model...                          │ │
│  │ [INFO] Adding 1234 variables                          │ │
│  │ [INFO] Adding 5678 constraints                        │ │
│  │ [INFO] Running Gurobi solver...                       │ │
│  │ [INFO] Best objective: 1450.32                        │ │
│  │ ...                                                    │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  [⏸️ Pause]  [⏹️ Stop]  [📥 Download Logs]                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  📜 Recent Experiments                                      │
├─────────────────────────────────────────────────────────────┤
│  Date         Algorithms        Storage  Status            │
│  2025-11-18   Freq, BigSubs     50MB    ✅ Completed       │
│  2025-11-17   Normal, Utility   30MB    ✅ Completed       │
│  2025-11-17   All               50MB    ❌ Failed          │
└─────────────────────────────────────────────────────────────┘
```

**機能:**
- アルゴリズム選択（マルチセレクト）
- ストレージ制限スライダー
- 実行フェーズの個別選択
- リアルタイム進行状況表示
- ライブログストリーミング
- 実験の一時停止・停止
- 過去の実験履歴表示

---

### 2. 結果分析画面

**レイアウト:**
```
┌─────────────────────────────────────────────────────────────┐
│  📊 Algorithm Comparison                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Select Experiment: [2025-11-18 15:30:22 ▼]                │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐
│  │  Key Metrics                                           │
│  ├─────────────────────────────────────────────────────────┤
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │  │ Normal  │  │ BigSubs │  │ Frequen │  │ Utility │  │
│  │  │   12    │  │   18    │  │   15    │  │   14    │  │
│  │  │  MVs    │  │  MVs    │  │  MVs    │  │  MVs    │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
│  │                                                         │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │  │ 1200.5  │  │ 1380.2  │  │ 1450.3  │  │ 1320.8  │  │
│  │  │ Utility │  │ Utility │  │ Utility │  │ Utility │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
│  │                                                         │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │  │ 42 MB   │  │ 49 MB   │  │ 45 MB   │  │ 48 MB   │  │
│  │  │ Storage │  │ Storage │  │ Storage │  │ Storage │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  📈 Performance Comparison                                  │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Interactive Plotly Bar Chart]                        │
│  │   - Selected MVs                                        │
│  │   - Total Utility                                       │
│  │   - Storage Usage                                       │
│  │   - Execution Time                                      │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  💾 Storage Efficiency                                      │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Scatter Plot: Utility vs Storage]                    │
│  │   - Each algorithm as a point                           │
│  │   - Pareto frontier highlighted                         │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  ⏱️ Execution Time Breakdown                                │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Stacked Bar Chart: Phase Times]                      │
│  │   - Query Parsing                                       │
│  │   - Optimization                                        │
│  │   - MV Creation                                         │
│  │   - Query Rewriting                                     │
│  │   - Benchmark                                           │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  [📥 Export Results (CSV)]  [📄 Generate Report (PDF)]     │
└─────────────────────────────────────────────────────────────┘
```

**機能:**
- 過去の実験から選択
- アルゴリズム間のメトリクス比較
- インタラクティブなグラフ（Plotly）
- フェーズごとの実行時間分析
- 結果のエクスポート（CSV, JSON, PDF）

---

### 3. クエリ分析画面

**レイアウト:**
```
┌─────────────────────────────────────────────────────────────┐
│  🔍 Query Performance Analysis                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Select Algorithm: [Frequency ▼]                            │
│                                                             │
│  📊 Query Performance Overview                              │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Heatmap: Query Performance Matrix]                   │
│  │   Rows: Queries (1a, 1b, 1c, ...)                      │
│  │   Columns: Original Cost | Rewritten Cost | Speedup    │
│  │   Color: Green (improved) → Red (degraded)             │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  🎯 Performance Distribution                                │
│  ┌───────────────┬─────────────────────────────────────────┐
│  │ Improved: 85  │ [████████████████████░░░] 75%          │
│  │ Degraded: 20  │ [████░░░░░░░░░░░░░░░░░░░] 18%          │
│  │ Neutral:  8   │ [█░░░░░░░░░░░░░░░░░░░░░░] 7%           │
│  └───────────────┴─────────────────────────────────────────┘
│                                                             │
│  📋 Query List                                              │
│  ┌─────────────────────────────────────────────────────────┐
│  │ Query  │ Original │ Rewritten │ Speedup │ Status       │
│  ├────────┼──────────┼───────────┼─────────┼──────────────┤
│  │ 1a     │ 3836.84  │ 57881.17  │ 0.07x   │ ❌ Degraded  │
│  │ 1b     │ 1234.50  │ 456.20    │ 2.71x   │ ✅ Improved  │
│  │ 1c     │ 5678.90  │ 890.12    │ 6.38x   │ ✅ Improved  │
│  │ ...    │ ...      │ ...       │ ...     │ ...          │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  🔎 Query Details (Select a query from the list)           │
│  ┌─────────────────────────────────────────────────────────┐
│  │  Query: 1a                                              │
│  │                                                          │
│  │  📊 Metrics                                             │
│  │  Original Cost:    3836.84                              │
│  │  Rewritten Cost:   57881.17                             │
│  │  Speedup:          0.07x (219x slower!)                 │
│  │                                                          │
│  │  📦 MVs Used                                            │
│  │  - leaf_101 (company_name_mv)                           │
│  │  - leaf_99 (title_mv)                                   │
│  │  - leaf_100 (movie_companies_mv)                        │
│  │                                                          │
│  │  ⚠️ Performance Issue Detected                          │
│  │  Cause: Missing indexes on MVs                          │
│  │  Recommendation: Add indexes to leaf_101.id             │
│  │                                                          │
│  │  🌳 Execution Plan Comparison                           │
│  │  ┌─────────────────────┬─────────────────────┐         │
│  │  │ Original Plan       │ Rewritten Plan      │         │
│  │  │ [Tree Viz]          │ [Tree Viz]          │         │
│  │  └─────────────────────┴─────────────────────┘         │
│  │                                                          │
│  │  [📄 View SQL]  [🔍 Analyze in Detail]                 │
│  └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

**機能:**
- クエリごとのパフォーマンス比較
- ヒートマップによる一覧表示
- 個別クエリの詳細分析
- 実行プランの視覚化（Graphviz）
- Original vs Rewritten の並列比較
- パフォーマンス問題の自動検出と推奨事項

---

### 4. MV Explorer 画面

**レイアウト:**
```
┌─────────────────────────────────────────────────────────────┐
│  📦 Materialized View Explorer                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Select Algorithm: [Frequency ▼]                            │
│                                                             │
│  📊 MV Selection Overview                                   │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Sankey Diagram]                                       │
│  │                                                          │
│  │  All Candidates (1000) ──┬──→ Initial Solution (50)    │
│  │                           │                              │
│  │                           └──→ Rejected (950)           │
│  │                                     ↓                    │
│  │                           ILP Optimization              │
│  │                                     ↓                    │
│  │                           Final Selection (15) ←────┐   │
│  │                                     ↓                │   │
│  │                           Rejected (35) ─────────────┘   │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  📈 Utility Distribution                                    │
│  ┌─────────────────────────────────────────────────────────┐
│  │  [Bar Chart: Utility by MV]                            │
│  │   Blue bars: Final selection                            │
│  │   Green bars: Initial solution only                     │
│  │   Gray bars: Not selected                               │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  💾 Storage Usage                                           │
│  ┌──────────────────────┬──────────────────────────────────┐
│  │ [Pie Chart]          │ [Cumulative Bar Chart]          │
│  │  Storage by MV       │  Storage + Capacity Limit       │
│  └──────────────────────┴──────────────────────────────────┘
│                                                             │
│  📋 Selected MVs (15)                                       │
│  ┌─────────────────────────────────────────────────────────┐
│  │ MV ID     │ Utility │ Storage │ Used By │ Status       │
│  ├───────────┼─────────┼─────────┼─────────┼──────────────┤
│  │ leaf_101  │ 150.5   │ 5.2 MB  │ 12 Q    │ ✅ Final     │
│  │ leaf_99   │ 145.3   │ 4.8 MB  │ 15 Q    │ ✅ Final     │
│  │ leaf_100  │ 132.1   │ 3.9 MB  │ 8 Q     │ ✅ Final     │
│  │ ...       │ ...     │ ...     │ ...     │ ...          │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  🔎 MV Details (Click on MV from the list)                 │
│  ┌─────────────────────────────────────────────────────────┐
│  │  MV: leaf_101 (company_name_mv)                         │
│  │                                                          │
│  │  📊 Metrics                                             │
│  │  Utility:           150.5                               │
│  │  Storage Size:      5.2 MB                              │
│  │  Maintenance Cost:  12.3                                │
│  │  Used by Queries:   12                                  │
│  │                                                          │
│  │  🔗 Usage Details                                       │
│  │  - Query 1a (position 3)                                │
│  │  - Query 2b (position 5)                                │
│  │  - Query 3c (position 2)                                │
│  │  ...                                                     │
│  │                                                          │
│  │  📝 SQL Definition                                      │
│  │  CREATE MATERIALIZED VIEW leaf_101 AS                   │
│  │  SELECT id, name, country_code                          │
│  │  FROM company_name                                      │
│  │  WHERE (country_code <> '[pl]') AND                     │
│  │        (name LIKE '%Film%' OR name LIKE '%Warner%');    │
│  │                                                          │
│  │  [📋 Copy SQL]  [🗑️ Drop MV]  [🔄 Refresh MV]          │
│  └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

**機能:**
- MV選択プロセスの可視化（Sankey diagram）
- Utility分布の表示
- ストレージ使用量の分析
- 個別MVの詳細情報
- SQL定義の表示・コピー
- MV管理機能（Drop, Refresh）

---

### 5. 設定画面

**レイアウト:**
```
┌─────────────────────────────────────────────────────────────┐
│  ⚙️ System Settings                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🗄️ Database Configuration                                 │
│  ┌─────────────────────────────────────────────────────────┐
│  │ Host:       [localhost           ]                      │
│  │ Port:       [5432                ]                      │
│  │ Database:   [imdbload            ]                      │
│  │ User:       [postgres            ]                      │
│  │ Password:   [••••••••            ]                      │
│  │ Timeout:    [1800                ] seconds              │
│  │                                                          │
│  │ [🔗 Test Connection]                                    │
│  │ Status: ✅ Connected                                    │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  📂 Path Configuration                                      │
│  ┌─────────────────────────────────────────────────────────┐
│  │ Output Dir:     [Output/             ] [📂 Browse]     │
│  │ Queries Dir:    [dataset/RED_JSON/   ] [📂 Browse]     │
│  │ SQL Dir:        [dataset/RED_SQL/    ] [📂 Browse]     │
│  │ Workloads Dir:  [Output/RED_WORKLOADS] [📂 Browse]     │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  🎨 UI Customization                                        │
│  ┌─────────────────────────────────────────────────────────┐
│  │ Theme:                                                   │
│  │ ○ Light  ● Dark  ○ Auto                                │
│  │                                                          │
│  │ Primary Color:  [#667eea] 🎨                            │
│  │                                                          │
│  │ Chart Style:                                             │
│  │ ○ Plotly  ● Seaborn  ○ Matplotlib                      │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  🔧 Advanced Options                                        │
│  ┌─────────────────────────────────────────────────────────┐
│  │ ☑ Enable debug logging                                 │
│  │ ☑ Auto-save experiment results                          │
│  │ ☑ Cache query parser                                    │
│  │ ☐ Enable performance profiling                          │
│  │                                                          │
│  │ Max concurrent experiments: [1 ▼]                       │
│  │ Auto-refresh interval:     [5 ▼] seconds               │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  📥 Configuration Management                                │
│  [💾 Save Settings]  [🔄 Reset to Default]  [📤 Export]   │
└─────────────────────────────────────────────────────────────┘
```

**機能:**
- データベース接続設定
- パス設定
- UIカスタマイズ
- 詳細オプション
- 設定の保存・読み込み・エクスポート

---

## 🔧 実装詳細

### Phase 1: 基本構造（Week 1）

#### 1.1 プロジェクトセットアップ

**タスク:**
- [ ] ディレクトリ構造作成
- [ ] 依存パッケージのインストール
- [ ] Streamlit設定ファイル作成
- [ ] 基本的なナビゲーション実装

**成果物:**
```python
# dashboard/app.py
import streamlit as st

st.set_page_config(
    page_title="MV Optimization Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS読み込み
with open('dashboard/styles/main.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

st.title("🚀 MV Query Optimization Dashboard")
st.markdown("Welcome to the Materialized View Optimization Dashboard")
```

#### 1.2 実験実行ロジックの統合

**タスク:**
- [ ] `ExperimentRunner` クラス実装
- [ ] `run_experiment.py` のラッパー作成
- [ ] セッション状態管理の実装
- [ ] プログレスバー統合

**成果物:**
```python
# dashboard/components/experiment_runner.py
import streamlit as st
from pathlib import Path
import threading
import queue
from typing import Dict, List, Optional

class ExperimentRunner:
    def __init__(self):
        self.is_running = False
        self.current_phase = None
        self.progress = 0
        self.log_queue = queue.Queue()
        
    def run_experiment(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict
    ):
        """Run experiment in background thread"""
        thread = threading.Thread(
            target=self._run_experiment_thread,
            args=(algorithms, storage_limit_mb, phases, settings)
        )
        thread.start()
        
    def _run_experiment_thread(self, ...):
        """Background execution thread"""
        # Import existing run_experiment logic
        from scripts.run_experiment import run_ilp_optimization
        # Execute with callbacks for progress updates
```

#### 1.3 ホーム画面の実装

**タスク:**
- [ ] アルゴリズム選択UI
- [ ] フェーズ選択UI
- [ ] 実行ボタンとロジック
- [ ] リアルタイム進行状況表示

---

### Phase 2: 可視化機能（Week 2）

#### 2.1 結果分析画面

**タスク:**
- [ ] 結果読み込みロジック
- [ ] Plotlyグラフの実装
  - アルゴリズム比較棒グラフ
  - Utility vs Storage 散布図
  - フェーズ実行時間スタックバー
- [ ] メトリクスカード表示
- [ ] エクスポート機能

**成果物:**
```python
# dashboard/components/visualizations.py
import plotly.graph_objects as go
import plotly.express as px

def create_algorithm_comparison_chart(results: List[Dict]) -> go.Figure:
    """Create algorithm comparison bar chart"""
    fig = go.Figure()
    
    algorithms = [r['algorithm'] for r in results]
    num_mvs = [len(r['selected_views']) for r in results]
    utilities = [r['total_utility'] for r in results]
    
    fig.add_trace(go.Bar(
        x=algorithms,
        y=num_mvs,
        name='Number of MVs',
        marker_color='rgb(102, 126, 234)'
    ))
    
    fig.update_layout(
        title='Algorithm Comparison',
        xaxis_title='Algorithm',
        yaxis_title='Metric Value',
        template='plotly_white'
    )
    
    return fig

def create_utility_storage_scatter(results: List[Dict]) -> go.Figure:
    """Create utility vs storage scatter plot"""
    fig = px.scatter(
        x=[r['total_storage'] / (1024**3) for r in results],
        y=[r['total_utility'] for r in results],
        text=[r['algorithm'] for r in results],
        labels={'x': 'Storage (GB)', 'y': 'Total Utility'}
    )
    
    fig.update_traces(
        marker=dict(size=12, line=dict(width=2, color='white')),
        textposition='top center'
    )
    
    return fig
```

#### 2.2 クエリ分析画面

**タスク:**
- [ ] クエリリスト表示
- [ ] パフォーマンスヒートマップ
- [ ] 実行プランビジュアライゼーション（Graphviz）
- [ ] ドリルダウン機能

**成果物:**
```python
# dashboard/components/visualizations.py
import graphviz

def create_execution_plan_tree(explain_json: Dict, mv_info: Dict) -> graphviz.Digraph:
    """Create execution plan tree visualization"""
    dot = graphviz.Digraph(
        comment='Execution Plan',
        format='svg'
    )
    dot.attr(rankdir='TB')
    dot.attr('node', shape='box', style='rounded,filled')
    
    # Parse EXPLAIN JSON and build tree
    # Color nodes based on MV usage
    
    return dot
```

#### 2.3 MV Explorer 画面

**タスク:**
- [ ] MV選択フロー（Sankey diagram）
- [ ] Utility分布グラフ
- [ ] ストレージ使用量グラフ
- [ ] MVリストと詳細表示

---

### Phase 3: 高度な機能（Week 3）

#### 3.1 インタラクティブ機能

**タスク:**
- [ ] クエリフィルタリング
- [ ] MVサーチ機能
- [ ] 複数実験の比較
- [ ] カスタムクエリの実行

#### 3.2 設定管理

**タスク:**
- [ ] 設定画面の実装
- [ ] 設定の永続化（YAML）
- [ ] データベース接続テスト
- [ ] テーマカスタマイズ

#### 3.3 エクスポートとレポート

**タスク:**
- [ ] CSV/JSONエクスポート
- [ ] HTMLレポート生成
- [ ] グラフのPNG/SVGエクスポート
- [ ] 実験結果のアーカイブ

---

## 📊 データフロー

```
User Input (Streamlit UI)
    ↓
ExperimentRunner
    ↓
run_experiment.py (既存ロジック)
    ↓
├─ QueryParser
├─ OptimizerFactory
├─ MaterializedViewManager
└─ QueryRewriter
    ↓
Results (JSON/Pickle)
    ↓
ResultLoader
    ↓
Visualization Components
    ↓
Streamlit Display
```

---

## 🎯 成功指標

### 機能要件
- ✅ CLIから移行した全機能が利用可能
- ✅ リアルタイムな実行進捗表示
- ✅ 複数アルゴリズムの並列比較
- ✅ クエリレベルの詳細分析
- ✅ MV選択プロセスの可視化

### 非機能要件
- ✅ レスポンス時間 < 3秒（通常操作）
- ✅ 実験実行中もUIが応答
- ✅ 100クエリ以上でも快適に動作
- ✅ ブラウザ互換性（Chrome, Firefox, Safari）

### ユーザビリティ
- ✅ 初回利用者が30分以内に実験実行可能
- ✅ 直感的なナビゲーション
- ✅ エラーメッセージが明確
- ✅ ヘルプドキュメントの統合

---

## 📦 必要なパッケージ

### requirements-dashboard.txt
```txt
# Core
streamlit>=1.32.0
streamlit-option-menu>=0.3.6

# Visualization
plotly>=5.18.0
graphviz>=0.20.1
matplotlib>=3.10.1
seaborn>=0.13.0

# Data Processing
pandas>=2.2.3
numpy>=2.2.4

# File Handling
pyyaml>=6.0
python-dotenv>=1.0.0

# Utilities
watchdog>=4.0.0
psutil>=5.9.0
```

---

## 🚀 デプロイメント

### ローカル開発
```bash
# 依存パッケージのインストール
pip install -r requirements-dashboard.txt

# ダッシュボードの起動
streamlit run dashboard/app.py

# 自動リロードを有効にして起動
streamlit run dashboard/app.py --server.runOnSave true
```

### Streamlit Cloud デプロイ
```yaml
# .streamlit/config.toml
[server]
headless = true
port = 8501

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#667eea"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

---

## 📚 参考資料

### Streamlit公式ドキュメント
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Streamlit Gallery](https://streamlit.io/gallery)
- [Streamlit Components](https://streamlit.io/components)

### 可視化ライブラリ
- [Plotly Python](https://plotly.com/python/)
- [Graphviz Python](https://graphviz.readthedocs.io/)

### ベストプラクティス
- [Streamlit Best Practices](https://docs.streamlit.io/library/advanced-features/performance)
- [Caching Guide](https://docs.streamlit.io/library/advanced-features/caching)

---

## 🔄 更新履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2025-11-18 | 初版作成 |

---

## 👥 責任者

- **計画立案**: AI Assistant
- **実装**: To be assigned
- **レビュー**: To be assigned

---

## 📝 TODO

### 即時実施項目
- [ ] プロジェクト構造の作成
- [ ] 依存パッケージのインストール
- [ ] 基本的なStreamlitアプリの起動確認

### 次のステップ
- [ ] Phase 1の実装開始
- [ ] UIプロトタイプの作成
- [ ] ユーザーフィードバックの収集
