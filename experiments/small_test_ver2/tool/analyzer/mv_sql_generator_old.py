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
from experiments.small_test_ver2.query_rewriter import QueryRewriter
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
    
    def generate_mv_sql_with_existing(
        self, 
        node_id: str, 
        existing_mvs: list[str], 
        time_id: str
    ) -> Optional[str]:
        """既存のMVを利用して新しいMVのSQLを作成
        
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
            # schema_providerを初期化
            schema_provider = SmallTestSchemaProvider()

            # EnhancedMVGeneratorを初期化
            mv_generator = EnhancedMVGenerator(
                query_manager=target_qp.qm,
                schema_provider=schema_provider,
                selected_mvs=set(existing_mvs)  # ここで既存MVを指定
            )

            create_sql = mv_generator.generate_mv_sql(node_id)
            
            if not create_sql:
                print(f"SQL生成失敗: {node_id}")
                return None
            
            print(f"  [INFO] {node_id} のSQL生成完了")
            print(f"  [INFO] 再利用するMV: {existing_mvs if existing_mvs else 'なし'}")
            
            # 既存MVをFROM句で参照するように置き換え
            # EnhancedMVGeneratorが子ノードをMVとして参照していない場合の対処
            if existing_mvs:
                create_sql = self._replace_tables_with_mvs(
                    create_sql, 
                    existing_mvs, 
                    target_qp
                )
            
            print(f"  [DEBUG] 最終SQL (最初の200文字): {create_sql[:200]}")
            return create_sql

        except Exception as e:
            print(f"SQL生成失敗: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
                
                # 既存MVがカバーするテーブルエイリアスを特定
                mv_covers = self._determine_mv_coverage(existing_mvs, target_qp, base_query)
                
                if mv_covers:
                    print(f"  [INFO] 既存MVがカバーするテーブル: {mv_covers}")
                    
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
                    print(f"  [INFO] MVカバレッジ判定失敗、元クエリを使用")
                    rewritten_query = base_query
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
    
    def _build_mv_mappings(self, existing_mvs: list[str], target_qp) -> dict:
        """既存MVのマッピング情報を構築
        
        Args:
            existing_mvs: 既存MVのノードIDリスト
            target_qp: 対象のQueryParser
            
        Returns:
            {mv_node_id: {'tables': [...], 'aliases': [...]}} の辞書
        """
        mappings = {}
        
        for mv_node_id in existing_mvs:
            # MVに含まれるテーブル情報を取得
            tables_info = self._get_mv_tables_info(mv_node_id, target_qp)
            
            if tables_info:
                mappings[mv_node_id] = tables_info
                print(f"    [DEBUG] MV {mv_node_id}: {tables_info}")
        
        return mappings
    
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
    
    def _determine_mv_coverage(
        self, 
        existing_mvs: list[str], 
        target_qp, 
        query: str
    ) -> dict[str, set]:
        """各MVがカバーするテーブルエイリアスを判定
        
        Args:
            existing_mvs: 既存MVのリスト
            target_qp: QueryParser instance
            query: クエリ文字列
            
        Returns:
            {mv_id: set(aliases)} の辞書
        """
        mv_coverage = {}
        
        for mv_id in existing_mvs:
            aliases = self._get_mv_covered_aliases(mv_id, target_qp, query)
            if aliases:
                mv_coverage[mv_id] = aliases
        
        return mv_coverage
    
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
    
    def _rewrite_query_with_mvs(
        self, 
        query: str, 
        mv_mappings: dict,
        rewriter: QueryRewriter,
        target_qp
    ) -> str:
        """クエリを既存MVを使用する形に書き換え
        
        Args:
            query: 元のクエリ
            mv_mappings: MVマッピング情報
            rewriter: QueryRewriter instance
            target_qp: QueryParser instance
            
        Returns:
            書き換えられたクエリ
        """
        rewritten = query
        
        # 各MVについて、対応するテーブル参照を置き換え
        for mv_node_id, mv_info in mv_mappings.items():
            rewritten = self._substitute_tables_with_mv(
                rewritten, 
                mv_node_id, 
                mv_info
            )
        
        return rewritten
    
    def _substitute_tables_with_mv(
        self, 
        query: str, 
        mv_node_id: str,
        mv_info: dict
    ) -> str:
        """クエリ内のテーブル参照をMV参照に置換
        
        Args:
            query: 元のクエリ
            mv_node_id: MVのノードID
            mv_info: MVに含まれるテーブル情報
            
        Returns:
            置換後のクエリ
        """
        tables = mv_info.get('tables', [])
        aliases = mv_info.get('aliases', [])
        
        if not tables or not aliases:
            return query
        
        # 最初のテーブル/エイリアスをMVに置き換え
        first_table = tables[0]
        first_alias = aliases[0]
        
        # FROM句のパターン: "FROM table_name AS alias"
        pattern1 = rf'\bFROM\s+{first_table}\s+AS\s+{first_alias}\b'
        query = re.sub(pattern1, rf'FROM {mv_node_id} AS {first_alias}', query, flags=re.IGNORECASE)
        
        # JOIN句のパターン: ", table_name AS alias"
        pattern2 = rf',\s+{first_table}\s+AS\s+{first_alias}\b'
        query = re.sub(pattern2, rf', {mv_node_id} AS {first_alias}', query, flags=re.IGNORECASE)
        
        # 残りのテーブルを削除（MVに含まれているため不要）
        for i in range(1, len(tables)):
            table = tables[i]
            alias = aliases[i]
            
            # ", table AS alias" パターンを削除
            pattern = rf',\s+{table}\s+AS\s+{alias}\b'
            query = re.sub(pattern, '', query, flags=re.IGNORECASE)
            
            # WHERE句のJOIN条件も削除する必要がある場合は追加処理
            # （現時点では簡易実装）
        
        return query
    
    def _replace_tables_with_mvs(
        self, 
        create_sql: str, 
        existing_mvs: list[str],
        target_qp
    ) -> str:
        """テーブル参照をMV参照に置き換え
        
        Args:
            create_sql: 元のCREATE SQL
            existing_mvs: 既存MVのリスト
            target_qp: 対象のQueryParser
            
        Returns:
            置き換え後のSQL
        """
        # 各子ノードのテーブル名をMV名に置き換え
        for child_node_id in existing_mvs:
            # 全てのQueryParserから子ノードの情報を検索
            found = False
            for qp_time_id, qp in self.qp_dict.items():
                # leaf_nodeの場合
                if child_node_id in qp.qm.leaf_nodes_map_r:
                    operator, table_name, alias, filter_cond = qp.qm.leaf_nodes_map_r[child_node_id]
                    mv_name = child_node_id  # mv_プレフィックスなし
                    found = True
                    
                    print(f"    [DEBUG] {qp_time_id} でleaf発見: table_name={table_name}, alias={alias}")
                    
                    # FROM句でテーブル名をMV名に置き換え
                    # 例: "FROM orders AS o" -> "FROM leaf_1 AS o"
                    # パターン1: FROM table_name AS alias
                    pattern1 = rf'\bFROM\s+{table_name}\s+AS\s+{alias}\b'
                    before_sql = create_sql
                    create_sql = re.sub(pattern1, rf'FROM {mv_name} AS {alias}', create_sql)
                    if before_sql != create_sql:
                        print(f"    [DEBUG] パターン1でマッチ: '{pattern1}'")
                    
                    # パターン2: , table_name AS alias (JOIN内)
                    pattern2 = rf',\s+{table_name}\s+AS\s+{alias}\b'
                    before_sql = create_sql
                    create_sql = re.sub(pattern2, rf', {mv_name} AS {alias}', create_sql)
                    if before_sql != create_sql:
                        print(f"    [DEBUG] パターン2でマッチ: '{pattern2}'")
                    
                    print(f"  → {child_node_id} ({table_name}) を {mv_name} に置き換え")
                    break
                
                # non_leaf_nodeの場合
                elif child_node_id in qp.qm.non_leaf_nodes_info:
                    non_leaf_info = qp.qm.non_leaf_nodes_info[child_node_id]
                    mv_name = child_node_id  # mv_プレフィックスなし
                    found = True
                    
                    print(f"    [DEBUG] {qp_time_id} でnon_leaf発見: {child_node_id}, children={non_leaf_info.children}")
                    
                    # 子ノードに含まれる全てのテーブルを特定
                    all_tables = self._get_all_tables(child_node_id, qp)
                    print(f"    [DEBUG] non_leaf_nodeに含まれるテーブル: {all_tables}")
                    
                    # 最初のテーブルをMVに置き換え、残りのテーブルを削除する戦略
                    if all_tables:
                        first_table, first_alias = all_tables[0]
                        
                        # 最初のテーブルをMVに置き換え
                        pattern1 = rf'\bFROM\s+{first_table}\s+AS\s+{first_alias}\b'
                        create_sql = re.sub(pattern1, rf'FROM {mv_name} AS {first_alias}', create_sql)
                        
                        # 残りのテーブルとそのJOIN条件を削除
                        for table_name, alias in all_tables[1:]:
                            # ", table AS alias" パターンを削除
                            pattern = rf',\s+{table_name}\s+AS\s+{alias}\b'
                            create_sql = re.sub(pattern, '', create_sql)
                        
                        print(f"  → {child_node_id} を {mv_name} に置き換え (含まれるテーブル: {len(all_tables)}個)")
                    
                    break
            
            if not found:
                print(f"    [DEBUG] {child_node_id} は全てのQueryParserで見つかりませんでした")
        
        return create_sql
    
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



    def generate_mv_sql_with_rewriter_ver2(
            self,
            node_id: str,
            existing_mvs: list[str],
            time_id: str
    ) -> Optional[str]:
        
        if time_id not in self.qp_dict:
            print(f" エラー: {time_id}のパーサーがありません")
            return None
        
        target_qp = self.qp_dict[time_id]
        if not hasattr(target_qp, 'qm'):
            return None
        
        try:
            schema_provider = SmallTestSchemaProvider()
            mv_generator = EnhancedMVGenerator(
                query_manager = target_qp.qm,
                schema_provider = schema_provider,
                selected_mvs = set()
            )

            original_sql = mv_generator.generate_mv_sql(node_id)
            if not original_sql:
                return None
            
            base_query = self._extract_query_from_create(original_sql)
            if not base_query:
                return None
            
            # QueryRewriterは mv_selections を dict[str, list[str]] 形式で期待
            mv_selections_dict = {node_id: existing_mvs}
            rewriter = QueryRewriter(
                qm=target_qp.qm,
                mv_selections=mv_selections_dict
            )

            # rewrite_query は (query_id, original_sql) を引数に取る
            rewritten_query = rewriter.rewrite_query(
                query_id=None,
                original_sql=base_query
            )

            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{rewritten_query};"

            print(f" [INFO] {node_id} のSQL生成完了")
            print(f" [INFO] 再利用するMV: {existing_mvs}")

            return create_sql
        
        except Exception as e:
            print(f"SQL生成失敗（Rewriter方式）: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_mv_sql_with_subtree_restore(
        self,
        node_id: str,
        existing_mvs: list[str],
        time_id: str,
        preserve_join_structure: bool = True
    ) -> Optional[str]:
        """SubtreeRestorerとQueryRewriterを組み合わせてMV SQLを生成
        
        Args:
            node_id: 生成するMVのノードID
            existing_mvs: 既存のMV（前の時刻のMV）のノードIDリスト
            time_id: 対象時刻のID
            preserve_join_structure: JOIN構造を保持するか（True: INNER JOIN ... ON, False: comma JOIN + WHERE）
            
        Returns:
            CREATE MATERIALIZED VIEW文。生成失敗時はNone
        """
        from experiments.small_test_ver2.subtree_restorer import SubtreeRestorer
        
        # 指定された時刻のQueryParserを使用
        if time_id not in self.qp_dict:
            print(f"  エラー: {time_id} のQueryParserが見つかりません")
            return None
        
        target_qp = self.qp_dict[time_id]
        if not hasattr(target_qp, 'qm'):
            return None
        
        try:
            # schema_providerを初期化
            schema_provider = SmallTestSchemaProvider()
            
            # SubtreeRestorerを初期化（schema_providerを渡す）
            restorer = SubtreeRestorer(
                query_manager=target_qp.qm,
                schema_provider=schema_provider
            )
            
            # ノード情報からサブツリーのSQLを復元
            base_query = restorer.restore_subtree_sql(
                node_id=node_id,
                preserve_join_structure=preserve_join_structure
            )
            
            if not base_query:
                print(f"  エラー: {node_id} のSQL復元失敗")
                return None
            
            print(f" [INFO] 復元されたベースクエリ:")
            print(base_query)
            
            # 既存MVがある場合はQueryRewriterで書き換え
            if existing_mvs:
                # QueryRewriterは mv_selections を dict[str, list[str]] 形式で期待
                mv_selections_dict = {node_id: existing_mvs}
                query_rewriter = QueryRewriter(
                    qm=target_qp.qm,
                    mv_selections=mv_selections_dict
                )
                
                rewritten_query = query_rewriter.rewrite_query(
                    query_id=None,
                    original_sql=base_query
                )
                
                if rewritten_query:
                    print(f" [INFO] QueryRewriterによる書き換え完了")
                    final_query = rewritten_query
                else:
                    print(f" [WARNING] QueryRewriterによる書き換え失敗、ベースクエリを使用")
                    final_query = base_query
            else:
                # 既存MVがない場合はそのまま使用
                final_query = base_query
            
            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{final_query};"
            
            print(f" [INFO] {node_id} のSQL生成完了（SubtreeRestorer方式）")
            if existing_mvs:
                print(f" [INFO] 再利用するMV: {existing_mvs}")
            
            return create_sql
        
        except Exception as e:
            print(f"SQL生成失敗（SubtreeRestorer方式）: {e}")
            import traceback
            traceback.print_exc()
            return None
        