# NeuroCardによるサイズ推定の導入手順

このドキュメントでは、サブモジュールとして追加された `neurocard` を使用して、MVのサイズ推定（カーディナリティ推定）を行うための手順を説明します。

## 1. 環境セットアップ

NeuroCardを実行するために必要なライブラリをインストールします。

```bash
# 必要なライブラリのインストール
pip install torch numpy pandas ray matplotlib sqlparse
```

**注意**: PyTorchのバージョンは環境に合わせて適切なものを選択してください。

## 2. データセットの準備

NeuroCardは学習と推論のために、CSV形式のIMDBデータセットを必要とします。
プロジェクト内の `dataset/` ディレクトリにあるCSVファイルを使用できるようにリンクを作成します。

```bash
# NeuroCardのデータディレクトリを作成
mkdir -p neurocard/neurocard/datasets/job

# 既存のCSVデータへのシンボリックリンクを作成（パスは環境に合わせて調整してください）
# 例: dataset/redbench/imdb/benchmarks/job/csv/ にCSVがある場合
ln -s $(pwd)/dataset/redbench/imdb/benchmarks/job/csv/*.csv neurocard/neurocard/datasets/job/
```

## 3. モデルの準備

サイズ推定を行うには、学習済みのNeuroCardモデルが必要です。

### オプションA: 学習済みモデルがある場合
学習済みモデル（チェックポイント）を `neurocard/neurocard/checkpoints/` などのディレクトリに配置します。

### オプションB: 新規に学習する場合
以下のコマンドでモデルを学習します（時間がかかります）。

```bash
cd neurocard/neurocard
python run.py --run job-light --epochs 10 --gpus 0  # GPUがない場合は0
```

## 4. 統合実装（ラッパーの作成）

NeuroCardを既存のパイプラインから呼び出すためのラッパークラスを作成します。

**ファイル作成**: `src/estimation/neurocard_wrapper.py`

```python
import sys
import os
import torch
import numpy as np

# NeuroCardへのパスを通す
sys.path.append(os.path.join(os.path.dirname(__file__), '../../neurocard/neurocard'))

from neurocard.neurocard.run import NeuroCard
from neurocard.neurocard.datasets import LoadImdb

class NeuroCardEstimator:
    def __init__(self, checkpoint_path, dataset_dir):
        self.checkpoint_path = checkpoint_path
        self.dataset_dir = dataset_dir
        self.model = self._load_model()
        
    def _load_model(self):
        # モデルの設定とロード（簡略化）
        # 実際にはrun.pyの設定に合わせてconfigを構築する必要があります
        config = {
            'dataset': 'job',
            'data_dir': self.dataset_dir,
            # ... その他の設定
        }
        model = NeuroCard()
        model._setup(config)
        model.LoadCheckpoint(self.checkpoint_path)
        return model
    
    def estimate_size(self, table_names, filters):
        """
        MVのサイズ（バイト）を推定する
        
        Args:
            table_names: 結合に含まれるテーブル名のリスト
            filters: フィルタ条件のリスト [(col, op, val), ...]
            
        Returns:
            estimated_bytes: 推定サイズ（バイト）
        """
        # 1. カーディナリティ（行数）を推定
        cardinality = self.model.Query(
            estimators=[self.model],
            query=(columns, operators, vals) # フィルタを変換
        )
        
        # 2. 行幅（width）を推定（平均行長などを使用）
        avg_row_width = self._calculate_avg_width(table_names)
        
        return cardinality * avg_row_width
```

## 5. Phase 5への組み込み

`experiments/small_test_ver2/migration/simple_migration_cost_calculator.py` を修正して、PostgreSQLの推定値の代わりに `NeuroCardEstimator` を使用するようにします。

```python
from src.estimation.neurocard_wrapper import NeuroCardEstimator

class SimpleMigrationCostCalculator:
    def __init__(self, ...):
        # ...
        self.ml_estimator = NeuroCardEstimator(checkpoint_path, data_dir)
        
    def calculate_cost(self, plan):
        # ...
        if self.use_ml_estimation:
            size = self.ml_estimator.estimate_size(plan.tables, plan.filters)
        else:
            size = self._get_postgres_estimate(plan.sql)
        # ...
```

## 次のステップ

1. 上記のセットアップ（ライブラリ、データ）を行ってください。
2. 学習済みモデルの有無を確認してください。
3. `src/estimation/neurocard_wrapper.py` の実装を開始しますか？
