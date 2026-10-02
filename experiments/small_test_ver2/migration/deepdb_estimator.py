# DeepDB カーディナリティ推定ラッパー
#
# DeepDB の SPN アンサンブルを使ってカーディナリティを推定するラッパークラス
#
# Usage:
#   from migration.deepdb_estimator import DeepDBEstimator
#   estimator = DeepDBEstimator(ensemble_path, csv_path)
#   rows = estimator.estimate_cardinality(select_sql)

import sys
import re
import logging
from pathlib import Path
from typing import Optional, Tuple

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# DeepDB パスを追加
deepdb_root = project_root / "deepdb_full" / "deepdb"
sys.path.insert(0, str(deepdb_root))

logger = logging.getLogger(__name__)


class DeepDBEstimator:
    """DeepDB SPN アンサンブルによるカーディナリティ推定クラス
    
    DeepDB の学習済みアンサンブルを読み込み、SQL クエリから
    カーディナリティ（推定行数）を計算します。
    
    Attributes:
        schema: DeepDB の IMDB スキーマオブジェクト
        ensemble: 学習済み SPN アンサンブル
        
    Example:
        >>> estimator = DeepDBEstimator(
        ...     ensemble_path="./imdb_ensemble/ensemble_join_3_budget_5_10000000.pkl",
        ...     csv_path="./imdb_csv/{}.csv"
        ... )
        >>> rows = estimator.estimate_cardinality(
        ...     "SELECT t.id FROM title t WHERE t.production_year > 2000"
        ... )
        >>> print(f"Estimated rows: {rows}")
    """
    
    def __init__(self, ensemble_path: str, csv_path: str):
        """DeepDBEstimator を初期化
        
        Args:
            ensemble_path: 学習済みアンサンブルファイルのパス
                例: "./imdb_ensemble/ensemble_join_3_budget_5_10000000.pkl"
            csv_path: CSV ファイルのパステンプレート（テーブル名の {} を含む）
                例: "./imdb_csv/{}.csv"
        """
        self.ensemble_path = ensemble_path
        self.csv_path = csv_path
        self._schema = None
        self._ensemble = None
        self._loaded = False
        
    def _load(self):
        """スキーマとアンサンブルを遅延ロード"""
        if self._loaded:
            return
            
        try:
            # DeepDB のモジュールをインポート (imdb-all-job を使用)
            from schemas.imdb.schema import gen_all_job_imdb_schema
            from ensemble_compilation.spn_ensemble import read_ensemble
            
            logger.info(f"Loading IMDB all-job schema from {self.csv_path}")
            self._schema = gen_all_job_imdb_schema(self.csv_path)
            
            logger.info(f"Loading ensemble from {self.ensemble_path}")
            self._ensemble = read_ensemble(self.ensemble_path, build_reverse_dict=True)
            
            self._loaded = True
            logger.info("DeepDB estimator loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load DeepDB estimator: {e}")
            raise
    
    @property
    def schema(self):
        """スキーマを取得（遅延ロード）"""
        self._load()
        return self._schema
    
    @property
    def ensemble(self):
        """アンサンブルを取得（遅延ロード）"""
        self._load()
        return self._ensemble
    
    def estimate_cardinality(self, sql: str) -> int:
        """SQL クエリからカーディナリティを推定
        
        Args:
            sql: SELECT 文（COUNT(*) を含む場合と含まない場合の両方に対応）
            
        Returns:
            推定行数（最小1）
            
        Raises:
            ValueError: SQL のパースに失敗した場合
        """
        if not sql or not isinstance(sql, str):
            return 0
            
        # CREATE MATERIALIZED VIEW の場合、SELECT 部分を抽出
        sql = self._extract_select_from_sql(sql)
        
        # SELECT の先頭を COUNT(*) に変換（必要な場合）
        sql = self._convert_to_count_query(sql)
        
        # エイリアス正規化: DeepDB は 'AS' キーワードをサポートしていないため削除
        sql = self._remove_as_keyword(sql)
        
        # 推移的結合を正規化（FK-FK → FK-PK-FK）
        sql = self._normalize_transitive_joins(sql)
        
        # 冗長な結合条件を削除
        sql = self._remove_redundant_joins(sql)
        
        # 結合順序をスキーマに合わせて正規化
        sql = self._normalize_join_order(sql)
        
        # sql = self._normalize_aliases(sql)
        
        try:
            # DeepDB のクエリパーサーを使用
            from evaluation.utils import parse_query
            from ensemble_compilation.graph_representation import QueryType
            
            query = parse_query(sql.strip(), self.schema)
            
            if query.query_type != QueryType.CARDINALITY:
                logger.warning(f"Query type is not CARDINALITY: {query.query_type}")
                # カーディナリティクエリに変換を試みる
                query.query_type = QueryType.CARDINALITY
            
            # アンサンブルでカーディナリティを推定
            # cardinality() は (expectation, true_card, predict_card, factor) を返す
            result = self.ensemble.cardinality(query)
            
            # predict_card を使用
            predicted_cardinality = result[2] if len(result) > 2 else result[0]
            
            # 最小1を保証
            return max(1, int(predicted_cardinality))
            
        except Exception as e:
            logger.error(f"Failed to estimate cardinality: {e}")
            logger.error(f"SQL: {sql[:200]}...")
            raise ValueError(f"Cardinality estimation failed: {e}")
    
    def estimate_with_details(self, sql: str) -> Tuple[int, float, dict]:
        """カーディナリティと詳細情報を推定
        
        Args:
            sql: SELECT 文
            
        Returns:
            (推定行数, 確信度, 詳細情報dict) のタプル
        """
        if not sql or not isinstance(sql, str):
            return (0, 0.0, {})
            
        sql = self._extract_select_from_sql(sql)
        sql = self._convert_to_count_query(sql)
        sql = self._remove_as_keyword(sql)
        
        try:
            from evaluation.utils import parse_query
            
            query = parse_query(sql.strip(), self.schema)
            result = self.ensemble.cardinality(query)
            
            # result = (expectation, true_card, predict_card, factor)
            expectation = result[0] if len(result) > 0 else 0
            predict_card = result[2] if len(result) > 2 else expectation
            factor = result[3] if len(result) > 3 else 1.0
            
            details = {
                "expectation": expectation,
                "predict_card": predict_card,
                "factor": factor,
                "tables": list(query.table_set),
                "join_conditions": list(query.relationship_set),
                "where_conditions": dict(query.table_where_condition_dict)
            }
            
            # 確信度は factor の逆数（高いほど確信度が低い）
            confidence = 1.0 / max(factor, 1.0)
            
            return (max(1, int(predict_card)), confidence, details)
            
        except Exception as e:
            logger.error(f"Failed to estimate with details: {e}")
            return (0, 0.0, {"error": str(e)})
    
    def _extract_select_from_sql(self, sql: str) -> str:
        """SQL から SELECT 部分を抽出
        
        CREATE MATERIALIZED VIEW ... AS SELECT ... の形式から
        SELECT 以降を抽出します。
        
        Args:
            sql: CREATE 文または SELECT 文
            
        Returns:
            SELECT 文
        """
        sql = sql.strip()
        
        # CREATE MATERIALIZED VIEW の場合
        match = re.search(
            r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', 
            sql, 
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return match.group(1).strip()
        
        # CREATE VIEW の場合（通常のビュー）
        match = re.search(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+\S+\s+AS\s+(.*)', 
            sql, 
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return match.group(1).strip()
        
        # すでに SELECT 文の場合はそのまま返す
        if sql.upper().strip().startswith('SELECT'):
            return sql
            
        # その他の場合はそのまま返す（エラーはパース時に発生）
        return sql
    
    def _convert_to_count_query(self, sql: str) -> str:
        """SELECT 文を COUNT(*) クエリに変換
        
        DeepDB のカーディナリティ推定は COUNT(*) クエリを期待するため、
        通常の SELECT 文を COUNT(*) 形式に変換します。
        
        Args:
            sql: SELECT 文
            
        Returns:
            COUNT(*) を含む SELECT 文
        """
        sql = sql.strip()
        
        # すでに COUNT(*) を含む場合はそのまま
        if re.search(r'\bCOUNT\s*\(\s*\*\s*\)', sql, re.IGNORECASE):
            return sql
        
        # SELECT ... FROM を SELECT COUNT(*) FROM に置換
        # 最初の FROM の前までを COUNT(*) に置換
        match = re.match(r'SELECT\s+(.*?)\s+FROM\s+', sql, re.IGNORECASE | re.DOTALL)
        if match:
            # SELECT 以降、FROM の直前までを COUNT(*) に置換
            return re.sub(
                r'SELECT\s+.*?\s+FROM\s+',
                'SELECT COUNT(*) FROM ',
                sql,
                count=1,
                flags=re.IGNORECASE | re.DOTALL
            )
        
        return sql
    
    def _normalize_aliases(self, sql: str) -> str:
        """テーブルエイリアスを実際のテーブル名に変換
        
        DeepDB のパーサーはエイリアスを認識しないため、
        FROM 句のエイリアス定義を抽出し、SQL 全体のエイリアスを
        テーブル名に置換します。
        
        例:
            movie_companies AS mc2 → mc2.* を movie_companies.* に置換
        
        Args:
            sql: SELECT 文
            
        Returns:
            エイリアスが正規化された SQL
        """
        sql = sql.strip()
        
        # FROM句を抽出（FROM ... WHERE または FROM ... ORDER BY または末尾まで）
        from_match = re.search(
            r'\bFROM\s+(.*?)(?:\s+WHERE\b|\s+ORDER\s+BY\b|\s+GROUP\s+BY\b|\s+HAVING\b|$)',
            sql,
            re.IGNORECASE | re.DOTALL
        )
        if not from_match:
            return sql
        
        from_clause = from_match.group(1)
        
        # テーブル名 AS エイリアス または テーブル名 エイリアス のパターンを抽出
        # パターン: table_name AS alias または table_name alias
        alias_pattern = re.compile(
            r'(\w+)\s+(?:AS\s+)?(\w+)(?:\s*[,)]|\s*$|\s+(?:ON|JOIN|LEFT|RIGHT|INNER|CROSS|FULL))',
            re.IGNORECASE
        )
        
        # エイリアス -> テーブル名のマッピングを構築
        alias_to_table = {}
        for match in alias_pattern.finditer(from_clause):
            table_name = match.group(1).lower()
            alias = match.group(2).lower()
            
            # 表名自体がキーワードでないことを確認
            keywords = {'on', 'join', 'left', 'right', 'inner', 'cross', 'full', 'as', 'where', 'and', 'or'}
            if alias not in keywords and table_name not in keywords:
                # エイリアスがテーブル名と異なる場合のみ追加
                if alias != table_name:
                    alias_to_table[alias] = table_name
        
        if not alias_to_table:
            return sql
        
        # エイリアス.カラム名 を テーブル名.カラム名 に置換
        result_sql = sql
        for alias, table_name in alias_to_table.items():
            # alias. を table_name. に置換（大文字小文字を無視）
            pattern = re.compile(r'\b' + re.escape(alias) + r'\.', re.IGNORECASE)
            result_sql = pattern.sub(table_name + '.', result_sql)
            
            # FROM 句の ... AS alias を ... AS table_name に置換
            pattern = re.compile(
                r'\b' + re.escape(alias) + r'\b(?!\s*\.)',  # エイリアス単体（ドットが続かない）
                re.IGNORECASE
            )
            # ただし FROM 句内のエイリアス定義は残す（AS の後のエイリアスは置換しない）
            # これは複雑なので、カラム参照の置換のみで十分
            return result_sql
        
    def _remove_as_keyword(self, sql: str) -> str:
        """FROM 句から AS キーワードを削除（DeepDB のパースエラー回避用）
        
        DeepDB の内部で使用している sqlparse の処理において、
        'table AS alias' 形式（トークン長5）だとうまく認識されず、
        'table alias' 形式（トークン長3）である必要があるため、
        FROM 句内の ' AS ' を削除します。
        """
        # FROM 句を抽出（単純化のため、最初の FROM から WHERE/GROUP/ORDER の前まで）
        # サブクエリなどは考慮していないが、今回のワークロードでは問題ないはず
        match = re.search(r'(\bFROM\s+)(.*?)(\s+(?:WHERE|GROUP\s+BY|ORDER\s+BY|HAVING)\b|$)', sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return sql
            
        prefix = sql[:match.start(2)]
        from_content = match.group(2)
        suffix = sql[match.end(2):]
        
        # AS を削除 ("table AS alias" -> "table alias")
        # 前後にスペースがある AS のみを置換
        new_from = re.sub(r'\s+AS\s+', ' ', from_content, flags=re.IGNORECASE)
        
        return prefix + new_from + suffix
    
    def _remove_redundant_joins(self, sql: str) -> str:
        """冗長な結合条件を削除
        
        同じテーブル間の結合条件が複数回出現する場合、重複を削除します。
        例: WHERE a.id = b.id AND b.id = a.id → WHERE a.id = b.id
        """
        # WHERE 句を抽出
        where_match = re.search(r'(\bWHERE\s+)(.*?)(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+HAVING|$)', 
                                sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return sql
        
        where_prefix = sql[:where_match.end(1)]
        where_content = where_match.group(2)
        where_suffix = sql[where_match.end(2):]
        
        # 結合条件を抽出 (table.col = table.col 形式)
        join_pattern = re.compile(r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)', re.IGNORECASE)
        
        seen_joins = set()
        conditions = []
        
        # AND で分割
        parts = re.split(r'\s+AND\s+', where_content, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            match = join_pattern.search(part)
            if match:
                # 結合条件を正規化（アルファベット順）
                left = f"{match.group(1).lower()}.{match.group(2).lower()}"
                right = f"{match.group(3).lower()}.{match.group(4).lower()}"
                normalized = tuple(sorted([left, right]))
                
                if normalized not in seen_joins:
                    seen_joins.add(normalized)
                    conditions.append(part)
            else:
                # 結合条件以外はそのまま追加
                conditions.append(part)
        
        new_where = ' AND '.join(conditions)
        return where_prefix + new_where + where_suffix
    
    def _normalize_join_order(self, sql: str) -> str:
        """結合条件の順序を正規化（FK → PK）
        
        DeepDB の relationship_dictionary に登録されている形式に合わせて
        結合条件の左右を入れ替えます。
        """
        # スキーマから FK → PK の順序を取得
        fk_pk_order = {}
        for rel_key in self.schema.relationship_dictionary.keys():
            # rel_key: "table1.col1 = table2.col2"
            parts = rel_key.split(' = ')
            if len(parts) == 2:
                fk_pk_order[(parts[0].lower(), parts[1].lower())] = rel_key
                # 逆順も登録（検索用）
                fk_pk_order[(parts[1].lower(), parts[0].lower())] = rel_key
        
        # WHERE 句を抽出
        where_match = re.search(r'(\bWHERE\s+)(.*?)(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+HAVING|$)', 
                                sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return sql
        
        where_prefix = sql[:where_match.end(1)]
        where_content = where_match.group(2)
        where_suffix = sql[where_match.end(2):]
        
        # 結合条件を正規化
        def normalize_join(match):
            left = f"{match.group(1).lower()}.{match.group(2).lower()}"
            right = f"{match.group(3).lower()}.{match.group(4).lower()}"
            
            # スキーマに登録されている形式を探す
            if (left, right) in fk_pk_order:
                # 現在の順序が正しい
                return match.group(0)
            elif (right, left) in fk_pk_order:
                # 順序を入れ替え
                return f"{match.group(3)}.{match.group(4)} = {match.group(1)}.{match.group(2)}"
            else:
                # スキーマにない場合はそのまま
                return match.group(0)
        
        join_pattern = re.compile(r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)', re.IGNORECASE)
        new_where = join_pattern.sub(normalize_join, where_content)
        
        return where_prefix + new_where + where_suffix
    
    def _normalize_transitive_joins(self, sql: str) -> str:
        """推移的結合を正規化（FK-FK → FK-PK-FK）
        
        DeepDB は title.id や name.id をハブとした結合のみを学習しているため、
        直接的な FK-FK 結合（例: ci.movie_id = mk.movie_id）を
        ハブテーブル経由（例: ci.movie_id = t.id AND mk.movie_id = t.id）に変換します。
        
        ハブテーブルがFROM句にない場合は自動的に追加します。
        """
        # 推移的結合のパターン定義
        # {共通カラム: (ハブテーブル, ハブカラム, デフォルトエイリアス)}
        hub_definitions = {
            'movie_id': ('title', 'id', 't'),
            'person_id': ('name', 'id', 'n'),
        }
        
        # FROM 句を抽出
        from_match = re.search(r'(\bFROM\s+)(.*?)(\s+WHERE\b|\s+GROUP\s+BY\b|\s+ORDER\s+BY\b|$)', 
                               sql, re.IGNORECASE | re.DOTALL)
        if not from_match:
            return sql
        
        from_prefix = sql[:from_match.start(2)]
        from_content = from_match.group(2)
        from_suffix_start = from_match.end(2)
        
        # テーブルエイリアスを解析
        alias_to_table = {}
        table_to_alias = {}
        table_pattern = re.compile(r'(\w+)(?:\s+(\w+))?(?:\s*,|\s*$)', re.IGNORECASE)
        for match in table_pattern.finditer(from_content):
            table_name = match.group(1).lower()
            alias = match.group(2).lower() if match.group(2) else table_name
            alias_to_table[alias] = table_name
            table_to_alias[table_name] = alias
        
        # WHERE 句を抽出
        where_match = re.search(r'(\bWHERE\s+)(.*?)(\s+GROUP\s+BY|\s+ORDER\s+BY|\s+HAVING|$)', 
                                sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return sql
        
        where_content = where_match.group(2)
        
        # 推移的結合を検出
        transitive_pattern = re.compile(
            r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)', 
            re.IGNORECASE
        )
        
        # 必要なハブテーブルを収集
        needed_hubs = set()
        for match in transitive_pattern.finditer(where_content):
            alias1 = match.group(1).lower()
            col1 = match.group(2).lower()
            alias2 = match.group(3).lower()
            col2 = match.group(4).lower()
            
            if col1 == col2 and col1 in hub_definitions:
                hub_table, _, _ = hub_definitions[col1]
                table1 = alias_to_table.get(alias1, alias1)
                table2 = alias_to_table.get(alias2, alias2)
                
                # 両方がハブテーブルでない場合
                if table1 != hub_table and table2 != hub_table:
                    # ハブテーブルがFROM句にあるか確認
                    if hub_table not in table_to_alias:
                        needed_hubs.add(col1)  # カラム名でハブを識別
        
        # 必要なハブテーブルをFROM句に追加
        new_from_content = from_content
        for col_name in needed_hubs:
            hub_table, hub_col, default_alias = hub_definitions[col_name]
            # 既存のテーブルと重複しないエイリアスを選択
            alias = default_alias
            counter = 1
            while alias in alias_to_table:
                alias = f"{default_alias}{counter}"
                counter += 1
            
            # FROM句に追加
            new_from_content = new_from_content.rstrip().rstrip(',') + f" , {hub_table} {alias}"
            alias_to_table[alias] = hub_table
            table_to_alias[hub_table] = alias
        
        # ハブテーブルのエイリアスを見つける関数
        def find_hub_alias(hub_table):
            return table_to_alias.get(hub_table)
        
        # 推移的結合を変換
        def replace_transitive(match):
            alias1 = match.group(1).lower()
            col1 = match.group(2).lower()
            alias2 = match.group(3).lower()
            col2 = match.group(4).lower()
            
            # 同じカラム名でない場合や、ハブ定義にない場合はそのまま
            if col1 != col2 or col1 not in hub_definitions:
                return match.group(0)
            
            hub_table, hub_col, _ = hub_definitions[col1]
            
            # 両方がハブテーブルでない場合のみ変換
            table1 = alias_to_table.get(alias1, alias1)
            table2 = alias_to_table.get(alias2, alias2)
            
            if table1 == hub_table or table2 == hub_table:
                # 一方がハブテーブルなら通常の結合なのでそのまま
                return match.group(0)
            
            # ハブテーブルのエイリアスを取得
            hub_alias = find_hub_alias(hub_table)
            
            if not hub_alias:
                # これは起きないはずだが、念のため
                return match.group(0)
            
            # 変換: alias1.col = alias2.col → alias1.col = hub.id AND alias2.col = hub.id
            return f"{alias1}.{col1} = {hub_alias}.{hub_col} AND {alias2}.{col2} = {hub_alias}.{hub_col}"
        
        new_where = transitive_pattern.sub(replace_transitive, where_content)
        
        # SQLを再構築
        result = (sql[:from_match.start(2)] + 
                  new_from_content + 
                  sql[from_match.end(2):where_match.start(2)] + 
                  new_where + 
                  sql[where_match.end(2):])
        
        return result
    
    def get_supported_tables(self) -> list:
        """サポートされているテーブル名のリストを取得"""
        self._load()
        return [table.table_name for table in self._schema.tables]
    
    def is_query_supported(self, sql: str) -> Tuple[bool, str]:
        """クエリがサポートされているかをチェック
        
        Args:
            sql: チェックする SQL
            
        Returns:
            (サポート状況, 理由やエラーメッセージ) のタプル
        """
        try:
            sql = self._extract_select_from_sql(sql)
            sql = self._convert_to_count_query(sql)
            
            from evaluation.utils import parse_query
            query = parse_query(sql.strip(), self.schema)
            
            # テーブルがスキーマに含まれているかチェック
            supported_tables = set(self.get_supported_tables())
            unknown_tables = query.table_set - supported_tables
            
            if unknown_tables:
                return (False, f"Unknown tables: {unknown_tables}")
            
            return (True, "Query is supported")
            
        except Exception as e:
            return (False, str(e))


# テスト用のメイン関数
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepDB Cardinality Estimator Test")
    parser.add_argument(
        "--ensemble-path",
        type=str,
        default="../../deepdb_full/deepdb/run/imdb-all-job/spn_ensembles/ensemble_join_3_budget_5_10000000.pkl",
        help="Path to the trained ensemble file"
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default="../../deepdb_full/deepdb/csv/{}.csv",
        help="Path template for CSV files"
    )
    parser.add_argument(
        "--sql",
        type=str,
        default="SELECT COUNT(*) FROM title t WHERE t.production_year > 2000",
        help="SQL query to estimate"
    )
    
    args = parser.parse_args()
    
    # ロギング設定
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("DeepDB Cardinality Estimator Test")
    print("="*60)
    
    try:
        estimator = DeepDBEstimator(args.ensemble_path, args.csv_path)
        
        print(f"\nSupported tables: {estimator.get_supported_tables()}")
        
        print(f"\nSQL: {args.sql}")
        
        is_supported, message = estimator.is_query_supported(args.sql)
        print(f"Supported: {is_supported} - {message}")
        
        if is_supported:
            rows, confidence, details = estimator.estimate_with_details(args.sql)
            print(f"\nEstimated rows: {rows}")
            print(f"Confidence: {confidence:.4f}")
            print(f"Details: {details}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
