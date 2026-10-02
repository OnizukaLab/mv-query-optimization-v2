# 修正プラン

## フェーズごと

### パースフェーズ
それぞれのワークロードをパースする。
例えばredbenchのワークロードをパースする時、それぞれのクエリは複数回現る場合があり、その分frequecyをとる設計にしてたと思う。例えばクエリaが5回現れてたらクエリa単体の利得(更新コストとインデックス作成コストを引いた利得よ)を5倍にするなど（それぞれのサブクエリの利得を5倍）。それで合ってると思うけども。
そのようにパースできてるか確認して。

### 最適化フェーズ
パースした結果を元に最適化で、例えばredbenchのjobのクエリだけを最初から対象にしていたら、純粋に83このクエリを最適化すれば良い。

### 実体化ビュー作成　&　クエリ書き換え
最適化結果を元に実行

### ベンチマーク実行
対象にしてたワークロードを実行
例えばredbenchを元にしてたらグループごとに実行して結果を出力。クエリも複数回実行するということになる。

---

## 現状の実装確認結果

### ✅ パースフェーズ - OK
**正しく実装されている**

`src/core/query_parser.py`の`convert_node()`メソッドで、frequencyがcostに掛けられている：

```python
# Line 427-429, 487-489
"cost": cost * frequency,
"original_cost": original_cost * frequency,
```

`src/utils/legacy.py`の`get_red_queries()`で、RedBenchワークロードCSVからクエリの出現回数をカウント：

```python
if query_path not in query_paths:
    query_paths.append(query_path)
    query_count[query_path] = 1
else:
    query_count[query_path] += 1  # 複数回出現をカウント
```

### ✅ 最適化フェーズ - OK
パースした結果（frequency込みのcost）を使って最適化するので問題なし。

### ✅ 実体化ビュー作成 & クエリ書き換え - OK
最適化結果を元に実行するので問題なし。

### ❌ ベンチマークフェーズ - 問題あり

**現状の`run_experiment.py`のベンチマーク**:
- 書き換えたクエリを**1回ずつ**実行するだけ
- グループ別の集計なし
- RedBenchワークロードの重複実行なし

**`run_redbench_workload.py`のgroupモード**:
- グループ（変動性バケット）ごとに実行・集計
- 同じクエリを複数回実行（ワークロードの重複を反映）
- これが本来やりたいベンチマーク

---

## 修正案

### 案1: `run_experiment.py`のベンチマークフェーズを拡張

`run_experiment.py`に`--benchmark-mode`オプションを追加:

```
--benchmark-mode simple   # 現在の動作（各クエリ1回）
--benchmark-mode redbench # RedBenchワークロードに従って実行（グループ別、重複あり）
```

**メリット**: 1つのスクリプトで完結
**デメリット**: スクリプトが複雑化

### 案2: ベンチマークフェーズをスキップして`run_redbench_workload.py`を使う（推奨）

```bash
# MV最適化（ベンチマークなし）
python scripts/run_experiment.py --algorithms normal --phases query_parsing optimization sql_generation mv_creation query_rewriting

# ベンチマーク実行（RedBenchワークロード）
python scripts/run_redbench_workload.py --mode group --algorithm normal
```

**メリット**: 
- 各スクリプトがシンプル
- 既存の`run_redbench_workload.py`のgroupモードをそのまま活用
- 柔軟性が高い（ベンチマークだけ再実行可能）

**デメリット**: 2つのコマンドが必要

### 案3: ダッシュボードで統合

ダッシュボードから両方のスクリプトを呼び出せるようにする：
1. 「Run Experiment」ボタン → `run_experiment.py`（ベンチマークフェーズOFF）
2. 「Run Benchmark」ボタン → `run_redbench_workload.py --mode group`

---

## 修正案（改訂版）

### 案: `run_experiment.py`のベンチマークフェーズで`run_redbench_workload.py`を呼び出す

`run_experiment.py`のベンチマークフェーズで、内部的に`run_redbench_workload.py`の機能を呼び出す。

#### 方法1: サブプロセスとして呼び出す

```python
# run_experiment.py のベンチマークフェーズ
import subprocess

if settings.execution.should_run_phase('benchmark'):
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "run_redbench_workload.py"),
        "--workload", workload_type,
        "--algorithm", ilp_type,
        "--output", str(benchmark_dir / "benchmark_results.json")
    ]
    subprocess.run(cmd, check=True)
```

**メリット**: 実装が簡単、既存コードをそのまま活用
**デメリット**: サブプロセスのオーバーヘッド、エラーハンドリングが複雑

#### 方法2: 共通モジュールとして関数を呼び出す（推奨）

`run_redbench_workload.py`のベンチマーク実行ロジックを`src/benchmark/`に移動し、両方のスクリプトから呼び出す。

```
src/benchmark/
├── __init__.py
├── query_executor.py      # 既存
├── workload_runner.py     # 新規: ワークロード実行ロジックを移動
```

```python
# run_experiment.py のベンチマークフェーズ
from src.benchmark.workload_runner import run_workload_benchmark

if settings.execution.should_run_phase('benchmark'):
    results = run_workload_benchmark(
        workload=workload_type,  # "job", "ceb", "redbench", "redbench-job", "redbench-ceb"
        algorithm=ilp_type,
        settings=settings
    )
```

**メリット**: 
- コードの重複なし
- エラーハンドリングが統一
- テストしやすい

**デメリット**: リファクタリングが必要

---

## 推奨: 方法2（共通モジュール化）

### 引数の統一

#### `--workload-type` オプション（パース〜最適化〜書き換えで使用）

既に実装済み。最適化対象のクエリセットを選択：

| 値 | 説明 |
|----|------|
| `job` | JOBの全113クエリ |
| `ceb` | CEBの全クエリ |
| `redbench` | RedBenchフルワークロード（JOB+CEB混在） |
| `redbench-job` | RedBenchのJOBクエリのみ（83クエリ） |
| `redbench-ceb` | RedBenchのCEBクエリのみ |

#### ベンチマークの実行方法

**最適化とベンチマークは同じ`--workload-type`を使う**ことで一貫性を保つ：

| workload-type | パース対象 | ベンチマーク実行方法 |
|---------------|-----------|---------------------|
| `job` | 全113 JOBクエリ | 各クエリ1回実行 |
| `ceb` | 全CEBクエリ | 各クエリ1回実行 |
| `redbench` | RedBench全体 | グループ別に実行（重複あり） |
| `redbench-job` | RedBench JOB 83クエリ | グループ別に実行（重複あり） |
| `redbench-ceb` | RedBench CEBクエリ | グループ別に実行（重複あり） |

**ポイント**: 
- `job`/`ceb` → シンプル実行（各クエリ1回）
- `redbench*` → RedBenchワークロードに従って実行（グループ別、重複あり）

---

### 実装計画

#### Step 1: `src/benchmark/workload_runner.py` を作成
- `run_redbench_workload.py`から実行ロジックを移動
- 共通インターフェースを作成

```python
def run_workload_benchmark(
    workload_type: str,  # "job", "ceb", "redbench", "redbench-job", "redbench-ceb"
    algorithm: str,
    settings: Settings,
    output_dir: Path = None,
    verbose: bool = False,
    warmup: bool = True
) -> dict:
    """ワークロードに応じたベンチマークを実行"""
    
    if workload_type in ["job", "ceb"]:
        # シンプル実行: 各クエリ1回
        return run_simple_benchmark(...)
    else:
        # RedBench実行: グループ別、重複あり
        return run_redbench_benchmark(...)
```

#### Step 2: `run_experiment.py` を修正
- ベンチマークフェーズで`workload_runner`を呼び出す
- `--workload-type`に応じて適切な実行方法を自動選択

#### Step 3: `run_redbench_workload.py` を修正
- `workload_runner`を呼び出すラッパーに変更
- 既存のコマンドライン互換性は維持
- `--mode job/group/ceb`は`--workload redbench-job/redbench/ceb`に置き換え

#### Step 4: ダッシュボードを修正
- 既存の`--workload-type`設定でベンチマーク方法も自動決定

---

### コマンド例（修正後）

```bash
# RedBench JOBクエリで最適化＆ベンチマーク（グループ別実行）
python scripts/run_experiment.py --algorithms normal --workload-type redbench-job

# 全JOBクエリで最適化＆ベンチマーク（シンプル実行）
python scripts/run_experiment.py --algorithms normal --workload-type job

# RedBench全体で最適化＆ベンチマーク（JOB+CEB混在、グループ別）
python scripts/run_experiment.py --algorithms normal --workload-type redbench

# ベンチマークだけ再実行したい場合
python scripts/run_redbench_workload.py --workload redbench-job --algorithm normal
```

---

### ダッシュボードUI（変更なし）

既に実装した`--workload-type`選択UIがそのまま使える：

```
📂 Workload Configuration
├── Workload Type: [redbench-job ▼]
│   ├── job - All 113 JOB queries
│   ├── ceb - All CEB queries  
│   ├── redbench - Full workload (JOB + CEB mixed)
│   ├── redbench-job - Only JOB queries from RedBench (83 queries)  ← デフォルト
│   └── redbench-ceb - Only CEB queries from RedBench
```

---

## まとめ

| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| オプション名 | `--benchmark-mode` | なし（`--workload-type`で自動決定） |
| 引数 | `simple`/`job`/`group` | `job`/`ceb`/`redbench`/`redbench-job`/`redbench-ceb` |
| ベンチマーク | 各クエリ1回のみ | workload-typeに応じて自動選択 |
| コマンド | 2つ必要 | 1つで完結 |
| 実装 | 別々のコード | 共通モジュール |