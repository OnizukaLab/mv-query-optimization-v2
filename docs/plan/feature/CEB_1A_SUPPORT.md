# CEB 1aクエリ対応計画

## 1. 背景と目的

### 1.1 現状
現在のシステムはJOB (Join Order Benchmark) のクエリのみに対応しています。CEBクエリを実行するには以下の拡張が必要です。

### 1.2 データ構造の違い

| 項目 | JOB | CEB |
|------|-----|-----|
| クエリSQL | `dataset/RED_SQL/job/*.sql` | `dataset/RED_SQL/ceb/{1a,2a,...}/*.sql` |
| クエリJSON | `dataset/RED_JSON/job/*.json` | **存在しない** ❌ |
| クエリ数 | 113個 | 1a: 3,000個、全体: 数万個 |
| 構造 | フラット | サブディレクトリ構造 |

### 1.3 目標
まずはCEB 1aクエリのみを対象として、システムの拡張を行う。

---

## 2. 主要な課題

### 2.1 ❌ EXPLAIN JSON が存在しない
**最も重要な問題**: 現在のシステムは PostgreSQL の `EXPLAIN (FORMAT JSON)` 出力を解析してMV最適化を行う設計になっています。

- JOB: `dataset/RED_JSON/job/*.json` が存在（113個）
- CEB: JSONファイルが存在しない

**対応策**:
1. CEB 1a用のEXPLAIN JSONを生成するスクリプトを作成
2. `dataset/RED_JSON/ceb/1a/` にJSON ファイルを保存

### 2.2 ディレクトリ構造の違い
- JOB: `RED_SQL/job/1a.sql`, `1b.sql`, ...（フラット）
- CEB: `RED_SQL/ceb/1a/1a1.sql`, `1a2.sql`, ...（サブディレクトリ）

### 2.3 クエリ数のスケール
- JOB: 113クエリ
- CEB 1a: 3,000クエリ（最初のテストには多い可能性あり）

### 2.4 SQL構文の違い（GROUP BY / ORDER BY）

CEBクエリの一部には `GROUP BY` や `ORDER BY` 句が含まれています。

| テンプレート | GROUP BY/ORDER BY | 既存パーサー |
|-------------|-------------------|-------------|
| **1a** | **なし** | ✅ 対応済み |
| 2a〜8a | なし | ✅ 対応済み |
| 3b, 9a, 9b, 10a, 11a, 11b | **あり** | ⚠️ 一部対応 |

**現在の実装状況**:
- `src/rewrite/query_rewriter.py`:
  - `GROUP BY` の抽出・再構築: ✅ 実装済み
  - `ORDER BY` の抽出・再構築: ❌ **未実装**
- `src/rewrite/sql_parser.py`:
  - `GROUP BY` / `ORDER BY` 対応の `reconstruct_query()`: ✅ 実装済み

**結論**: CEB 1aは GROUP BY/ORDER BY がないため、現状のパーサーで対応可能。

## 3. 拡張計画

### Phase 1: EXPLAIN JSON生成スクリプトの作成

#### 3.1.1 既存スクリプトの参照
`scripts/get_explain_json.py` を参考に、CEB用スクリプトを作成。

#### 3.1.2 新規スクリプト `scripts/get_explain_json_ceb.py`

```python
#!/usr/bin/env python3
"""
CEBクエリのEXPLAIN (FORMAT JSON)を取得してRED_JSON/ceb/に保存するスクリプト
"""

import os
import json
import psycopg2
from pathlib import Path
import argparse

# データベース接続設定
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'imdbload',
    'user': 'postgres',
    'password': 'pass'
}

# パス設定
PROJECT_ROOT = Path(__file__).parent.parent
SQL_BASE_DIR = PROJECT_ROOT / "dataset" / "RED_SQL" / "ceb"
OUTPUT_BASE_DIR = PROJECT_ROOT / "dataset" / "RED_JSON" / "ceb"

def get_explain_json(cursor, sql_query):
    """クエリのEXPLAIN (FORMAT JSON)を取得"""
    explain_query = f"EXPLAIN (FORMAT JSON) {sql_query}"
    cursor.execute(explain_query)
    result = cursor.fetchone()[0]
    return result

def process_ceb_queries(cursor, template: str, limit: int = None):
    """指定したCEBテンプレート（例: 1a）のクエリを処理"""
    sql_dir = SQL_BASE_DIR / template
    output_dir = OUTPUT_BASE_DIR / template
    
    if not sql_dir.exists():
        print(f"❌ ディレクトリが存在しません: {sql_dir}")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    sql_files = sorted(sql_dir.glob("*.sql"))
    if limit:
        sql_files = sql_files[:limit]
    
    print(f"処理するクエリ数: {len(sql_files)}")
    
    success_count = 0
    error_count = 0
    
    for sql_file in sql_files:
        query_name = sql_file.stem
        output_file = output_dir / f"{query_name}.json"
        
        try:
            sql_query = sql_file.read_text().strip()
            if sql_query.endswith(';'):
                sql_query = sql_query[:-1]
            
            explain_result = get_explain_json(cursor, sql_query)
            
            with open(output_file, 'w') as f:
                json.dump(explain_result, f, indent=4)
            
            success_count += 1
            if success_count % 100 == 0:
                print(f"  進捗: {success_count}/{len(sql_files)}")
            
        except Exception as e:
            print(f"✗ {query_name}: {e}")
            error_count += 1
    
    print(f"完了: 成功={success_count}, エラー={error_count}")

def main():
    parser = argparse.ArgumentParser(description='CEB用EXPLAIN JSON生成')
    parser.add_argument('--template', '-t', default='1a', 
                        help='CEBテンプレート（例: 1a, 2a）')
    parser.add_argument('--limit', '-l', type=int, default=None,
                        help='処理するクエリ数の上限')
    args = parser.parse_args()
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Bitmap scan有効化
    cursor.execute("SET enable_bitmapscan = on;")
    
    process_ceb_queries(cursor, args.template, args.limit)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
```

#### 3.1.3 使用方法

```bash
# CEB 1a の全クエリを処理
python scripts/get_explain_json_ceb.py --template 1a

# テスト用: 最初の100クエリのみ処理
python scripts/get_explain_json_ceb.py --template 1a --limit 100
```

---

### Phase 2: クエリ取得ロジックの拡張

#### 3.2.1 `src/utils/legacy.py` に追加

```python
def get_all_ceb_queries(source_path: str, template: str = "1a") -> tuple[list[str], dict[str, int]]:
    """
    Get all CEB query JSON files from the directory.
    
    Args:
        source_path: Path to the JSON files directory (RED_JSON)
        template: CEB template to load (e.g., "1a", "2a")
        
    Returns:
        Tuple of (query_paths, query_count_dict)
    """
    query_paths = []
    query_count = {}
    
    ceb_dir = Path(source_path) / "ceb" / template
    if not ceb_dir.exists():
        print(f"Warning: CEB directory not found: {ceb_dir}")
        return [], {}
    
    for json_file in sorted(ceb_dir.glob("*.json")):
        query_path = str(json_file)
        query_paths.append(query_path)
        query_count[query_path] = 1
    
    return query_paths, query_count
```

#### 3.2.2 `src/core/query_parser.py` の修正

```python
# query_parse メソッド内の修正

from ..utils.legacy import get_red_queries, get_all_job_queries, get_all_ceb_queries, natural_sort_key

def query_parse(self, q_num: int, path: str, insert_query: int) -> None:
    workloads_dir = self.settings.benchmark.workloads_dir
    benchmark_type = self.settings.benchmark.type
    query_selection_mode = self.settings.benchmark.query_selection_mode
    
    # Get query files with frequencies based on selection mode
    if query_selection_mode == "all_job":
        print(f"Query selection mode: all_job (using all JOB queries)")
        files, file_freq = get_all_job_queries(path)
    elif query_selection_mode == "all_ceb":
        # 新規追加: CEB全クエリモード
        ceb_template = self.settings.benchmark.ceb_template  # 例: "1a"
        print(f"Query selection mode: all_ceb (using all CEB {ceb_template} queries)")
        files, file_freq = get_all_ceb_queries(path, ceb_template)
    else:
        # Use RedBench workload-based selection (default)
        print(f"Query selection mode: redbench (using workload-based queries)")
        get_ceb = benchmark_type == "ceb"
        files, file_freq = get_red_queries(path, workloads_dir, get_ceb)
    
    # 以降は同じ...
```

---

### Phase 3: 設定の拡張

#### 3.3.1 `config/settings.py` に追加

```python
@dataclass
class BenchmarkSettings:
    type: str = "job"
    workloads_dir: str = "dataset/redbench"
    query_selection_mode: str = "redbench"
    ceb_template: str = "1a"  # 新規追加
```

#### 3.3.2 `config/default.yaml` に追加

```yaml
benchmark:
  type: "job"
  workloads_dir: "dataset/redbench"
  query_selection_mode: "redbench"
  ceb_template: "1a"  # 新規追加
```

---

### Phase 4: コマンドライン引数の拡張

#### 3.4.1 `scripts/run_experiment.py` の修正

```python
parser.add_argument(
    "--workload-type",
    type=str,
    choices=["job", "ceb", "ceb-1a", "redbench", "redbench-job", "redbench-ceb"],
    default="redbench-job",
    help="Workload type to use"
)

parser.add_argument(
    "--ceb-template",
    type=str,
    default="1a",
    help="CEB template to use (e.g., 1a, 2a, 3a)"
)

# main() 内の処理
if args.workload_type == 'ceb-1a':
    settings.benchmark.type = 'ceb'
    settings.benchmark.query_selection_mode = 'all_ceb'
    settings.benchmark.ceb_template = '1a'
```

---

### Phase 5: ベンチマーク実行の拡張

#### 3.5.1 `src/benchmark/workload_runner.py` の修正

CEB用のシンプル実行モードを追加:

```python
def run_simple_benchmark(
    executor: QueryExecutor,
    algorithm: str,
    query_dir: Path,
    timeout_minutes: int = 30,
    verbose: bool = False,
    warmup: bool = True,
    logger: logging.Logger = None
) -> dict:
    """シンプルベンチマーク実行（各クエリ1回）
    
    JOBとCEB両方に対応。
    """
    # query_dir が ceb/1a のようなサブディレクトリの場合も対応
    sql_files = sorted(query_dir.glob("*.sql"))
    
    # ... 実行ロジック
```

---

## 4. 実装優先順位

### ✅ Step 1: EXPLAIN JSON生成（必須・最優先）
1. `scripts/get_explain_json_ceb.py` を作成
2. CEB 1aのJSON生成を実行（3,000クエリ、推定所要時間: 10-30分）

### Step 2: クエリ取得ロジック
1. `get_all_ceb_queries()` 関数を追加
2. `query_parser.py` の分岐を追加

### Step 3: 設定とCLI
1. `settings.py` にCEB設定追加
2. `run_experiment.py` に `--ceb-template` オプション追加

### Step 4: テスト実行
```bash
# 1. JSON生成
python scripts/get_explain_json_ceb.py --template 1a --limit 100

# 2. MV最適化実行
python scripts/run_experiment.py --workload-type ceb-1a --algorithms normal
```

---

## 5. 注意事項

### 5.1 スケーラビリティ
- CEB 1aは3,000クエリあり、JOBの113クエリより大幅に多い
- 最初は `--limit` オプションで100-500クエリでテストを推奨

### 5.2 メモリ使用量
- 3,000クエリのパースにはメモリが必要
- 必要に応じてバッチ処理を検討

### 5.3 実行時間
- EXPLAIN JSON生成: 3,000クエリで10-30分程度（DB性能による）
- MV最適化: クエリ数に比例して増加

### 5.4 クエリの特性とSQL構文の違い

#### 5.4.1 CEBテンプレート別のSQL構文

| テンプレート | クエリ数 | GROUP BY/ORDER BY | 複雑度 |
|-------------|---------|-------------------|-------|
| **1a** | 3,000 | **なし** ✅ | 低 |
| 2a | 888 | なし | 低 |
| 2b | 500 | なし | 低 |
| 2c | 298 | なし | 低 |
| 3a | 1,383 | なし | 低 |
| **3b** | 256 | **あり** ⚠️ | 中 |
| 4a | 516 | なし | 低 |
| 5a | 1,014 | なし | 低 |
| 6a | 465 | なし | 低 |
| 7a | 167 | なし | 低 |
| 8a | 515 | なし | 低 |
| **9a** | 2,247 | **あり** ⚠️ | 中 |
| **9b** | 537 | **あり** ⚠️ | 中 |
| **10a** | 1,019 | **あり** ⚠️ | 中 |
| **11a** | 491 | **あり** ⚠️ | 中 |
| **11b** | 350 | **あり** ⚠️ | 中 |

**結論: CEB 1aは GROUP BY/ORDER BY がないため、既存のパーサーで対応可能！**

#### 5.4.2 CEB 1aクエリの特徴（サンプル: `1a1.sql`）
```sql
SELECT COUNT(*) FROM title as t,
kind_type as kt,
movie_info as mi1,
info_type as it1,
movie_info as mi2,
info_type as it2,
cast_info as ci,
role_type as rt,
name as n
WHERE
t.id = ci.movie_id
AND t.id = mi1.movie_id
...
```
- テーブル結合: 9テーブル
- 同一テーブルの複数JOIN（`movie_info as mi1`, `movie_info as mi2`）
- フィルタ条件の変動（`mi1.info IN (...)`）
- **GROUP BY/ORDER BY なし** ✅

これらの特性はJOBと類似しており、既存のパーサーで対応可能。

#### 5.4.3 GROUP BY/ORDER BY があるテンプレート（3b, 9a, 9b, 10a, 11a, 11b）

例: `3b/xxx.sql`
```sql
SELECT t.title, n.name, cn.name, COUNT(*)
FROM title as t, ...
WHERE ...
GROUP BY t.title, n.name, cn.name
ORDER BY COUNT(*) DESC
```

**現在のパーサーの問題点**:
1. `src/rewrite/query_rewriter.py` の `_parse_sql_parts()` は `group_by` を処理
2. ただし `order_by` は処理していない ❌
3. `_reconstruct_sql()` も `order_by` を出力しない

**将来の対応が必要**:
- `_parse_sql_parts()` に `order_by` の抽出を追加
- `_reconstruct_sql()` に `ORDER BY` 句の再構築を追加
- MVを使った書き換え時に `ORDER BY` の参照を正しく更新

---

## 6. 将来の拡張

CEB 1aが動作確認できたら、以下を順次対応:

1. **CEB 2a, 3a, ..., 11b** の追加
2. **RedBench CEB統合**: `redbench-ceb` モードでCEBクエリをワークロードベースで実行
3. **ダッシュボード対応**: CEB選択UIの追加

---

## 7. 参考リンク

- [CEB (Cardinality Estimation Benchmark)](https://github.com/learnedsystems/CEB)
- 既存ドキュメント: `docs/plan/refactor/CHANGE_WORKLOAD.md`
- 既存スクリプト: `scripts/get_explain_json.py`
