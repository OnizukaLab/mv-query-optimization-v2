# Phase 6: クエリ書き換えモジュールのリファクタリング

## 🎯 目的

`query_rewrite_beta.py` を新しい構造に移行し、責務を明確に分離します。

## ⏱️ 推定時間: 5-7時間

## 📋 前提条件

- [x] Phase 0-5 が完了
- [x] `src/core/query_manager.py` が動作
- [x] `src/core/query_parser.py` が動作
- [x] `src/database/mv_manager.py` が動作

## 🔧 実行手順

### Step 1: SQLパーサーヘルパーの作成 (1-2時間)

#### 1.1 ファイル作成

```bash
touch src/rewrite/sql_parser.py
touch tests/unit/test_sql_parser.py
```

#### 1.2 実装

```python
# src/rewrite/sql_parser.py
"""SQL解析ユーティリティ"""
import re
import sqlparse
from typing import List, Tuple, Dict, Optional


class SQLParser:
    """SQLクエリの解析を行うヘルパークラス"""
    
    def __init__(self):
        """初期化"""
        pass
    
    def extract_from_clause(self, sql: str) -> str:
        """FROM句を抽出
        
        Args:
            sql: SQL文字列
            
        Returns:
            FROM句の文字列
        """
        pattern = r'FROM\s+(.+?)(?:WHERE|GROUP BY|ORDER BY|LIMIT|$)'
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def extract_where_clause(self, sql: str) -> str:
        """WHERE句を抽出
        
        Args:
            sql: SQL文字列
            
        Returns:
            WHERE句の文字列
        """
        pattern = r'WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)'
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def extract_tables(self, from_clause: str) -> List[Tuple[str, str]]:
        """FROM句からテーブルとエイリアスを抽出
        
        Args:
            from_clause: FROM句の文字列
            
        Returns:
            (テーブル名, エイリアス) のリスト
        """
        tables = []
        # カンマで分割
        parts = from_clause.split(',')
        
        for part in parts:
            part = part.strip()
            # JOIN句を含む場合
            if 'JOIN' in part.upper():
                # 複数のJOINを処理
                join_parts = re.split(r'\s+(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\s+', part, flags=re.IGNORECASE)
                for jp in join_parts:
                    table_alias = self._extract_table_alias(jp)
                    if table_alias:
                        tables.append(table_alias)
            else:
                table_alias = self._extract_table_alias(part)
                if table_alias:
                    tables.append(table_alias)
        
        return tables
    
    def _extract_table_alias(self, part: str) -> Optional[Tuple[str, str]]:
        """テーブル名とエイリアスを抽出
        
        Args:
            part: SQL断片
            
        Returns:
            (テーブル名, エイリアス) または None
        """
        # ON句を削除
        part = re.sub(r'\s+ON\s+.+$', '', part, flags=re.IGNORECASE)
        part = part.strip()
        
        # "table AS alias" または "table alias" の形式
        match = re.match(r'(\w+)(?:\s+(?:AS\s+)?(\w+))?', part, re.IGNORECASE)
        if match:
            table = match.group(1)
            alias = match.group(2) if match.group(2) else table
            return (table, alias)
        return None
    
    def parse_condition(self, condition: str) -> Dict[str, List[str]]:
        """条件式を解析してカラムごとに分類
        
        Args:
            condition: WHERE句の条件式
            
        Returns:
            {alias.column: [条件1, 条件2, ...]}
        """
        conditions = {}
        
        # AND/ORで分割
        parts = re.split(r'\s+(?:AND|OR)\s+', condition, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            # alias.column を抽出
            match = re.match(r'(\w+)\.(\w+)\s*([<>=!]+|LIKE|IN)\s*(.+)', part, re.IGNORECASE)
            if match:
                alias = match.group(1)
                column = match.group(2)
                operator = match.group(3)
                value = match.group(4)
                
                key = f"{alias}.{column}"
                if key not in conditions:
                    conditions[key] = []
                conditions[key].append(f"{column} {operator} {value}")
        
        return conditions
    
    def reconstruct_query(
        self,
        select_clause: str,
        from_clause: str,
        where_clause: str = "",
        group_by: str = "",
        order_by: str = "",
        limit: str = ""
    ) -> str:
        """クエリを再構築
        
        Args:
            select_clause: SELECT句
            from_clause: FROM句
            where_clause: WHERE句
            group_by: GROUP BY句
            order_by: ORDER BY句
            limit: LIMIT句
            
        Returns:
            再構築されたSQL
        """
        sql = f"SELECT {select_clause}\nFROM {from_clause}"
        
        if where_clause:
            sql += f"\nWHERE {where_clause}"
        if group_by:
            sql += f"\nGROUP BY {group_by}"
        if order_by:
            sql += f"\nORDER BY {order_by}"
        if limit:
            sql += f"\nLIMIT {limit}"
        
        return sql
```

#### 1.3 テスト作成

```python
# tests/unit/test_sql_parser.py
"""SQLParserのテスト"""
import pytest
from src.rewrite.sql_parser import SQLParser


class TestSQLParser:
    """SQLParserクラスのテスト"""
    
    @pytest.fixture
    def parser(self):
        """パーサーのフィクスチャ"""
        return SQLParser()
    
    def test_extract_from_clause(self, parser):
        """FROM句の抽出"""
        sql = "SELECT * FROM users u WHERE u.age > 20"
        from_clause = parser.extract_from_clause(sql)
        assert "users u" in from_clause
    
    def test_extract_where_clause(self, parser):
        """WHERE句の抽出"""
        sql = "SELECT * FROM users WHERE age > 20 AND name = 'test'"
        where = parser.extract_where_clause(sql)
        assert "age > 20" in where
        assert "name = 'test'" in where
    
    def test_extract_tables_simple(self, parser):
        """単純なFROM句からテーブル抽出"""
        from_clause = "users u, orders o"
        tables = parser.extract_tables(from_clause)
        assert len(tables) == 2
        assert ("users", "u") in tables
        assert ("orders", "o") in tables
    
    def test_extract_tables_with_join(self, parser):
        """JOIN句を含むFROM句"""
        from_clause = "users u INNER JOIN orders o ON u.id = o.user_id"
        tables = parser.extract_tables(from_clause)
        assert len(tables) == 2
    
    def test_parse_condition(self, parser):
        """条件式の解析"""
        condition = "u.age > 20 AND u.name = 'test' AND o.total > 1000"
        conditions = parser.parse_condition(condition)
        assert "u.age" in conditions
        assert "u.name" in conditions
        assert "o.total" in conditions
    
    def test_reconstruct_query(self, parser):
        """クエリの再構築"""
        sql = parser.reconstruct_query(
            select_clause="u.name, COUNT(*)",
            from_clause="users u",
            where_clause="u.age > 20",
            group_by="u.name"
        )
        assert "SELECT u.name, COUNT(*)" in sql
        assert "FROM users u" in sql
        assert "WHERE u.age > 20" in sql
        assert "GROUP BY u.name" in sql
```

### Step 2: MV生成SQLの作成 (1-2時間)

#### 2.1 ファイル作成

```bash
touch src/rewrite/mv_generator.py
touch tests/unit/test_mv_generator.py
```

#### 2.2 実装

```python
# src/rewrite/mv_generator.py
"""マテリアライズドビュー生成SQL作成"""
from typing import List, Dict
from pathlib import Path

from src.core.models import LeafNode, NonLeafNode, MaterializedView
from src.rewrite.sql_parser import SQLParser
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class MVGenerator:
    """マテリアライズドビュー生成SQLの作成"""
    
    # IMDBスキーマ情報（将来的には外部ファイル化）
    TABLE_COLUMNS = {
        "aka_name": ["id", "person_id", "name", "imdb_index", "name_pcode_cf", 
                     "name_pcode_nf", "surname_pcode", "md5sum"],
        "aka_title": ["id", "movie_id", "title", "imdb_index", "kind_id", 
                      "production_year", "phonetic_code", "episode_of_id", 
                      "season_nr", "episode_nr", "note", "md5sum"],
        "cast_info": ["id", "person_id", "movie_id", "person_role_id", 
                      "note", "nr_order", "role_id"],
        # ... 他のテーブル
    }
    
    def __init__(self):
        """初期化"""
        self.sql_parser = SQLParser()
    
    def generate_create_sql(
        self,
        mv: MaterializedView,
        node: LeafNode | NonLeafNode
    ) -> str:
        """MV作成SQLを生成
        
        Args:
            mv: マテリアライズドビュー情報
            node: クエリノード
            
        Returns:
            CREATE MATERIALIZED VIEW 文
        """
        if isinstance(node, LeafNode):
            return self._generate_leaf_mv(mv, node)
        else:
            return self._generate_nonleaf_mv(mv, node)
    
    def _generate_leaf_mv(self, mv: MaterializedView, node: LeafNode) -> str:
        """リーフノード用MV生成SQL
        
        Args:
            mv: MV情報
            node: リーフノード
            
        Returns:
            CREATE文
        """
        table = node.table_name
        alias = node.alias
        
        # カラムリスト取得
        columns = self.TABLE_COLUMNS.get(table, [])
        if not columns:
            logger.warning(f"Unknown table: {table}")
            columns = ["*"]
        
        # SELECT句作成
        if columns == ["*"]:
            select_clause = "*"
        else:
            select_clause = ", ".join([f"{alias}.{col}" for col in columns])
        
        # FROM句
        from_clause = f"{table} {alias}"
        
        # WHERE句
        where_clause = node.filter_condition if node.filter_condition else ""
        
        # SQL組み立て
        sql = f"CREATE MATERIALIZED VIEW {mv.view_id} AS\n"
        sql += self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=from_clause,
            where_clause=where_clause
        )
        sql += ";"
        
        return sql
    
    def _generate_nonleaf_mv(self, mv: MaterializedView, node: NonLeafNode) -> str:
        """非リーフノード用MV生成SQL
        
        Args:
            mv: MV情報
            node: 非リーフノード
            
        Returns:
            CREATE文
        """
        # 非リーフノードの場合は既存のSQLをそのまま使用
        # または child_ids から再構築
        sql = f"CREATE MATERIALIZED VIEW {mv.view_id} AS\n"
        sql += "-- TODO: 非リーフノード用の実装\n"
        sql += ";"
        
        logger.warning(f"Non-leaf MV generation not fully implemented: {mv.view_id}")
        return sql
    
    def save_create_sqls(
        self,
        mvs: List[MaterializedView],
        output_dir: Path
    ) -> None:
        """MV作成SQLをファイルに保存
        
        Args:
            mvs: MVリスト
            output_dir: 出力ディレクトリ
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for mv in mvs:
            sql_file = output_dir / f"{mv.view_id}.sql"
            with open(sql_file, 'w') as f:
                f.write(mv.create_sql)
            
            logger.info(f"Saved MV creation SQL: {sql_file}")
```

#### 2.3 テスト作成

```python
# tests/unit/test_mv_generator.py
"""MVGeneratorのテスト"""
import pytest
from pathlib import Path

from src.rewrite.mv_generator import MVGenerator
from src.core.models import LeafNode, MaterializedView


class TestMVGenerator:
    """MVGeneratorクラスのテスト"""
    
    @pytest.fixture
    def generator(self):
        """ジェネレーターのフィクスチャ"""
        return MVGenerator()
    
    def test_generate_leaf_mv(self, generator):
        """リーフノード用MV生成"""
        node = LeafNode(
            node_id="1",
            node_type="leaf",
            total_cost=100.0,
            size=1000,
            width=10,
            operator="Seq Scan",
            table_name="users",
            alias="u",
            filter_condition="u.age > 20"
        )
        
        mv = MaterializedView(
            view_id="mv_test_1",
            node_id="1",
            create_sql="",
            size=1000,
            maintenance_cost=10.0
        )
        
        sql = generator.generate_create_sql(mv, node)
        
        assert "CREATE MATERIALIZED VIEW mv_test_1" in sql
        assert "FROM users u" in sql
        assert "WHERE u.age > 20" in sql
    
    def test_save_create_sqls(self, generator, tmp_path):
        """SQL保存"""
        mv = MaterializedView(
            view_id="mv_test_1",
            node_id="1",
            create_sql="CREATE MATERIALIZED VIEW mv_test_1 AS SELECT * FROM users;",
            size=1000,
            maintenance_cost=10.0
        )
        
        generator.save_create_sqls([mv], tmp_path)
        
        sql_file = tmp_path / "mv_test_1.sql"
        assert sql_file.exists()
        assert "CREATE MATERIALIZED VIEW" in sql_file.read_text()
```

### Step 3: クエリ書き換えメインロジック (2-3時間)

#### 3.1 ファイル作成

```bash
touch src/rewrite/query_rewriter.py
touch tests/unit/test_query_rewriter.py
```

#### 3.2 実装

```python
# src/rewrite/query_rewriter.py
"""クエリ書き換えロジック"""
from typing import List, Dict
from pathlib import Path

from src.core.query_manager import QueryManager
from src.core.models import MaterializedView, QueryPlan
from src.rewrite.sql_parser import SQLParser
from src.rewrite.mv_generator import MVGenerator
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class QueryRewriter:
    """クエリ書き換え管理"""
    
    def __init__(self, query_manager: QueryManager):
        """初期化
        
        Args:
            query_manager: クエリ管理オブジェクト
        """
        self.qm = query_manager
        self.sql_parser = SQLParser()
        self.mv_generator = MVGenerator()
    
    def rewrite_workload(
        self,
        selected_mvs: Dict[int, List[MaterializedView]],
        output_dir: Path
    ) -> Dict[int, str]:
        """ワークロード全体を書き換え
        
        Args:
            selected_mvs: {query_id: [MVリスト]}
            output_dir: 出力ディレクトリ
            
        Returns:
            {query_id: 書き換え後SQL}
        """
        rewritten_queries = {}
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for query_id, mvs in selected_mvs.items():
            logger.info(f"Rewriting query {query_id} with {len(mvs)} MVs")
            
            # 元のクエリ取得
            original_sql = self.qm.get_query_sql(query_id)
            
            # MVを使って書き換え
            rewritten_sql = self.rewrite_query(query_id, mvs, original_sql)
            rewritten_queries[query_id] = rewritten_sql
            
            # ファイルに保存
            sql_file = output_dir / f"query_{query_id}.sql"
            with open(sql_file, 'w') as f:
                f.write(rewritten_sql)
            
            logger.info(f"Saved rewritten query: {sql_file}")
        
        return rewritten_queries
    
    def rewrite_query(
        self,
        query_id: int,
        mvs: List[MaterializedView],
        original_sql: str
    ) -> str:
        """クエリを書き換え
        
        Args:
            query_id: クエリID
            mvs: 使用するMVリスト
            original_sql: 元のSQL
            
        Returns:
            書き換え後のSQL
        """
        if not mvs:
            return original_sql
        
        # MVをnode_idでマッピング
        mv_map = {mv.node_id: mv for mv in mvs}
        
        # クエリプラン取得
        query_plan = self.qm.get_query_plan(query_id)
        
        # ノードをMVで置換
        rewritten_sql = self._replace_nodes_with_mvs(
            original_sql,
            query_plan,
            mv_map
        )
        
        return rewritten_sql
    
    def _replace_nodes_with_mvs(
        self,
        sql: str,
        plan: QueryPlan,
        mv_map: Dict[str, MaterializedView]
    ) -> str:
        """ノードをMVで置換
        
        Args:
            sql: 元のSQL
            plan: クエリプラン
            mv_map: {node_id: MV}
            
        Returns:
            書き換え後SQL
        """
        # FROM句を解析
        from_clause = self.sql_parser.extract_from_clause(sql)
        where_clause = self.sql_parser.extract_where_clause(sql)
        
        # テーブルリスト取得
        tables = self.sql_parser.extract_tables(from_clause)
        
        # リーフノードを置換
        new_from_parts = []
        for table, alias in tables:
            # このテーブルに対応するMVがあるか確認
            replaced = False
            for node in plan.leaf_nodes:
                if node.table_name == table and node.node_id in mv_map:
                    mv = mv_map[node.node_id]
                    new_from_parts.append(f"{mv.view_id} {alias}")
                    replaced = True
                    logger.info(f"Replaced {table} with {mv.view_id}")
                    break
            
            if not replaced:
                new_from_parts.append(f"{table} {alias}")
        
        # 新しいFROM句
        new_from = ", ".join(new_from_parts)
        
        # SQLを再構築
        # SELECT句は元のまま
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        select_clause = select_match.group(1) if select_match else "*"
        
        rewritten_sql = self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=new_from,
            where_clause=where_clause
        )
        
        return rewritten_sql
    
    def generate_mv_creation_scripts(
        self,
        mvs: List[MaterializedView],
        output_dir: Path
    ) -> None:
        """MV作成スクリプトを生成
        
        Args:
            mvs: MVリスト
            output_dir: 出力ディレクトリ
        """
        self.mv_generator.save_create_sqls(mvs, output_dir)
        logger.info(f"Generated {len(mvs)} MV creation scripts")
```

#### 3.3 テスト作成

```python
# tests/unit/test_query_rewriter.py
"""QueryRewriterのテスト"""
import pytest
from pathlib import Path

from src.rewrite.query_rewriter import QueryRewriter
from src.core.query_manager import QueryManager
from src.core.models import MaterializedView, QueryPlan, LeafNode


class TestQueryRewriter:
    """QueryRewriterクラスのテスト"""
    
    @pytest.fixture
    def query_manager(self, tmp_path):
        """QueryManagerのフィクスチャ"""
        # テスト用の設定
        config = {
            'database': {
                'name': 'test_db'
            },
            'paths': {
                'output_base': str(tmp_path)
            }
        }
        return QueryManager(config)
    
    @pytest.fixture
    def rewriter(self, query_manager):
        """Rewriterのフィクスチャ"""
        return QueryRewriter(query_manager)
    
    def test_rewrite_query_with_mv(self, rewriter):
        """MVを使ったクエリ書き換え"""
        original_sql = "SELECT u.name FROM users u WHERE u.age > 20"
        
        mv = MaterializedView(
            view_id="mv_users_1",
            node_id="1",
            create_sql="",
            size=1000,
            maintenance_cost=10.0
        )
        
        # TODO: 実際の書き換えロジックのテスト
        # 現在は基本構造のみ
        assert rewriter is not None
```

### Step 4: 統合と検証 (1時間)

#### 4.1 統合テスト

```bash
touch tests/integration/test_query_rewriting.py
```

```python
# tests/integration/test_query_rewriting.py
"""クエリ書き換えの統合テスト"""
import pytest
from pathlib import Path

from src.rewrite.query_rewriter import QueryRewriter
from src.core.query_manager import QueryManager


@pytest.mark.integration
class TestQueryRewritingIntegration:
    """クエリ書き換えの統合テスト"""
    
    def test_full_rewrite_flow(self, tmp_path):
        """完全な書き換えフロー"""
        # 設定
        config = {
            'database': {'name': 'test_db'},
            'paths': {'output_base': str(tmp_path)}
        }
        
        qm = QueryManager(config)
        rewriter = QueryRewriter(qm)
        
        # TODO: 実際のワークロードでテスト
        assert rewriter is not None
```

#### 4.2 既存コードとの互換性確認

```bash
# 既存のquery_rewrite_beta.pyと比較
python -c "
from src.rewrite.query_rewriter import QueryRewriter
print('New QueryRewriter loaded successfully')
"
```

## ✅ 検証チェックリスト

- [ ] `src/rewrite/sql_parser.py` 実装完了
- [ ] `src/rewrite/mv_generator.py` 実装完了
- [ ] `src/rewrite/query_rewriter.py` 実装完了
- [ ] ユニットテストが全て通る
- [ ] 統合テストが通る
- [ ] 既存の `query_rewrite_beta.py` との互換性確認

## 📝 コミット

```bash
git add src/rewrite/ tests/unit/test_sql_parser.py tests/unit/test_mv_generator.py tests/unit/test_query_rewriter.py tests/integration/test_query_rewriting.py
git commit -m "Phase 6: クエリ書き換えモジュールのリファクタリング

- SQLパーサーヘルパーの実装
- MV生成SQL作成の実装
- クエリ書き換えメインロジックの実装
- ユニットテストと統合テストの追加"
```

## 🚨 トラブルシューティング

### テストが失敗する場合

```bash
# 詳細なエラー表示
pytest tests/unit/test_sql_parser.py -v

# 特定のテストのみ実行
pytest tests/unit/test_sql_parser.py::TestSQLParser::test_extract_from_clause -v
```

### インポートエラーが出る場合

```bash
# パッケージの再インストール
pip install -e .

# PYTHONPATHの確認
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

---

**所要時間**: 5-7時間  
**難易度**: ⭐⭐⭐⭐ (Very Hard)