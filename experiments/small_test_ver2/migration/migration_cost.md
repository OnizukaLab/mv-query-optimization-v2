現状の2つの手法の問題点を踏まえ、より良いコスト推定の案を提示します。

## 現状の問題点の整理

### 手法1: migration_cost_with_limited_ex.py (EXPLAIN実行版)
- **問題**: `target_cost - dependency_cost` の計算で、多くが下限値1.0になる
- **原因**: 依存MVを使った場合のコスト削減効果を過大評価している

### 手法2: advanced_migration_costs.py (プラン推定版)
- **問題**: 元のクエリプランのコストから推定するため、実際と乖離
- **原因**: クエリオプティマイザの実際の判断と異なる可能性

---

## 改善案

### 案1: **ハイブリッド推定法（推奨）**

**基本方針**: EXPLAIN実行結果とプラン推定を組み合わせる

```
マイグレーションコスト = 
  base_cost (EXPLAIN実行) × dependency_reduction_factor
```

**実装の考え方**:
1. `[]`プラン（依存なし）のコストは migration_cost_with_limited_ex.py で取得（実測値）
2. 依存MVありプランのコストは、以下の式で推定:
   ```
   cost = base_cost × (1 - overlap_ratio × reduction_rate)
   ```
   - `overlap_ratio`: 依存MVとの重複度（どれだけの計算を省略できるか）
   - `reduction_rate`: コスト削減率（0.3～0.7程度、調整可能なパラメータ）

**メリット**:
- 実測値（EXPLAIN）をベースにするため信頼性が高い
- 1.0の下限値問題を回避できる
- 調整可能なパラメータで柔軟性を持たせられる

---

### 案2: **サンプリング + 補間法**

**基本方針**: 一部のMVを実際に作成してEXPLAINし、その結果から他のコストを補間

**実装の考え方**:
1. 代表的なMV候補（例: コストが高い上位10%、低い下位10%）を実際に作成
2. それらのMVを使ったプランをEXPLAINで実測
3. 実測値から、以下のような関係式を導出:
   ```
   migration_cost = f(base_cost, dependency_count, node_depth, ...)
   ```
4. 未実測のノードは回帰モデルや補間で推定

**メリット**:
- 実測データに基づくため精度が高い
- 全MVを作成する必要がない（10～20%程度で十分）

**デメリット**:
- 初回実行時にMV作成・削除のオーバーヘッドがある
- サンプル選択が結果に影響する

---

### 案3: **カーディナリティベース推定法**

**基本方針**: MVの行数（カーディナリティ）の比率からコストを推定

**実装の考え方**:
```
migration_cost = base_cost × (target_rows / base_rows)^α
```
- `target_rows`: 依存MV使用後の推定行数
- `base_rows`: ベース（依存なし）の行数
- `α`: 調整パラメータ（通常1.0～1.5、JOIN の複雑さに応じて変更）

**行数の推定方法**:
- `target_rows ≈ base_rows × (1 - selectivity_of_dependencies)`
- `selectivity`: 依存MVのフィルタ条件による選択率（EXPLAIN結果から取得可能）

**メリット**:
- EXPLAIN結果の行数情報を活用できる
- シンプルで理解しやすい

---

### 案4: **下限値の動的調整法**

**基本方針**: 現在の下限値1.0を、ノードの特性に応じて動的に調整

**実装の考え方**:
```python
min_cost = max(
    1.0,
    base_cost × 0.1,  # ベースコストの10%
    dependency_cost × 0.05  # 依存コストの5%
)

migration_cost = max(target_cost - dependency_cost, min_cost)
```

**メリット**:
- 既存コードへの変更が最小限
- 極端に小さい値（1.0）を避けられる

**デメリット**:
- 根本的な解決にはならない

---

### 案5: **段階的マイグレーションコスト推定**

**基本方針**: 依存MVを段階的に適用した場合のコストを考慮

**実装の考え方**:
1. 依存MV1つだけを使った場合のコスト削減率を推定
2. 複数の依存MVを使う場合は、削減率を累積（ただし逓減を考慮）:
   ```
   total_reduction = 1 - ∏(1 - reduction_i × decay_factor^i)
   ```
3. マイグレーションコスト = `base_cost × (1 - total_reduction)`

**メリット**:
- 複数の依存関係を持つノードでも現実的な推定が可能
- 過度な削減を防げる

---

## 推奨アプローチ

**案1（ハイブリッド推定法）を基本とし、案3（カーディナリティベース推定）を補助的に使用**

### 具体的な実装ステップ:

1. **ベースコストの取得** (migration_cost_with_limited_ex.pyの結果)
2. **依存関係の分析**:
   - 各依存MVがカバーするテーブル数
   - JOIN条件の重複度
   - フィルタ条件の選択率
3. **コスト削減率の計算**:
   ```python
   overlap_ratio = len(dependency_tables ∩ target_tables) / len(target_tables)
   reduction_rate = 0.3 + (0.4 × selectivity)  # 30%～70%の範囲
   estimated_cost = base_cost × (1 - overlap_ratio × reduction_rate)
   ```
4. **下限値の設定**:
   ```python
   min_cost = base_cost × 0.15  # ベースコストの15%を下限とする
   final_cost = max(estimated_cost, min_cost)
   ```

### パラメータの調整方法:

- サンプリング（案2）で一部のMVを実際に作成し、実測値と推定値を比較
- 誤差が大きい場合は `reduction_rate` や `α` を調整
- 反復的に精度を向上させる

---

この方法により、**実測値ベースの信頼性**と**全MV作成不要の実用性**を両立できると考えます。