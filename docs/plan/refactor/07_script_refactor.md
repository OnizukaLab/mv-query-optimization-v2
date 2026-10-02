# Phase 7: 実験スクリプトの整理

## 🎯 目的

実験実行スクリプトをCLI化し、設定ファイルベースで実行できるようにします。

## ⏱️ 推定時間: 3-5時間

## 📋 前提条件

- [x] Phase 0-6 が完了
- [x] すべてのコアモジュールが動作
- [x] 設定管理システムが動作

## 🔧 実行手順

### Step 1: メイン実験スクリプト (2-3時間)

#### 1.1 ファイル作成

```bash
touch scripts/run_experiment.py
chmod +x scripts/run_experiment.py
```

#### 1.2 実装

```python
#!/usr/bin/env python3
# scripts/run_experiment.py
"""実験実行メインスクリプト"""
import argparse
import sys
from pathlib import Path
from typing import List

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.core.query_manager import QueryManager
from src.optimization.factory import OptimizerFactory
from src.rewrite.query_rewriter import QueryRewriter
from src.database.mv_manager import MaterializedViewManager
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)


def parse_args():
    """コマンドライン引数解析"""
    parser = argparse.ArgumentParser(
        description="Run MV optimization experiment"
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/default.yaml',
        help='Configuration file path'
    )
    
    parser.add_argument(
        '--algorithms',
        nargs='+',
        choices=['normal', 'bigsubs', 'utility', 'utility_capacity', 'frequency'],
        default=['normal'],
        help='Optimization algorithms to run'
    )
    
    parser.add_argument(
        '--workload',
        type=str,
        help='Workload file path (overrides config)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output directory (overrides config)'
    )
    
    parser.add_argument(
        '--skip-mv-creation',
        action='store_true',
        help='Skip MV creation in database'
    )
    
    parser.add_argument(
        '--skip-rewrite',
        action='store_true',
        help='Skip query rewriting'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    return parser.parse_args()


def run_optimization(
    algorithm: str,
    query_manager: QueryManager,
    settings: Settings
) -> None:
    """最適化を実行
    
    Args:
        algorithm: アルゴリズム名
        query_manager: クエリ管理オブジェクト
        settings: 設定
    """
    logger.info(f"Running {algorithm} optimization...")
    
    # Optimizer作成
    optimizer = OptimizerFactory.create(
        algorithm,
        query_manager=query_manager,
        config=settings.to_dict()
    )
    
    # 最適化実行
    result = optimizer.optimize()
    
    # 結果保存
    output_dir = Path(settings.paths.output_base) / algorithm
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result_file = output_dir / "optimization_result.json"
    result.save(result_file)
    
    logger.info(f"Optimization completed: {result_file}")
    logger.info(f"  Selected MVs: {len(result.selected_views)}")
    logger.info(f"  Total utility: {result.total_utility:.2f}")
    logger.info(f"  Total storage: {result.total_storage} bytes")


def create_materialized_views(
    selected_mvs: List,
    settings: Settings
) -> None:
    """マテリアライズドビューを作成
    
    Args:
        selected_mvs: 選択されたMVリスト
        settings: 設定
    """
    logger.info("Creating materialized views in database...")
    
    mv_manager = MaterializedViewManager(settings.to_dict())
    
    for mv in selected_mvs:
        try:
            mv_manager.create_view(mv.view_id, mv.create_sql)
            logger.info(f"Created MV: {mv.view_id}")
        except Exception as e:
            logger.error(f"Failed to create MV {mv.view_id}: {e}")


def rewrite_queries(
    query_manager: QueryManager,
    selected_mvs: dict,
    output_dir: Path
) -> None:
    """クエリを書き換え
    
    Args:
        query_manager: クエリ管理オブジェクト
        selected_mvs: 選択されたMV辞書
        output_dir: 出力ディレクトリ
    """
    logger.info("Rewriting queries...")
    
    rewriter = QueryRewriter(query_manager)
    rewritten = rewriter.rewrite_workload(selected_mvs, output_dir)
    
    logger.info(f"Rewritten {len(rewritten)} queries")


def main():
    """メイン処理"""
    args = parse_args()
    
    # ロギング設定
    log_level = 'DEBUG' if args.verbose else 'INFO'
    setup_logging(level=log_level)
    
    try:
        # 設定ロード
        logger.info(f"Loading configuration from {args.config}")
        settings = Settings.load(args.config)
        
        # コマンドライン引数で上書き
        if args.workload:
            settings.workload.path = args.workload
        if args.output:
            settings.paths.output_base = args.output
        
        # QueryManager初期化
        logger.info("Initializing query manager...")
        query_manager = QueryManager(settings.to_dict())
        query_manager.parse_workload(settings.workload.path)
        
        # 各アルゴリズムで最適化
        for algo in args.algorithms:
            run_optimization(algo, query_manager, settings)
            
            # MV作成
            if not args.skip_mv_creation:
                # TODO: 結果から selected_mvs を取得
                pass
            
            # クエリ書き換え
            if not args.skip_rewrite:
                output_dir = Path(settings.paths.output_base) / algo / "rewritten"
                # TODO: selected_mvs を渡す
                pass
        
        logger.info("Experiment completed successfully!")
        
    except Exception as e:
        logger.error(f"Experiment failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

#### 1.3 使用例

```bash
# デフォルト設定で実行
python scripts/run_experiment.py

# 特定のアルゴリズムのみ実行
python scripts/run_experiment.py --algorithms normal bigsubs

# カスタム設定ファイル使用
python scripts/run_experiment.py --config config/experiments/job_benchmark.yaml

# MV作成をスキップ
python scripts/run_experiment.py --skip-mv-creation

# 詳細ログ
python scripts/run_experiment.py --verbose
```

### Step 2: 最適化比較スクリプト (1時間)

#### 2.1 ファイル作成

```bash
touch scripts/compare_algorithms.py
chmod +x scripts/compare_algorithms.py
```

#### 2.2 実装

```python
#!/usr/bin/env python3
# scripts/compare_algorithms.py
"""アルゴリズム比較スクリプト"""
import argparse
import json
from pathlib import Path
from typing import List, Dict
import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def load_results(result_dir: Path, algorithms: List[str]) -> Dict:
    """結果をロード
    
    Args:
        result_dir: 結果ディレクトリ
        algorithms: アルゴリズムリスト
        
    Returns:
        {algorithm: result_data}
    """
    results = {}
    
    for algo in algorithms:
        result_file = result_dir / algo / "optimization_result.json"
        if result_file.exists():
            with open(result_file) as f:
                results[algo] = json.load(f)
        else:
            logger.warning(f"Result not found: {result_file}")
    
    return results


def compare_metrics(results: Dict) -> pd.DataFrame:
    """メトリクスを比較
    
    Args:
        results: 結果辞書
        
    Returns:
        比較DataFrame
    """
    data = []
    
    for algo, result in results.items():
        data.append({
            'Algorithm': algo,
            'Selected MVs': len(result.get('selected_views', [])),
            'Total Utility': result.get('total_utility', 0),
            'Total Storage': result.get('total_storage', 0),
            'Execution Time': result.get('execution_time', 0)
        })
    
    df = pd.DataFrame(data)
    return df


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Compare optimization algorithms")
    parser.add_argument('--results', type=str, required=True, help='Results directory')
    parser.add_argument('--algorithms', nargs='+', default=['normal', 'bigsubs', 'utility'])
    parser.add_argument('--output', type=str, help='Output CSV file')
    
    args = parser.parse_args()
    
    # 結果ロード
    results = load_results(Path(args.results), args.algorithms)
    
    # 比較
    df = compare_metrics(results)
    
    # 表示
    print("\n=== Algorithm Comparison ===")
    print(df.to_string(index=False))
    
    # ファイル保存
    if args.output:
        df.to_csv(args.output, index=False)
        logger.info(f"Saved comparison to {args.output}")


if __name__ == '__main__':
    main()
```

### Step 3: データベースセットアップスクリプト (1時間)

#### 3.1 ファイル作成

```bash
touch scripts/setup_database.py
chmod +x scripts/setup_database.py
```

#### 3.2 実装

```python
#!/usr/bin/env python3
# scripts/setup_database.py
"""データベースセットアップスクリプト"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import Settings
from src.database.connection import DatabaseConnection
from src.database.schema import SchemaManager
from src.utils.logging_utils import get_logger, setup_logging

logger = get_logger(__name__)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Setup database for experiments")
    parser.add_argument('--config', type=str, default='config/default.yaml')
    parser.add_argument('--schema', type=str, help='Schema SQL file')
    parser.add_argument('--data', type=str, help='Data SQL file')
    parser.add_argument('--drop-existing', action='store_true', help='Drop existing MVs')
    
    args = parser.parse_args()
    
    setup_logging()
    
    try:
        # 設定ロード
        settings = Settings.load(args.config)
        
        # データベース接続
        logger.info("Connecting to database...")
        db = DatabaseConnection(settings.to_dict())
        
        # スキーマ管理
        schema_manager = SchemaManager(db)
        
        # 既存MV削除
        if args.drop_existing:
            logger.info("Dropping existing materialized views...")
            # TODO: MV一覧取得して削除
        
        # スキーマ作成
        if args.schema:
            logger.info(f"Creating schema from {args.schema}")
            with open(args.schema) as f:
                sql = f.read()
            db.execute(sql)
        
        # データロード
        if args.data:
            logger.info(f"Loading data from {args.data}")
            with open(args.data) as f:
                sql = f.read()
            db.execute(sql)
        
        logger.info("Database setup completed!")
        
    except Exception as e:
        logger.error(f"Setup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

## ✅ 検証チェックリスト

- [ ] `scripts/run_experiment.py` 実装完了
- [ ] `scripts/compare_algorithms.py` 実装完了
- [ ] `scripts/setup_database.py` 実装完了
- [ ] スクリプトが実行可能
- [ ] ヘルプメッセージが表示される
- [ ] 設定ファイルから読み込める

## 📝 コミット

```bash
git add scripts/
git commit -m "Phase 7: 実験スクリプトの整理

- メイン実験スクリプトのCLI化
- アルゴリズム比較スクリプトの追加
- データベースセットアップスクリプトの追加"
```

---

**所要時間**: 3-5時間  
**難易度**: ⭐⭐⭐ (Hard)