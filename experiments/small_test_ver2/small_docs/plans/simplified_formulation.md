# 簡略化版 Time-Dependent MV Optimizer 定式化

本ドキュメントは、simple_migration_planner（2パターンのみ）を前提とした簡略化版の最適化定式化です。

## 前提条件

- 各MVに対して**2つのマイグレーションパターンのみ**:
  1. `NON_MIGRATE`: 既に存在している（マイグレーション不要、コスト0）
  2. `[]`: 依存MV無しでフルビルド（固定コスト）

- レシピ選択の自由度がないため、`a[j,t,k]` 変数が不要

## インデックス・パラメータ

### インデックス
- $i \in \{1, \ldots, I\}$: クエリのインデックス
- $j \in \{1, \ldots, J\}$: MV候補のインデックス
- $t \in \{0, \ldots, T-1\}$: タイムステップのインデックス

### パラメータ
- $u_{i,j}$: クエリ$i$がMV $j$を使用した場合の利得（コスト削減量）
- $f_{i,t}$: タイムステップ$t$でのクエリ$i$の実行頻度
- $X_{j,u} \in \{0,1\}$: MV $j$がMV $u$を包含する場合1、そうでない場合0
- $b_j$: MV $j$のストレージサイズ
- $B_{\max}$: ストレージ予算の上限
- $m_j$: MV $j$のフルビルドマイグレーションコスト（固定値）

## 決定変数

### 変数定義
- $y_{i,j,t} \in \{0,1\}$: クエリ$i$がタイムステップ$t$でMV $j$を使用する場合1
- $z_{j,t} \in \{0,1\}$: MV $j$がタイムステップ$t$で存在する場合1
- $c_{j,t} \in \{0,1\}$: MV $j$がタイムステップ$t$で新規作成される場合1

**削除された変数**: 
- ~~$a_{j,t,k}$~~: レシピ選択変数（2パターンのみなので不要）

## 制約式

### 1. 使用→実体化制約
$$
y_{i,j,t} \leq z_{j,t} \quad \forall i, j, t
$$

**意味**: クエリがMVを使用するには、そのMVが存在している必要がある。

---

### 2. 包含・重複排除制約
$$
y_{i,j,t} + \sum_{\substack{u \neq j \\ X_{j,u}=1}} y_{i,u,t} \leq 1 \quad \forall i, j, t
$$

**意味**: クエリ$i$は、MV $j$と、$j$に包含されるMV $u$を同時に使用できない。

---

### 3. ストレージ予算制約
$$
\sum_{j=1}^{J} b_j \cdot z_{j,t} \leq B_{\max} \quad \forall t
$$

**意味**: 各タイムステップで選択されたMVの合計サイズが予算を超えない。

---

### 4. 作成フラグ制約（初期タイムステップ）
$$
c_{j,0} = z_{j,0} \quad \forall j
$$

**意味**: 初期タイムステップで存在するMVはすべて新規作成とみなす。

---

### 5. 作成フラグ制約（後続タイムステップ）
$$
\begin{align}
c_{j,t} &\geq z_{j,t} - z_{j,t-1} \quad &&\forall j, t \geq 1 \\
c_{j,t} &\leq z_{j,t} \quad &&\forall j, t \geq 1 \\
c_{j,t} &\leq 1 - z_{j,t-1} \quad &&\forall j, t \geq 1
\end{align}
$$

**意味**: 
- (5.1) 前タイムステップで存在せず、現タイムステップで存在する場合、$c_{j,t}=1$（作成）
- (5.2) 存在しない場合、作成できない
- (5.3) 前タイムステップで存在していた場合、$c_{j,t}=0$（継続、作成なし）

---

## 削除された制約

元の定式化から以下の制約が削除されます：

### ~~6. レシピ選択制約~~（削除）
$$
\require{cancel}
\cancel{\sum_k a_{j,t,k} = c_{j,t} \quad \forall j, t}
$$

**理由**: レシピが2パターンのみで、作成時は常にフルビルドを使用するため不要。

---

### ~~7. レシピ有効化制約~~（削除）
$$
\cancel{a_{j,t,k} \leq c_{j,t} \quad \forall j, t, k}
$$

**理由**: $a$変数が存在しないため不要。

---

### ~~8. レシピ依存制約（t=0）~~（削除）
$$
\cancel{a_{j,0,k} = 0 \quad \forall j, k \text{ where } k \text{ has dependencies}}
$$

**理由**: simple_migration_plannerでは依存レシピが存在しないため不要。

---

### ~~9. レシピ依存制約（t>0）~~（削除）
$$
\cancel{a_{j,t,k} \leq z_{m,t-1} \quad \forall j, t > 0, k, m \in \text{deps}(k)}
$$

**理由**: 依存関係を持つレシピが存在しないため不要。

---

## 目的関数

### 最小化問題
$$
\min \quad \underbrace{\sum_{t=0}^{T-1} \sum_{i=1}^{I} \sum_{j=1}^{J} \left( -u_{i,j} \cdot f_{i,t} \cdot y_{i,j,t} \right)}_{\text{ワークロードコスト}} + \underbrace{\sum_{t=0}^{T-1} \sum_{j=1}^{J} m_j \cdot c_{j,t}}_{\text{マイグレーションコスト}}
$$

### 各項の説明

#### 1. ワークロードコスト
$$
\sum_{t=0}^{T-1} \sum_{i=1}^{I} \sum_{j=1}^{J} \left( -u_{i,j} \cdot f_{i,t} \cdot y_{i,j,t} \right)
$$

- $u_{i,j}$: 利得（コスト削減量）
- $f_{i,t}$: クエリ頻度
- 負符号: 利得の最大化 = コストの最小化

#### 2. マイグレーションコスト（簡略化版）
$$
\sum_{t=0}^{T-1} \sum_{j=1}^{J} m_j \cdot c_{j,t}
$$

- $m_j$: MV $j$のフルビルドコスト（**固定値**）
- $c_{j,t}=1$のときのみコストが加算される

**元の定式化との違い**:
- 元: $\sum_t \sum_j \sum_k \text{cost}_{j,k} \cdot a_{j,t,k}$ （レシピ$k$ごとのコスト）
- 簡略化: $\sum_t \sum_j m_j \cdot c_{j,t}$ （固定のフルビルドコストのみ）

---

## 完全な定式化まとめ

### 変数
$$
\begin{align}
y_{i,j,t} &\in \{0,1\} \quad &&\forall i, j, t \\
z_{j,t} &\in \{0,1\} \quad &&\forall j, t \\
c_{j,t} &\in \{0,1\} \quad &&\forall j, t
\end{align}
$$

### 制約
$$
\begin{align}
&\text{(1) 使用→実体化:} & y_{i,j,t} &\leq z_{j,t} \quad &&\forall i, j, t \\
&\text{(2) 包含排除:} & y_{i,j,t} + \sum_{\substack{u \neq j \\ X_{j,u}=1}} y_{i,u,t} &\leq 1 \quad &&\forall i, j, t \\
&\text{(3) ストレージ:} & \sum_{j=1}^{J} b_j \cdot z_{j,t} &\leq B_{\max} \quad &&\forall t \\
&\text{(4) 初期作成:} & c_{j,0} &= z_{j,0} \quad &&\forall j \\
&\text{(5.1) 作成下限:} & c_{j,t} &\geq z_{j,t} - z_{j,t-1} \quad &&\forall j, t \geq 1 \\
&\text{(5.2) 作成上限:} & c_{j,t} &\leq z_{j,t} \quad &&\forall j, t \geq 1 \\
&\text{(5.3) 継続時非作成:} & c_{j,t} &\leq 1 - z_{j,t-1} \quad &&\forall j, t \geq 1
\end{align}
$$

### 目的関数
$$
\min \quad \sum_{t=0}^{T-1} \sum_{i=1}^{I} \sum_{j=1}^{J} \left( -u_{i,j} \cdot f_{i,t} \cdot y_{i,j,t} \right) + \sum_{t=0}^{T-1} \sum_{j=1}^{J} m_j \cdot c_{j,t}
$$

---

## 変数数・制約数の比較

### 簡略化版

| 項目 | 数式 | 例（I=33, J=536, T=16） |
|------|------|-------------------------|
| **変数数** | | |
| $y$ 変数 | $I \times J \times T$ | 283,008 |
| $z$ 変数 | $J \times T$ | 8,576 |
| $c$ 変数 | $J \times T$ | 8,576 |
| **合計** | $I \times J \times T + 2 \times J \times T$ | **300,160** |
| | | |
| **制約数** | | |
| 使用→実体化 | $I \times J \times T$ | 283,008 |
| 包含排除 | $\leq I \times J \times T$ | ≤ 283,008 |
| ストレージ | $T$ | 16 |
| 作成フラグ | $J + 3 \times J \times (T-1)$ | 24,656 |
| **合計** | $\approx 2 \times I \times J \times T + 4 \times J \times T$ | **≈ 590,688** |

### 元の定式化（レシピあり）

| 項目 | 数式 | 例（平均レシピ数=2） |
|------|------|---------------------|
| **変数数** | | |
| $y$ 変数 | $I \times J \times T$ | 283,008 |
| $z$ 変数 | $J \times T$ | 8,576 |
| $c$ 変数 | $J \times T$ | 8,576 |
| $a$ 変数 | $J \times T \times \bar{K}$ | 17,152 |
| **合計** | $I \times J \times T + (2+\bar{K}) \times J \times T$ | **317,312** |
| | | |
| **制約数** | | |
| （前述の制約） | | 590,688 |
| レシピ選択 | $J \times T$ | 8,576 |
| レシピ有効化 | $J \times T \times \bar{K}$ | 17,152 |
| レシピ依存 | $\approx J \times T \times \bar{K} \times \bar{D}$ | ～0（依存なし） |
| **合計** | | **≈ 616,416** |

### 削減効果

- **変数削減**: 17,152個（5.4%減）
- **制約削減**: 25,728個（4.2%減）
- **効果**: 小規模（全体の5%程度の削減）

---

## 実装上の変更点

元の実装と比較して、以下のメソッドが簡略化されます：

### `build_variables`
```python
# 削除: a[j,t,k] 変数の生成ループ
# for k_idx, (_recipe, _cost) in enumerate(recs):
#     self.a[j, t, k_idx] = m.addVar(...)
```

### `add_creation_and_recipe_constraints`
```python
# 削除: レシピ選択制約
# m.addConstr(quicksum(self.a[j, t, k_idx] ...) == self.c[j, t], ...)

# 削除: レシピ有効化制約
# m.addConstr(self.a[j, t, k_idx] <= self.c[j,t], ...)

# 削除: レシピ依存制約
# for dep in recipe:
#     m.addConstr(self.a[j, t, k_idx] <= self.z[dep, t - 1], ...)
```

### `build_objective`
```python
# 元のマイグレーションコスト項
# migration_cost = gp.quicksum(
#     float(self.recipes.get(j, [(tuple(), 0.0)])[k_idx][1]) * self.a[j, t, k_idx]
#     for t in range(self.T)
#     for j in range(self.J)
#     for k_idx in range(len(self.recipes.get(j, [(tuple(), 0.0)])))
# )

# 簡略化版のマイグレーションコスト項
migration_cost = gp.quicksum(
    float(self.migration_cost[j]) * self.c[j, t]  # 固定コスト
    for t in range(self.T)
    for j in range(self.J)
)
```

---

## まとめ

簡略化版では：

1. **レシピ選択の自由度を削除**して、常にフルビルドのみを使用
2. **変数 `a[j,t,k]` を削除**し、全体の変数数を5.4%削減
3. **レシピ関連の制約を削除**し、制約数を4.2%削減
4. **マイグレーションコストを簡略化**して、固定値 $m_j$ を使用

ただし、**ILP求解時間は全体の0.006%**しか占めていないため、実行時間への影響は微小です。
