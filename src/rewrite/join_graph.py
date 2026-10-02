"""結合条件のグラフ表現と最小化

このモジュールは、SQLの結合条件を無向グラフとしてモデル化し、
最小全域木（Minimum Spanning Tree）を構築することで、
推移的に冗長な結合条件を削除する。

例:
    元の結合条件:
        t.id = mk.movie_id
        mk.movie_id = at.movie_id
        t.id = at.movie_id  ← 冗長（推移律により t→mk→at で到達可能）
    
    最小化後:
        t.id = mk.movie_id
        mk.movie_id = at.movie_id
"""

import re
import logging
from typing import Set, List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)


IDENT = r'"?[A-Za-z_][A-Za-z0-9_]*"?'


class JoinGraph:
    """結合条件をグラフとして表現し、最小全域木を構築する
    
    結合条件を無向グラフとしてモデル化:
    - ノード: テーブル/MVのエイリアス
    - エッジ: 結合条件（alias1.col = alias2.col）
    
    Kruskalアルゴリズムを使用して最小全域木を構築し、
    推移的に冗長な結合条件を削除する。
    
    Attributes:
        nodes: グラフ内のすべてのノード（テーブルエイリアス）
        edges: グラフ内のすべてのエッジ（結合条件）
    """
    
    def __init__(self):
        """初期化"""
        self.nodes: Set[str] = set()
        self.edges: List[Tuple[str, str, str]] = []  # (table1, table2, condition)
        self._parent: Dict[str, str] = {}  # Union-Find用
    
    def add_join_condition(self, table1: str, table2: str, condition: str):
        """結合条件をグラフに追加
        
        Args:
            table1: 1つ目のテーブルエイリアス
            table2: 2つ目のテーブルエイリアス
            condition: 結合条件（例: "t.id = mk.movie_id"）
        """
        if table1 and table2 and table1 != table2:
            self.nodes.add(table1)
            self.nodes.add(table2)
            self.edges.append((table1, table2, condition))
            logger.debug(f"Added join edge: {table1} <-> {table2}: {condition}")
    
    def build_minimal_spanning_tree(self) -> List[str]:
        """最小全域木を構築して必要最小限の結合条件を返す
        
        Kruskalアルゴリズムを使用:
        1. すべてのノードを独立した集合として初期化
        2. 各エッジ（結合条件）を順に試行
        3. 2つの異なる集合を結合する場合のみエッジを追加
        4. サイクルを作る場合は追加しない（冗長な結合）
        
        Returns:
            最小限の結合条件のリスト
        """
        if not self.nodes:
            logger.debug("No nodes in join graph")
            return []
        
        if len(self.nodes) == 1:
            logger.debug("Only one node in join graph, no joins needed")
            return []
        
        # Union-Findの初期化（各ノードが独立した集合）
        self._parent = {node: node for node in self.nodes}
        
        minimal_conditions = []
        redundant_count = 0
        
        logger.info(f"Building minimal spanning tree from {len(self.edges)} join conditions")
        logger.debug(f"Nodes in graph: {sorted(self.nodes)}")
        
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
        expected_edges = len(self.nodes) - 1
        if len(minimal_conditions) < expected_edges:
            logger.warning(f"Join graph may not be fully connected: "
                          f"{len(self.nodes)} nodes need {expected_edges} joins, "
                          f"but only {len(minimal_conditions)} joins were added")
        elif len(minimal_conditions) == expected_edges:
            logger.info(f"✓ Join graph is fully connected with minimal joins")
        
        return minimal_conditions
    
    def _find(self, x: str) -> str:
        """Union-Find: ルートを見つける（経路圧縮付き）
        
        経路圧縮により、後続の検索を高速化する。
        
        Args:
            x: ノード
            
        Returns:
            ルートノード
        """
        if self._parent[x] != x:
            # 経路圧縮: 途中のノードを直接ルートに接続
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
            # 異なる集合に属している → 結合
            self._parent[px] = py
            return True
        else:
            # 既に同じ集合に属している → サイクルを作るので結合しない
            return False
    
    def get_connectivity_info(self) -> Dict[str, List[str]]:
        """連結成分の情報を取得（デバッグ用）
        
        Returns:
            {ルートノード: [そのグループに属するノード]} の辞書
        """
        components: Dict[str, List[str]] = {}
        
        for node in self.nodes:
            root = self._find(node)
            if root not in components:
                components[root] = []
            components[root].append(node)
        
        return components
    
    @staticmethod
    def parse_join_condition(condition: str) -> Tuple[str, str]:
        """結合条件からテーブルエイリアスを抽出
        
        結合条件は以下の形式を想定:
        - alias1.column1 = alias2.column2
        - alias1.column1=alias2.column2
        
        Args:
            condition: 結合条件（例: "t.id = mk.movie_id"）
            
        Returns:
            (table1, table2) のタプル、解析失敗時は ('', '')
        """
        # 正規化: 前後の空白を削除
        condition = condition.strip()
        
        # alias1.col = alias2.col のパターン（ダブルクォート識別子対応）
        pattern = rf'({IDENT})\.({IDENT})\s*=\s*({IDENT})\.({IDENT})'
        match = re.search(pattern, condition)
        
        if match:
            table1 = match.group(1).strip('"')
            table2 = match.group(3).strip('"')
            logger.debug(f"Parsed join condition '{condition}' -> ({table1}, {table2})")
            return table1, table2
        
        logger.debug(f"Failed to parse join condition: {condition}")
        return '', ''
    
    @staticmethod
    def is_join_condition(condition: str) -> bool:
        """条件が結合条件かどうかを判定
        
        結合条件は alias1.col1 = alias2.col2 の形式
        フィルタ条件は alias1.col1 = 'value' や alias1.col1 > 100 など
        
        Args:
            condition: 条件文字列
            
        Returns:
            結合条件ならTrue、フィルタ条件ならFalse
        """
        # alias1.col1 = alias2.col2 のパターンをチェック（ダブルクォート識別子対応）
        pattern = rf'^\s*{IDENT}\.{IDENT}\s*=\s*{IDENT}\.{IDENT}\s*$'
        return re.match(pattern, condition.strip()) is not None


class JoinMinimizer:
    """結合条件の最小化を管理する高レベルクラス
    
    JoinGraphを使用して、SQL WHERE句の結合条件を最小化する。
    """
    
    def __init__(self):
        """初期化"""
        pass
    
    def minimize_joins(
        self, 
        join_conditions: List[str], 
        filter_conditions: List[str]
    ) -> Tuple[List[str], List[str]]:
        """結合条件を最小化
        
        Args:
            join_conditions: 結合条件のリスト（alias1.col = alias2.col）
            filter_conditions: フィルタ条件のリスト（alias.col = 'value'など）
            
        Returns:
            (最小化された結合条件のリスト, フィルタ条件のリスト)
        """
        if not join_conditions:
            logger.debug("No join conditions to minimize")
            return [], filter_conditions
        
        # 結合グラフを構築
        graph = JoinGraph()
        
        for condition in join_conditions:
            table1, table2 = JoinGraph.parse_join_condition(condition)
            if table1 and table2:
                graph.add_join_condition(table1, table2, condition)
            else:
                logger.warning(f"Could not parse join condition, treating as filter: {condition}")
                filter_conditions.append(condition)
        
        # 最小全域木を構築
        minimal_joins = graph.build_minimal_spanning_tree()
        
        # 連結性を確認（デバッグ）
        if logger.isEnabledFor(logging.DEBUG):
            components = graph.get_connectivity_info()
            logger.debug(f"Connectivity components: {len(components)}")
            for root, nodes in components.items():
                logger.debug(f"  Component rooted at {root}: {nodes}")
        
        return minimal_joins, filter_conditions
    
    @staticmethod
    def classify_conditions(where_clause: str) -> Tuple[List[str], List[str]]:
        """WHERE句を結合条件とフィルタ条件に分類
        
        Args:
            where_clause: WHERE句の文字列
            
        Returns:
            (結合条件のリスト, フィルタ条件のリスト)
        """
        if not where_clause:
            return [], []
        
        # ANDで分割（BETWEEN...AND を保護）
        conditions = JoinMinimizer._extract_conditions(where_clause)
        
        join_conditions = []
        filter_conditions = []
        
        for cond in conditions:
            if JoinGraph.is_join_condition(cond):
                join_conditions.append(cond)
            else:
                filter_conditions.append(cond)
        
        logger.debug(f"Classified {len(conditions)} conditions: "
                    f"{len(join_conditions)} joins, {len(filter_conditions)} filters")
        
        return join_conditions, filter_conditions
    
    @staticmethod
    def _extract_conditions(where_clause: str) -> List[str]:
        """WHERE句から個別の条件を抽出
        
        BETWEEN...AND構文を適切に処理するため、BETWEENを含む条件を
        一時的にプレースホルダーに置き換えてからANDで分割します。
        
        Args:
            where_clause: WHERE句の文字列
            
        Returns:
            条件のリスト
        """
        if not where_clause:
            return []
        
        # BETWEEN...AND句を保護するため、一時的にプレースホルダーに置き換え
        between_pattern = re.compile(
            r'(\w+\.?\w*\s+BETWEEN\s+[\w\d\'\"\-]+\s+AND\s+[\w\d\'\"\-]+)',
            re.IGNORECASE
        )
        
        between_clauses = {}
        placeholder_counter = 0
        
        def replace_between(match):
            nonlocal placeholder_counter
            placeholder = f'__BETWEEN_PLACEHOLDER_{placeholder_counter}__'
            between_clauses[placeholder] = match.group(1)
            placeholder_counter += 1
            return placeholder
        
        # BETWEENをプレースホルダーに置き換え
        protected_clause = between_pattern.sub(replace_between, where_clause)
        
        # ANDで分割
        conditions = [c.strip() for c in protected_clause.split(' AND ') if c.strip()]
        
        # プレースホルダーを元のBETWEEN句に戻す
        restored_conditions = []
        for cond in conditions:
            restored = cond
            for placeholder, original in between_clauses.items():
                restored = restored.replace(placeholder, original)
            if restored and restored.upper() not in ('WHERE', 'AND', 'OR'):
                restored_conditions.append(restored)
        
        return restored_conditions
