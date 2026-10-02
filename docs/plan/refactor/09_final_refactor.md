# Phase 9: 最終調整とドキュメント整備

## 🎯 目的

プロジェクトの最終調整を行い、ドキュメントを整備して、リファクタリングを完了します。

## ⏱️ 推定時間: 2-3時間

## 📋 前提条件

- [x] Phase 0-8 が完了している
- [x] すべてのコアモジュールが動作している
- [x] テストカバレッジが目標値を達成している

---

## 🔧 実行手順

### Step 1: コードフォーマットと静的解析 (30分)

#### 1.1 Black でフォーマット

```bash
# 全体をフォーマット
black src/ tests/ scripts/

# 確認
black --check src/ tests/ scripts/

# 差分表示
black --diff src/ tests/ scripts/
```

#### 1.2 Ruff でリント

```bash
# リント実行
ruff check src/ tests/ scripts/

# 自動修正可能なものを修正
ruff check --fix src/ tests/ scripts/

# 厳密なチェック
ruff check --select ALL src/
```

#### 1.3 isort でインポート整理

```bash
# インストール（未インストールの場合）
pip install isort

# 実行
isort src/ tests/ scripts/

# 確認
isort --check-only src/ tests/ scripts/
```

### Step 2: 型チェック (30分)

#### 2.1 Mypy 実行

```bash
# 基本的な型チェック
mypy src/

# 厳密モード（徐々に移行）
mypy --strict src/core/

# エラー箇所の詳細表示
mypy --show-error-codes src/
```

#### 2.2 型ヒントの追加

未対応の関数に型ヒントを追加：

```bash
# 型ヒントが不足している関数を検索
grep -r "def " src/ | grep -v ":" | grep -v "__init__" | wc -l

# 手動で追加が必要な箇所をリストアップ
mypy src/ 2>&1 | grep "error:" | cut -d: -f1-2 | sort | uniq
```

型ヒント追加例：

```python
# Before
def process_data(data):
    return data * 2

# After
from typing import Union

def process_data(data: Union[int, float]) -> Union[int, float]:
    """Process numeric data.
    
    Args:
        data: Input numeric value
        
    Returns:
        Processed value (doubled)
    """
    return data * 2
```

### Step 3: ドキュメント整備 (1時間)

#### 3.1 README.md の更新

```bash
cat > README.md << 'EOF'
# Materialized View Query Optimization

マテリアライズドビュー選択を用いたクエリ最適化システム

## 📋 概要

このプロジェクトは、ILP（整数線形計画法）を用いてマテリアライズドビューを選択し、
クエリ実行時間を最適化するシステムです。

### 主要機能

- **クエリ解析**: PostgreSQL EXPLAIN JSONからクエリプランを解析
- **MV選択最適化**: 5種類のILPアルゴリズムによる最適化
  - Normal ILP
  - BigSubs ILP
  - Utility-based
  - Utility-Capacity
  - Frequency-based
- **クエリ書き換え**: 選択されたMVを使用するようクエリを自動書き換え
- **ベンチマーク**: JOB/CEB/RedBenchでの性能評価

## 🚀 クイックスタート

### 前提条件

- Python 3.10以上
- PostgreSQL 13以上
- Gurobi Optimizer（ライセンス必要）

### インストール

```bash
# リポジトリクローン
git clone https://github.com/your-org/mv-query-optimization.git
cd mv-query-optimization

# 依存パッケージインストール
pip install -e .

# 環境設定
cp .env.example .env
# .env を編集してデータベース接続情報を設定
```

### 基本的な使い方

```bash
# 1. クエリ解析
python scripts/parse_queries.py --workload dataset/RED_JSON/job

# 2. 最適化実行
python scripts/run_experiment.py --algorithms normal bigsubs

# 3. 結果比較
python scripts/compare_algorithms.py --results Output/experiments
```

## 📁 プロジェクト構造

```
mv-query-optimization/
├── src/                    # ソースコード
│   ├── core/              # コアモジュール
│   ├── optimization/      # 最適化アルゴリズム
│   ├── rewrite/          # クエリ書き換え
│   ├── database/         # DB操作
│   └── utils/            # ユーティリティ
├── config/                # 設定ファイル
├── scripts/               # 実行スクリプト
├── tests/                 # テストコード
├── dataset/               # ベンチマークデータ
└── docs/                  # ドキュメント
```

## 🔧 詳細な使い方

### 設定ファイル

`config/default.yaml` で基本設定を行います：

```yaml
database:
  host: localhost
  port: 5432
  database: imdbload

optimization:
  storage_limit_mb: 50
  algorithms:
    normal: true
    bigsubs: true
```

### CLI オプション

```bash
# アルゴリズム指定
python scripts/run_experiment.py --algorithms normal bigsubs utility

# カスタム設定ファイル
python scripts/run_experiment.py --config config/experiments/job_benchmark.yaml

# 出力ディレクトリ指定
python scripts/run_experiment.py --output Output/my_experiment

# 詳細ログ
python scripts/run_experiment.py --verbose
```

## 📊 ベンチマーク

### JOB (Join Order Benchmark)

```bash
python scripts/run_experiment.py \
  --config config/experiments/job_benchmark.yaml \
  --algorithms normal bigsubs utility
```

### CEB (Complex Expression Benchmark)

```bash
python scripts/run_experiment.py \
  --config config/experiments/ceb_benchmark.yaml \
  --algorithms normal utility_capacity frequency
```

## 🧪 テスト

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=src --cov-report=html

# 統合テストのみ
pytest -m integration

# 特定モジュールのみ
pytest tests/unit/test_query_manager.py -v
```

## 📚 ドキュメント

- [プロジェクト概要](docs/project_overview.md)
- [リファクタリング計画](docs/refactoring_plan.md)
- [API ドキュメント](docs/api/)
- [技術スタック評価](docs/technology_evaluation.md)

## 🤝 コントリビューション

### 開発環境セットアップ

```bash
# 開発用依存パッケージ
pip install -e ".[dev]"

# pre-commit フック
pre-commit install
```

### コーディング規約

- **フォーマット**: Black (line-length=100)
- **リント**: Ruff
- **型チェック**: Mypy
- **docstring**: Google スタイル

## 📄 ライセンス

MIT License

## 👥 開発者

OnizukaLab

## 📞 サポート

問題が発生した場合は、GitHubのIssueを作成してください。

---

**バージョン**: 0.2.0  
**最終更新**: 2025年1月
EOF
```

#### 3.2 API ドキュメント作成

```bash
mkdir -p docs/api

cat > docs/api/README.md << 'EOF'
# API ドキュメント

## Core Modules

### QueryManager

クエリの管理と解析を担当するコアクラス。

```python
from src.core.query_manager import QueryManager

# 初期化
qm = QueryManager(config)

# クエリ登録
qm.register_query(
    query_num=1,
    query_path="path/to/query.json",
    original_sql="SELECT ..."
)

# リーフノード追加
leaf_id = qm.add_leaf_node(
    table_name="users",
    alias="u",
    conditions="u.age > 20"
)

# 状態保存
qm.save_state("qm_state.pkl")
```

**主要メソッド**:

- `register_query(query_num, query_path, original_sql)`: クエリを登録
- `add_leaf_node(table_name, alias, conditions)`: リーフノード追加
- `add_non_leaf_node(child_ids, join_condition)`: 非リーフノード追加
- `save_state(filepath)`: 状態を保存
- `load_state(filepath)`: 状態を読み込み

### QueryParser

クエリプランのJSONを解析するクラス。

```python
from src.core.query_parser import QueryParser

parser = QueryParser(config)

# ワークロード解析
parser.parse_workload(
    workload_dir="dataset/RED_WORKLOADS",
    queries_dir="dataset/RED_JSON/job"
)

# 単一クエリ解析
parser.parse_query(query_num=1, json_path="query.json")
```

**主要メソッド**:

- `parse_workload(workload_dir, queries_dir)`: ワークロード全体を解析
- `parse_query(query_num, json_path)`: 単一クエリを解析
- `convert_json(plan_json, frequency)`: JSONをノード構造に変換

## Optimization Modules

### OptimizerFactory

最適化アルゴリズムのファクトリークラス。

```python
from src.optimization.factory import OptimizerFactory

# Normal ILP
optimizer = OptimizerFactory.create(
    'normal',
    query_manager=qm,
    config=config
)

# 最適化実行
result = optimizer.optimize()

print(f"Selected MVs: {len(result.selected_views)}")
print(f"Total utility: {result.total_utility}")
```

**利用可能なアルゴリズム**:

- `normal`: 標準ILP
- `bigsubs`: BigSubs制約付きILP
- `utility`: ユーティリティベース
- `utility_capacity`: ユーティリティ・容量
- `frequency`: 頻度ベース

### 個別最適化クラス

各アルゴリズムのクラス：

- `NormalILP`: 標準的なILP定式化
- `BigSubsILP`: BigSubs制約を追加
- `UtilityILP`: ユーティリティ関数を使用
- `UtilityCapacityILP`: 容量制約付き
- `FrequencyILP`: クエリ頻度を考慮

## Rewrite Modules

### QueryRewriter

クエリ書き換えクラス。

```python
from src.rewrite.query_rewriter import QueryRewriter

rewriter = QueryRewriter(query_manager)

# ワークロード書き換え
rewritten = rewriter.rewrite_workload(
    selected_mvs={1: [mv1, mv2], 2: [mv3]},
    output_dir="Output/rewritten"
)
```

### MVGenerator

MV作成SQLの生成クラス。

```python
from src.rewrite.mv_generator import MVGenerator

generator = MVGenerator()

# MV作成SQL生成
create_sql = generator.generate_create_sql(mv, node)

# ファイル保存
generator.save_create_sqls(mvs, output_dir)
```

## Database Modules

### DatabaseConnection

データベース接続管理。

```python
from src.database.connection import DatabaseConnection

db = DatabaseConnection(config)

# クエリ実行
result = db.execute_query("SELECT * FROM users")

# トランザクション
with db.transaction():
    db.execute("CREATE MATERIALIZED VIEW ...")
```

### MaterializedViewManager

マテリアライズドビュー管理。

```python
from src.database.mv_manager import MaterializedViewManager

mv_manager = MaterializedViewManager(config)

# MV作成
mv_manager.create_view("mv_users_1", create_sql)

# MV削除
mv_manager.drop_view("mv_users_1")

# サイズ取得
size = mv_manager.get_view_size("mv_users_1")
```

## Utility Modules

### ロギング

```python
from src.utils.logging_utils import get_logger, setup_logging

# ロガー取得
logger = get_logger(__name__)

logger.info("Processing query...")
logger.error("Failed to process", exc_info=True)

# ロギング設定
setup_logging(level='DEBUG', log_file='app.log')
```

### ファイル操作

```python
from src.utils.file_utils import natural_sort_key, load_json_files

# 自然順ソート
files = sorted(file_list, key=natural_sort_key)

# JSON一括読み込み
data = load_json_files(directory)
```

---

詳細な型定義は各モジュールのソースコードを参照してください。
EOF
```

#### 3.3 開発者ガイド作成

```bash
cat > docs/CONTRIBUTING.md << 'EOF'
# 開発者ガイド

## 開発環境セットアップ

### 1. リポジトリクローン

```bash
git clone https://github.com/your-org/mv-query-optimization.git
cd mv-query-optimization
```

### 2. 仮想環境作成

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 依存パッケージインストール

```bash
# 開発用依存含む
pip install -e ".[dev]"

# pre-commit フック設定
pre-commit install
```

### 4. データベースセットアップ

```bash
# PostgreSQL起動
docker-compose up -d postgres

# スキーマ作成
python scripts/setup_database.py --schema dataset/imdb_schema.sql
```

## コーディング規約

### Python スタイル

- **PEP 8** に準拠
- **Black** でフォーマット（line-length=100）
- **Ruff** でリント
- **Mypy** で型チェック

### Docstring

Google スタイルを使用：

```python
def process_query(query_id: int, config: Dict[str, Any]) -> QueryPlan:
    """Process a single query.
    
    Args:
        query_id: Query identifier
        config: Configuration dictionary
        
    Returns:
        Parsed query plan
        
    Raises:
        ValueError: If query_id is invalid
        FileNotFoundError: If query file not found
        
    Example:
        >>> plan = process_query(1, config)
        >>> print(plan.total_cost)
        1234.56
    """
    pass
```

### 型ヒント

すべての関数に型ヒントを付与：

```python
from typing import List, Dict, Optional

def get_query_ids(
    workload_file: str,
    limit: Optional[int] = None
) -> List[int]:
    """Get query IDs from workload file."""
    pass
```

## テスト

### テスト作成

```bash
# ユニットテスト
touch tests/unit/test_new_module.py

# 統合テスト
touch tests/integration/test_new_flow.py
```

テストテンプレート：

```python
"""Tests for new_module."""
import pytest
from src.new_module import NewClass


class TestNewClass:
    """Test suite for NewClass."""
    
    @pytest.fixture
    def instance(self):
        """Create instance for testing."""
        return NewClass()
    
    def test_basic_functionality(self, instance):
        """Test basic functionality."""
        result = instance.process()
        assert result is not None
    
    def test_error_handling(self, instance):
        """Test error handling."""
        with pytest.raises(ValueError):
            instance.process(invalid_input)
```

### テスト実行

```bash
# 全テスト
pytest

# 特定のテスト
pytest tests/unit/test_query_manager.py::TestQueryManager::test_add_leaf_node

# カバレッジ
pytest --cov=src --cov-report=html

# マーカー指定
pytest -m "not slow"
```

## Git ワークフロー

### ブランチ戦略

- `main`: 安定版
- `develop`: 開発版
- `feature/*`: 新機能
- `fix/*`: バグ修正
- `refactor/*`: リファクタリング

### コミットメッセージ

```
<type>: <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: フォーマット
- `refactor`: リファクタリング
- `test`: テスト追加
- `chore`: その他

**Example**:

```
feat: Add frequency-based ILP optimizer

- Implement FrequencyILP class
- Add query frequency calculation
- Update factory to support new algorithm

Closes #123
```

### プルリクエスト

1. **ブランチ作成**: `git checkout -b feature/new-feature`
2. **変更実装**: コード + テスト
3. **コミット**: 明確なメッセージ
4. **Push**: `git push origin feature/new-feature`
5. **PR作成**: GitHub上で
6. **レビュー**: コードレビューを受ける
7. **マージ**: レビュー承認後

## デバッグ

### ロギング

```python
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

logger.debug(f"Processing query {query_id}")
logger.info("Optimization completed")
logger.warning("Storage limit exceeded")
logger.error("Failed to connect", exc_info=True)
```

### 対話的デバッグ

```python
# pdb使用
import pdb; pdb.set_trace()

# IPython使用
from IPython import embed; embed()
```

### プロファイリング

```bash
# cProfile
python -m cProfile -o profile.stats scripts/run_experiment.py

# 結果表示
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumtime'); p.print_stats(20)"

# line_profiler
kernprof -l -v scripts/run_experiment.py
```

## リリース

### バージョニング

Semantic Versioning (MAJOR.MINOR.PATCH):

- MAJOR: 破壊的変更
- MINOR: 新機能追加
- PATCH: バグ修正

### リリースプロセス

1. バージョン更新: `pyproject.toml`
2. CHANGELOG更新
3. タグ作成: `git tag v0.2.0`
4. Push: `git push origin v0.2.0`
5. GitHub Release作成

## トラブルシューティング

### テスト失敗

```bash
# 詳細表示
pytest -vv

# 失敗したテストのみ再実行
pytest --lf

# デバッグモード
pytest --pdb
```

### インポートエラー

```bash
# パッケージ再インストール
pip install -e .

# PYTHONPATH設定
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### 型エラー

```bash
# Mypy実行
mypy src/

# 特定ファイルのみ
mypy src/core/query_manager.py

# エラーコード表示
mypy --show-error-codes src/
```

## リソース

- [プロジェクト概要](project_overview.md)
- [API ドキュメント](api/README.md)
- [技術スタック評価](technology_evaluation.md)

---

質問がある場合は、GitHubのDiscussionsで聞いてください。
EOF
```

### Step 4: 不要ファイルの整理 (30分)

#### 4.1 移行済みファイルの確認

```bash
# 移行済みファイルをリストアップ
cat > docs/MIGRATION_STATUS.md << 'EOF'
# 移行状況

## ✅ 移行完了（削除可能）

以下のファイルは新構造に移行済みで、削除可能です：

- [ ] `utils.py` → `src/utils/` 配下に分割済み
- [ ] `query_parse_beta.py` → `src/core/` に移行済み
- [ ] `ILP_*.py` → `src/optimization/` に統合済み

## ⚠️ 暫定的に残存

以下は後方互換性のため残存：

- `experiment.py` → `scripts/run_experiment.py` に移行予定
- `compare_bata.py` → `scripts/compare_algorithms.py` に移行予定

## 📦 アーカイブ

古いファイルは `archive/` に移動：

```bash
mkdir -p archive/old_scripts
mv query_parse_beta.py archive/old_scripts/
mv ILP_*.py archive/old_scripts/
```
EOF
```

#### 4.2 .gitignore の更新

```bash
cat >> .gitignore << 'EOF'

# Archive
archive/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Jupyter
.ipynb_checkpoints/

# Mypy
.mypy_cache/

# Pytest
.pytest_cache/

# Coverage
.coverage
htmlcov/

# Ruff
.ruff_cache/
EOF
```

### Step 5: 最終検証 (30分)

#### 5.1 全テスト実行

```bash
# すべてのテスト
pytest -v

# カバレッジ確認
pytest --cov=src --cov-report=term-missing

# 統合テスト含む
pytest -m integration
```

#### 5.2 静的解析の最終確認

```bash
# Black
black --check src/ tests/ scripts/

# Ruff
ruff check src/ tests/ scripts/

# Mypy
mypy src/

# isort
isort --check-only src/ tests/ scripts/
```

#### 5.3 動作確認

```bash
# インポート確認
python << 'PYTHON'
from src.core.query_manager import QueryManager
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.rewrite.query_rewriter import QueryRewriter
from src.database.mv_manager import MaterializedViewManager
print("✅ All imports successful")
PYTHON

# 簡易実行確認
python scripts/run_experiment.py --help
python scripts/compare_algorithms.py --help
```

## ✅ 完了チェックリスト

### コード品質
- [ ] Black でフォーマット完了
- [ ] Ruff チェック完了（エラーなし）
- [ ] Mypy チェック完了（主要モジュール）
- [ ] isort でインポート整理完了

### ドキュメント
- [ ] README.md 更新完了
- [ ] API ドキュメント作成完了
- [ ] CONTRIBUTING.md 作成完了
- [ ] MIGRATION_STATUS.md 作成完了

### 検証
- [ ] 全テストがパスする
- [ ] カバレッジ目標達成（60%以上）
- [ ] 統合テストがパスする
- [ ] インポートエラーなし

### Git
- [ ] 不要ファイル整理完了
- [ ] .gitignore 更新完了
- [ ] コミット完了

## 📝 最終コミット

```bash
# ステージング
git add -A

# コミット
git commit -m "Phase 9: 最終調整とドキュメント整備

- コードフォーマット（Black, Ruff, isort）
- 型チェック（Mypy）対応
- README.md 完全更新
- API ドキュメント作成
- CONTRIBUTING.md 追加
- 不要ファイル整理
- .gitignore 更新

全フェーズ完了 🎉"

# タグ作成
git tag v0.2.0 -m "Refactoring completed"

# Push
git push origin fix/20251003-refactoring
git push origin v0.2.0
```

## 🎯 プルリクエスト作成

```markdown
# Title
Refactoring: Project structure reorganization (Phase 0-9)

## 概要
プロジェクト全体のリファクタリングを完了しました。

## 変更内容

### Phase 0-2: 基盤整備
- ディレクトリ構造の再編成
- 設定管理システムの導入（YAML）
- ユーティリティモジュールの整理

### Phase 3-5: コアモジュール
- QueryManager, QueryParser のリファクタリング
- ILP最適化モジュールの統合
- データベース操作モジュールの分離

### Phase 6-7: 実験系
- クエリ書き換えモジュールの実装
- 実験スクリプトのCLI化

### Phase 8-9: 品質向上
- テストカバレッジ 60% 達成
- 型ヒント追加
- ドキュメント整備

## 主な改善点

✨ **新機能**
- CLI による柔軟な実験実行
- YAML による設定管理
- 統一されたロギング

🐛 **バグ修正**
- 循環依存の解消
- エラーハンドリングの改善

📚 **ドキュメント**
- API ドキュメント完備
- 開発者ガイド追加
- README 完全更新

🧪 **テスト**
- ユニットテスト: 103個
- 統合テスト: 12個
- カバレッジ: 60%

## 破壊的変更

⚠️ **後方互換性**
- 既存の `experiment.py` は引き続き動作します
- 新しい `scripts/run_experiment.py` への移行を推奨

## チェックリスト

- [x] すべてのテストがパスする
- [x] ドキュメントが更新されている
- [x] 型チェックが通る
- [x] コードフォーマット済み

## スクリーンショット

（必要に応じて追加）

## レビュワー

@reviewer1 @reviewer2
```

## 📊 最終統計

```bash
# コード行数
echo "=== Code Statistics ==="
find src/ -name "*.py" | xargs wc -l | tail -1

# テスト数
echo "=== Test Count ==="
pytest --collect-only | grep "test session starts" -A 100 | grep "<Function" | wc -l

# カバレッジ
echo "=== Coverage ==="
pytest --cov=src --cov-report=term | grep "TOTAL"

# ファイル数
echo "=== File Count ==="
find src/ -name "*.py" | wc -l
```

## 🎉 リファクタリング完了！

おめでとうございます！全9フェーズのリファクタリングが完了しました。

### 達成したこと

✅ **構造改善**
- モジュール化された設計
- 明確な責務分離
- 保守性の向上

✅ **品質向上**
- 型安全性の向上
- テストカバレッジ 60%
- コードフォーマット統一

✅ **開発体験**
- CLI による柔軟な実行
- YAML による設定管理
- 充実したドキュメント

### 次のステップ

1. **プルリクエストのレビュー**: チームメンバーにレビューを依頼
2. **実験実行**: 新しいスクリプトで実験を実行して動作確認
3. **ドキュメント展開**: チームに新しい構造を説明
4. **継続的改善**: カバレッジ80%を目指す

---

**所要時間**: 2-3時間  
**難易度**: ⭐⭐ (Medium)  
**重要度**: ⭐⭐⭐⭐ (High)

**リファクタリング合計時間**: 約 40-60時間  
**フェーズ数**: 9  
**新規ファイル数**: 50+  
**テスト数**: 100+  
**コード行数**: 5,000+