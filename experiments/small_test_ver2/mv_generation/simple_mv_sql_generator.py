"""MV SQL Generator with existing MV support.

This module provides functionality to generate MV creation SQL
that can reference existing MVs.

Features:
- Uses CommaJoinRewriter to rewrite queries with existing MVs
- Time-independent: uses a single QueryParser instance
"""

from typing import Optional
import re
import logging

from experiments.small_test_ver2.mv_generation.enhanced_mv_generator import EnhancedMVGenerator
from experiments.small_test_ver2.mv_generation.comma_join_rewriter import CommaJoinRewriter


logger = logging.getLogger(__name__)


class SimpleMVSQLGenerator:
    """Generate MV SQL that can reference existing MVs.
    
    This class generates CREATE MATERIALIZED VIEW SQL by rewriting
    the base query to reference existing MVs when beneficial.
    """
    
    def __init__(self, qp, db_config: dict | None = None):
        """Initialize MVSQLGenerator.
        
        Args:
            qp: QueryParser instance (single, time-independent)
            db_config: Database configuration dict for SchemaProvider
        """
        self.qp = qp
        self.db_config = db_config
        # SchemaProviderを1回だけ作成して再利用（パフォーマンス最適化）
        from src.rewrite.schema_provider import SchemaProvider
        self.schema_provider = SchemaProvider(self.db_config)
    
    def generate_mv_sql(
        self, 
        node_id: str, 
        existing_mvs: list[str]
    ) -> Optional[str]:
        """既存MVを考慮してMV SQLを生成
        
        Args:
            node_id: 生成するMVのノードID
            existing_mvs: 既存のMVノードIDリスト（再利用可能なMV）
            
        Returns:
            CREATE MATERIALIZED VIEW文。生成失敗時はNone
        """
        if not hasattr(self.qp, 'qm'):
            print(f"  エラー: QueryParserにqmが存在しません")
            return None
        
        try:
            # 1. EnhancedMVGeneratorで元のMV定義を生成（再利用したschema_providerを使用）
            mv_generator = EnhancedMVGenerator(
                query_manager=self.qp.qm,
                schema_provider=self.schema_provider,
                selected_mvs=set(),  # 既存MVなしで純粋なクエリを生成
                query_parser=self.qp,  # 元SQL JOIN条件へのアクセスを提供
            )
            
            original_sql = mv_generator.generate_mv_sql(node_id)
            
            if not original_sql:
                print(f"  エラー: {node_id} のMV SQL生成失敗")
                return None
            
            print(f"  [INFO] 元のSQL生成完了")
            
            # 2. CREATE MATERIALIZED VIEW ... AS 部分を削除して元クエリを取得
            base_query = self._extract_query_from_create(original_sql)
            
            if not base_query:
                print(f"  エラー: {node_id} のクエリ抽出失敗")
                return None
            
            # 3. 既存MVがある場合、CommaJoinRewriterで書き換え
            if existing_mvs:
                print(f"  [INFO] 既存MV {len(existing_mvs)}個を使用して書き換え")
                
                # CommaJoinRewriterを初期化（再利用したschema_providerを使用）
                comma_rewriter = CommaJoinRewriter(
                    query_manager=self.qp.qm,
                    schema_provider=self.schema_provider
                )
                
                # 各既存MVのカバー範囲を判定
                mv_dict = {}  # mv_id -> set of covered aliases
                for mv_id in existing_mvs:
                    mv_tables = self._get_mv_covered_aliases(mv_id, base_query)
                    if mv_tables:
                        print(f"  [INFO] {mv_id} がカバー: {mv_tables}")
                        mv_dict[mv_id] = mv_tables
                    else:
                        print(f"  [INFO] {mv_id} はクエリをカバーしない")
                
                # 複数MVで書き換え
                if mv_dict:
                    rewritten_query = comma_rewriter.rewrite_with_multiple_mvs(
                        base_query, 
                        mv_dict
                    )
                else:
                    rewritten_query = base_query
            else:
                print(f"  [INFO] 既存MVなし、元クエリを使用")
                rewritten_query = base_query
            
            # 4. CREATE MATERIALIZED VIEW文に変換
            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{rewritten_query};"
            
            print(f"  [INFO] {node_id} のSQL生成完了")
            if existing_mvs:
                print(f"  [INFO] 再利用MV: {existing_mvs}")
            
            return create_sql
            
        except Exception as e:
            print(f"  エラー: SQL生成失敗 - {e}")
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
    
    
    def _get_mv_tables_info(self, mv_node_id: str) -> Optional[dict]:
        """MVに含まれるテーブル情報を取得
        
        Args:
            mv_node_id: MVのノードID
            
        Returns:
            {'tables': [table_name, ...], 'aliases': [alias, ...]} または None
        """
        # leaf_nodeの場合
        if mv_node_id in self.qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = self.qp.qm.leaf_nodes_map_r[mv_node_id]
            return {
                'tables': [table_name],
                'aliases': [alias],
                'filters': [filter_cond] if filter_cond else []
            }
        
        # non_leaf_nodeの場合
        elif mv_node_id in self.qp.qm.non_leaf_nodes_info:
            all_tables = self._get_all_tables(mv_node_id)
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
        query: str
    ) -> Optional[set]:
        """MVがカバーするテーブルエイリアスを取得
        
        Args:
            mv_id: MVのノードID
            query: クエリ文字列
            
        Returns:
            カバーするエイリアスのset、または None
        """
        try:
            # MVのテーブル情報を取得
            mv_info = self._get_mv_tables_info(mv_id)
            if not mv_info:
                return None
            
            mv_aliases = set(mv_info['aliases'])
            
            # クエリからテーブルエイリアスを抽出して検証
            # CommaJoinRewriterのparse_queryを使用（再利用したschema_providerを使用）
            from experiments.small_test_ver2.mv_generation.comma_join_rewriter import CommaJoinRewriter
            
            rewriter = CommaJoinRewriter(self.qp.qm, self.schema_provider)
            
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
    
    

    def _get_all_tables(self, node_id: str) -> list[tuple[str, str]]:
        """ノードIDから全てのテーブル(table_name, alias)を再帰的に取得
        
        Args:
            node_id: ノードID
            
        Returns:
            List of (table_name, alias) tuples
        """
        tables = []
        if node_id in self.qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = self.qp.qm.leaf_nodes_map_r[node_id]
            tables.append((table_name, alias))
        elif node_id in self.qp.qm.non_leaf_nodes_info:
            info = self.qp.qm.non_leaf_nodes_info[node_id]
            for child in info.children:
                tables.extend(self._get_all_tables(child))
        return tables


