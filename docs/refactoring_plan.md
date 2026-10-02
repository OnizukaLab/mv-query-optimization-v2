# プロジェクト構造再編成計画

## 1. 現在の問題点

### 1.1 ファイル構造の問題
- ✗ ルートディレクトリに40以上のPythonファイルとシェルスクリプトが混在
- ✗ 責務が不明確（1ファイルに複数の機能が混在）
- ✗ テストコードが存在しない
- ✗ 設定がハードコード（`GET_CEB`などのグローバル変数）
- ✗ 命名規則の不統一（`compare_bata.py`のタイポなど）

### 1.2 コード品質の問題
- ✗ 型ヒントがない
- ✗ ドキュメント文字列が不足
- ✗ エラーハンドリングが不十分
- ✗ コードの重複が多い（各ILPアルゴリズムで類似コード）
- ✗ 循環依存（`query_parse_beta.py`がILPモジュールをimport）

### 1.3 依存関係の問題
```
query_parse_beta.py
  ↓
ILP_*_beta.py (5つのILPアルゴリズム)
  ↑
compare_bata.py
  ↓
query_parse_beta.py  # 循環依存
```

## 2. 新しいプロジェクト構造案

### 2.1 提案する構造

```
mv-query-optimization/
├── README.md
├── pyproject.toml              # 新規: プロジェクト設定（Poetry/setuptools）
├── setup.py                    # 新規: パッケージ設定
├── requirements.txt
├── .gitignore
├── .env.example                # 新規: 環境変数テンプレート
│
├── config/                     # 新規: 設定ファイル
│   ├── __init__.py
│   ├── settings.py            # 設定管理クラス
│   ├── default.yaml           # デフォルト設定
│   └── experiments/           # 実験別設定
│       ├── job_benchmark.yaml
│       └── ceb_benchmark.yaml
│
├── src/                        # 新規: メインソースコード
│   ├── __init__.py
│   │
│   ├── core/                   # コアドメインロジック
│   │   ├── __init__.py
│   │   ├── query_manager.py   # QueryManagerクラス
│   │   ├── query_parser.py    # QueryParserクラス
│   │   └── models.py          # データモデル（dataclasses）
│   │
│   ├── optimization/           # ILP最適化アルゴリズム
│   │   ├── __init__.py
│   │   ├── base.py            # 基底クラス（共通ILP処理）
│   │   ├── normal.py          # Normal ILP
│   │   ├── bigsubs.py         # BigSubs ILP
│   │   ├── utility_capacity.py # Utility-Capacity ILP
│   │   ├── utility.py         # Utility ILP
│   │   ├── frequency.py       # Frequency ILP
│   │   └── factory.py         # アルゴリズム選択Factory
│   │
│   ├── rewrite/                # クエリ書き換え
│   │   ├── __init__.py
│   │   ├── query_rewriter.py  # クエリ書き換えロジック
│   │   ├── mv_generator.py    # MV生成SQL作成
│   │   └── sql_parser.py      # SQL解析ユーティリティ
│   │
│   ├── benchmark/              # ベンチマーク実行
│   │   ├── __init__.py
│   │   ├── executor.py        # クエリ実行
│   │   ├── workload.py        # ワークロード管理
│   │   └── metrics.py         # メトリクス収集
│   │
│   ├── database/               # DB接続・操作
│   │   ├── __init__.py
│   │   ├── connection.py      # DB接続管理
│   │   ├── mv_manager.py      # MV作成・削除
│   │   └── schema.py          # スキーマ情報
│   │
│   └── utils/                  # ユーティリティ
│       ├── __init__.py
│       ├── file_utils.py      # ファイル操作
│       ├── logging_utils.py   # ロギング設定
│       └── validators.py      # バリデーション
│
├── scripts/                    # 新規: 実行スクリプト
│   ├── run_experiment.py      # 実験実行メイン
│   ├── setup_database.py      # DB初期化
│   ├── generate_queries.py    # クエリ生成
│   └── analyze_results.py     # 結果分析
│
├── tests/                      # 新規: テストコード
│   ├── __init__.py
│   ├── conftest.py            # pytest設定
│   ├── unit/                  # ユニットテスト
│   │   ├── test_query_parser.py
│   │   ├── test_optimization.py
│   │   └── test_rewriter.py
│   ├── integration/           # 統合テスト
│   │   ├── test_experiment_flow.py
│   │   └── test_db_operations.py
│   └── fixtures/              # テストデータ
│       ├── sample_queries.json
│       └── expected_results.csv
│
├── data/                       # データファイル（既存）
│   ├── schema.sql
│   ├── setup.sql
│   ├── insert_queries.sql
│   └── triggers.sql
│
├── dataset/                    # ベンチマークデータセット（既存）
│   ├── RED_JSON/
│   ├── RED_SQL/
│   └── redbench/
│
├── output/                     # 実験結果出力（既存、名前変更）
│   ├── experiments/           # 実験ごとの結果
│   ├── logs/                  # ログファイル
│   └── artifacts/             # 中間生成物
│
├── docs/                       # ドキュメント
│   ├── project_overview.md
│   ├── refactoring_plan.md
│   ├── api/                   # API ドキュメント
│   │   └── README.md
│   └── experiments/           # 実験ノート
│       └── README.md
│
└── docker/                     # Docker関連（既存を整理）
    ├── Dockerfile
    ├── docker-compose.yml
    └── entrypoint.sh
```

### 2.2 主要な変更点

#### A. ソースコードの整理
| 現在のファイル | 新しい場所 | 変更内容 |
|--------------|-----------|---------|
| `query_parse_beta.py` | `src/core/query_parser.py`<br>`src/core/query_manager.py` | クラスを分離 |
| `ILP_*_beta.py` (5ファイル) | `src/optimization/` | 共通基底クラス化 |
| `query_rewrite_beta.py` | `src/rewrite/query_rewriter.py` | 機能ごとに分割 |
| `compare_bata.py` | `scripts/run_optimization.py` | 名前修正、CLI化 |
| `experiment.py` | `scripts/run_experiment.py` | 整理、設定外部化 |
| `utils.py` | `src/utils/`配下 | 機能別に分割 |
| `*.sh` | `scripts/` | Python化も検討 |

#### B. 設定の外部化
```yaml
# config/default.yaml
database:
  host: localhost
  port: 5432
  database: imdbload
  user: postgres
  timeout: 1800  # 30 minutes

optimization:
  storage_limit: 52428800  # 50MB in bytes
  insert_queries: 1000
  algorithms:
    - normal
    - bigsubs
    - utility_capacity
    - utility
    - frequency

benchmark:
  type: job  # or 'ceb'
  workloads_dir: Output/RED_WORKLOADS
  queries_dir: dataset/RED_JSON

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: output/logs/experiment.log
```

#### C. パッケージ管理
```toml
# pyproject.toml
[tool.poetry]
name = "mv-query-optimization"
version = "0.1.0"
description = "Materialized View Selection using ILP Optimization"
authors = ["OnizukaLab"]

[tool.poetry.dependencies]
python = "^3.10"
gurobipy = "^11.0.0"
sqlparse = "^0.4.4"
pyyaml = "^6.0"
psycopg2-binary = "^2.9"
pandas = "^2.0"
pydantic = "^2.0"

[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-cov = "^4.1"
black = "^23.0"
mypy = "^1.5"
ruff = "^0.1"

[tool.poetry.scripts]
mv-optimize = "scripts.run_experiment:main"
```

## 3. 実装計画

### Phase 1: 基盤整備（Week 1-2）

#### Step 1.1: プロジェクト構造の作成
- [ ] `src/`ディレクトリ構造の作成
- [ ] `config/`ディレクトリと設定ファイルの作成
- [ ] `tests/`ディレクトリの作成
- [ ] `pyproject.toml`の作成

#### Step 1.2: 設定管理システムの実装
- [ ] `config/settings.py`の実装
  - YAML読み込み
  - 環境変数オーバーライド
  - 設定バリデーション
- [ ] グローバル変数の削除（`GET_CEB`など）

#### Step 1.3: ロギングシステムの実装
- [ ] `src/utils/logging_utils.py`の実装
- [ ] 全ファイルで統一されたロギング

### Phase 2: コアモジュールのリファクタリング（Week 3-4）

#### Step 2.1: データモデルの定義
```python
# src/core/models.py
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

@dataclass
class QueryNode:
    """クエリプランのノード"""
    node_id: str
    node_type: str  # 'leaf' or 'non_leaf'
    total_cost: float
    size: int
    width: int
    
@dataclass
class LeafNode(QueryNode):
    """リーフノード（テーブルスキャン）"""
    operator: str
    table_name: str
    alias: str
    filter_condition: str
    
@dataclass
class NonLeafNode(QueryNode):
    """非リーフノード（JOIN等）"""
    child_ids: Tuple[str, ...]
    operator: str

@dataclass
class MaterializedView:
    """マテリアライズドビュー"""
    view_id: str
    node_id: str
    create_sql: str
    size: int
    maintenance_cost: float
    
@dataclass
class OptimizationResult:
    """最適化結果"""
    algorithm: str
    selected_views: List[MaterializedView]
    total_utility: float
    total_storage: int
    execution_time: float
```

#### Step 2.2: QueryManagerのリファクタリング
- [ ] `src/core/query_manager.py`に移動
- [ ] 型ヒントの追加
- [ ] docstringの追加
- [ ] メソッドの整理と命名改善

#### Step 2.3: QueryParserのリファクタリング
- [ ] `src/core/query_parser.py`に移動
- [ ] ILP依存の削除（循環依存解消）
- [ ] 型ヒントの追加
- [ ] テストコードの追加

### Phase 3: 最適化モジュールのリファクタリング（Week 5-6）

#### Step 3.1: 基底クラスの作成
```python
# src/optimization/base.py
from abc import ABC, abstractmethod
from typing import List, Tuple
import gurobipy as gp

class BaseILPOptimizer(ABC):
    """ILP最適化の基底クラス"""
    
    def __init__(self, query_manager, config):
        self.qm = query_manager
        self.config = config
        self.model = None
        
    @abstractmethod
    def initialize(self, **kwargs) -> List[int]:
        """初期解の生成（アルゴリズムごとに異なる）"""
        pass
        
    def build_ilp_model(self, candidates_i, candidates_j, **kwargs):
        """ILPモデルの構築（共通処理）"""
        self.model = gp.Model(f"{self.__class__.__name__}")
        self.model.Params.OutputFlag = 0
        # ... 共通のモデル構築処理
        
    def solve(self) -> Tuple[List[List[int]], List[int], float]:
        """ILPモデルの求解（共通処理）"""
        self.model.optimize()
        # ... 結果の取得
        
    def optimize(self, **kwargs) -> OptimizationResult:
        """最適化の実行（テンプレートメソッド）"""
        # 1. 初期化
        initial_solution = self.initialize(**kwargs)
        # 2. 近傍探索（必要に応じて）
        # 3. ILPモデル構築
        # 4. 求解
        # 5. 結果の整形
        pass
```

#### Step 3.2: 各アルゴリズムの実装
- [ ] `src/optimization/normal.py`
- [ ] `src/optimization/bigsubs.py`
- [ ] `src/optimization/utility_capacity.py`
- [ ] `src/optimization/utility.py`
- [ ] `src/optimization/frequency.py`

#### Step 3.3: Factoryパターンの実装
```python
# src/optimization/factory.py
from typing import Dict, Type
from .base import BaseILPOptimizer
from .normal import NormalOptimizer
from .frequency import FrequencyOptimizer
# ... 他のインポート

class OptimizerFactory:
    """最適化アルゴリズムのファクトリ"""
    
    _optimizers: Dict[str, Type[BaseILPOptimizer]] = {
        'normal': NormalOptimizer,
        'bigsubs': BigSubsOptimizer,
        'utility_capacity': UtilityCapacityOptimizer,
        'utility': UtilityOptimizer,
        'frequency': FrequencyOptimizer,
    }
    
    @classmethod
    def create(cls, algorithm: str, **kwargs) -> BaseILPOptimizer:
        if algorithm not in cls._optimizers:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        return cls._optimizers[algorithm](**kwargs)
```

### Phase 4: クエリ書き換えモジュール（Week 7）

#### Step 4.1: モジュール分割
- [ ] `src/rewrite/query_rewriter.py` - メインロジック
- [ ] `src/rewrite/mv_generator.py` - MV SQL生成
- [ ] `src/rewrite/sql_parser.py` - SQL解析ヘルパー

#### Step 4.2: インターフェースの明確化
```python
# src/rewrite/query_rewriter.py
from typing import List, Dict
from ..core.models import MaterializedView

class QueryRewriter:
    """クエリ書き換え管理"""
    
    def __init__(self, query_parser, config):
        self.parser = query_parser
        self.config = config
        
    def rewrite_query(
        self, 
        query_id: int, 
        selected_views: List[MaterializedView]
    ) -> str:
        """クエリを書き換え"""
        pass
        
    def rewrite_workload(
        self, 
        workload_path: str,
        selected_views: List[MaterializedView]
    ) -> Dict[str, str]:
        """ワークロード全体を書き換え"""
        pass
```

### Phase 5: データベース操作モジュール（Week 8）

#### Step 5.1: 接続管理
```python
# src/database/connection.py
import psycopg2
from contextlib import contextmanager
from typing import Iterator

class DatabaseConnection:
    """データベース接続管理"""
    
    def __init__(self, config):
        self.config = config
        self._conn = None
        
    @contextmanager
    def cursor(self) -> Iterator[psycopg2.extensions.cursor]:
        """カーソルのコンテキストマネージャ"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
```

#### Step 5.2: MV管理
```python
# src/database/mv_manager.py
from typing import List
from ..core.models import MaterializedView

class MaterializedViewManager:
    """マテリアライズドビュー管理"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        
    def create_view(self, view: MaterializedView) -> bool:
        """MVを作成"""
        pass
        
    def drop_view(self, view_id: str) -> bool:
        """MVを削除"""
        pass
        
    def list_views(self) -> List[str]:
        """既存のMVをリスト"""
        pass
```

### Phase 6: スクリプトとCLI（Week 9）

#### Step 6.1: メイン実験スクリプト
```python
# scripts/run_experiment.py
import click
from src.config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory

@click.command()
@click.option('--config', default='config/default.yaml', help='設定ファイル')
@click.option('--algorithm', multiple=True, help='実行するアルゴリズム')
@click.option('--output', default='output/experiments', help='出力ディレクトリ')
def main(config, algorithm, output):
    """実験メインスクリプト"""
    # 設定読み込み
    settings = Settings.from_yaml(config)
    
    # クエリパース
    parser = QueryParser(settings)
    parser.parse_workload()
    
    # 各アルゴリズムで最適化
    for algo in algorithm:
        optimizer = OptimizerFactory.create(algo, query_manager=parser.qm)
        result = optimizer.optimize()
        result.save(output)
        
if __name__ == '__main__':
    main()
```

### Phase 7: テストの追加（Week 10-11）

#### Step 7.1: ユニットテスト
- [ ] `tests/unit/test_query_parser.py`
- [ ] `tests/unit/test_optimization.py`
- [ ] `tests/unit/test_rewriter.py`

#### Step 7.2: 統合テスト
- [ ] `tests/integration/test_experiment_flow.py`
- [ ] `tests/integration/test_db_operations.py`

#### Step 7.3: テストカバレッジ
```bash
pytest --cov=src --cov-report=html
# 目標: 80%以上のカバレッジ
```

### Phase 8: ドキュメントと最終調整（Week 12）

#### Step 8.1: APIドキュメント
- [ ] すべてのパブリックメソッドにdocstring
- [ ] Sphinx等でドキュメント生成

#### Step 8.2: README更新
- [ ] 新しい構造に合わせて更新
- [ ] クイックスタートガイド
- [ ] 開発者向けガイド

## 4. 移行戦略

### 4.1 段階的移行（推奨）

**メリット:**
- リスクが低い
- 継続的に動作確認可能
- 途中で問題が見つかっても修正しやすい

**手順:**
1. 新しい構造を別ブランチで作成
2. モジュールごとに段階的に移行
3. 各段階で既存機能との互換性を確保
4. テストを書きながら移行
5. すべて完了後にマージ

### 4.2 並行実行期間

移行中は旧構造と新構造を並行して維持:

```
mv-query-optimization/
├── src/          # 新構造
├── scripts/      # 新構造
├── *.py          # 旧ファイル（非推奨マーク）
└── legacy/       # 旧ファイルを徐々に移動
```

### 4.3 移行チェックリスト

各モジュール移行時:
- [ ] 新しい場所にコピー
- [ ] リファクタリング（型ヒント、docstring追加）
- [ ] テスト作成
- [ ] 統合テスト通過
- [ ] 旧ファイルに非推奨マーク
- [ ] ドキュメント更新

## 5. 期待される効果

### 5.1 開発効率の向上
- **モジュール化**: 機能の追加・修正が容易
- **テスト**: バグの早期発見、リグレッション防止
- **型ヒント**: IDEの補完、静的解析

### 5.2 保守性の向上
- **明確な責務**: どこに何があるか分かりやすい
- **ドキュメント**: 新規参加者のオンボーディング容易
- **設定の外部化**: 実験条件の変更が簡単

### 5.3 拡張性の向上
- **新アルゴリズム追加**: 基底クラスを継承するだけ
- **新ベンチマーク対応**: プラグイン方式で追加可能
- **並列実行**: モジュール化により実装しやすい

## 6. リスクと対策

### 6.1 リスク

| リスク | 影響 | 確率 | 対策 |
|-------|------|------|------|
| 移行中のバグ混入 | 高 | 中 | 段階的移行、テストの徹底 |
| 性能劣化 | 中 | 低 | ベンチマーク実行、プロファイリング |
| 学習コスト | 低 | 高 | ドキュメント整備、ペアプログラミング |
| スケジュール遅延 | 中 | 中 | バッファ期間の確保 |

### 6.2 対策

1. **継続的テスト**: 各フェーズでテスト実行
2. **コードレビュー**: プルリクエストで品質確保
3. **ドキュメント優先**: コードより先にドキュメント作成
4. **段階的リリース**: 小さな変更を頻繁にマージ

## 7. 成功の指標

### 7.1 定量的指標
- [ ] テストカバレッジ 80%以上
- [ ] すべての関数に型ヒント
- [ ] すべてのパブリックAPIにdocstring
- [ ] 循環依存 0件
- [ ] Ruff/Black準拠率 100%

### 7.2 定性的指標
- [ ] 新機能追加が1日以内で可能
- [ ] 新規開発者が1週間でコントリビュート可能
- [ ] 実験設定変更がコード修正なしで可能

---

**作成日**: 2025年10月3日  
**作成者**: OnizukaLab  
**次回レビュー**: フェーズ1完了後
