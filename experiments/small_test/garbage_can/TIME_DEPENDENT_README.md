# 時刻依存型頻度重み付け最適化の使用方法

## 概要

複数の時刻でクエリの実行頻度が変化する場合に対応した最適化を行います。
各時刻ごとに異なる頻度で重み付けされた利得を計算し、最適なMV選択を決定します。

## ユースケース

### 例: 朝と夕方でクエリパターンが異なる

- **朝（9:00-12:00）**: ユーザー情報の集計クエリが頻繁（レポート生成）
- **夕方（17:00-20:00）**: カテゴリ別集計クエリが頻繁（ダッシュボード表示）

それぞれの時刻で最適なMVセットが異なる可能性があります。

## 設定ファイル

### frequency_time_dependent.json

`experiments/small_test/01_queries/frequency_time_dependent.json`:

```json
{
  "description": "時刻依存型クエリ頻度設定",
  "timesteps": [
    {
      "time_id": "morning",
      "label": "朝（9:00-12:00）",
      "duration_hours": 3,
      "frequencies": {
        "query1.json": 200,
        "query2.json": 50,
        "query3.json": 100
      },
      "comment": "朝は query1 が頻繁"
    },
    {
      "time_id": "evening",
      "label": "夕方（17:00-20:00）",
      "duration_hours": 3,
      "frequencies": {
        "query1.json": 50,
        "query2.json": 300,
        "query3.json": 150
      },
      "comment": "夕方は query2 が頻繁"
    }
  ]
}
```

### パラメータ説明

- `time_id`: タイムステップの識別子（英数字）
- `label`: タイムステップの説明（日本語可）
- `duration_hours`: 時間帯の長さ（時間単位）
- `frequencies`: 各クエリの実行回数
  - キー: クエリファイル名
  - 値: 実行回数

## 実行手順

### 1. フェーズ1: 時刻依存型パース

```bash
python experiments/small_test/run_time_dependent_experiment.py --phase 1
```

**出力例**:
```
======================================================================
フェーズ 1: 時刻依存型クエリパース
======================================================================

[TimeDependentFrequency] 時刻依存型頻度情報を読み込み
  ファイル: .../frequency_time_dependent.json
  タイムステップ数: 2

  [1] morning - 朝（9:00-12:00） (3時間)
      総実行回数: 350
      query1.json: 200回
      query2.json: 50回
      query3.json: 100回

  [2] evening - 夕方（17:00-20:00） (3時間)
      総実行回数: 500
      query1.json: 50回
      query2.json: 300回
      query3.json: 150回

======================================================================
タイムステップ 1/2: morning
  朝（9:00-12:00）
======================================================================
  → クエリをパース中...
  → 頻度の重みを適用中...
  ✓ morning のパース完了
    総利得: 3500.00
    ノード数: 19

======================================================================
タイムステップ 2/2: evening
  夕方（17:00-20:00）
======================================================================
  → クエリをパース中...
  → 頻度の重みを適用中...
  ✓ evening のパース完了
    総利得: 5000.00
    ノード数: 19

[TimeDependentFrequency] パーサーを保存中...
  ✓ time_dependent_output/qp_morning.pkl
  ✓ time_dependent_output/qp_evening.pkl
  ✓ time_dependent_output/time_metadata.json
```

### 2. フェーズ2: 全タイムステップで最適化

```bash
python experiments/small_test/run_time_dependent_experiment.py --phase 2 --algorithm normal
```

**出力例**:
```
======================================================================
フェーズ 2: 時刻依存型最適化
======================================================================
  → 使用アルゴリズム: normal
  → タイムステップ数: 2

======================================================================
タイムステップ 1/2: morning
  朝（9:00-12:00） (3時間)
======================================================================
  → パーサーを読み込み: time_dependent_output/qp_morning.pkl
  →   ノード数: 19
  →   総利得: 3500.00
  → 最適化を実行中...
  ✓ 最適化完了
  →   選択MV数: 8
  →   総ユーティリティ: 3200.00
  →   使用ストレージ: 0.01 MB
  →   実行時間: 0.15 秒

======================================================================
タイムステップ 2/2: evening
  夕方（17:00-20:00） (3時間)
======================================================================
  → パーサーを読み込み: time_dependent_output/qp_evening.pkl
  →   ノード数: 19
  →   総利得: 5000.00
  → 最適化を実行中...
  ✓ 最適化完了
  →   選択MV数: 9
  →   総ユーティリティ: 4800.00
  →   使用ストレージ: 0.01 MB
  →   実行時間: 0.18 秒

======================================================================
最適化サマリー
======================================================================

時刻別最適化結果の比較:
時刻            総利得     MV数   ストレージ(MB)
-------------------------------------------------------
朝（9:00-12:00）  3200.00        8          0.0100
夕方（17:00-20:00） 4800.00        9          0.0110

MV選択の違い:
  leaf_2: evening
  non_leaf_5: morning
```

### 3. フェーズ3: 全フェーズを連続実行

```bash
python experiments/small_test/run_time_dependent_experiment.py --phase 3 --algorithm normal
```

## 結果ファイル

実行後、`experiments/small_test/time_dependent_output/` に以下のファイルが生成されます:

```
time_dependent_output/
├── qp_morning.pkl                    # 朝のパース結果
├── qp_evening.pkl                    # 夕方のパース結果
├── time_metadata.json                # タイムステップメタデータ
├── normal_morning_result.json        # 朝の最適化結果
├── normal_evening_result.json        # 夕方の最適化結果
└── normal_summary.json               # サマリー
```

### サマリーファイルの例

`normal_summary.json`:
```json
[
  {
    "time_id": "morning",
    "label": "朝（9:00-12:00）",
    "duration_hours": 3,
    "total_utility": 3200.0,
    "num_mvs": 8,
    "storage_mb": 0.01,
    "execution_time": 0.15,
    "selected_mvs": [
      "leaf_1",
      "leaf_3",
      "non_leaf_2",
      "non_leaf_5",
      ...
    ]
  },
  {
    "time_id": "evening",
    "label": "夕方（17:00-20:00）",
    "duration_hours": 3,
    "total_utility": 4800.0,
    "num_mvs": 9,
    "storage_mb": 0.011,
    "execution_time": 0.18,
    "selected_mvs": [
      "leaf_1",
      "leaf_2",
      "non_leaf_3",
      "non_leaf_7",
      ...
    ]
  }
]
```

## 分析と解釈

### MV選択の違い

サマリー出力から、各時刻で選択されるMVの違いを確認できます:

```
MV選択の違い:
  leaf_2: evening          # 夕方のみ選択
  non_leaf_5: morning      # 朝のみ選択
```

これは、各時刻で頻度が高いクエリで使われるノードが優先的に選択されたことを示します。

### 利得の違い

- **朝**: query1の頻度が200回 → query1で使われるノードの利得が高い
- **夕方**: query2の頻度が300回 → query2で使われるノードの利得が高い

### 総ユーティリティの比較

夕方の総ユーティリティ（4800）が朝（3200）より高いのは、
夕方の総実行回数（500回）が朝（350回）より多いためです。

## 高度な使用例

### 3つ以上の時刻

```json
{
  "timesteps": [
    {
      "time_id": "morning",
      "label": "朝（9:00-12:00）",
      ...
    },
    {
      "time_id": "afternoon",
      "label": "昼（12:00-17:00）",
      ...
    },
    {
      "time_id": "evening",
      "label": "夕方（17:00-20:00）",
      ...
    },
    {
      "time_id": "night",
      "label": "夜（20:00-24:00）",
      ...
    }
  ]
}
```

### 異なるアルゴリズムで比較

```bash
# normal アルゴリズム
python experiments/small_test/run_time_dependent_experiment.py --phase 2 --algorithm normal

# bigsubs アルゴリズム
python experiments/small_test/run_time_dependent_experiment.py --phase 2 --algorithm bigsubs

# frequency アルゴリズム
python experiments/small_test/run_time_dependent_experiment.py --phase 2 --algorithm frequency
```

## トラブルシューティング

### エラー: frequency_time_dependent.json が見つかりません

```bash
# ファイルの存在確認
ls experiments/small_test/01_queries/frequency_time_dependent.json

# なければサンプルをコピー
cp experiments/small_test/01_queries/frequency.json \
   experiments/small_test/01_queries/frequency_time_dependent.json
```

### phase1 をスキップして phase2 だけ実行したい

phase1 で生成されたパース結果（`qp_*.pkl`）が必要です。
先に phase1 を実行してください。

## まとめ

- **時刻依存型**: 複数の時刻で異なる頻度を設定
- **数式**: `u_ij(t) = cost_j × frequency_i(t)`
- **効果**: 各時刻で最適なMVセットを選択
- **用途**: 時間帯別のワークロード変化に対応

これにより、1日の中でクエリパターンが変化する環境で、各時刻に最適化されたMV戦略を立てることができます。
