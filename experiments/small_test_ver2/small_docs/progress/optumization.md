了解です。
では、`time_dependent_optimizer.py` 内に**実際に実装されている制約（コメントアウトを除く）**をすべて網羅し、
それらを踏まえて **目的関数・制約・変数** の完全な理論構成として整理して説明します。

---

# 🧮 Time-dependent ILP Model（`TimeDependentOptimizer`）

## ■ 概要

このモデルは、**時刻ごとに変化するワークロードに対して、どの実体化ビュー (MV)** を保持するか、
および **どのレシピでマイグレーション（再構築）するか** を最適化する **整数線形計画 (ILP)** です。

目的は、

> **時刻ごとのワークロード実行コストとマイグレーションコストの合計を最小化すること。**

---

## 🎯 目的関数 (Objective Function)

$$
\min ; \text{WorkloadCost} + \text{MigrationCost}
$$

### (1) Workload Cost

$$
\text{WorkloadCost} =
-\sum_{t \in T} \sum_{i \in I} \sum_{j \in J}
u_{ij} \cdot f_{i,t} \cdot y_{ijt}
$$

* $(u_{ij})$：クエリ $(i)$ が MV $(j)$ を使用する効果（benefit）
* $(f_{i,t})$：時刻 $(t)$ におけるクエリ $(i)$ の出現頻度
* $(y_{ijt})$：クエリ $(i)$ が時刻 $(t)$ に MV $(j)$ を使う場合 1
  → 効果を「−」符号で扱うことで benefit 最大化 = コスト最小化 に変換

---

### (2) Migration Cost

$$
\text{MigrationCost} =
\sum_{t \in T} \sum_{j \in J} \sum_{k \in K_j}
c_{jk} \cdot a_{jtk}
$$

* $(c_{jk})$：MV $(j)$ をレシピ $(k)$ で作成する際のコスト
* $(a_{jtk})$：MV $(j)$ が時刻 $(t)$ にレシピ $(k)$ で作られるなら 1

---

## 🔧 制約条件 (Constraints)

以下、ファイル内で**実際に addConstr で追加されているもの**をすべて網羅します。

---

### (1) **使用 ⇒ 実体化**

```python
self.y[i, j, t] <= self.z[j, t]
```

$$
y_{ijt} \le z_{jt}
$$

* クエリがMVを使用するなら、そのMVは存在していなければならない。
* **論理的整合性制約**。

---

### (2) **包含・重複排除 (Overlap Exclusion)**

```python
self.y[i, j, t] + gp.quicksum(self.y[i, u, t] * self.X[j][u] for u in range(self.J) if u != j) <= 1
```

$$
y_{ijt} + \sum_{u \neq j} X_{ju} \cdot y_{iut} \le 1
$$

* $(X_{ju} = 1)$：MV $(j)$ が MV $(u)$ を包含している場合。
* 同時に包含関係を持つMVを使用しないようにする。
* **重複するMV利用の排除制約**。

---

### (3) **ストレージ容量制限 (Storage Budget)**

```python
gp.quicksum(self.b_j[j] * self.z[j, t] for j in range(self.J)) <= self.B_max
```

$$
\sum_{j} b_j \cdot z_{jt} \le B_{\max}
$$

* $(b_j)$：MV $(j)$ のストレージサイズ
* $(B_{\max})$：総ストレージ容量上限
* 各時刻でのストレージ使用量を制限。

---

### (4) **生成フラグ定義 (Creation Flag Definition)**

#### 初期時刻 (t=0):

```python
self.c[j, 0] == self.z[j, 0]
```

$$
c_{j0} = z_{j0}
$$

* 初期時刻では「存在 = 作成」を意味する。

#### 以降 (t > 0):

```python
c[j, t] >= z[j, t] - z[j, t - 1]
c[j, t] <= z[j, t]
c[j, t] <= 1 - z[j, t - 1]
```

$$
\begin{cases}
c_{jt} \ge z_{jt} - z_{j,t-1} \\
c_{jt} \le z_{jt} \\
c_{jt} \le 1 - z_{j,t-1}
\end{cases}
$$

* これにより、**新しく作成されたときのみ** $(c_{jt}=1)$。
* 前時刻から継続して存在している場合は $(c_{jt}=0)$。

---

### (5) **レシピ選択 (Recipe Selection)**

```python
gp.quicksum(self.a[j, t, k_idx] for k_idx in range(len(recs))) == self.c[j, t]
```

$$
\sum_{k} a_{jtk} = c_{jt}
$$

* MVが新規作成されるとき、レシピを**ちょうど1つ**選ぶ。

---

### (6) **レシピ有効化 (Recipe Enablement)**

```python
self.a[j, t, k_idx] <= self.c[j, t]
```

$$
a_{jtk} \le c_{jt}
$$

* レシピは、MVが作成されるときにのみ有効化できる。

---

### (7) **初期時刻の依存制約 (No dependency at t=0)**

```python
if t == 0 and len(recipe) > 0:
    self.a[j, t, k_idx] == 0
```

$$
a_{j0k} = 0 \quad (\text{if recipe has dependencies})
$$

* 時刻0では、依存元MVが存在しないため、依存を持つレシピは使用禁止。

---

### (8) **レシピ依存関係 (Dependency Constraint)**

```python
self.a[j, t, k_idx] <= self.z[dep, t - 1]
```

$$
a_{jtk} \le z_{d,t-1} \quad \forall d \in \text{recipe}_k
$$

* レシピが依存するMVは**前時刻に存在**していなければならない。

---

## 🧩 変数（Decision Variables）

| 記号        | 定義                             | 型      | 意味    |
| --------- | ------------------------------ | ------ | ----- |
| $(y_{ijt})$ | クエリ $(i)$ が MV $(j)$ を時刻 $(t)$ に使う   | binary | 使用関係  |
| $(z_{jt})$  | MV $(j)$ が時刻 $(t)$ に存在する           | binary | 実体化状態 |
| $(c_{jt})$  | MV $(j)$ が時刻 $(t)$ に新規作成される        | binary | 作成フラグ |
| $(a_{jtk})$ | MV $(j)$ が時刻 $(t)$ にレシピ $(k)$ で作成される | binary | レシピ選択 |

---

## ⚖️ 理論的解釈

このILPは、「**時間軸付きの実体化ビュー選択問題**」を厳密に表しています。

* 各時刻でストレージ制約を守りながら
* ワークロード（クエリの利益）を最大化（＝コスト最小化）し
* 必要に応じてマイグレーション（再作成）を行う

時刻 $(t)$ と $(t-1)$ の関係が明示的に制約されているため、
**時間的整合性を保ったマルチステップ最適化**になっています。

---

## ✅ まとめスライド向け要約

| 項目       | 内容                               |
| -------- | -------------------------------- |
| **目的関数** | ワークロードコスト + マイグレーションコストの最小化      |
| **制約**   | 使用→存在、容量制限、包含排除、生成フラグ、レシピ選択・依存関係 |
| **変数**   | $(y)$：使用, $(z)$：存在, $(c)$：作成, $(a)$：レシピ  |

---

もし希望があれば、これを

* 「研究発表スライド用の1枚構成」または
* 「目的関数・制約・変数の3スライド構成」

として図と数式入りで整えたスライド用文案（PowerPointやBeamer用）も作れます。
どちらの形式にしましょうか？
