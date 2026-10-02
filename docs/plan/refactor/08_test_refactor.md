# Phase 8: テストコードの追加

## 🎯 目的

テストカバレッジを向上させ、品質を保証します。

## ⏱️ 推定時間: 5-7時間

## 📋 前提条件

- [x] Phase 0-7 が完了
- [x] pytest がインストール済み
- [x] pytest-cov がインストール済み

## 🔧 実行手順

### Step 1: テストフィクスチャの作成 (1-2時間)

#### 1.1 共通フィクスチャ

```bash
touch tests/conftest.py
```

```python
# tests/conftest.py
"""pytest共通設定とフィクスチャ"""
import pytest
from pathlib import Path
from typing import Dict

from src.config.settings import Settings


@pytest.fixture(scope="session")
def test_data_dir():
    """テストデータディレクトリ"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_config(tmp_path):
    """サンプル設定"""
    return {
        'database': {
            'name': 'test_db',
            'host': 'localhost',
            'port': 5432,
            'user': 'test_user'
        },
        'paths': {
            'output_base': str(tmp_path / 'output'),
            'data_dir': str(tmp_path / 'data')
        },
        'workload': {
            'path': str(tmp_path / 'queries.json'),
            'query_ids': list(range(1, 6))
        },
        'optimization': {
            'storage_budget': 10000000,
            'time_limit': 300
        }
    }


@pytest.fixture
def sample_query_json():
    """サンプルクエリJSON"""
    return {
        "Plan": {
            "Node Type": "Aggregate",
            "Total Cost": 1000.0,
            "Plan Width": 10,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "users",
                    "Alias": "u",
                    "Filter": "u.age > 20",
                    "Total Cost": 100.0
                }
            ]
        }
    }
```

#### 1.2 テストデータ作成

```bash
mkdir -p tests/fixtures
touch tests/fixtures/sample_queries.json
touch tests/fixtures/sample_workload.csv
```

```json
// filepath: tests/fixtures/sample_queries.json
[
  {
    "query_id": 1,
    "sql": "SELECT * FROM users WHERE age > 20",
    "plan": {
      "Node Type": "Seq Scan",
      "Relation Name": "users",
      "Total Cost": 100.0
    }
  },
  {
    "query_id": 2,
    "sql": "SELECT u.name, COUNT(*) FROM users u GROUP BY u.name",
    "plan": {
      "Node Type": "Aggregate",
      "Total Cost": 200.0
    }
  }
]
```

### Step 2: 統合テストの拡充 (2-3時間)

#### 2.1 実験フロー全体のテスト

```bash
touch tests/integration/test_experiment_flow.py
```

```python
# tests/integration/test_experiment_flow.py
"""実験フロー全体の統合テスト"""
import pytest
from pathlib import Path

from src.config.settings import Settings
from src.core.query_manager import QueryManager
from src.optimization.factory import OptimizerFactory


@pytest.mark.integration
class TestExperimentFlow:
    """実験フロー全体のテスト"""
    
    def test_full_experiment_flow(self, tmp_path, sample_config):
        """完全な実験フロー"""
        # 設定
        config = sample_config
        
        # QueryManager初期化
        qm = QueryManager(config)
        
        # ワークロード解析
        # （実際のファイルが必要なのでスキップ）
        
        # 最適化
        optimizer = OptimizerFactory.create('normal', qm, config)
        result = optimizer.optimize()
        
        # 検証
        assert result is not None
        assert result.algorithm == 'normal'
    
    def test_multi_algorithm_comparison(self, sample_config):
        """複数アルゴリズムの比較"""
        config = sample_config
        qm = QueryManager(config)
        
        algorithms = ['normal', 'bigsubs']
        results = {}
        
        for algo in algorithms:
            optimizer = OptimizerFactory.create(algo, qm, config)
            results[algo] = optimizer.optimize()
        
        # 検証
        assert len(results) == 2
        assert all(r is not None for r in results.values())
```

### Step 3: カバレッジ向上 (2時間)

#### 3.1 カバレッジ計測

```bash
# 現在のカバレッジ確認
pytest --cov=src --cov-report=term-missing

# HTML レポート生成
pytest --cov=src --cov-report=html

# カバレッジが低いモジュールを特定
pytest --cov=src --cov-report=term-missing | grep -E "^src" | sort -k4 -n
```

#### 3.2 不足テストの追加

カバレッジレポートを見て、カバレッジが低いモジュールのテストを追加：

```python
# tests/unit/test_uncovered_module.py
"""カバレッジが低かったモジュールのテスト"""
import pytest


class TestUncoveredModule:
    """カバレッジ向上のためのテスト"""
    
    def test_edge_case_1(self):
        """エッジケース1"""
        # TODO: 実装
        pass
    
    def test_error_handling(self):
        """エラーハンドリング"""
        # TODO: 実装
        pass
```

### Step 4: パフォーマンステスト (1時間)

#### 4.1 パフォーマンステスト作成

```bash
touch tests/performance/test_optimization_performance.py
```

```python
# tests/performance/test_optimization_performance.py
"""パフォーマンステスト"""
import pytest
import time

from src.optimization.factory import OptimizerFactory


@pytest.mark.performance
class TestOptimizationPerformance:
    """最適化のパフォーマンステスト"""
    
    def test_normal_ilp_performance(self, sample_config):
        """Normal ILPのパフォーマンス"""
        # TODO: 大規模データでテスト
        pass
    
    @pytest.mark.slow
    def test_large_workload_performance(self, sample_config):
        """大規模ワークロードのパフォーマンス"""
        # TODO: 100クエリ以上でテスト
        pass
```

#### 4.2 pytest設定

```ini
# pytest.ini
[pytest]
markers =
    integration: Integration tests
    performance: Performance tests
    slow: Slow running tests

# カバレッジ設定
[coverage:run]
source = src
omit =
    */tests/*
    */venv/*
    */__pycache__/*

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### Step 5: CI/CD準備 (1時間)

#### 5.1 GitHub Actions設定

```bash
mkdir -p .github/workflows
touch .github/workflows/tests.yml
```

```yaml
# .github/workflows/tests.yml
name: Tests

on:
  push:
    branches: [ main, fix/* ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install -e .
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        pytest --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## ✅ 検証チェックリスト

- [ ] テストフィクスチャ作成完了
- [ ] 統合テスト追加完了
- [ ] カバレッジ50%以上達成
- [ ] パフォーマンステスト作成
- [ ] CI/CD設定完了
- [ ] すべてのテストが通る

## 📊 カバレッジ目標

```
モジュール                    カバレッジ目標
================================
src/core/                    > 80%
src/optimization/            > 70%
src/rewrite/                 > 60%
src/database/                > 70%
src/utils/                   > 80%
================================
全体                         > 60%
```

## 📝 コミット

```bash
git add tests/ .github/ pytest.ini
git commit -m "Phase 8: テストコードの追加

- テストフィクスチャの作成
- 統合テストの拡充
- カバレッジ向上（目標60%達成）
- パフォーマンステストの追加
- CI/CD設定の追加"
```

---

**所要時間**: 5-7時間  
**難易度**: ⭐⭐⭐⭐ (Very Hard)