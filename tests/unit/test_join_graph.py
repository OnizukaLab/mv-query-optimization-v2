"""結合グラフのユニットテスト"""

import pytest
from src.rewrite.join_graph import JoinGraph, JoinMinimizer


class TestJoinGraph:
    """JoinGraphクラスのテスト"""
    
    def test_simple_join_graph(self):
        """シンプルな結合グラフのテスト"""
        graph = JoinGraph()
        graph.add_join_condition('t', 'mk', 't.id = mk.movie_id')
        graph.add_join_condition('mk', 'at', 'mk.movie_id = at.movie_id')
        
        minimal = graph.build_minimal_spanning_tree()
        
        # 2つのエッジで3つのノードを連結できる
        assert len(minimal) == 2
        assert len(graph.nodes) == 3
    
    def test_redundant_join_removal(self):
        """冗長な結合条件の削除テスト"""
        graph = JoinGraph()
        graph.add_join_condition('t', 'mk', 't.id = mk.movie_id')
        graph.add_join_condition('mk', 'at', 'mk.movie_id = at.movie_id')
        graph.add_join_condition('t', 'at', 't.id = at.movie_id')  # 冗長（推移律）
        
        minimal = graph.build_minimal_spanning_tree()
        
        # 3本のうち2本だけ残る（推移律で1本は冗長）
        assert len(minimal) == 2
    
    def test_complex_join_graph(self):
        """複雑な結合グラフのテスト（15aクエリ相当）"""
        graph = JoinGraph()
        
        # 元のクエリの結合条件（10個）
        graph.add_join_condition('leaf_11', 'at', 'leaf_11.id = at.movie_id')
        graph.add_join_condition('leaf_11', 'mk', 'leaf_11.id = mk.movie_id')
        graph.add_join_condition('leaf_11', 'leaf_145', 'leaf_11.id = leaf_145.movie_id')
        graph.add_join_condition('leaf_11', 'non_leaf_379', 'leaf_11.id = non_leaf_379.movie_id')
        graph.add_join_condition('mk', 'at', 'mk.movie_id = at.movie_id')  # 冗長
        graph.add_join_condition('mk', 'leaf_145', 'mk.movie_id = leaf_145.movie_id')  # 冗長
        graph.add_join_condition('leaf_145', 'at', 'leaf_145.movie_id = at.movie_id')  # 冗長
        graph.add_join_condition('leaf_145', 'non_leaf_379', 'leaf_145.movie_id = non_leaf_379.movie_id')  # 冗長
        
        minimal = graph.build_minimal_spanning_tree()
        
        # 5つのノード → 最小4本のエッジで連結可能
        assert len(graph.nodes) == 5
        assert len(minimal) == 4  # 8本→4本に削減
    
    def test_star_topology(self):
        """スター型トポロジーのテスト（中心ノードから放射状）"""
        graph = JoinGraph()
        
        # 中心ノード 'center' から4つのノードへの結合
        graph.add_join_condition('center', 'a', 'center.id = a.id')
        graph.add_join_condition('center', 'b', 'center.id = b.id')
        graph.add_join_condition('center', 'c', 'center.id = c.id')
        graph.add_join_condition('center', 'd', 'center.id = d.id')
        
        minimal = graph.build_minimal_spanning_tree()
        
        # スター型は既に最小なので、すべてのエッジが残る
        assert len(minimal) == 4
        assert len(graph.nodes) == 5
    
    def test_empty_graph(self):
        """空のグラフのテスト"""
        graph = JoinGraph()
        minimal = graph.build_minimal_spanning_tree()
        
        assert len(minimal) == 0
        assert len(graph.nodes) == 0
    
    def test_single_edge(self):
        """単一エッジのテスト"""
        graph = JoinGraph()
        graph.add_join_condition('a', 'b', 'a.id = b.id')
        
        minimal = graph.build_minimal_spanning_tree()
        
        assert len(minimal) == 1
        assert len(graph.nodes) == 2
    
    def test_parse_join_condition(self):
        """結合条件のパース機能のテスト"""
        # 正常なケース
        t1, t2 = JoinGraph.parse_join_condition('t.id = mk.movie_id')
        assert t1 == 't'
        assert t2 == 'mk'
        
        # スペースなし
        t1, t2 = JoinGraph.parse_join_condition('t.id=mk.movie_id')
        assert t1 == 't'
        assert t2 == 'mk'
        
        # 複数スペース
        t1, t2 = JoinGraph.parse_join_condition('  t.id   =   mk.movie_id  ')
        assert t1 == 't'
        assert t2 == 'mk'
        
        # 失敗ケース（フィルタ条件）
        t1, t2 = JoinGraph.parse_join_condition("t.name = 'value'")
        assert t1 == ''
        assert t2 == ''
    
    def test_is_join_condition(self):
        """結合条件判定のテスト"""
        # 結合条件
        assert JoinGraph.is_join_condition('t.id = mk.movie_id') == True
        assert JoinGraph.is_join_condition('  t.id = mk.movie_id  ') == True
        
        # フィルタ条件
        assert JoinGraph.is_join_condition("t.name = 'value'") == False
        assert JoinGraph.is_join_condition('t.year > 2000') == False
        assert JoinGraph.is_join_condition('t.note LIKE \'%test%\'') == False
    
    def test_disconnected_graph(self):
        """非連結グラフのテスト"""
        graph = JoinGraph()
        
        # 2つの独立したコンポーネント
        graph.add_join_condition('a', 'b', 'a.id = b.id')
        graph.add_join_condition('c', 'd', 'c.id = d.id')
        
        minimal = graph.build_minimal_spanning_tree()
        
        # 2つのエッジが残る（各コンポーネントに1つずつ）
        assert len(minimal) == 2
        assert len(graph.nodes) == 4
        
        # 警告が出ることを確認（4ノードなら通常3エッジ必要だが2エッジしかない）
        # これはloggerの警告メッセージで確認可能


class TestJoinMinimizer:
    """JoinMinimizerクラスのテスト"""
    
    def test_classify_conditions(self):
        """条件の分類テスト"""
        where_clause = "t.id = mk.movie_id AND mk.movie_id = at.movie_id AND t.year > 2000 AND t.name LIKE '%test%'"
        
        joins, filters = JoinMinimizer.classify_conditions(where_clause)
        
        assert len(joins) == 2
        assert len(filters) == 2
        assert 't.id = mk.movie_id' in joins
        assert 'mk.movie_id = at.movie_id' in joins
        assert 't.year > 2000' in filters
        assert "t.name LIKE '%test%'" in filters
    
    def test_minimize_joins_simple(self):
        """シンプルな最小化テスト"""
        minimizer = JoinMinimizer()
        
        join_conditions = [
            't.id = mk.movie_id',
            'mk.movie_id = at.movie_id',
            't.id = at.movie_id'  # 冗長
        ]
        filter_conditions = ['t.year > 2000']
        
        minimal_joins, filters = minimizer.minimize_joins(join_conditions, filter_conditions)
        
        assert len(minimal_joins) == 2  # 3→2に削減
        assert len(filters) == 1
        assert filters[0] == 't.year > 2000'
    
    def test_minimize_joins_15a(self):
        """15aクエリ相当の最小化テスト"""
        minimizer = JoinMinimizer()
        
        join_conditions = [
            'leaf_11.id = at.movie_id',
            'leaf_11.id = mk.movie_id',
            'leaf_11.id = leaf_145.movie_id',
            'leaf_11.id = non_leaf_379.movie_id',
            'mk.movie_id = at.movie_id',  # 冗長
            'mk.movie_id = leaf_145.movie_id',  # 冗長
            'leaf_145.movie_id = at.movie_id',  # 冗長
            'leaf_145.movie_id = non_leaf_379.movie_id',  # 冗長
        ]
        filter_conditions = [
            "it1.info = 'release dates'",
            "leaf_145.note LIKE '%internet%'"
        ]
        
        minimal_joins, filters = minimizer.minimize_joins(join_conditions, filter_conditions)
        
        # 8個の結合条件 → 4個に削減（スター型）
        assert len(minimal_joins) == 4
        assert len(filters) == 2
    
    def test_empty_conditions(self):
        """空の条件のテスト"""
        minimizer = JoinMinimizer()
        
        minimal_joins, filters = minimizer.minimize_joins([], [])
        
        assert len(minimal_joins) == 0
        assert len(filters) == 0
    
    def test_only_filters(self):
        """フィルタ条件のみのテスト"""
        minimizer = JoinMinimizer()
        
        filter_conditions = ['t.year > 2000', "t.name = 'test'"]
        minimal_joins, filters = minimizer.minimize_joins([], filter_conditions)
        
        assert len(minimal_joins) == 0
        assert len(filters) == 2
    
    def test_between_clause_handling(self):
        """BETWEEN句の処理テスト"""
        where_clause = "t.id = mk.movie_id AND t.year BETWEEN 2000 AND 2010 AND mk.id = at.id"
        
        joins, filters = JoinMinimizer.classify_conditions(where_clause)
        
        assert len(joins) == 2
        assert len(filters) == 1
        assert 'BETWEEN' in filters[0].upper()
        assert 'AND' in filters[0]  # BETWEEN内のANDが保持されている


class TestIntegration:
    """統合テスト"""
    
    def test_full_15a_rewrite_scenario(self):
        """15aクエリの完全な書き換えシナリオ"""
        # 元のWHERE句（改行なしで）
        where_clause = "leaf_145.movie_id = non_leaf_379.movie_id AND leaf_11.id = non_leaf_379.movie_id AND mk.movie_id = non_leaf_379.movie_id AND non_leaf_379.movie_id = at.movie_id AND leaf_11.id = leaf_145.movie_id AND mk.movie_id = leaf_145.movie_id AND leaf_145.movie_id = at.movie_id AND leaf_11.id = at.movie_id AND leaf_11.id = mk.movie_id AND mk.movie_id = at.movie_id AND it1.info = 'release dates' AND it1.id = leaf_145.info_type_id AND k.id = mk.keyword_id"
        
        minimizer = JoinMinimizer()
        joins, filters = minimizer.classify_conditions(where_clause)
        
        # 結合条件とフィルタ条件の分類確認
        # it1.id = leaf_145.info_type_id と k.id = mk.keyword_id も結合条件として判定される
        assert len(joins) >= 10, f"Expected at least 10 join conditions, got {len(joins)}"
        assert len(filters) >= 1, f"Expected at least 1 filter condition, got {len(filters)}"
        
        # 最小化
        minimal_joins, minimal_filters = minimizer.minimize_joins(joins, filters)
        
        # 大幅に削減されることを確認（具体的な数は実装による）
        assert len(minimal_joins) < len(joins), f"Join minimization failed: {len(minimal_joins)} >= {len(joins)}"
        assert len(minimal_filters) == len(filters)  # フィルタは変わらない
        
        # 最終的な条件数
        total_conditions = len(minimal_joins) + len(minimal_filters)
        assert total_conditions <= 10, f"Too many conditions: {total_conditions}"  # 元より少ないはず
