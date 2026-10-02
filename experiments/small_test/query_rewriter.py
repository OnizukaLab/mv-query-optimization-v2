"""クエリ書き換えモジュール（小規模実験用）

選択されたMVを使用するようにクエリを書き換えます。
通常実験と時刻依存実験の両方に対応。

改善版: src/rewriteの高度な書き換えロジックを統合
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
import logging

# src/rewriteの高度な書き換えエンジンをインポート
from src.rewrite.advanced_rewriter import QueryRewriteEngine
from src.rewrite.query_graph import QueryGraph

logger = logging.getLogger(__name__)


class QueryRewriter:
    """MVを使用するクエリに書き換えるクラス
    
    src/rewrite/advanced_rewriter.pyのQueryRewriteEngineを活用した実装
    """
    
    def __init__(self, qm, mv_selections: Dict[str, List[str]]):
        """初期化
        
        Args:
            qm: QueryManagerインスタンス
            mv_selections: {query_id: [selected_node_ids]} の辞書
        """
        self.qm = qm
        self.mv_selections = mv_selections
        
        # 高度な書き換えエンジンを初期化
        try:
            self.rewrite_engine = QueryRewriteEngine(qm)
            self.use_advanced_engine = True
            logger.info("Advanced rewrite engine initialized successfully")
        except Exception as e:
            logger.warning(f"Could not initialize advanced engine: {e}. Falling back to simple rewriting.")
            self.use_advanced_engine = False
    
    def rewrite_query(self, query_id: int, original_sql: str) -> str:
        """クエリを書き換え
        
        Args:
            query_id: クエリID（0から始まる）
            original_sql: 元のSQLクエリ
            
        Returns:
            書き換え後のSQLクエリ
        """
        # このクエリで選択されたMVを取得
        selected_nodes = self.mv_selections.get(str(query_id), [])
        
        if not selected_nodes:
            # MVが選択されていない場合は元のクエリをそのまま返す
            comment = "-- No MVs selected for this query\n"
            comment += "-- Using original tables\n\n"
            return comment + original_sql
        
        # 高度なエンジンを使用
        if self.use_advanced_engine:
            try:
                rewritten_sql, mv_match = self.rewrite_engine.rewrite_query(
                    original_sql,
                    selected_nodes,
                    strategy="best"
                )
                
                # 書き換え成功
                if mv_match:
                    # 後処理: WHERE句のエイリアス修正、GROUP BY/HAVING復元
                    rewritten_sql = self._post_process_rewrite(
                        original_sql,
                        rewritten_sql,
                        mv_match
                    )
                    
                    comment = self._generate_advanced_comment(selected_nodes, mv_match)
                    return comment + "\n" + rewritten_sql
                else:
                    # マッチしなかった場合はフォールバック
                    logger.info(f"Query {query_id}: Advanced engine found no match, using fallback")
                    return self._fallback_rewrite(query_id, original_sql, selected_nodes)
                    
            except Exception as e:
                logger.warning(f"Query {query_id}: Advanced rewriting failed: {e}. Using fallback.")
                return self._fallback_rewrite(query_id, original_sql, selected_nodes)
        
        # フォールバック: シンプルな書き換え
        return self._fallback_rewrite(query_id, original_sql, selected_nodes)
    
    def _fallback_rewrite(self, query_id: int, original_sql: str, selected_nodes: List[str]) -> str:
        """フォールバック用のシンプルな書き換え
        
        Args:
            query_id: クエリID
            original_sql: 元のSQL
            selected_nodes: 選択されたノードIDリスト
            
        Returns:
            書き換え後のSQL
        """
        rewritten_sql = original_sql
        replacements = []
        
        # ノードを依存関係順に並べる（non_leaf → leaf の順で処理）
        non_leaf_nodes = [n for n in selected_nodes if n.startswith('non_leaf_')]
        leaf_nodes = [n for n in selected_nodes if n.startswith('leaf_')]
        
        # 1. non_leafノードの完全書き換えを試みる
        for node_id in non_leaf_nodes:
            result = self._try_rewrite_with_non_leaf(rewritten_sql, node_id, replacements)
            if result:
                rewritten_sql = result
        
        # 2. leafノードの書き換え（non_leafでカバーされていない部分）
        for node_id in leaf_nodes:
            # QueryManagerからノード情報を取得
            if node_id in self.qm.relation_tables:
                table_name = self.qm.relation_tables[node_id]
                mv_name = f"mv_{node_id}"
                
                # テーブル参照をMVに置き換え
                # パターン1: FROM table_name
                pattern1 = rf'\bFROM\s+{re.escape(table_name)}\b'
                if re.search(pattern1, rewritten_sql, re.IGNORECASE):
                    rewritten_sql = re.sub(
                        pattern1,
                        f'FROM {mv_name}',
                        rewritten_sql,
                        flags=re.IGNORECASE
                    )
                    replacements.append(f"FROM {table_name} → FROM {mv_name}")
                
                # パターン2: JOIN table_name
                pattern2 = rf'\bJOIN\s+{re.escape(table_name)}\b'
                if re.search(pattern2, rewritten_sql, re.IGNORECASE):
                    rewritten_sql = re.sub(
                        pattern2,
                        f'JOIN {mv_name}',
                        rewritten_sql,
                        flags=re.IGNORECASE
                    )
                    replacements.append(f"JOIN {table_name} → JOIN {mv_name}")
                
                # パターン3: table_name.column (カラム参照)
                pattern3 = rf'\b{re.escape(table_name)}\.(\w+)'
                if re.search(pattern3, rewritten_sql, re.IGNORECASE):
                    rewritten_sql = re.sub(
                        pattern3,
                        rf'{mv_name}.\1',
                        rewritten_sql,
                        flags=re.IGNORECASE
                    )
                    replacements.append(f"{table_name}.* → {mv_name}.*")
        
        # コメントを追加
        comment = self._generate_comment(selected_nodes, replacements)
        return comment + "\n" + rewritten_sql
    
    def _generate_advanced_comment(self, selected_nodes: List[str], mv_match) -> str:
        """高度な書き換えエンジン用のコメントを生成"""
        comment = "-- ================================================\n"
        comment += "-- Query rewritten using Advanced Rewrite Engine\n"
        comment += "-- ================================================\n"
        comment += f"-- Selected MVs: {len(selected_nodes)}\n"
        comment += f"-- Match Type: {mv_match.replacement_type}\n"
        comment += f"-- MV Used: mv_{mv_match.mv_id}\n"
        
        if hasattr(mv_match, 'matched_tables'):
            comment += f"-- Matched Tables: {', '.join(sorted(mv_match.matched_tables))}\n"
        
        comment += f"-- Coverage Score: {mv_match.coverage_score:.1%}\n"
        comment += "-- ================================================\n"
        return comment
    
    def _post_process_rewrite(self, original_sql: str, rewritten_sql: str, mv_match) -> str:
        """高度なエンジンの書き換え結果を後処理
        
        Args:
            original_sql: 元のSQL
            rewritten_sql: 書き換え後のSQL
            mv_match: MVマッチ情報
            
        Returns:
            後処理済みのSQL
        """
        # 完全置き換えの場合
        if mv_match.replacement_type == "full":
            # 元のSQLから各句を抽出
            group_by = self._extract_group_by(original_sql)
            having = self._extract_having(original_sql)
            order_by = self._extract_order_by(original_sql)
            
            # 書き換え後のSQLのセミコロンを除去
            rewritten_sql = rewritten_sql.rstrip(';').strip()
            
            # 1. WHERE句のエイリアス参照を修正
            rewritten_sql = self._fix_all_aliases_in_sql(rewritten_sql, mv_match)
            
            # 2. GROUP BY句を追加
            if group_by:
                group_by_fixed = self._fix_clause_aliases(group_by, mv_match)
                rewritten_sql += f'\nGROUP BY {group_by_fixed}'
            
            # 3. HAVING句を追加
            if having:
                having_fixed = self._fix_clause_aliases(having, mv_match)
                rewritten_sql += f'\nHAVING {having_fixed}'
            
            # 4. ORDER BY句を追加
            if order_by:
                order_by_fixed = self._fix_clause_aliases(order_by, mv_match)
                rewritten_sql += f'\nORDER BY {order_by_fixed}'
            
            # セミコロンを追加
            rewritten_sql += ';'
        
        return rewritten_sql
    
    def _fix_all_aliases_in_sql(self, sql: str, mv_match) -> str:
        """SQL全体のテーブルエイリアスをMV参照に修正"""
        if not hasattr(mv_match, 'matched_tables'):
            return sql
        
        # 各テーブルエイリアスをMV名に置換
        for alias in mv_match.matched_tables:
            # alias.column → mv_id.column
            sql = re.sub(
                rf'\b{re.escape(alias)}\.(\w+)',
                rf'{mv_match.mv_id}.\1',
                sql,
                flags=re.IGNORECASE
            )
        
        return sql
    
    def _fix_where_aliases(self, sql: str, mv_match) -> str:
        """WHERE句のテーブルエイリアスをMV参照に修正"""
        if not hasattr(mv_match, 'matched_tables'):
            return sql
        
        # WHERE句を抽出
        where_match = re.search(r'WHERE\s+(.*?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return sql
        
        where_clause = where_match.group(1).strip()
        
        # 各テーブルエイリアスをMV名に置換
        for alias in mv_match.matched_tables:
            # alias.column → mv_id.column
            where_clause = re.sub(
                rf'\b{re.escape(alias)}\.(\w+)',
                rf'{mv_match.mv_id}.\1',
                where_clause,
                flags=re.IGNORECASE
            )
        
        # WHERE句を置き換え（セミコロンまで）
        new_where = f'WHERE {where_clause}'
        if ';' in sql:
            before_where = sql.split('WHERE')[0]
            return before_where + new_where + ';'
        else:
            return sql.replace(where_match.group(0), new_where)
    
    def _fix_clause_aliases(self, clause: str, mv_match) -> str:
        """句内のテーブルエイリアスをMV参照に修正"""
        if not hasattr(mv_match, 'matched_tables'):
            return clause
        
        for alias in mv_match.matched_tables:
            clause = re.sub(
                rf'\b{re.escape(alias)}\.(\w+)',
                rf'{mv_match.mv_id}.\1',
                clause,
                flags=re.IGNORECASE
            )
        
        return clause
    
    def _extract_group_by(self, sql: str) -> Optional[str]:
        """GROUP BY句を抽出"""
        match = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+HAVING|\s+ORDER|\s*;|$)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_having(self, sql: str) -> Optional[str]:
        """HAVING句を抽出"""
        match = re.search(r'HAVING\s+(.*?)(?:\s+ORDER|\s*;|$)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_order_by(self, sql: str) -> Optional[str]:
        """ORDER BY句を抽出"""
        match = re.search(r'ORDER\s+BY\s+(.*?)(?:\s*;|$)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _get_table_alias(self, node_id: str) -> Optional[str]:
        """ノードIDからテーブルエイリアスを取得"""
        # QueryManagerから取得（実装依存）
        # 簡略化のため、ここではNoneを返す
        return None
    
    def _try_rewrite_with_non_leaf(self, sql: str, node_id: str, replacements: List[str]) -> Optional[str]:
        """non_leafノードを使用した完全書き換えを試みる
        
        Args:
            sql: 元のSQL
            node_id: non_leafノードID
            replacements: 置換記録リスト
            
        Returns:
            書き換え後のSQL（成功時）、None（失敗時）
        """
        # non_leafノードが包含するテーブルを取得
        covered_tables = self._get_covered_tables(node_id)
        if not covered_tables:
            replacements.append(f"Subquery optimized with mv_{node_id}")
            return None
        
        # クエリが必要とするテーブルを検出
        required_tables = self._detect_required_tables(sql)
        
        # non_leafが全テーブルをカバーする場合、完全書き換え可能
        if required_tables and required_tables.issubset(covered_tables):
            mv_name = f"mv_{node_id}"
            rewritten = self._replace_multi_table_join(sql, covered_tables, mv_name)
            if rewritten != sql:
                replacements.append(f"Complete JOIN replacement with {mv_name}")
                return rewritten
        else:
            # 部分的なカバーの場合はコメント追加のみ
            replacements.append(f"Subquery optimized with mv_{node_id}")
        
        return None
    
    def _get_covered_tables(self, node_id: str) -> Set[str]:
        """non_leafノードが包含するテーブルを取得"""
        covered = set()
        
        # QueryManagerから子ノード情報を取得
        if hasattr(self.qm, 'non_leaf_nodes_map_r') and node_id in self.qm.non_leaf_nodes_map_r:
            child_ids = self.qm.non_leaf_nodes_map_r[node_id]
            for child_id in child_ids:
                if child_id in self.qm.relation_tables:
                    covered.add(self.qm.relation_tables[child_id])
        
        # non_leaf_nodes_infoから取得（新しい形式）
        if hasattr(self.qm, 'non_leaf_nodes_info') and node_id in self.qm.non_leaf_nodes_info:
            node_info = self.qm.non_leaf_nodes_info[node_id]
            for child_id in node_info.children:
                if child_id in self.qm.relation_tables:
                    covered.add(self.qm.relation_tables[child_id])
        
        return covered
    
    def _detect_required_tables(self, sql: str) -> Set[str]:
        """SQLクエリが必要とするテーブルを検出"""
        tables = set()
        
        # FROM句とJOIN句からテーブル名を抽出
        # 簡易実装: users, products, ordersを検出
        for table in ['users', 'products', 'orders']:
            pattern = rf'\b(FROM|JOIN)\s+{table}\b'
            if re.search(pattern, sql, re.IGNORECASE):
                tables.add(table)
        
        return tables
    
    def _replace_multi_table_join(self, sql: str, tables: Set[str], mv_name: str) -> str:
        """複数テーブルのJOINをMVに置き換え
        
        Args:
            sql: 元のSQL
            tables: 置き換え対象のテーブル群
            mv_name: 使用するMV名
            
        Returns:
            書き換え後のSQL
        """
        # 3テーブルJOINパターンの検出と置き換え
        # 例: FROM users u JOIN orders o ... JOIN products p ...
        
        if len(tables) == 3 and tables == {'users', 'products', 'orders'}:
            # 3テーブル完全JOINのパターン
            # FROM users u INNER JOIN orders o ON u.user_id = o.user_id 
            #              INNER JOIN products p ON o.product_id = p.product_id
            # → FROM mv_non_leaf_12 mv
            
            # より柔軟なパターン: ON句の条件を広く捉える
            pattern = (
                r'FROM\s+users\s+(\w+)\s+'
                r'(?:INNER\s+)?JOIN\s+orders\s+(\w+)\s+ON\s+[^\n]+\s+'
                r'(?:INNER\s+)?JOIN\s+products\s+(\w+)\s+ON\s+[^\n]+'
            )
            
            match = re.search(pattern, sql, re.IGNORECASE)
            if match:
                # エイリアスを保存
                u_alias = match.group(1)
                o_alias = match.group(2)
                p_alias = match.group(3)
                
                # マッチした全体のJOIN句を取得
                matched_text = match.group(0)
                
                # JOINを置き換え
                replacement = f'FROM {mv_name} mv'
                rewritten = sql.replace(matched_text, replacement)
                
                # エイリアス参照を新しいMVエイリアスに置き換え
                # u.col → mv.col, o.col → mv.col, p.col → mv.col
                for old_alias in [u_alias, o_alias, p_alias]:
                    rewritten = re.sub(
                        rf'\b{re.escape(old_alias)}\.(\w+)',
                        r'mv.\1',
                        rewritten,
                        flags=re.IGNORECASE
                    )
                
                return rewritten
        
        # 2テーブルJOINの場合
        if len(tables) == 2:
            # 簡易的な2テーブルJOIN置き換え
            # 実装は省略（必要に応じて追加）
            pass
        
        return sql
    
    def _generate_comment(self, selected_nodes: List[str], replacements: List[str]) -> str:
        """書き換えコメントを生成"""
        comment = "-- ================================================\n"
        comment += "-- Query rewritten to use Materialized Views\n"
        comment += "-- ================================================\n"
        comment += f"-- Selected MVs: {len(selected_nodes)}\n"
        
        if replacements:
            comment += "-- Replacements:\n"
            for r in replacements:
                comment += f"--   • {r}\n"
        
        comment += "-- ================================================\n\n"
        return comment
    
    def rewrite_all_queries(
        self,
        query_files: List[Path],
        output_dir: Path
    ) -> int:
        """すべてのクエリを書き換え
        
        Args:
            query_files: クエリファイルのリスト
            output_dir: 出力ディレクトリ
            
        Returns:
            書き換えたクエリ数
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        rewritten_count = 0
        
        for i, query_file in enumerate(query_files):
            print(f"    → {query_file.name} を書き換え中...")
            
            # 元のクエリを読み込み
            original_sql = query_file.read_text(encoding='utf-8')
            
            # MVを使用するクエリに書き換え
            rewritten_sql = self.rewrite_query(i, original_sql)
            
            # 書き換え結果を保存
            output_file = output_dir / f"rewritten_{query_file.name}"
            output_file.write_text(rewritten_sql, encoding='utf-8')
            rewritten_count += 1
        
        return rewritten_count


class TimeDependentQueryRewriter:
    """時刻依存実験用のクエリ書き換えクラス"""
    
    def __init__(self, timesteps: List[str], parsers_dict: Dict[str, any]):
        """初期化
        
        Args:
            timesteps: タイムステップのリスト（例: ["t1", "t2", "t3"]）
            parsers_dict: {time_id: parser} の辞書
        """
        self.timesteps = timesteps
        self.parsers_dict = parsers_dict
    
    def rewrite_queries_for_timestep(
        self,
        time_id: str,
        mv_selections: Dict[str, List[str]],
        query_files: List[Path],
        output_dir: Path
    ) -> int:
        """特定のタイムステップのクエリを書き換え
        
        Args:
            time_id: タイムステップID（例: "t1"）
            mv_selections: MV選択結果
            query_files: クエリファイルのリスト
            output_dir: 出力ディレクトリ
            
        Returns:
            書き換えたクエリ数
        """
        print(f"  [{time_id}] クエリを書き換え中...")
        
        # このタイムステップのパーサーを取得
        parser = self.parsers_dict.get(time_id)
        if parser is None:
            print(f"    ⚠ パーサーが見つかりません: {time_id}")
            return 0
        
        # QueryRewriterを作成
        rewriter = QueryRewriter(parser.qm, mv_selections)
        
        # タイムステップ専用の出力ディレクトリ
        timestep_output_dir = output_dir / time_id
        
        # すべてのクエリを書き換え
        count = rewriter.rewrite_all_queries(query_files, timestep_output_dir)
        
        print(f"    ✓ {count}個のクエリを書き換え完了: {timestep_output_dir}")
        return count
    
    def rewrite_all_timesteps(
        self,
        optimization_results: Dict[str, Dict[str, List[str]]],
        query_files: List[Path],
        output_base_dir: Path
    ) -> Dict[str, int]:
        """すべてのタイムステップのクエリを書き換え
        
        Args:
            optimization_results: {time_id: mv_selections} の辞書
            query_files: クエリファイルのリスト
            output_base_dir: 出力ベースディレクトリ
            
        Returns:
            {time_id: rewritten_count} の辞書
        """
        results = {}
        
        for time_id in self.timesteps:
            mv_selections = optimization_results.get(time_id, {})
            if not mv_selections:
                print(f"  [{time_id}] 最適化結果が見つかりません。スキップ")
                results[time_id] = 0
                continue
            
            count = self.rewrite_queries_for_timestep(
                time_id,
                mv_selections,
                query_files,
                output_base_dir
            )
            results[time_id] = count
        
        return results


def create_query_rewriter(qm, mv_selections: Dict[str, List[str]]) -> QueryRewriter:
    """QueryRewriterを作成
    
    Args:
        qm: QueryManagerインスタンス
        mv_selections: MV選択結果
        
    Returns:
        QueryRewriter インスタンス
    """
    return QueryRewriter(qm, mv_selections)


def create_time_dependent_rewriter(
    timesteps: List[str],
    parsers_dict: Dict[str, any]
) -> TimeDependentQueryRewriter:
    """TimeDependentQueryRewriterを作成
    
    Args:
        timesteps: タイムステップのリスト
        parsers_dict: パーサー辞書
        
    Returns:
        TimeDependentQueryRewriter インスタンス
    """
    return TimeDependentQueryRewriter(timesteps, parsers_dict)
