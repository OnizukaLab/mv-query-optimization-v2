# Query Rewrite Logic Fix Plan

**作成日**: 2025年10月10日  
**対象**: クエリ書き換えロジックの根本的な修正  
**優先度**: 🔴 Critical

---

## 📋 問題の概要

### 現在の症状
- 書き換えられたクエリ（15a, 11d等）の実行がハング（無限実行）
- 元のクエリでは数秒〜数十秒で完了するクエリが、MV使用後に終了しない
- 複数の冗長な結合条件が生成されている

### 根本原因の分析

#### 1. **冗長な結合条件の大量生成**
現在の書き換えロジックは、MVに含まれるテーブル間の結合条件を適切に削除していない。

**例: 15aクエリの問題**
```sql
-- 書き換え後（問題あり）
WHERE leaf_145.movie_id = non_leaf_379.movie_id 
  AND leaf_11.id = non_leaf_379.movie_id 
  AND mk.movie_id = non_leaf_379.movie_id 
  AND non_leaf_379.movie_id = at.movie_id 
  AND leaf_11.id = leaf_145.movie_id 
  AND mk.movie_id = leaf_145.movie_id 
  AND leaf_145.movie_id = at.movie_id 
  AND leaf_11.id = at.movie_id 
  AND leaf_11.id = mk.movie_id 
  AND mk.movie_id = at.movie_id
  -- 10個の結合条件！
```

この問題により：
- PostgreSQLのクエリプランナーが最適な実行計画を見つけられない
- 不必要なカーテシアン積が発生する可能性
- 結合順序の最適化に失敗

#### 2. **推移律を考慮していない**
現在のコードは、推移律（A=B かつ B=C ならば A=C は冗長）を考慮していない。

**推移律の例**:
```
leaf_11.id = mk.movie_id  (1)
mk.movie_id = at.movie_id (2)
leaf_11.id = at.movie_id  (3) ← (1)と(2)から導出可能なので冗長
```

#### 3. **MVに既に含まれるテーブルの扱いが不適切**
MVの定義に既に含まれているテーブル（例: non_leaf_379にはmc+cnが含まれる）が、
FROM句から正しく削除されていない、または結合条件が残っている。

**例: 15aでの問題**
- `non_leaf_379` = `movie_companies (mc)` JOIN `company_name (cn)` + filters
- しかし書き換え後、`company_name`がFROM句に残っていない
- `company_type (ct)`との結合条件は残すべきだが、`cn`との結合は不要

---

## 🎯 修正目標

### 正しい書き換えの例（15aクエリ）

```sql
-- ✅ 正しい書き換え結果
SELECT MIN(leaf_145.info) AS release_date, 
       MIN(leaf_11.title) AS internet_movie
FROM aka_title AS at,
     company_type AS ct,
     info_type AS it1,
     keyword AS k,
     movie_keyword AS mk,
     leaf_145,
     leaf_11,
     non_leaf_379
WHERE it1.info = 'release dates'
  AND it1.id = leaf_145.info_type_id
  AND k.id = mk.keyword_id
  AND ct.id = non_leaf_379.company_type_id
  AND leaf_11.id = at.movie_id
  AND leaf_11.id = mk.movie_id
  AND leaf_11.id = leaf_145.movie_id
  AND leaf_11.id = non_leaf_379.movie_id
  AND mk.movie_id = at.movie_id;
  -- わずか9個の結合条件（最小限）
```

### 達成すべき品質基準
1. **結合条件の最小化**: 推移律を適用して冗長な条件を削除
2. **実行速度**: 元のクエリと同等か、それより高速
3. **正確性**: 結果セットが元のクエリと完全に一致
4. **FROM句のクリーンアップ**: MVに含まれるテーブルは完全に削除

---

## 🔍 現在のコードの問題点

### src/rewrite/query_rewriter.py の問題

#### 問題1: `_apply_mv_to_query` メソッド（行250-375）
```python
# 現在のコード（問題あり）
new_join_conditions = []
for join_cond in join_conditions:
    involved_tables = self._extract_tables_from_condition(join_cond, query_table_mappings)
    
    # 両方のテーブルがMVに含まれている → 削除
    if all(table in mv_tables for table in involved_tables):
        logger.debug(f"Removing internal MV join condition: {join_cond}")
        continue
    
    # 片方がMVに含まれている → エイリアスを書き換えて保持
    if any(table in mv_tables for table in involved_tables):
        new_join_conditions.append(join_cond)  # ← 問題: そのまま追加
    else:
        new_join_conditions.append(join_cond)
```

**問題点**:
- MVに含まれるテーブルのエイリアスをMVエイリアスに置き換えているが、
  その結果、同じ結合（mv.col = external.col）が複数生成される
- 例: `t.id = mk.movie_id` → `leaf_11.id = mk.movie_id` と
      `t.id = at.movie_id` → `leaf_11.id = at.movie_id` の両方が生成されるが、
      これらが同時に存在すると推移律で冗長な条件が増える

#### 問題2: `_remove_redundant_join_conditions` メソッド（行700-740）
```python
# 現在のコード
join_groups = {}  # {(mv_id, external_table): [conditions]}
for cond in conditions:
    pattern = rf'{re.escape(mv_id)}\.(\w+)\s*=\s*(\w+)\.(\w+)'
    match = re.match(pattern, cond.strip())
    if match:
        mv_col, ext_table, ext_col = match.groups()
        key = (mv_id, ext_table, ext_col)
        if key not in join_groups:
            join_groups[key] = []
        join_groups[key].append(cond)
```

**問題点**:
- 同じMVと同じ外部テーブルの結合は削除できているが、
  **異なる外部テーブル間の推移的冗長性**を検出できていない
- 例: `leaf_11.id = mk.movie_id` と `mk.movie_id = at.movie_id` があれば、
      `leaf_11.id = at.movie_id` は冗長だが、これを検出・削除できない

#### 問題3: MVのテーブルマッピングの不完全性
```python
mv_tables = self._extract_tables_from_from_clause(mv_parts['from'])
```

**問題点**:
- MVのFROM句からテーブルエイリアスを抽出しているが、
  元のクエリのテーブル名とMVのテーブルエイリアスのマッピングが不正確
- 例: 元のクエリで`title AS t`、MVで`title t`の場合、
      両方とも`t`だが、これが同じテーブルだと認識できていない可能性

---

## 🛠 修正アプローチ

### アプローチ1: グラフベースの結合条件最小化 【推奨】

#### 概要
結合条件を無向グラフとしてモデル化し、最小全域木（MST）を構築することで、
必要最小限の結合条件のみを保持する。

#### アルゴリズム

```python
class JoinGraph:
    """結合グラフの構築と最小化"""
    
    def __init__(self):
        self.nodes = set()  # テーブル/MVエイリアス
        self.edges = []     # (table1, table2, condition)
    
    def add_join(self, table1: str, table2: str, condition: str):
        """結合条件を追加"""
        self.nodes.add(table1)
        self.nodes.add(table2)
        self.edges.append((table1, table2, condition))
    
    def build_minimal_joins(self) -> list[str]:
        """最小全域木を構築して必要最小限の結合条件を返す"""
        # Union-Findで連結成分を管理
        parent = {node: node for node in self.nodes}
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
                return True
            return False
        
        minimal_conditions = []
        
        # すべてのエッジを試行
        for table1, table2, condition in self.edges:
            # この結合が新しい連結を作る場合のみ追加
            if union(table1, table2):
                minimal_conditions.append(condition)
            else:
                logger.debug(f"Redundant join (creates cycle): {condition}")
        
        return minimal_conditions
```

#### 使用例

```python
def _minimize_join_conditions(self, join_conditions: list[str], 
                               filter_conditions: list[str]) -> list[str]:
    """結合条件を最小化"""
    graph = JoinGraph()
    
    # すべての結合条件をグラフに追加
    for cond in join_conditions:
        if self._is_join_condition(cond):
            tables = self._extract_tables_from_join(cond)
            if len(tables) == 2:
                graph.add_join(tables[0], tables[1], cond)
    
    # 最小全域木を構築
    minimal_joins = graph.build_minimal_joins()
    
    # フィルタ条件を追加
    return minimal_joins + filter_conditions
```

#### メリット
- ✅ 推移律を自動的に考慮
- ✅ 数学的に最小であることが保証される
- ✅ 結合順序の最適化がPostgreSQLに委ねられる
- ✅ デバッグが容易（グラフとして可視化可能）

#### デメリット
- ⚠️ 実装が複雑（ただし、一度実装すれば堅牢）
- ⚠️ グラフ構築のオーバーヘッド（ただし、クエリ書き換えは一度だけなので問題ない）

---

### アプローチ2: ルールベースのシンプルな最小化 【代替案】

#### 概要
シンプルなルールで冗長な結合条件を削除する。

#### ルール

1. **ルール1: MVに含まれるテーブル間の結合は削除**
   ```
   MVが t JOIN ci なら、t.id = ci.movie_id は削除
   ```

2. **ルール2: 基準テーブルを1つ選び、他のすべてを基準に結合**
   ```
   基準: leaf_11 (title)
   結合: leaf_11.id = mk.movie_id
        leaf_11.id = at.movie_id
        leaf_11.id = leaf_145.movie_id
        leaf_11.id = non_leaf_379.movie_id
   
   その他のテーブル間の直接結合は削除:
   × mk.movie_id = at.movie_id (冗長)
   × mk.movie_id = leaf_145.movie_id (冗長)
   ```

3. **ルール3: 基準テーブルに直接結合できないテーブルは、他のテーブル経由で結合**
   ```
   ct.id = non_leaf_379.company_type_id (ctは基準のleaf_11と直接結合できない)
   k.id = mk.keyword_id (kは基準のleaf_11と直接結合できない)
   ```

#### 実装

```python
def _build_star_join(self, join_conditions: list[str], 
                     filter_conditions: list[str],
                     mv_tables: set[str]) -> list[str]:
    """スター型結合パターンを構築
    
    1つの中心テーブル（通常はtitleのMV）を選び、
    他のすべてのテーブルを中心に結合する。
    """
    # 中心テーブルを選択（通常はtitleテーブルのMV、またはmovie_idを持つMV）
    center_table = self._select_center_table(join_conditions, mv_tables)
    
    # すべてのテーブルを収集
    all_tables = set()
    join_map = {}  # {(table1, table2): condition}
    
    for cond in join_conditions:
        tables = self._extract_tables_from_join(cond)
        if len(tables) == 2:
            t1, t2 = tables
            all_tables.add(t1)
            all_tables.add(t2)
            join_map[(t1, t2)] = cond
            join_map[(t2, t1)] = cond  # 双方向
    
    # 中心テーブルと各テーブルの結合条件を収集
    star_joins = []
    connected_tables = {center_table}
    
    # 第1層: 中心テーブルと直接結合できるテーブル
    for table in all_tables:
        if table == center_table:
            continue
        
        if (center_table, table) in join_map:
            star_joins.append(join_map[(center_table, table)])
            connected_tables.add(table)
    
    # 第2層: 間接的に結合するテーブル
    for table in all_tables:
        if table in connected_tables:
            continue
        
        # 既に接続されているテーブル経由で結合を探す
        for conn_table in connected_tables:
            if (conn_table, table) in join_map:
                star_joins.append(join_map[(conn_table, table)])
                connected_tables.add(table)
                break
    
    return star_joins + filter_conditions

def _select_center_table(self, join_conditions: list[str], 
                          mv_tables: set[str]) -> str:
    """中心テーブルを選択
    
    優先順位:
    1. titleテーブルのMV (leaf_XXで production_year > XXXX)
    2. 最も多くの結合を持つテーブル
    """
    # 各テーブルの結合数をカウント
    table_degree = {}
    
    for cond in join_conditions:
        tables = self._extract_tables_from_join(cond)
        for table in tables:
            table_degree[table] = table_degree.get(table, 0) + 1
    
    # titleのMVを優先
    for table in table_degree:
        if table.startswith('leaf_') or table.startswith('non_leaf_'):
            # MVの定義を確認してtitleテーブルか判定
            # （簡易版: 名前で判定、または事前に構築したマッピングを使用）
            return table
    
    # 最も結合数が多いテーブルを選択
    return max(table_degree, key=table_degree.get) if table_degree else ''
```

#### メリット
- ✅ 実装がシンプル
- ✅ デバッグが容易
- ✅ 実行速度が速い

#### デメリット
- ⚠️ すべてのケースで最小とは限らない（ただし、十分に効果的）
- ⚠️ 中心テーブルの選択ヒューリスティックに依存

---

## 📝 実装計画

### Phase 1: 結合グラフクラスの実装 (2-3時間)

#### ファイル構成
```
src/rewrite/
├── join_graph.py          # NEW: 結合グラフとMST構築
├── query_rewriter.py      # MODIFY: join_graphを使用
└── tests/
    └── test_join_graph.py # NEW: ユニットテスト
```

#### タスク
1. ✅ `JoinGraph` クラスの実装
2. ✅ Union-Find アルゴリズムの実装
3. ✅ 最小全域木構築ロジック
4. ✅ ユニットテスト作成

#### 実装コード (join_graph.py)

```python
"""結合条件のグラフ表現と最小化"""

import re
import logging
from typing import Set, List, Tuple, Dict

logger = logging.getLogger(__name__)


class JoinGraph:
    """結合条件をグラフとして表現し、最小全域木を構築する
    
    結合条件を無向グラフとしてモデル化:
    - ノード: テーブル/MVのエイリアス
    - エッジ: 結合条件（alias1.col = alias2.col）
    
    最小全域木を構築することで、推移的に冗長な結合条件を削除する。
    
    例:
        元の結合条件:
            t.id = mk.movie_id
            mk.movie_id = at.movie_id
            t.id = at.movie_id  ← 冗長（推移律）
        
        最小化後:
            t.id = mk.movie_id
            mk.movie_id = at.movie_id
    """
    
    def __init__(self):
        """初期化"""
        self.nodes: Set[str] = set()
        self.edges: List[Tuple[str, str, str]] = []  # (table1, table2, condition)
        self._parent: Dict[str, str] = {}  # Union-Find用
    
    def add_join_condition(self, table1: str, table2: str, condition: str):
        """結合条件を追加
        
        Args:
            table1: 1つ目のテーブルエイリアス
            table2: 2つ目のテーブルエイリアス
            condition: 結合条件（例: "t.id = mk.movie_id"）
        """
        if table1 and table2:
            self.nodes.add(table1)
            self.nodes.add(table2)
            self.edges.append((table1, table2, condition))
            logger.debug(f"Added join: {table1} - {table2}: {condition}")
    
    def build_minimal_spanning_tree(self) -> List[str]:
        """最小全域木を構築して必要最小限の結合条件を返す
        
        Kruskalアルゴリズムを使用して、すべてのノードを連結する
        最小限のエッジ（結合条件）を選択する。
        
        Returns:
            最小限の結合条件のリスト
        """
        if not self.nodes:
            return []
        
        # Union-Findの初期化
        self._parent = {node: node for node in self.nodes}
        
        minimal_conditions = []
        redundant_count = 0
        
        # すべてのエッジを試行
        for table1, table2, condition in self.edges:
            # この結合が新しい連結を作る場合のみ追加
            if self._union(table1, table2):
                minimal_conditions.append(condition)
                logger.debug(f"  ✓ Keeping join: {condition}")
            else:
                redundant_count += 1
                logger.debug(f"  ✗ Redundant join (creates cycle): {condition}")
        
        logger.info(f"Join minimization: {len(self.edges)} → {len(minimal_conditions)} "
                   f"(removed {redundant_count} redundant joins)")
        
        # すべてのノードが連結されているか確認
        if len(minimal_conditions) < len(self.nodes) - 1:
            logger.warning(f"Join graph may not be fully connected: "
                          f"{len(self.nodes)} nodes but only {len(minimal_conditions)} joins")
        
        return minimal_conditions
    
    def _find(self, x: str) -> str:
        """Union-Find: ルートを見つける（経路圧縮付き）
        
        Args:
            x: ノード
            
        Returns:
            ルートノード
        """
        if self._parent[x] != x:
            self._parent[x] = self._find(self._parent[x])
        return self._parent[x]
    
    def _union(self, x: str, y: str) -> bool:
        """Union-Find: 2つのノードを結合
        
        Args:
            x: 1つ目のノード
            y: 2つ目のノード
            
        Returns:
            新しい結合が作成された場合True、既に同じ連結成分にある場合False
        """
        px = self._find(x)
        py = self._find(y)
        
        if px != py:
            self._parent[px] = py
            return True
        return False
    
    @staticmethod
    def parse_join_condition(condition: str) -> Tuple[str, str]:
        """結合条件からテーブルエイリアスを抽出
        
        Args:
            condition: 結合条件（例: "t.id = mk.movie_id"）
            
        Returns:
            (table1, table2) のタプル、解析失敗時は ('', '')
        """
        # alias1.col = alias2.col のパターン
        pattern = r'(\w+)\.\w+\s*=\s*(\w+)\.\w+'
        match = re.search(pattern, condition.strip())
        
        if match:
            return match.group(1), match.group(2)
        
        return '', ''
```

---

### Phase 2: QueryRewriterの修正 (2-3時間)

#### 修正内容

1. **`_apply_mv_to_query` メソッドの書き換え**
   - JoinGraphを使用した結合条件の最小化
   - MVテーブルマッピングの改善

2. **新メソッドの追加**
   - `_build_join_graph()`: 結合条件からグラフを構築
   - `_classify_conditions()`: 結合条件とフィルタ条件を分類
   - `_is_mv_internal_join()`: MVの内部結合かどうか判定

#### 修正後のコード構造

```python
def _apply_mv_to_query(self, parts: dict, mv: dict) -> dict:
    """MVを適用してクエリの構成要素を書き換え"""
    
    # 1. MV情報の取得
    view_id, create_sql = self._extract_mv_info(mv)
    mv_parts = self._analyze_mv_definition(create_sql)
    mv_tables = self._extract_mv_tables(mv_parts)
    
    # 2. WHERE句の分類
    join_conditions, filter_conditions = self._classify_conditions(
        parts['where'], 
        parts['from']
    )
    
    # 3. MVの内部結合を削除
    external_joins = [
        cond for cond in join_conditions
        if not self._is_mv_internal_join(cond, mv_tables)
    ]
    
    # 4. 結合グラフを構築して最小化
    from src.rewrite.join_graph import JoinGraph
    
    graph = JoinGraph()
    for cond in external_joins:
        table1, table2 = JoinGraph.parse_join_condition(cond)
        if table1 and table2:
            graph.add_join_condition(table1, table2, cond)
    
    minimal_joins = graph.build_minimal_spanning_tree()
    
    # 5. MVに含まれるフィルタ条件を削除
    mv_filters = self._extract_filter_conditions(mv_parts.get('where', ''))
    external_filters = [
        cond for cond in filter_conditions
        if not self._is_covered_by_mv(cond, mv_filters, mv_tables)
    ]
    
    # 6. WHERE句を再構築
    parts['where'] = ' AND '.join(minimal_joins + external_filters)
    
    # 7. FROM句を書き換え
    parts['from'] = self._replace_tables_with_mv(parts['from'], mv_tables, view_id)
    
    # 8. SELECT句のエイリアス更新
    parts['select'] = self._update_select_aliases(
        parts['select'], 
        mv_tables, 
        view_id, 
        mv_parts.get('select', '')
    )
    
    return parts
```

---

### Phase 3: テストと検証 (2-4時間)

#### テストケース

1. **ユニットテスト**
   ```python
   def test_join_graph_simple():
       """シンプルな結合グラフのテスト"""
       graph = JoinGraph()
       graph.add_join_condition('t', 'mk', 't.id = mk.movie_id')
       graph.add_join_condition('mk', 'at', 'mk.movie_id = at.movie_id')
       graph.add_join_condition('t', 'at', 't.id = at.movie_id')  # 冗長
       
       minimal = graph.build_minimal_spanning_tree()
       assert len(minimal) == 2  # 3本のうち2本だけ残る
   
   def test_query_rewrite_15a():
       """15aクエリの書き換えテスト"""
       # ... テスト実装
       rewritten = rewriter.rewrite_queries([mv1, mv2, mv3])
       
       # 結合条件の数を確認
       conditions = extract_where_conditions(rewritten['15a'])
       assert len(conditions) <= 10  # 冗長な条件が削除されている
   ```

2. **統合テスト**
   ```bash
   # 全クエリの書き換えと実行
   python scripts/run_experiment.py --algorithms bigsubs --phases query_rewriting,benchmark
   
   # 実行時間の比較
   # 元のクエリ vs 書き換えたクエリ
   ```

3. **性能テスト**
   - 15aクエリ: 元の実行時間 vs MV使用時（ハングしないこと）
   - 11dクエリ: 元の実行時間 vs MV使用時
   - 17fクエリ: 元の実行時間 vs MV使用時

---

## 📊 期待される改善効果

### Before（現在）
```
15a: 書き換え後ハング（>5分）
11d: 書き換え後ハング（>5分）
17f: 書き換え後16秒（元のクエリと同じ）
```

### After（修正後）
```
15a: 書き換え後1秒未満（MVの効果により高速化）
11d: 書き換え後1秒未満
17f: 書き換え後1秒未満
```

### 結合条件数の削減
```
15a: 10個 → 9個（10%削減）
複雑なクエリ: 20個以上 → 10個程度（50%以上削減）
```

---

## 🚀 実装スケジュール

### Day 1（3時間）
- ✅ `JoinGraph`クラスの実装
- ✅ Union-Findアルゴリズムの実装
- ✅ 基本的なユニットテストの作成

### Day 2（3時間）
- ✅ `QueryRewriter._apply_mv_to_query`の書き換え
- ✅ ヘルパーメソッドの実装
- ✅ 15aクエリでの動作確認

### Day 3（2時間）
- ✅ 統合テストの実行
- ✅ 全113クエリの書き換えと検証
- ✅ 性能測定とベンチマーク

### Day 4（2時間）
- ✅ バグ修正とエッジケースの対応
- ✅ ドキュメント更新
- ✅ コードレビューとリファクタリング

**合計**: 10時間（2-3日）

---

## ⚠️ リスクと対策

### リスク1: グラフアルゴリズムのバグ
- **対策**: 豊富なユニットテストで検証
- **フォールバック**: ルールベースの実装に切り替え

### リスク2: すべてのクエリパターンに対応できない
- **対策**: 段階的に対応（まず15a, 11d, 17fから）
- **フォールバック**: 問題のあるクエリは元のクエリを使用

### リスク3: 性能が期待通り向上しない
- **対策**: PostgreSQLのEXPLAINで実行計画を確認
- **調整**: 結合順序のヒント追加、インデックスの見直し

---

## 📚 参考資料

### 関連論文
- Chaudhuri, S., & Shim, K. (1994). "Including group-by in query optimization"
- Agrawal, S., et al. (2000). "Automated selection of materialized views"
- Goldstein, J., & Larson, P. (2001). "Optimizing queries using materialized views"

### PostgreSQL ドキュメント
- Query Planning: https://www.postgresql.org/docs/current/runtime-config-query.html
- Join Methods: https://www.postgresql.org/docs/current/explicit-joins.html

### 内部ドキュメント
- `docs/ILP_algorithm.md`: 最適化アルゴリズム
- `docs/output_files.md`: 出力ファイルの構造
- `docs/project_overview.md`: プロジェクト全体概要

---

## ✅ 完了基準

### 必須（Must Have）
- [ ] 15aクエリがハングせずに実行完了（<5秒）
- [ ] 11dクエリがハングせずに実行完了（<5秒）
- [ ] 結合条件が推移律により最小化されている
- [ ] すべてのユニットテストがパス

### 推奨（Should Have）
- [ ] 全113クエリが元のクエリと同じ結果を返す
- [ ] MVを使用した方が元のクエリより高速（平均50%以上）
- [ ] コードカバレッジ80%以上

### オプション（Nice to Have）
- [ ] 結合グラフの可視化ツール
- [ ] 書き換え前後のクエリ比較レポート
- [ ] 自動回帰テストスイート

---

## 📝 変更履歴

| 日付 | バージョン | 変更内容 | 担当者 |
|------|-----------|---------|--------|
| 2025-10-10 | 1.0 | 初版作成 | AI Assistant |

