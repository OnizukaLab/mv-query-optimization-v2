# 頻度重み付け最適化の使用方法

## 概要

`experiments/small_test` では、各クエリの実行頻度を利得（Utility）に乗算することで、頻度が高いクエリで使われるサブクエリをより価値が高いものとして扱います。

## 数式

### 従来の利得計算

```
u_ij = cost_j  (クエリiがノードjを使用する場合のコスト削減)
```

### 頻度重み付け利得計算

```
u_ij = cost_j × frequency_i  (頻度を乗算)
```

ここで：
- `u_ij`: クエリ i がノード j をMVとして使う場合の利得
- `cost_j`: ノード j の実行コスト
- `frequency_i`: クエリ i の実行頻度

### ILP目的関数

```
maximize: Σ_i Σ_j (u_ij × y_ij) - Σ_j (m_cost_j × z_j)
         = Σ_i Σ_j (cost_j × frequency_i × y_ij) - Σ_j (m_cost_j × z_j)
```

これにより、頻度が高いクエリ（例: `frequency_i = 100`）のノードは、
頻度が低いクエリ（例: `frequency_i = 10`）のノードより10倍の価値を持つことになります。

## 実装の仕組み

### 1. 頻度情報ファイル

`experiments/small_test/01_queries/frequency.json`:
```json
{
  "query1.json": 100,
  "query2.json": 50,
  "query3.json": 200
}
```

### 2. FrequencyWeightedParser

`experiments/small_test/frequency_weighted_parser.py`:
- `QueryParser` を継承
- `apply_frequency_weights()` メソッドで `u_ij` に頻度を乗算
- `src/` 配下のコードは変更しない

### 3. run_experiment.py の修正

`phase2_parse_queries()` で:
1. `FrequencyWeightedParser` を使用
2. 通常の `query_parse()` を実行
3. `apply_frequency_weights()` で頻度の重みを適用

## 使用手順

### 1. 頻度情報の設定

```bash
# 頻度情報ファイルを編集
nano experiments/small_test/01_queries/frequency.json
```

```json
{
  "query1.json": 10,   # query1 は10回実行
  "query2.json": 100,  # query2 は100回実行（頻繁）
  "query3.json": 50    # query3 は50回実行
}
```

### 2. クエリパース（頻度重み付け）

```bash
python experiments/small_test/run_experiment.py --phase 2
```

出力例:
```
[FrequencyWeighted] 頻度情報を読み込み: .../frequency.json
  query1.json: 10回
  query2.json: 100回
  query3.json: 50回

[FrequencyWeighted] 利得に頻度の重みを適用中...
  Query 0 (query1.json): 頻度 10x
  Query 1 (query2.json): 頻度 100x
  Query 2 (query3.json): 頻度 50x

[FrequencyWeighted] 重み付け完了
  総利得 (U_max): 15000.00
  総実行回数: 160
  平均実行回数: 53.3
```

### 3. 検証

```bash
python experiments/small_test/verify_frequency_weights.py
```

### 4. 最適化実行

```bash
python experiments/small_test/run_experiment.py --phase 3
```

### 5. 結果確認

```bash
# 最適化結果
cat experiments/small_test/Output/normal_result.json

# 選択されたMVを確認
jq '.materialized_nodes' experiments/small_test/Output/normal_result.json
```

## 期待される効果

### 例: 3つのクエリ

| クエリ | 頻度 | ノード | 元の利得 | 重み付け後 |
|--------|------|--------|----------|------------|
| query1 | 10x  | node_1 | 10.0     | 100.0      |
| query2 | 100x | node_2 | 10.0     | 1000.0     |
| query3 | 50x  | node_3 | 10.0     | 500.0      |

→ `node_2`（query2で使用）が最も価値が高いと評価される

### メリット

1. **頻繁に実行されるクエリを優先**: query2（100回）で使われるMVが優先的に選択
2. **実運用に即した最適化**: アクセス頻度の高いクエリのパフォーマンスを重視
3. **設定の柔軟性**: 頻度情報を変更するだけで最適化の方針を調整可能

## トラブルシューティング

### 頻度情報が反映されない

```bash
# パース結果を確認
python experiments/small_test/verify_frequency_weights.py
```

「利得比率 ≈ 頻度比率」と表示されれば正常です。

### 元のパーサーに戻したい

`run_experiment.py` の `phase2_parse_queries()` で:
```python
# FrequencyWeightedParser を使わない
self.qp = QueryParser(self.settings)
```

## 設定ファイル

`experiments/small_test/config.yaml`:
```yaml
optimization:
  insert_queries: 0  # メンテナンスコスト無効化推奨

benchmark:
  frequency_file: experiments/small_test/01_queries/frequency.json
```

## まとめ

- **変更箇所**: `experiments/small_test/` 配下のみ
- **src/ は無変更**: 元のコードベースに影響なし
- **数式**: `u_ij = cost_j × frequency_i`
- **効果**: 頻度が高いクエリのMVを優先選択
