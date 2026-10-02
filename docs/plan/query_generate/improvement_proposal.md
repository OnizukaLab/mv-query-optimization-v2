# MV作成SQL生成とクエリ書き換えロジック - 改善提案

## 📋 エグゼクティブサマリー

現在の実装では、非リーフMVのJOIN条件が不正確で、クエリ書き換え時に63%のMVが使用できない状態です。本提案では、EXPLAIN JSONから完全な情報を抽出し、堅牢なSQLパーサーと高度なクエリマッチングアルゴリズムを導入することで、この問題を根本的に解決します。

**優先度順の改善項目:**
1. 🔴 **SQLパーサーの堅牢性向上** (最優先)
2. 🟠 **データ構造の再設計とEXPLAIN JSON情報の完全活用**
3. 🟡 **非リーフMV SQL生成の正確性向上**
4. 🟢 **高度なクエリ書き換えロジック実装**
5. 🔵 **スキーマ情報の動的取得**

---

## 1. データ構造の拡張設計

### 1.1 非リーフノード情報の拡張

**現状の問題:**
```python
# 現在: 情報が大幅に失われている
non_leaf_nodes_map_r[node_id] = tuple(sorted([child1, child2, ...]))
# 例: ('leaf_4', 'leaf_7', 'leaf_11')
```

**改善後:**
```python
@dataclass
class NonLeafNodeInfo:
    """非リーフノード詳細情報"""
    node_id: str
    operator: str  # "Hash Join", "Merge Join", "Nested Loop", etc.
    join_type: str  # "Inner", "Left", "Right", "Full", "Semi", "Anti"
    children: list[str]  # 順序を保持（ソートしない）
    join_conditions: list[JoinCondition]  # JOIN条件の詳細
    filters: list[str]  # WHERE句フィルタ
    output_columns: Optional[list[ColumnRef]]  # 出力カラム情報
    cost: float
    rows: int
    width: int
    
@dataclass
class JoinCondition:
    """JOIN条件の詳細"""
    left_table: str
    left_column: str
    operator: str  # "=", "<", ">", etc.
    right_table: str
    right_column: str
    condition_type: str  # "Hash Cond", "Merge Cond", "Join Filter", "Index Cond"
    original_text: str  # 元の条件テキスト (例: "t.id = ci.movie_id")
    
@dataclass  
class ColumnRef:
    """カラム参照情報"""
    table: str
    column: str
    alias: Optional[str] = None
```

### 1.2 QueryManagerの拡張

```python
class QueryManager:
    def __init__(self):
        # 既存のマッピング
        self.leaf_nodes_map: dict[tuple[str, str, str, str], str] = {}
        self.leaf_nodes_map_r: dict[str, tuple[str, str, str, str]] = {}
        
        # 拡張: 非リーフノード詳細情報
        self.non_leaf_nodes_info: dict[str, NonLeafNodeInfo] = {}
        
        # 拡張: JOIN条件の詳細保存
        self.join_conditions: dict[str, list[JoinCondition]] = {}
        
        # 拡張: オペレータ情報
        self.node_operators: dict[str, str] = {}
        
        # 拡張: テーブル間の結合関係グラフ
        self.join_graph: dict[str, list[tuple[str, JoinCondition]]] = {}
        
    def process_non_leaf_node_v2(
        self,
        operator: str,
        join_type: str,
        child_node_ids: list[str],
        join_conditions: list[JoinCondition],
        filters: list[str],
        position: list[int],
        total_cost: float,
        rows: int,
        width: int,
        output_columns: Optional[list[ColumnRef]] = None
    ) -> str:
        """拡張版: 非リーフノード処理（詳細情報を保持）"""
        # 新しいキー: 順序を保持し、JOIN条件もハッシュに含める
        # これにより、異なるJOIN条件の同じテーブル組み合わせを区別できる
        join_cond_hash = hash(tuple(sorted([jc.original_text for jc in join_conditions])))
        key = (tuple(child_node_ids), join_cond_hash)  # 順序保持、条件も考慮
        
        if key in self.non_leaf_nodes_map:
            node_id = self.non_leaf_nodes_map[key]
        else:
            node_id = self._generate_unique_id("non_leaf")
            self.non_leaf_nodes_map[key] = node_id
            
            # 詳細情報を保存
            self.non_leaf_nodes_info[node_id] = NonLeafNodeInfo(
                node_id=node_id,
                operator=operator,
                join_type=join_type,
                children=child_node_ids,  # 順序保持
                join_conditions=join_conditions,
                filters=filters,
                output_columns=output_columns,
                cost=total_cost,
                rows=rows,
                width=width
            )
        
        # 以下、既存のロジック...
        return node_id
```

---

## 2. QueryParserの拡張: EXPLAIN JSON完全解析

### 2.1 JOIN条件の抽出ロジック

```python
def extract_join_conditions(self, node: dict[str, Any]) -> list[JoinCondition]:
    """EXPLAIN JSONからJOIN条件を抽出"""
    conditions = []
    
    # ノードタイプに応じて適切なキーから条件を取得
    condition_keys = {
        "Hash Join": "Hash Cond",
        "Merge Join": "Merge Cond", 
        "Nested Loop": "Join Filter",
    }
    
    node_type = node.get("Node Type", "")
    cond_key = condition_keys.get(node_type)
    
    if cond_key and cond_key in node:
        condition_text = node[cond_key]
        # 条件をパース
        parsed = self.parse_join_condition(condition_text)
        conditions.extend(parsed)
    
    # Index Condも考慮
    if "Index Cond" in node:
        parsed = self.parse_join_condition(node["Index Cond"])
        for cond in parsed:
            cond.condition_type = "Index Cond"
        conditions.extend(parsed)
    
    return conditions

def parse_join_condition(self, condition_text: str) -> list[JoinCondition]:
    """JOIN条件テキストをパース
    
    例: "(t.id = ci.movie_id)" -> JoinCondition(...)
    例: "(mc.company_type_id = ct.id)" -> JoinCondition(...)
    """
    conditions = []
    
    # 正規表現でパース
    # パターン: (alias1.column1 = alias2.column2)
    pattern = r'\((\w+)\.(\w+)\s*(=|<|>|<=|>=|!=)\s*(\w+)\.(\w+)\)'
    matches = re.finditer(pattern, condition_text)
    
    for match in matches:
        left_table = match.group(1)
        left_column = match.group(2)
        operator = match.group(3)
        right_table = match.group(4)
        right_column = match.group(5)
        
        conditions.append(JoinCondition(
            left_table=left_table,
            left_column=left_column,
            operator=operator,
            right_table=right_table,
            right_column=right_column,
            condition_type="Join Condition",
            original_text=match.group(0)
        ))
    
    return conditions
```

### 2.2 convert_node メソッドの拡張

```python
def convert_node_v2(
    self,
    node: dict[str, Any],
    subquery_list: list[dict[str, Any]],
    # ... 既存の引数
) -> tuple[dict[str, Any], int]:
    """拡張版: JOIN条件を含む完全な情報を抽出"""
    
    if "Plans" in node:  # Non-leaf node
        children = []
        new_order = order
        
        # 子ノードを再帰的に処理
        for child in node["Plans"]:
            converted_child, order_1 = self.convert_node_v2(
                child, subquery_list, # ...
            )
            children.append(converted_child)
            new_order = order_1
        
        # JOIN条件を抽出
        join_conditions = self.extract_join_conditions(node)
        
        # JOIN種別を取得
        join_type = node.get("Join Type", "Inner")
        
        # フィルタ条件を抽出
        filters = []
        for filter_key in ["Filter", "Join Filter", "Hash Cond", "Merge Cond"]:
            if filter_key in node and filter_key not in ["Hash Cond", "Merge Cond"]:
                filters.append(node[filter_key])
        
        # 非リーフノード情報を構築
        subquery_list.append({
            "type": "non_leaf",
            "operator": node["Node Type"],
            "join_type": join_type,
            "join_conditions": join_conditions,
            "filters": filters,
            "cost": node.get("Total Cost", 0.0) * frequency,
            "rows": node.get("Plan Rows", 0),
            "width": node.get("Plan Width", 1),
            "children": children,
        })
        
        return subquery_list[-1], new_order
    
    else:  # Leaf node (既存のロジック)
        # ...
```

---

## 3. SQLパーサーの堅牢性向上 (最優先)

### 3.1 現状の問題点

- 正規表現ベース → 複雑なSQLで破綻
- ネストされたサブクエリ非対応
- JOIN条件の抽出が不完全
- エイリアスとテーブル名の対応が曖昧

### 3.2 改善アプローチ: ASTベースのSQLパーサー

**選択肢A: sqlparseライブラリの活用**
```python
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Comparison
from sqlparse.tokens import Keyword, DML

class RobustSQLParser:
    """堅牢なSQLパーサー (sqlparse使用)"""
    
    def parse_sql(self, sql: str) -> ParsedSQL:
        """SQLを完全にパース"""
        parsed = sqlparse.parse(sql)[0]
        
        return ParsedSQL(
            select_clause=self.extract_select(parsed),
            from_clause=self.extract_from(parsed),
            where_clause=self.extract_where(parsed),
            joins=self.extract_joins(parsed),
            group_by=self.extract_group_by(parsed),
            order_by=self.extract_order_by(parsed),
        )
    
    def extract_from(self, parsed) -> FromClause:
        """FROM句を完全抽出"""
        from_seen = False
        tables = []
        
        for token in parsed.tokens:
            if from_seen:
                if token.ttype is Keyword:
                    break
                if isinstance(token, IdentifierList):
                    for identifier in token.get_identifiers():
                        tables.append(self.parse_table_ref(identifier))
                elif isinstance(token, Identifier):
                    tables.append(self.parse_table_ref(token))
            elif token.ttype is Keyword and token.value.upper() == 'FROM':
                from_seen = True
        
        return FromClause(tables=tables)
    
    def parse_table_ref(self, identifier) -> TableRef:
        """テーブル参照をパース"""
        # "table_name AS alias" または "table_name alias" をパース
        name = identifier.get_real_name()
        alias = identifier.get_alias() or name
        
        return TableRef(
            table=name,
            alias=alias,
            full_text=str(identifier)
        )
    
    def extract_joins(self, parsed) -> list[JoinInfo]:
        """JOIN句を抽出"""
        joins = []
        tokens = list(parsed.flatten())
        
        for i, token in enumerate(tokens):
            if token.ttype is Keyword and 'JOIN' in token.value.upper():
                join_type = self.determine_join_type(tokens, i)
                table = self.extract_join_table(tokens, i)
                condition = self.extract_join_condition(tokens, i)
                
                joins.append(JoinInfo(
                    join_type=join_type,
                    table=table,
                    condition=condition
                ))
        
        return joins
```

**選択肢B: PostgreSQL pg_query (より正確)**
```python
import pg_query

class PostgreSQLParser:
    """PostgreSQL専用パーサー (pg_query使用)"""
    
    def parse_sql(self, sql: str) -> ParsedSQL:
        """PostgreSQLのSQLを正確にパース"""
        try:
            result = pg_query.parse(sql)
            ast = result['stmts'][0]['stmt']
            
            select_stmt = ast['SelectStmt']
            
            return ParsedSQL(
                select_clause=self.parse_target_list(select_stmt.get('targetList', [])),
                from_clause=self.parse_from_clause(select_stmt.get('fromClause', [])),
                where_clause=self.parse_where(select_stmt.get('whereClause')),
                # ... その他の句
            )
        except Exception as e:
            # フォールバック: 正規表現ベースパーサー
            return self.fallback_parse(sql)
    
    def parse_from_clause(self, from_clause: list) -> FromClause:
        """FROM句をASTからパース"""
        tables = []
        
        for item in from_clause:
            if 'JoinExpr' in item:
                # JOIN式を処理
                join_info = self.parse_join_expr(item['JoinExpr'])
                tables.extend(join_info)
            elif 'RangeVar' in item:
                # 単純なテーブル参照
                range_var = item['RangeVar']
                tables.append(TableRef(
                    table=range_var['relname'],
                    alias=range_var.get('alias', {}).get('aliasname', range_var['relname']),
                    schema=range_var.get('schemaname')
                ))
        
        return FromClause(tables=tables)
```

**推奨: 段階的アプローチ**
1. **Phase 1:** `sqlparse`で基本的な堅牢性を確保
2. **Phase 2:** `pg_query`でPostgreSQL完全互換を実現
3. **Fallback:** 複雑すぎる場合は正規表現ベースに退避

### 3.3 実装例: 強化されたSQLParser

```python
from typing import Optional
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Token
from sqlparse.tokens import Keyword, Whitespace

@dataclass
class ParsedSQL:
    """パース済みSQL"""
    select_clause: SelectClause
    from_clause: FromClause
    where_clause: Optional[WhereClause] = None
    joins: list[JoinInfo] = field(default_factory=list)
    group_by: Optional[list[str]] = None
    order_by: Optional[list[str]] = None
    limit: Optional[str] = None

@dataclass
class TableRef:
    """テーブル参照"""
    table: str
    alias: str
    schema: Optional[str] = None
    is_subquery: bool = False
    
@dataclass
class JoinInfo:
    """JOIN情報"""
    join_type: str  # INNER, LEFT, RIGHT, FULL
    left_table: str
    right_table: str
    condition: str
    parsed_condition: Optional[JoinCondition] = None

class EnhancedSQLParser:
    """強化されたSQLパーサー"""
    
    def __init__(self):
        self.table_alias_map: dict[str, str] = {}  # alias -> table_name
    
    def parse(self, sql: str) -> ParsedSQL:
        """SQLを完全パース"""
        # sqlparseでパース
        parsed = sqlparse.parse(sql)[0]
        
        # 各句を抽出
        select_clause = self._extract_select_clause(parsed)
        from_clause = self._extract_from_clause(parsed)
        where_clause = self._extract_where_clause(parsed)
        joins = self._extract_joins(parsed)
        
        # エイリアスマップを構築
        self._build_alias_map(from_clause, joins)
        
        return ParsedSQL(
            select_clause=select_clause,
            from_clause=from_clause,
            where_clause=where_clause,
            joins=joins,
        )
    
    def _extract_from_clause(self, parsed) -> FromClause:
        """FROM句を抽出 (JOINも含む)"""
        tables = []
        from_seen = False
        
        for token in parsed.tokens:
            if token.ttype is Keyword and token.value.upper() == 'FROM':
                from_seen = True
                continue
            
            if from_seen:
                # WHERE, GROUP BY などのキーワードで終了
                if token.ttype is Keyword and token.value.upper() in ['WHERE', 'GROUP', 'ORDER', 'LIMIT']:
                    break
                
                # JOINを処理
                if isinstance(token, Identifier):
                    table_ref = self._parse_table_identifier(token)
                    if table_ref:
                        tables.append(table_ref)
                elif isinstance(token, IdentifierList):
                    for identifier in token.get_identifiers():
                        table_ref = self._parse_table_identifier(identifier)
                        if table_ref:
                            tables.append(table_ref)
        
        return FromClause(tables=tables)
    
    def _parse_table_identifier(self, identifier) -> Optional[TableRef]:
        """テーブル識別子をパース"""
        # 実名とエイリアスを取得
        real_name = identifier.get_real_name()
        alias = identifier.get_alias()
        
        if not real_name:
            return None
        
        return TableRef(
            table=real_name,
            alias=alias or real_name,
        )
    
    def _extract_joins(self, parsed) -> list[JoinInfo]:
        """JOIN句を抽出"""
        joins = []
        tokens_str = str(parsed)
        
        # JOINパターンをマッチ
        # 例: "INNER JOIN table2 t2 ON t1.id = t2.id"
        join_pattern = r'(INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\s+(\w+)\s+(?:AS\s+)?(\w+)?\s+ON\s+([^\s]+\s*=\s*[^\s]+)'
        
        import re
        for match in re.finditer(join_pattern, tokens_str, re.IGNORECASE):
            join_type = match.group(1) or "INNER"
            table_name = match.group(2)
            alias = match.group(3) or table_name
            condition = match.group(4)
            
            joins.append(JoinInfo(
                join_type=join_type.upper(),
                left_table="",  # 後で解決
                right_table=alias,
                condition=condition,
            ))
        
        return joins
    
    def reconstruct_sql(
        self,
        select_clause: str,
        from_clause: str,
        where_clause: Optional[str] = None,
        **kwargs
    ) -> str:
        """SQLを再構築"""
        sql_parts = [f"SELECT {select_clause}", f"FROM {from_clause}"]
        
        if where_clause:
            sql_parts.append(f"WHERE {where_clause}")
        if kwargs.get('group_by'):
            sql_parts.append(f"GROUP BY {kwargs['group_by']}")
        if kwargs.get('order_by'):
            sql_parts.append(f"ORDER BY {kwargs['order_by']}")
        if kwargs.get('limit'):
            sql_parts.append(f"LIMIT {kwargs['limit']}")
        
        return "\n".join(sql_parts)
```

---

## 4. MV作成SQL生成の改善

### 4.1 リーフMV生成 (既存を強化)

```python
class EnhancedMVGenerator:
    """強化版MVジェネレーター"""
    
    def __init__(self, schema_provider: SchemaProvider):
        self.schema = schema_provider
        self.sql_parser = EnhancedSQLParser()
    
    def generate_leaf_mv_sql(
        self,
        node_id: str,
        node_info: tuple[str, str, str, str]
    ) -> str:
        """リーフMV SQL生成"""
        operator, table, alias, filter_condition = node_info
        
        # スキーマから動的にカラム取得
        columns = self.schema.get_table_columns(table)
        
        # SELECT句
        if columns:
            select_items = [f"{alias}.{col}" for col in columns]
            select_clause = ", ".join(select_items)
        else:
            select_clause = f"{alias}.*"
        
        # CREATE文組み立て
        sql_parts = [
            f"CREATE MATERIALIZED VIEW {node_id} AS",
            f"SELECT {select_clause}",
            f"FROM {table} {alias}"
        ]
        
        if filter_condition:
            sql_parts.append(f"WHERE {filter_condition}")
        
        sql_parts.append(";")
        
        return "\n".join(sql_parts)
```

### 4.2 非リーフMV生成 (完全再設計)

```python
def generate_non_leaf_mv_sql(
    self,
    node_id: str,
    node_info: NonLeafNodeInfo
) -> str:
    """非リーフMV SQL生成 (JOIN条件を正確に反映)"""
    
    # 子ノードの情報を再帰的に取得
    child_mvs = []
    for child_id in node_info.children:
        child_info = self._get_node_info(child_id)
        child_mvs.append({
            'id': child_id,
            'info': child_info,
            'tables': self._get_child_tables(child_id)
        })
    
    # FROM句構築: 最初の子ノード
    from_clause = f"{child_mvs[0]['id']}"
    
    # JOIN句構築
    for i, child_mv in enumerate(child_mvs[1:], 1):
        join_type = node_info.join_type
        child_id = child_mv['id']
        
        # このJOINの条件を見つける
        join_conditions = self._find_join_conditions(
            child_mvs[0]['id'],
            child_id,
            node_info.join_conditions
        )
        
        if join_conditions:
            # 条件を再構築 (MVのエイリアスを使用)
            condition_str = self._rebuild_join_condition(
                join_conditions,
                child_mvs[0]['id'],
                child_id
            )
            from_clause += f"\n{join_type} JOIN {child_id} ON {condition_str}"
        else:
            # 条件が不明な場合は、カラム名から推測
            from_clause += f"\n{join_type} JOIN {child_id} ON {self._infer_join_condition(child_mvs[0], child_mv)}"
    
    # SELECT句: すべてのカラムを含める
    select_clause = self._build_select_clause(child_mvs, node_info)
    
    # WHERE句: フィルタ条件
    where_clause = ""
    if node_info.filters:
        # MVのエイリアスに条件を書き換え
        where_clause = "\nWHERE " + " AND ".join(
            self._rewrite_filter_for_mvs(f, child_mvs) for f in node_info.filters
        )
    
    # SQL組み立て
    sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT {select_clause}
FROM {from_clause}{where_clause};"""
    
    return sql

def _find_join_conditions(
    self,
    left_mv: str,
    right_mv: str,
    all_conditions: list[JoinCondition]
) -> list[JoinCondition]:
    """2つのMV間のJOIN条件を検索"""
    left_tables = self._get_child_tables(left_mv)
    right_tables = self._get_child_tables(right_mv)
    
    matching_conditions = []
    for cond in all_conditions:
        # 左テーブルがleft_mvに、右テーブルがright_mvに含まれるか
        if (cond.left_table in left_tables and cond.right_table in right_tables) or \
           (cond.right_table in left_tables and cond.left_table in right_tables):
            matching_conditions.append(cond)
    
    return matching_conditions

def _rebuild_join_condition(
    self,
    conditions: list[JoinCondition],
    left_mv: str,
    right_mv: str
) -> str:
    """JOIN条件をMVエイリアスで書き直し"""
    rebuilt_conditions = []
    
    for cond in conditions:
        # 元: t.id = ci.movie_id
        # 変換: left_mv.id = right_mv.movie_id (または left_mv.movie_id = right_mv.id)
        
        left_tables = self._get_child_tables(left_mv)
        
        if cond.left_table in left_tables:
            rebuilt_conditions.append(
                f"{left_mv}.{cond.left_column} {cond.operator} {right_mv}.{cond.right_column}"
            )
        else:
            rebuilt_conditions.append(
                f"{left_mv}.{cond.right_column} {cond.operator} {right_mv}.{cond.left_column}"
            )
    
    return " AND ".join(rebuilt_conditions)

def _infer_join_condition(
    self,
    left_mv: dict,
    right_mv: dict
) -> str:
    """JOIN条件を推測 (外部キー情報から)"""
    left_tables = left_mv['tables']
    right_tables = right_mv['tables']
    
    # 外部キー関係を検索
    fk_relations = self.schema.get_foreign_key_relations(left_tables, right_tables)
    
    if fk_relations:
        # 最初のFK関係を使用
        fk = fk_relations[0]
        return f"{left_mv['id']}.{fk.from_column} = {right_mv['id']}.{fk.to_column}"
    
    # 推測不可能な場合
    return "TRUE  -- WARNING: Join condition could not be inferred"
```

---

## 5. クエリ書き換えロジックの高度化

### 5.1 クエリグラフマッチング

```python
class QueryGraphMatcher:
    """クエリグラフとMVグラフのマッチング"""
    
    def __init__(self, qm: QueryManager):
        self.qm = qm
        self.sql_parser = EnhancedSQLParser()
    
    def find_mv_matches(
        self,
        parsed_query: ParsedSQL,
        available_mvs: list[str]
    ) -> list[MVMatch]:
        """クエリに適用可能なMVを検索"""
        matches = []
        
        # クエリからテーブルグラフを構築
        query_graph = self._build_query_graph(parsed_query)
        
        # 各MVについてマッチングを試行
        for mv_id in available_mvs:
            mv_graph = self._build_mv_graph(mv_id)
            
            # サブグラフマッチング
            match_info = self._match_graphs(query_graph, mv_graph)
            
            if match_info:
                matches.append(MVMatch(
                    mv_id=mv_id,
                    matched_tables=match_info.tables,
                    matched_joins=match_info.joins,
                    coverage_score=match_info.coverage,
                    replacement_type=match_info.type  # "full" or "partial"
                ))
        
        # スコア順にソート
        matches.sort(key=lambda m: m.coverage_score, reverse=True)
        return matches
    
    def _build_query_graph(self, parsed_query: ParsedSQL) -> QueryGraph:
        """クエリからグラフを構築"""
        graph = QueryGraph()
        
        # ノード追加 (テーブル)
        for table_ref in parsed_query.from_clause.tables:
            graph.add_node(table_ref.alias, table_ref.table)
        
        # エッジ追加 (JOIN)
        for join in parsed_query.joins:
            graph.add_edge(
                join.left_table,
                join.right_table,
                join.condition,
                join.join_type
            )
        
        return graph
    
    def _match_graphs(
        self,
        query_graph: QueryGraph,
        mv_graph: MVGraph
    ) -> Optional[MatchInfo]:
        """グラフマッチング (サブグラフ同型判定)"""
        
        # MVグラフがクエリグラフのサブグラフか判定
        if mv_graph.is_subgraph_of(query_graph):
            # 完全一致または部分一致を判定
            coverage = mv_graph.node_count() / query_graph.node_count()
            
            return MatchInfo(
                tables=mv_graph.get_all_tables(),
                joins=mv_graph.get_all_joins(),
                coverage=coverage,
                type="full" if coverage == 1.0 else "partial"
            )
        
        return None
```

### 5.2 書き換え実行エンジン

```python
class QueryRewriteEngine:
    """クエリ書き換えエンジン"""
    
    def __init__(self, qm: QueryManager):
        self.qm = qm
        self.matcher = QueryGraphMatcher(qm)
        self.sql_parser = EnhancedSQLParser()
    
    def rewrite_query(
        self,
        original_sql: str,
        selected_mvs: list[str]
    ) -> str:
        """クエリを書き換え"""
        
        # 元のクエリをパース
        parsed_query = self.sql_parser.parse(original_sql)
        
        # MVマッチング
        mv_matches = self.matcher.find_mv_matches(parsed_query, selected_mvs)
        
        if not mv_matches:
            print("Warning: No MV matches found")
            return original_sql
        
        # 最適なMVを選択 (最もカバレッジの高いもの)
        best_match = mv_matches[0]
        
        # 書き換えタイプに応じて処理
        if best_match.replacement_type == "full":
            return self._rewrite_full_replacement(parsed_query, best_match)
        else:
            return self._rewrite_partial_replacement(parsed_query, best_match)
    
    def _rewrite_full_replacement(
        self,
        parsed_query: ParsedSQL,
        mv_match: MVMatch
    ) -> str:
        """完全置換: クエリ全体をMVで置き換え"""
        
        mv_id = mv_match.mv_id
        
        # SELECT句はそのまま (カラム名をMVのものに調整)
        select_clause = self._adjust_select_for_mv(
            parsed_query.select_clause,
            mv_id
        )
        
        # FROM句: MVのみ
        from_clause = mv_id
        
        # WHERE句: MVに含まれないフィルタのみ残す
        where_clause = self._filter_where_for_mv(
            parsed_query.where_clause,
            mv_match
        )
        
        return self.sql_parser.reconstruct_sql(
            select_clause=select_clause,
            from_clause=from_clause,
            where_clause=where_clause
        )
    
    def _rewrite_partial_replacement(
        self,
        parsed_query: ParsedSQL,
        mv_match: MVMatch
    ) -> str:
        """部分置換: MVと他のテーブルをJOIN"""
        
        mv_id = mv_match.mv_id
        
        # MVがカバーするテーブルを特定
        covered_tables = set(mv_match.matched_tables)
        
        # FROM句を再構築
        new_from_parts = [mv_id]  # MVを先頭に
        
        # MVでカバーされないテーブルを追加
        for table_ref in parsed_query.from_clause.tables:
            if table_ref.alias not in covered_tables:
                new_from_parts.append(f"{table_ref.table} {table_ref.alias}")
        
        # JOIN句を再構築
        new_joins = []
        for join in parsed_query.joins:
            # 両方のテーブルがMVに含まれる → スキップ
            if join.left_table in covered_tables and join.right_table in covered_tables:
                continue
            
            # 片方がMVに含まれる → MVとのJOINに書き換え
            elif join.left_table in covered_tables:
                new_joins.append(f"{join.join_type} JOIN {join.right_table} ON {self._rewrite_join_condition(join.condition, covered_tables, mv_id)}")
            elif join.right_table in covered_tables:
                new_joins.append(f"{join.join_type} JOIN {join.left_table} ON {self._rewrite_join_condition(join.condition, covered_tables, mv_id)}")
            else:
                # 両方ともMV外 → そのまま
                new_joins.append(f"{join.join_type} JOIN {join.right_table} ON {join.condition}")
        
        from_clause = " ".join(new_from_parts + new_joins)
        
        # SELECT句とWHERE句を調整
        select_clause = self._adjust_select_for_partial_mv(
            parsed_query.select_clause,
            mv_id,
            covered_tables
        )
        
        where_clause = self._adjust_where_for_partial_mv(
            parsed_query.where_clause,
            mv_id,
            covered_tables
        )
        
        return self.sql_parser.reconstruct_sql(
            select_clause=select_clause,
            from_clause=from_clause,
            where_clause=where_clause
        )
    
    def _rewrite_join_condition(
        self,
        condition: str,
        covered_tables: set[str],
        mv_id: str
    ) -> str:
        """JOIN条件をMV用に書き換え
        
        例: t.id = ci.movie_id (tがMV内)
         → mv_id.id = ci.movie_id
        """
        # 条件をパース
        parts = condition.split('=')
        if len(parts) != 2:
            return condition
        
        left = parts[0].strip()
        right = parts[1].strip()
        
        # alias.column形式を分解
        left_parts = left.split('.')
        right_parts = right.split('.')
        
        if len(left_parts) == 2 and left_parts[0] in covered_tables:
            left = f"{mv_id}.{left_parts[1]}"
        
        if len(right_parts) == 2 and right_parts[0] in covered_tables:
            right = f"{mv_id}.{right_parts[1]}"
        
        return f"{left} = {right}"
```

---

## 6. スキーマ情報の動的取得

### 6.1 SchemaProviderの実装

```python
class SchemaProvider:
    """PostgreSQLスキーマ情報プロバイダー"""
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self._column_cache: dict[str, list[str]] = {}
        self._fk_cache: dict[tuple[str, str], list[ForeignKeyRelation]] = {}
    
    def get_table_columns(self, table_name: str) -> list[str]:
        """テーブルのカラム一覧を取得"""
        if table_name in self._column_cache:
            return self._column_cache[table_name]
        
        import psycopg2
        
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """
        
        cur.execute(query, (table_name,))
        columns = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        self._column_cache[table_name] = columns
        return columns
    
    def get_foreign_key_relations(
        self,
        left_tables: list[str],
        right_tables: list[str]
    ) -> list[ForeignKeyRelation]:
        """外部キー関係を取得"""
        cache_key = (tuple(sorted(left_tables)), tuple(sorted(right_tables)))
        
        if cache_key in self._fk_cache:
            return self._fk_cache[cache_key]
        
        import psycopg2
        
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        query = """
            SELECT
                kcu1.table_name AS from_table,
                kcu1.column_name AS from_column,
                kcu2.table_name AS to_table,
                kcu2.column_name AS to_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu1
                ON tc.constraint_name = kcu1.constraint_name
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.key_column_usage kcu2
                ON rc.unique_constraint_name = kcu2.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND kcu1.table_name = ANY(%s)
                AND kcu2.table_name = ANY(%s);
        """
        
        cur.execute(query, (left_tables, right_tables))
        
        fk_relations = []
        for row in cur.fetchall():
            fk_relations.append(ForeignKeyRelation(
                from_table=row[0],
                from_column=row[1],
                to_table=row[2],
                to_column=row[3]
            ))
        
        cur.close()
        conn.close()
        
        self._fk_cache[cache_key] = fk_relations
        return fk_relations
    
    def get_primary_key(self, table_name: str) -> Optional[list[str]]:
        """主キーカラムを取得"""
        import psycopg2
        
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = %s
            ORDER BY kcu.ordinal_position;
        """
        
        cur.execute(query, (table_name,))
        pk_columns = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return pk_columns if pk_columns else None
```

---

## 7. 実装計画とマイグレーション

### 7.1 Phase 1: 基盤強化 (2週間)

**Week 1: SQLパーサー強化**
- [ ] `sqlparse`ライブラリ導入
- [ ] `EnhancedSQLParser`実装
- [ ] 既存のSQLParserとの互換性テスト
- [ ] FROM/JOIN/WHERE句の抽出精度向上

**Week 2: データ構造拡張**
- [ ] `NonLeafNodeInfo`, `JoinCondition`データクラス定義
- [ ] `QueryManager.process_non_leaf_node_v2`実装
- [ ] `QueryParser.extract_join_conditions`実装
- [ ] `convert_node`メソッド拡張

### 7.2 Phase 2: MV生成改善 (2週間)

**Week 3: SchemaProvider & リーフMV**
- [ ] `SchemaProvider`実装 (PostgreSQL接続)
- [ ] カラム情報の動的取得
- [ ] 外部キー情報の取得
- [ ] リーフMV生成の動的スキーマ対応

**Week 4: 非リーフMV生成**
- [ ] `EnhancedMVGenerator`実装
- [ ] JOIN条件の正確な再構築
- [ ] フィルタ条件の適切な配置
- [ ] テストケースでの検証

### 7.3 Phase 3: クエリ書き換え (3週間)

**Week 5-6: グラフマッチング**
- [ ] `QueryGraph`, `MVGraph`クラス実装
- [ ] サブグラフマッチングアルゴリズム
- [ ] `QueryGraphMatcher`実装
- [ ] マッチング精度のベンチマーク

**Week 7: 書き換えエンジン**
- [ ] `QueryRewriteEngine`実装
- [ ] 完全置換ロジック
- [ ] 部分置換ロジック
- [ ] エッジケースのハンドリング

### 7.4 Phase 4: 統合とテスト (2週間)

**Week 8: 統合**
- [ ] 全コンポーネントの統合
- [ ] `run_experiment.py`への組み込み
- [ ] パフォーマンス測定

**Week 9: テストと最適化**
- [ ] 113クエリでの動作確認
- [ ] バグ修正
- [ ] ドキュメント整備

### 7.5 マイグレーション戦略

**段階的移行 (Backward Compatibility維持)**

```python
# config/settings.py
class OptimizationSettings:
    # 新機能のフラグ
    use_enhanced_parser: bool = True
    use_enhanced_mv_generator: bool = True
    use_graph_based_rewrite: bool = True
    
    # フォールバック設定
    fallback_to_legacy_on_error: bool = True
```

**デュアルモード実装例:**
```python
class QueryRewriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.legacy_rewriter = LegacyQueryRewriter()
        self.enhanced_rewriter = QueryRewriteEngine(qm)
    
    def rewrite_workload(self, mv_selections, output_dir, original_queries):
        if self.settings.optimization.use_graph_based_rewrite:
            try:
                return self.enhanced_rewriter.rewrite_workload(...)
            except Exception as e:
                if self.settings.optimization.fallback_to_legacy_on_error:
                    print(f"Enhanced rewriter failed: {e}, falling back to legacy")
                    return self.legacy_rewriter.rewrite_workload(...)
                raise
        else:
            return self.legacy_rewriter.rewrite_workload(...)
```

---

## 8. テスト戦略

### 8.1 ユニットテスト

```python
# tests/unit/test_enhanced_sql_parser.py
import pytest
from src.rewrite.enhanced_sql_parser import EnhancedSQLParser

class TestEnhancedSQLParser:
    def test_parse_simple_select(self):
        parser = EnhancedSQLParser()
        sql = "SELECT t.id, t.title FROM title t WHERE t.year > 2000"
        
        parsed = parser.parse(sql)
        
        assert len(parsed.from_clause.tables) == 1
        assert parsed.from_clause.tables[0].table == "title"
        assert parsed.from_clause.tables[0].alias == "t"
    
    def test_parse_join(self):
        parser = EnhancedSQLParser()
        sql = """
            SELECT t.id, ci.note
            FROM title t
            INNER JOIN cast_info ci ON t.id = ci.movie_id
            WHERE t.year > 2000
        """
        
        parsed = parser.parse(sql)
        
        assert len(parsed.from_clause.tables) == 2
        assert len(parsed.joins) == 1
        assert parsed.joins[0].join_type == "INNER"
        assert parsed.joins[0].condition == "t.id = ci.movie_id"
    
    def test_parse_complex_nested_joins(self):
        # JOB 1a.sql のような複雑なクエリ
        sql = """
            SELECT MIN(mc.note) AS production_note,
                   MIN(t.title) AS movie_title,
                   MIN(t.production_year) AS movie_year
            FROM company_type AS ct,
                 info_type AS it,
                 movie_companies AS mc,
                 movie_info_idx AS mi_idx,
                 title AS t
            WHERE ct.kind = 'production companies'
              AND it.info = 'top 250 rank'
              AND mc.note NOT LIKE '%(as Metro-Goldwyn-Mayer Pictures)%'
              AND (mc.note LIKE '%(co-production)%' OR mc.note LIKE '%(presents)%')
              AND ct.id = mc.company_type_id
              AND t.id = mc.movie_id
              AND t.id = mi_idx.movie_id
              AND mc.movie_id = mi_idx.movie_id
              AND it.id = mi_idx.info_type_id;
        """
        
        parser = EnhancedSQLParser()
        parsed = parser.parse(sql)
        
        assert len(parsed.from_clause.tables) == 5
        # JOIN条件の抽出を確認
        # ...

# tests/unit/test_mv_generator.py
class TestEnhancedMVGenerator:
    def test_leaf_mv_generation(self):
        generator = EnhancedMVGenerator(schema_provider)
        
        node_info = ("Seq Scan", "company_type", "ct", "((kind)::text = 'production companies'::text)")
        sql = generator.generate_leaf_mv_sql("leaf_4", node_info)
        
        expected = """CREATE MATERIALIZED VIEW leaf_4 AS
SELECT ct.id, ct.kind
FROM company_type ct
WHERE ((kind)::text = 'production companies'::text);"""
        
        assert sql.strip() == expected.strip()
    
    def test_non_leaf_mv_with_join_conditions(self):
        # JOIN条件を含む非リーフMV
        # ...
```

### 8.2 統合テスト

```python
# tests/integration/test_end_to_end.py
class TestEndToEnd:
    def test_full_pipeline_job_1a(self):
        """JOB 1a.sql の完全パイプライン"""
        
        # 1. EXPLAIN JSON読み込み
        with open("dataset/RED_JSON/job/1a.json") as f:
            explain_json = json.load(f)
        
        # 2. QueryParser でパース
        parser = QueryParser(settings)
        parser.query_parse(...)
        
        # 3. ILP最適化
        optimizer = BigSubsILP(parser)
        result = optimizer.optimize()
        
        # 4. MV SQL生成
        mv_generator = EnhancedMVGenerator(schema_provider)
        mv_sqls = mv_generator.generate_mv_scripts(result.selected_views, ...)
        
        # 5. クエリ書き換え
        rewriter = QueryRewriteEngine(parser.qm)
        rewritten_sql = rewriter.rewrite_query(original_sql, result.selected_views)
        
        # 6. 検証
        assert "non_leaf_" in rewritten_sql  # 非リーフMVが使われている
        assert validate_sql_syntax(rewritten_sql)  # 構文エラーなし
```

### 8.3 性能ベンチマーク

```python
# tests/benchmark/test_performance.py
class TestPerformance:
    def test_rewrite_speed(self):
        """書き換え速度のベンチマーク"""
        
        rewriter = QueryRewriteEngine(qm)
        
        start = time.time()
        for i in range(100):
            rewriter.rewrite_query(complex_sql, mvs)
        elapsed = time.time() - start
        
        # 1クエリあたり < 100ms
        assert elapsed / 100 < 0.1
    
    def test_actual_query_performance(self, postgresql_conn):
        """実際のクエリ実行時間の改善を検証"""
        
        # 元のクエリ実行
        original_time = execute_and_measure(postgresql_conn, original_sql)
        
        # MV作成
        for mv_sql in mv_creation_sqls:
            postgresql_conn.execute(mv_sql)
        
        # 書き換え後のクエリ実行
        rewritten_time = execute_and_measure(postgresql_conn, rewritten_sql)
        
        # 性能改善を確認
        improvement = (original_time - rewritten_time) / original_time
        assert improvement > 0.1  # 少なくとも10%改善
```

---

## 9. ベストプラクティスと注意点

### 9.1 コーディング規約

- **型ヒント必須:** すべての関数に型アノテーションを付ける
- **Docstring:** Google形式で詳細なドキュメント
- **エラーハンドリング:** 具体的な例外クラスを定義
- **ロギング:** `logging`モジュールを使用（`print`は禁止）

```python
import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class MVGenerationError(Exception):
    """MV生成時のエラー"""
    pass

def generate_mv_sql(
    node_id: str,
    node_info: NonLeafNodeInfo
) -> str:
    """MV作成SQLを生成
    
    Args:
        node_id: ノードID
        node_info: ノード詳細情報
        
    Returns:
        CREATE MATERIALIZED VIEW文
        
    Raises:
        MVGenerationError: SQL生成に失敗した場合
    """
    try:
        # ...
    except Exception as e:
        logger.error(f"Failed to generate MV SQL for {node_id}: {e}")
        raise MVGenerationError(f"Cannot generate SQL for {node_id}") from e
```

### 9.2 パフォーマンス最適化

1. **キャッシング:** スキーマ情報、パース結果をキャッシュ
2. **遅延評価:** 必要になるまで計算を遅延
3. **並列処理:** 複数MVの生成を並列化

```python
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

class OptimizedMVGenerator:
    @lru_cache(maxsize=1000)
    def get_table_columns(self, table_name: str) -> list[str]:
        """キャッシュ付きカラム取得"""
        return self.schema.get_table_columns(table_name)
    
    def generate_all_mvs_parallel(self, mv_nodes: list[str]) -> list[str]:
        """並列MV生成"""
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(self.generate_mv_sql, node_id)
                for node_id in mv_nodes
            ]
            return [f.result() for f in futures]
```

### 9.3 デバッグとトラブルシューティング

```python
class DebugRewriter:
    """デバッグ機能付き書き換えエンジン"""
    
    def rewrite_query_with_debug(
        self,
        original_sql: str,
        selected_mvs: list[str],
        debug_output_dir: Path
    ) -> str:
        """デバッグ情報を出力しながら書き換え"""
        
        # 1. パース結果をダンプ
        parsed = self.sql_parser.parse(original_sql)
        with open(debug_output_dir / "parsed_query.json", "w") as f:
            json.dump(asdict(parsed), f, indent=2)
        
        # 2. MVマッチング結果をダンプ
        matches = self.matcher.find_mv_matches(parsed, selected_mvs)
        with open(debug_output_dir / "mv_matches.json", "w") as f:
            json.dump([asdict(m) for m in matches], f, indent=2)
        
        # 3. 書き換え実行
        rewritten = self.rewrite_query(original_sql, selected_mvs)
        
        # 4. 差分を出力
        with open(debug_output_dir / "rewrite_diff.txt", "w") as f:
            f.write("=== ORIGINAL ===\n")
            f.write(original_sql)
            f.write("\n\n=== REWRITTEN ===\n")
            f.write(rewritten)
        
        return rewritten
```

---

## 10. 期待される改善効果

### 10.1 定量的効果

| 指標 | 現状 | 改善後 | 改善率 |
|------|------|--------|--------|
| 非リーフMV使用率 | 0% | 90%+ | +90pt |
| クエリ書き換え成功率 | 37% (リーフのみ) | 95%+ | +58pt |
| SQL生成精度 | 60% | 98%+ | +38pt |
| 平均クエリ実行時間削減 | 0% | 30-50% | - |

### 10.2 定性的効果

- ✅ **堅牢性:** 複雑なクエリでも正確に処理
- ✅ **保守性:** モジュール化で変更が容易
- ✅ **拡張性:** 新しいアルゴリズム追加が簡単
- ✅ **デバッグ性:** 詳細なログとデバッグ機能

---

## 11. 次のステップ

### 11.1 即座に着手すべきタスク

1. **SQLパーサー選定:** `sqlparse` vs `pg_query` の評価
2. **プロトタイプ作成:** 小規模なPoCで基本概念を検証
3. **既存コードの分析:** 影響範囲の特定

### 11.2 中長期的な改善

- **機械学習ベースのMV選択:** 実行履歴からMVを自動推薦
- **インクリメンタルMV更新:** 効率的なMVメンテナンス
- **マルチクエリ最適化:** 複数クエリを同時に考慮

### 11.3 技術的課題

- **複雑なサブクエリ:** ネストされたサブクエリの書き換え
- **集約関数:** GROUP BY/HAVING を含むMVの扱い
- **ウィンドウ関数:** OVER句を含むクエリの対応

---

## 12. 付録

### 12.1 参考実装

- [Apache Calcite](https://calcite.apache.org/): MVベースのクエリ最適化
- [Materialize](https://materialize.com/): ストリーミングMVシステム
- [PostgreSQL pg_query](https://github.com/pganalyze/pg_query): PostgreSQL SQLパーサー

### 12.2 参考文献

- "Optimizing Queries Using Materialized Views: A Practical, Scalable Solution" (SIGMOD 2001)
- "Query Rewriting Using Views in the Presence of Arithmetic Comparisons" (VLDB 2003)
- "Automated Selection of Materialized Views and Indexes in SQL Databases" (VLDB 2000)

---

## 📞 質問・フィードバック

このドキュメントについての質問や提案があれば、以下の観点でフィードバックをお願いします:

1. **技術的実現可能性:** 提案された方法で実装可能か?
2. **優先順位:** Phase分けは適切か? 順序の変更が必要か?
3. **スコープ:** 追加すべき機能、削除すべき機能はあるか?
4. **リスク:** 見落としている技術的リスクはあるか?

---

**Last Updated:** 2025年10月7日  
**Status:** Draft - Review Required
