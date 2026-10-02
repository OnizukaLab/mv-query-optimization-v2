# 統合された run_experiment.py の使い方

`run_experiment.py` が時刻依存型最適化機能と統合されました。
1つのスクリプトで通常モードと時刻依存型モードの両方を実行できます。

## 前提条件

PyYAMLのインストールが必要です：

```bash
pip install PyYAML
```

## 実行モード

### 1. 通常モード（デフォルト）

単一の頻度重み付けで最適化を実行します。

```bash
# 全フェーズ実行
python experiments/small_test/run_experiment.py --phase all

# フェーズ2のみ実行（頻度重み付けパース）
python experiments/small_test/run_experiment.py --phase 2

# フェーズ3のみ実行（最適化）
python experiments/small_test/run_experiment.py --phase 3
```

**必要なファイル:**
- `experiments/small_test/01_queries/frequency.json` - クエリごとの実行頻度

**出力先:**
- `experiments/small_test/qp_class.pkl` - パース結果
- `experiments/small_test/04_optimized/` - 最適化結果

---

### 2. 時刻依存型モード

複数の時刻（タイムステップ）で異なる頻度を設定し、それぞれ最適化を実行します。

```bash
# フェーズ2: 時刻依存型パース
python experiments/small_test/run_experiment.py --mode time-dependent --phase 2

# フェーズ3: 時刻依存型最適化（アルゴリズム指定必須）
python experiments/small_test/run_experiment.py --mode time-dependent --phase 3 --algorithm normal
```

**必要なファイル:**
- `experiments/small_test/01_queries/frequency_time_dependent.json` - 時刻別頻度設定

**出力先:**
- `experiments/small_test/time_dependent_output/` - すべての時刻依存型結果
  - `qp_<time_id>.pkl` - 各タイムステップのパース結果
  - `<algorithm>_<time_id>_result.json` - 各タイムステップの最適化結果
  - `<algorithm>_summary.json` - 全タイムステップの比較サマリー

---

## コマンドライン引数

### `--mode`

実行モードを指定します。

- `normal` (デフォルト): 通常モード（単一頻度）
- `time-dependent`: 時刻依存型モード（複数タイムステップ）

### `--phase`

実行するフェーズを指定します。

**通常モード:**
- `all`: 全フェーズを順番に実行
- `0`: データベースセットアップ
- `1`: EXPLAIN JSON生成
- `2`: クエリパース（頻度重み付け）
- `3`: ILP最適化
- `4`: MV生成SQL作成
- `5`: MV作成（データベース）

**時刻依存型モード:**
- `2`: 時刻依存型クエリパース
- `3`: 時刻依存型最適化（`--algorithm` 必須）

### `--algorithm`

使用する最適化アルゴリズムを指定します（時刻依存型モードのphase 3で必須）。

- `normal`: 通常のILP
- `bigsubs`: BigSubs アルゴリズム
- `frequency`: 頻度重み付けILP（実験的）

### `--config`

設定ファイルのパスを指定します（デフォルト: `experiments/small_test/config.yaml`）。

---

## 使用例

### 例1: 通常モードで頻度重み付け最適化

```bash
# パースのみ実行
python experiments/small_test/run_experiment.py --phase 2

# 最適化のみ実行
python experiments/small_test/run_experiment.py --phase 3
```

### 例2: 時刻依存型最適化（朝と夜で異なる頻度）

```bash
# ステップ1: 時刻依存型パース
python experiments/small_test/run_experiment.py --mode time-dependent --phase 2

# ステップ2: 各タイムステップで最適化
python experiments/small_test/run_experiment.py --mode time-dependent --phase 3 --algorithm normal

# 結果確認
cat experiments/small_test/time_dependent_output/normal_summary.json
```

### 例3: カスタム設定ファイルを使用

```bash
python experiments/small_test/run_experiment.py \
  --mode time-dependent \
  --phase 3 \
  --algorithm normal \
  --config experiments/small_test/custom_config.yaml
```

---

## 設定ファイルの準備

### 通常モード用頻度ファイル

`experiments/small_test/01_queries/frequency.json`:

```json
{
  "query1": 100,
  "query2": 200,
  "query3": 150
}
```

### 時刻依存型頻度ファイル

`experiments/small_test/01_queries/frequency_time_dependent.json`:

```json
{
  "timesteps": [
    {
      "id": "morning",
      "label": "朝の時間帯（6:00-12:00）",
      "duration_hours": 6,
      "frequencies": {
        "query1": 200,
        "query2": 50,
        "query3": 100
      }
    },
    {
      "id": "evening",
      "label": "夜の時間帯（18:00-24:00）",
      "duration_hours": 6,
      "frequencies": {
        "query1": 50,
        "query2": 300,
        "query3": 150
      }
    }
  ]
}
```

---

## 出力の確認

### 通常モードの結果

```bash
# パース結果のサマリー
cat experiments/small_test/03_parsed/parse_summary.json

# 最適化結果
cat experiments/small_test/04_optimized/normal_result.json
```

### 時刻依存型モードの結果

```bash
# 全タイムステップの比較サマリー
cat experiments/small_test/time_dependent_output/normal_summary.json

# 個別タイムステップの結果
cat experiments/small_test/time_dependent_output/normal_morning_result.json
cat experiments/small_test/time_dependent_output/normal_evening_result.json
```

---

## トラブルシューティング

### エラー: `ModuleNotFoundError: No module named 'yaml'`

**解決策:**
```bash
pip install PyYAML
```

### エラー: `frequency_time_dependent.json が見つかりません`

時刻依存型モードを使用する場合、`frequency_time_dependent.json` が必要です。

**解決策:**
1. サンプルファイルをコピー:
   ```bash
   cp experiments/small_test/01_queries/frequency.json \
      experiments/small_test/01_queries/frequency_time_dependent.json
   ```
2. 時刻依存型フォーマットに編集（上記の例を参照）

### エラー: `時刻依存型モードでは --algorithm を指定してください`

phase 3（最適化）を実行する際は、アルゴリズムの指定が必須です。

**解決策:**
```bash
python experiments/small_test/run_experiment.py \
  --mode time-dependent \
  --phase 3 \
  --algorithm normal
```

---

## 統合のメリット

1. **単一のスクリプト**: 通常モードと時刻依存型モードを1つのスクリプトで管理
2. **一貫したインターフェース**: コマンドライン引数が統一されている
3. **簡単な切り替え**: `--mode` フラグで簡単にモード切り替え
4. **保守性の向上**: 共通のロジック（設定読み込み、出力など）を共有

---

## 関連ファイル

- `experiments/small_test/frequency_weighted_parser.py` - 頻度重み付けパーサー
- `experiments/small_test/time_dependent_parser.py` - 時刻依存型パーサー
- `experiments/small_test/run_time_dependent_experiment.py` - 旧時刻依存型スクリプト（非推奨）

**推奨**: 今後は統合された `run_experiment.py` を使用してください。
