### MVマイグレーションプランの全パターン列挙手法

前の時刻のMV構成が不明な場合に、全てのマイグレーションプランを列挙する手法を提案します。

---

## 🎯 問題の定式化

### **入力**
- **Target MV**: 作成したいMV（例: `non_leaf_28`）
- **Dependency Graph**: Target MVが依存する全ノード（テーブル、中間ノード）

### **未知の情報**
- **Previous MV Configuration**: 前の時刻でどのノードがMV化されているか

### **目標**
- **全てのマイグレーションプランを列挙**
  - どのMVを再利用するか
  - どのMVを新規作成するか
  - どのMVを削除するか

---

## 📊 手法1: 冪集合（Power Set）による全列挙

### **基本アイデア**
- Target MVの依存ノード集合の**冪集合**を生成
- 各部分集合を「前の時刻のMV構成」として扱う

### **アルゴリズム**

```python
from itertools import combinations

def enumerate_all_migration_plans(target_mv, dependency_graph):
    """
    全てのマイグレーションプランを列挙
    
    Args:
        target_mv: 作成したいMVのノードID
        dependency_graph: 依存グラフ (Dict[node_id, List[child_nodes]])
    
    Returns:
        List[MigrationPlan]: 全てのマイグレーションプラン
    """
    # 1. Target MVが依存する全ノードを収集
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    
    # 2. Leaf（テーブル）を除外（MVになり得るのは非Leafのみ）
    candidate_mvs = [node for node in dependent_nodes if not is_leaf(node)]
    
    # 3. 冪集合を生成（全ての部分集合）
    all_mv_configs = []
    for r in range(len(candidate_mvs) + 1):
        for subset in combinations(candidate_mvs, r):
            all_mv_configs.append(set(subset))
    
    # 4. 各MV構成に対してマイグレーションプランを計算
    migration_plans = []
    for prev_mv_config in all_mv_configs:
        plan = compute_migration_plan(target_mv, prev_mv_config, dependency_graph)
        migration_plans.append(plan)
    
    return migration_plans


def get_all_dependent_nodes(node_id, dependency_graph):
    """依存する全ノードを再帰的に収集"""
    visited = set()
    stack = [node_id]
    
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        
        # 子ノードをスタックに追加
        if current in dependency_graph:
            stack.extend(dependency_graph[current])
    
    return visited - {node_id}  # 自分自身を除外


def compute_migration_plan(target_mv, prev_mv_config, dependency_graph):
    """
    特定のMV構成に対するマイグレーションプランを計算
    
    Args:
        target_mv: 作成したいMV
        prev_mv_config: 前の時刻のMV構成（Set[node_id]）
        dependency_graph: 依存グラフ
    
    Returns:
        MigrationPlan: {
            'reuse_mvs': 再利用するMV,
            'create_mvs': 新規作成するMV,
            'drop_mvs': 削除するMV,
            'cost': 推定コスト
        }
    """
    # Target MVの依存ノード
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    
    # 再利用可能なMV（前の時刻に存在 & Target MVの依存ノード）
    reuse_mvs = prev_mv_config & dependent_nodes
    
    # 新規作成が必要なMV（Target MVの依存ノード & 前の時刻に存在しない）
    create_mvs = dependent_nodes - prev_mv_config
    
    # 削除するMV（前の時刻に存在 & Target MVの依存ノードではない）
    drop_mvs = prev_mv_config - dependent_nodes
    
    # コスト計算
    cost = estimate_migration_cost(reuse_mvs, create_mvs, drop_mvs)
    
    return {
        'prev_mv_config': prev_mv_config,
        'reuse_mvs': reuse_mvs,
        'create_mvs': create_mvs,
        'drop_mvs': drop_mvs,
        'cost': cost
    }
```

---

### **計算量**

```python
# 候補MVの数: n
# 冪集合のサイズ: 2^n

# 例: n=10 の場合
2^10 = 1024 パターン

# 例: n=20 の場合
2^20 = 1,048,576 パターン（実用的な限界）
```

**問題点**: 候補MVが多いと組み合わせ爆発。

---

## 📊 手法2: 動的計画法（DP）による最適化

### **基本アイデア**
- 全パターンを列挙せず、**最適なプランのみを探索**
- コストを最小化するMV構成を動的に選択

### **アルゴリズム**

```python
def find_optimal_migration_plans(target_mv, dependency_graph, max_plans=10):
    """
    動的計画法で最適なマイグレーションプランを探索
    
    Args:
        target_mv: 作成したいMV
        dependency_graph: 依存グラフ
        max_plans: 返す最適プランの数
    
    Returns:
        List[MigrationPlan]: コストが低い順にソートされたプラン
    """
    # 1. 依存ノードを取得
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    candidate_mvs = [node for node in dependent_nodes if not is_leaf(node)]
    
    # 2. DPテーブル: dp[mv_subset] = (cost, plan)
    dp = {}
    dp[frozenset()] = (0, {'reuse_mvs': set(), 'create_mvs': set(), 'drop_mvs': set()})
    
    # 3. 各候補MVについて、追加するか決定
    for mv in candidate_mvs:
        new_dp = dp.copy()
        
        for prev_config, (prev_cost, prev_plan) in dp.items():
            # MVを追加する場合
            new_config = frozenset(prev_config | {mv})
            create_cost = estimate_create_cost(mv, prev_config, dependency_graph)
            new_cost = prev_cost + create_cost
            
            # より良いプランなら更新
            if new_config not in new_dp or new_cost < new_dp[new_config][0]:
                new_plan = prev_plan.copy()
                new_plan['create_mvs'].add(mv)
                new_dp[new_config] = (new_cost, new_plan)
        
        dp = new_dp
    
    # 4. コストが低い順にソート
    plans = sorted(dp.values(), key=lambda x: x[0])
    return [plan for cost, plan in plans[:max_plans]]


def estimate_create_cost(mv, existing_mvs, dependency_graph):
    """MV作成コストを推定"""
    # 既存MVを利用できる場合はコスト削減
    children = dependency_graph.get(mv, [])
    reusable_children = [c for c in children if c in existing_mvs]
    
    base_cost = get_node_cost(mv)
    discount = len(reusable_children) / len(children) if children else 0
    
    return base_cost * (1 - discount * 0.5)  # 50%のコスト削減
```

---

### **計算量**

```python
# 候補MVの数: n
# DPテーブルのサイズ: O(2^n)
# 各状態の遷移: O(1)

# 総計算量: O(2^n)

# しかし、実際には枝刈りで大幅に削減可能
```

---

## 📊 手法3: ヒューリスティック探索（実用的）

### **基本アイデア**
- 全パターンを列挙せず、**有望なパターンのみを探索**
- コスト削減効果が高いMVを優先的に選択

### **アルゴリズム**

```python
def heuristic_migration_plans(target_mv, dependency_graph, beam_width=100):
    """
    ヒューリスティック探索で上位のマイグレーションプランを探索
    
    Args:
        target_mv: 作成したいMV
        dependency_graph: 依存グラフ
        beam_width: ビーム幅（探索する候補数）
    
    Returns:
        List[MigrationPlan]: 有望なプラン
    """
    # 1. 依存ノードを取得
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    candidate_mvs = [node for node in dependent_nodes if not is_leaf(node)]
    
    # 2. 各MVの「価値」を計算（コスト削減効果 / 作成コスト）
    mv_values = []
    for mv in candidate_mvs:
        cost_saving = estimate_cost_saving(mv, target_mv, dependency_graph)
        creation_cost = estimate_create_cost(mv, set(), dependency_graph)
        value = cost_saving / creation_cost if creation_cost > 0 else 0
        mv_values.append((value, mv))
    
    # 3. 価値が高い順にソート
    mv_values.sort(reverse=True)
    
    # 4. Beam Search
    # 初期状態: MVなし
    beam = [{'mv_config': set(), 'cost': 0}]
    
    for value, mv in mv_values:
        new_beam = []
        
        for state in beam:
            # MVを追加しない場合
            new_beam.append(state)
            
            # MVを追加する場合
            new_config = state['mv_config'] | {mv}
            new_cost = state['cost'] + estimate_create_cost(mv, state['mv_config'], dependency_graph)
            new_beam.append({'mv_config': new_config, 'cost': new_cost})
        
        # コストが低い順にソートし、上位beam_width個を保持
        new_beam.sort(key=lambda x: x['cost'])
        beam = new_beam[:beam_width]
    
    # 5. 最終的なプランを生成
    plans = []
    for state in beam:
        plan = compute_migration_plan(target_mv, state['mv_config'], dependency_graph)
        plans.append(plan)
    
    return plans


def estimate_cost_saving(mv, target_mv, dependency_graph):
    """MVを作成することによるコスト削減を推定"""
    # Target MVのクエリで、このMVを使う回数
    usage_count = count_usage_in_query(mv, target_mv, dependency_graph)
    
    # MVのスキャンコスト vs 元のクエリのコスト
    mv_scan_cost = get_node_cost(mv)
    original_cost = get_subtree_cost(mv, dependency_graph)
    
    return (original_cost - mv_scan_cost) * usage_count
```

---

### **計算量**

```python
# 候補MVの数: n
# Beam width: w

# 総計算量: O(n * w)

# 例: n=20, w=100
O(20 * 100) = O(2000)  # 非常に高速
```

---

## 📊 手法4: グラフベースの制約付き列挙

### **基本アイデア**
- 依存関係を考慮し、**矛盾のない構成のみ列挙**
- 例: 親ノードがMVなら子ノードもMVにする

### **アルゴリズム**

```python
def enumerate_valid_mv_configs(target_mv, dependency_graph):
    """
    依存関係を満たすMV構成のみを列挙
    
    制約:
    - 親ノードがMVなら、その子ノードもMVまたはLeaf
    - 孤立したMVは作らない
    """
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    candidate_mvs = [node for node in dependent_nodes if not is_leaf(node)]
    
    valid_configs = []
    
    # トポロジカルソート（依存順序）
    sorted_mvs = topological_sort(candidate_mvs, dependency_graph)
    
    # バックトラッキング
    def backtrack(index, current_config):
        if index == len(sorted_mvs):
            valid_configs.append(current_config.copy())
            return
        
        mv = sorted_mvs[index]
        
        # MVを追加しない場合
        backtrack(index + 1, current_config)
        
        # MVを追加する場合（制約チェック）
        if is_valid_addition(mv, current_config, dependency_graph):
            current_config.add(mv)
            backtrack(index + 1, current_config)
            current_config.remove(mv)
    
    backtrack(0, set())
    return valid_configs


def is_valid_addition(mv, current_config, dependency_graph):
    """MVを追加することが有効かチェック"""
    # 子ノードが全てMVまたはLeafであることを確認
    children = dependency_graph.get(mv, [])
    for child in children:
        if not is_leaf(child) and child not in current_config:
            return False  # 子ノードが非MV、非Leafなので無効
    return True
```

---

## 🎯 推奨アプローチ

### **フェーズ1: 小規模（n < 15）**
- **手法1（冪集合）**: 全パターンを列挙
- **利点**: 完全な探索、最適解保証
- **計算量**: O(2^n) = 最大32,768パターン

### **フェーズ2: 中規模（15 ≤ n < 25）**
- **手法3（ヒューリスティック）**: Beam Search
- **利点**: 高速、実用的な良解
- **計算量**: O(n * w) = 数千パターン

### **フェーズ3: 大規模（n ≥ 25）**
- **手法2（DP）+ 枝刈り**: 最適化
- **手法4（制約付き）**: 無効な構成を除外
- **利点**: 探索空間の削減

---

## 🛠️ 実装例（ハイブリッド）

```python
def enumerate_migration_plans_hybrid(target_mv, dependency_graph, threshold=15):
    """
    ハイブリッドアプローチ
    - 小規模: 全列挙
    - 大規模: ヒューリスティック
    """
    dependent_nodes = get_all_dependent_nodes(target_mv, dependency_graph)
    candidate_mvs = [node for node in dependent_nodes if not is_leaf(node)]
    n = len(candidate_mvs)
    
    if n <= threshold:
        # 全列挙
        print(f"Enumerating all {2**n} patterns...")
        return enumerate_all_migration_plans(target_mv, dependency_graph)
    else:
        # ヒューリスティック
        print(f"Using heuristic search for {n} candidates...")
        return heuristic_migration_plans(target_mv, dependency_graph, beam_width=100)
```

---

## 📈 まとめ

| 手法 | 計算量 | 完全性 | 適用範囲 | 推奨度 |
|------|--------|--------|----------|--------|
| **冪集合** | O(2^n) | ✅ 完全 | n < 15 | ⭐⭐⭐ |
| **動的計画法** | O(2^n) | ✅ 最適 | n < 20 | ⭐⭐ |
| **ヒューリスティック** | O(n*w) | ⚠️ 近似 | n < 100 | ⭐⭐⭐ |
| **制約付き列挙** | O(2^n) | ✅ 有効解 | n < 20 | ⭐⭐⭐ |

**推奨**: **ハイブリッドアプローチ**（小規模は全列挙、大規模はヒューリスティック）