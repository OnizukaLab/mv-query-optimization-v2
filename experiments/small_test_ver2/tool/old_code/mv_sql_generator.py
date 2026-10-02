"""MV SQL Generator with existing MV support.

This module provides functionality to generate MV creation SQL
that can reference existing MVs from previous time periods.

Features:
1. Enhanced MV Generator approach: Uses selected_mvs for direct reference
2. Query Rewriter approach: Uses query rewriting to incorporate existing MVs
"""

from pathlib import Path
from typing import Optional
import re
import logging

from experiments.small_test_ver2.enhanced_mv_generator import EnhancedMVGenerator
from experiments.small_test_ver2.small_test_schema_provider import SmallTestSchemaProvider
from experiments.small_test_ver2.comma_join_rewriter import CommaJoinRewriter


logger = logging.getLogger(__name__)


class MVSQLGenerator:
    """Generate MV SQL that can reference existing MVs.
    
    This class provides two approaches:
    1. Enhanced MV Generator: Direct MV reference via selected_mvs
    2. Query Rewriter: Query rewriting with MV substitution
    """
    
    def __init__(self, qp_dict: dict):
        """Initialize MVSQLGenerator.
        
        Args:
            qp_dict: Dictionary of time_id -> QueryParser instances
        """
        self.qp_dict = qp_dict
    
    
    def generate_mv_sql_with_rewriter(
        self, 
        node_id: str, 
        existing_mvs: list[str], 
        time_id: str
    ) -> Optional[str]:
        """クエリ書き換え機能を使用してMV SQLを生成
        
        この方法では、QueryRewriterを使用して元のMV定義クエリを
        既存MVを参照する形に書き換えます。
        
        Args:
            node_id: 生成するMVのノードID
            existing_mvs: 既存のMV（前の時刻のMV）のノードIDリスト
            time_id: 対象時刻のID
            
        Returns:
            CREATE MATERIALIZED VIEW文。生成失敗時はNone
        """
        # 指定された時刻のQueryParserを使用
        if time_id not in self.qp_dict:
            print(f"  エラー: {time_id} のQueryParserが見つかりません")
            return None
        
        target_qp = self.qp_dict[time_id]
        if not hasattr(target_qp, 'qm'):
            return None
        
        try:
            # 1. EnhancedMVGeneratorで元のMV定義を生成（既存MVなしで純粋なクエリを生成）
            schema_provider = SmallTestSchemaProvider()
            
            mv_generator = EnhancedMVGenerator(
                query_manager=target_qp.qm,
                schema_provider=schema_provider,
                selected_mvs=set()  # 既存MVなしで生成（後でCommaJoinRewriterで書き換える）
            )
            
            original_sql = mv_generator.generate_mv_sql(node_id)
            
            if not original_sql:
                print(f"  エラー: {node_id} のMV SQL生成失敗")
                return None
            
            print(f"  [INFO] EnhancedMVGeneratorでSQL生成完了")
            
            # CREATE MATERIALIZED VIEW ... AS 部分を削除して元クエリを取得
            base_query = self._extract_query_from_create(original_sql)
            
            if not base_query:
                print(f"  エラー: {node_id} のクエリ抽出失敗")
                return None
            
            print(f"  [INFO] 元クエリ抽出完了: {base_query[:100]}...")
            
            # 2. 既存MVがある場合、CommaJoinRewriterで書き換え
            if existing_mvs:
                print(f"  [INFO] CommaJoinRewriterで既存MV利用に書き換え")
                
                # CommaJoinRewriterを初期化
                comma_rewriter = CommaJoinRewriter(
                    query_manager=target_qp.qm,
                    schema_provider=schema_provider
                )
                
                # 各既存MVに対して書き換えを試行
                rewritten_query = base_query
                for mv_id in existing_mvs:
                    mv_tables = self._get_mv_covered_aliases(mv_id, target_qp, rewritten_query)
                    if mv_tables:
                        print(f"  [INFO] {mv_id} で書き換え試行: {mv_tables}")
                        rewritten_query = comma_rewriter.rewrite_with_mv(
                            rewritten_query, 
                            mv_id, 
                            mv_tables
                        )
                    else:
                        print(f"  [INFO] {mv_id} はクエリをカバーしない、スキップ")
            else:
                print(f"  [INFO] 既存MVなし、元クエリを使用")
                rewritten_query = base_query
            
            # 3. CREATE MATERIALIZED VIEW文に変換
            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{rewritten_query};"
            
            print(f"  [INFO] {node_id} のSQL生成完了（EnhancedMVGenerator + CommaJoinRewriter）")
            print(f"  [INFO] 再利用するMV: {existing_mvs if existing_mvs else 'なし'}")
            print(f"  [DEBUG] 最終SQL (最初の200文字): {create_sql[:200]}")
            
            return create_sql
            
        except Exception as e:
            print(f"SQL生成失敗（Rewriter方式）: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_query_from_create(self, create_sql: str) -> Optional[str]:
        """CREATE MATERIALIZED VIEW文からSELECTクエリを抽出
        
        Args:
            create_sql: CREATE MATERIALIZED VIEW文
            
        Returns:
            SELECTクエリ部分。抽出失敗時はNone
        """
        import re
        match = re.search(r'CREATE MATERIALIZED VIEW\s+\w+\s+AS\s+(.+)', 
                         create_sql, re.DOTALL | re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            # 末尾のセミコロンを削除
            query = query.rstrip(';').strip()
            return query
        return None
    
    
    def _get_mv_tables_info(self, mv_node_id: str, qp) -> Optional[dict]:
        """MVに含まれるテーブル情報を取得
        
        Args:
            mv_node_id: MVのノードID
            qp: QueryParser instance
            
        Returns:
            {'tables': [table_name, ...], 'aliases': [alias, ...]} または None
        """
        # leaf_nodeの場合
        if mv_node_id in qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = qp.qm.leaf_nodes_map_r[mv_node_id]
            return {
                'tables': [table_name],
                'aliases': [alias],
                'filters': [filter_cond] if filter_cond else []
            }
        
        # non_leaf_nodeの場合
        elif mv_node_id in qp.qm.non_leaf_nodes_info:
            all_tables = self._get_all_tables(mv_node_id, qp)
            if all_tables:
                tables = [t[0] for t in all_tables]
                aliases = [t[1] for t in all_tables]
                return {
                    'tables': tables,
                    'aliases': aliases,
                    'filters': []
                }
        
        return None
    
    def _get_mv_covered_aliases(
        self, 
        mv_id: str, 
        target_qp, 
        query: str
    ) -> Optional[set]:
        """MVがカバーするテーブルエイリアスを取得
        
        Args:
            mv_id: MVのノードID
            target_qp: QueryParser instance
            query: クエリ文字列
            
        Returns:
            カバーするエイリアスのset、または None
        """
        try:
            # MVのテーブル情報を取得
            mv_info = self._get_mv_tables_info(mv_id, target_qp)
            if not mv_info:
                return None
            
            mv_aliases = set(mv_info['aliases'])
            
            # クエリからテーブルエイリアスを抽出して検証
            # CommaJoinRewriterのparse_queryを使用
            from experiments.small_test_ver2.comma_join_rewriter import CommaJoinRewriter
            from experiments.small_test_ver2.small_test_schema_provider import SmallTestSchemaProvider
            
            schema_provider = SmallTestSchemaProvider()
            rewriter = CommaJoinRewriter(target_qp.qm, schema_provider)
            
            # クエリをパースして使用されているテーブルを確認
            parsed = rewriter.parse_query(query)
            if not parsed:
                return None
            
            query_aliases = set()
            for table_info in parsed['tables']:
                query_aliases.add(table_info.alias)
            
            # MVのエイリアスがクエリに含まれているかチェック
            covered = mv_aliases & query_aliases
            
            return covered if covered else None
            
        except Exception as e:
            print(f"  [WARN] MVカバレッジ判定エラー ({mv_id}): {e}")
            return None
    
    

    def _get_all_tables(self, node_id: str, qp) -> list[tuple[str, str]]:
        """ノードIDから全てのテーブル(table_name, alias)を再帰的に取得
        
        Args:
            node_id: ノードID
            qp: QueryParser instance
            
        Returns:
            List of (table_name, alias) tuples
        """
        tables = []
        if node_id in qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = qp.qm.leaf_nodes_map_r[node_id]
            tables.append((table_name, alias))
        elif node_id in qp.qm.non_leaf_nodes_info:
            info = qp.qm.non_leaf_nodes_info[node_id]
            for child in info.children:
                tables.extend(self._get_all_tables(child, qp))
        return tables

