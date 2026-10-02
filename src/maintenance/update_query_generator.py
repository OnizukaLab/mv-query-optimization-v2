"""更新クエリ生成モジュール.

IMDB の各ベーステーブルに対して、IMMV の差分更新を実際に引き起こす
INSERT / UPDATE / DELETE クエリを生成する。

設計方針
--------
IMDB は静的スナップショット (更新が存在しない) なので、
「これから起きそうな更新」をシミュレーションする。

* INSERT : 既存行をコピーして新しい id で挿入 (FK 先の値を流用するため整合性が保たれる)
* UPDATE : FK 以外のカラムのみ変更 (note, info, production_year 等)
* DELETE : 既存行を削除 (ROLLBACK で必ず戻す)

IMMV フィルタとの関係
---------------------
IMMV が WHERE 条件を持つ場合 (例: WHERE note ~~ '%internet%')、
UPDATE が IMMV の内容を変えるためには、変更前または変更後の行が
フィルタ条件に合致している必要がある。
→ INSERT は「フィルタに合致する既存行をコピー」することで確実に IMMV を更新させる。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UpdateQuery:
    """1件の更新クエリ."""
    table_name: str
    op_type: str      # "INSERT" | "UPDATE" | "DELETE"
    sql: str          # 実行可能な SQL (BEGIN/ROLLBACK は含まない)
    description: str  # 人間可読な説明


class UpdateQueryGenerator:
    """IMMV の差分更新を引き起こす更新クエリを生成するクラス.

    使い方::

        gen = UpdateQueryGenerator(conn)
        queries = gen.generate_for_immv(
            immv_name='leaf_122',
            immv_sql='SELECT ... FROM movie_info WHERE note ~~ ...',
            n=5,
        )
        for q in queries:
            print(q.description)
            print(q.sql)
    """

    def __init__(self, conn):
        self.conn = conn

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def generate_for_immv(
        self,
        immv_name: str,
        base_table: str,
        where_clause: Optional[str] = None,
        n: int = 5,
    ) -> list[UpdateQuery]:
        """IMMV に影響を与える更新クエリを n 件生成する.

        Args:
            immv_name:   IMMV の名前 (ログ用)
            base_table:  更新対象のベーステーブル名
            where_clause: IMMV の WHERE 条件 (省略可)。
                          指定すると INSERT でフィルタに合致する行をコピーする。
            n:           生成するクエリ数 (INSERT/UPDATE/DELETE の混合)

        Returns:
            UpdateQuery のリスト
        """
        queries: list[UpdateQuery] = []

        # INSERT (n の半分)
        n_insert = max(1, n // 2)
        queries.extend(self._generate_inserts(base_table, where_clause, n_insert))

        # UPDATE (残り)
        n_update = n - n_insert
        queries.extend(self._generate_updates(base_table, n_update))

        return queries

    def generate_all_op_types(
        self,
        base_table: str,
        where_clause: Optional[str] = None,
        n_each: int = 3,
    ) -> list[UpdateQuery]:
        """INSERT / UPDATE / DELETE を各 n_each 件ずつ生成する (実験比較用)."""
        queries: list[UpdateQuery] = []
        queries.extend(self._generate_inserts(base_table, where_clause, n_each))
        queries.extend(self._generate_updates(base_table, n_each))
        queries.extend(self._generate_deletes(base_table, n_each))
        return queries

    # ──────────────────────────────────────────────────────────────
    # INSERT 生成
    # ──────────────────────────────────────────────────────────────

    def _generate_inserts(
        self, table: str, where_clause: Optional[str], n: int
    ) -> list[UpdateQuery]:
        """既存行をコピーして新しい id で INSERT するクエリを生成する.

        IMMV が WHERE 条件を持つ場合は、その条件を満たす行を優先的にコピーする。
        FK 先の値を流用するため外部キー整合性が壊れない。
        """
        queries: list[UpdateQuery] = []
        cols = self._get_columns(table)
        if not cols:
            return queries

        # id カラムのインデックス
        id_col = cols[0]  # 先頭が id と仮定
        other_cols = cols[1:]

        # MAX(id) + offset でユニークな id を確保
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT MAX({id_col}) FROM {table}")
                max_id = cur.fetchone()[0] or 0
        except Exception:
            self.conn.rollback()
            return queries

        # コピー元の行を取得 (WHERE 条件がある場合はそれを使う)
        source_filter = f"WHERE {where_clause}" if where_clause else ""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(cols)} FROM {table} {source_filter} "
                    f"LIMIT {n} OFFSET 10"  # 先頭 10 件をスキップして多様性を確保
                )
                rows = cur.fetchall()
        except Exception:
            self.conn.rollback()
            return queries

        if not rows:
            # フィルタ条件に一致する行がなければ全件から取得
            try:
                with self.conn.cursor() as cur:
                    cur.execute(f"SELECT {', '.join(cols)} FROM {table} LIMIT {n} OFFSET 10")
                    rows = cur.fetchall()
            except Exception:
                self.conn.rollback()
                return queries

        for i, row in enumerate(rows):
            new_id = max_id + 100_000_000 + i  # 本番 id と衝突しない大きな値
            # id カラムを new_id に置換した行を組み立て
            new_values = [new_id] + list(row[1:])
            placeholders = ", ".join(["%s"] * len(cols))
            col_list = ", ".join(cols)

            # SQL 文字列化 (デバッグしやすいように VALUES をリテラルで埋め込む)
            val_literals = self._values_to_literals(new_values)
            sql = (
                f"INSERT INTO {table} ({col_list}) "
                f"VALUES ({', '.join(val_literals)})"
            )
            filter_note = f"(filter: {where_clause[:40]})" if where_clause else "(no filter)"
            queries.append(UpdateQuery(
                table_name=table,
                op_type="INSERT",
                sql=sql,
                description=f"INSERT into {table} {filter_note}: id={new_id}",
            ))

        return queries

    # ──────────────────────────────────────────────────────────────
    # UPDATE 生成
    # ──────────────────────────────────────────────────────────────

    # テーブルごとの「安全に変更できるカラム」と変更値
    _UPDATE_TARGETS: dict[str, tuple[str, str]] = {
        "movie_info":      ("note", "'ivm_update_test'"),
        "movie_keyword":   ("keyword_id", "keyword_id + 0"),  # 値は変えず行を「触る」
        "cast_info":       ("note", "'ivm_update_test'"),
        "movie_companies": ("note", "'ivm_update_test'"),
        "title":           ("production_year", "production_year"),  # no-op だが触れる
        "name":            ("gender", "gender"),
        "keyword":         ("phonetic_code", "'IVM'"),
        "info_type":       ("info", "info"),
        "kind_type":       ("kind", "kind"),
        "company_name":    ("name", "name"),
        "comp_cast_type":  ("kind", "kind"),
    }

    def _generate_updates(self, table: str, n: int) -> list[UpdateQuery]:
        """既存行の非 FK カラムを変更する UPDATE クエリを生成する."""
        queries: list[UpdateQuery] = []
        target = self._UPDATE_TARGETS.get(table)
        if target is None:
            return queries

        col, val_expr = target
        # 対象行の id をサンプリング
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT id FROM {table} LIMIT {n} OFFSET 100")
                ids = [r[0] for r in cur.fetchall()]
        except Exception:
            self.conn.rollback()
            return queries

        for row_id in ids:
            sql = f"UPDATE {table} SET {col} = {val_expr} WHERE id = {row_id}"
            queries.append(UpdateQuery(
                table_name=table,
                op_type="UPDATE",
                sql=sql,
                description=f"UPDATE {table}.{col} WHERE id={row_id}",
            ))
        return queries

    # ──────────────────────────────────────────────────────────────
    # DELETE 生成
    # ──────────────────────────────────────────────────────────────

    def _generate_deletes(self, table: str, n: int) -> list[UpdateQuery]:
        """既存行を削除する DELETE クエリを生成する (必ず ROLLBACK で戻す)."""
        queries: list[UpdateQuery] = []
        try:
            with self.conn.cursor() as cur:
                # FK 参照されていない行を選ぶために末尾の id を使う
                cur.execute(f"SELECT id FROM {table} ORDER BY id DESC LIMIT {n}")
                ids = [r[0] for r in cur.fetchall()]
        except Exception:
            self.conn.rollback()
            return queries

        for row_id in ids:
            sql = f"DELETE FROM {table} WHERE id = {row_id}"
            queries.append(UpdateQuery(
                table_name=table,
                op_type="DELETE",
                sql=sql,
                description=f"DELETE FROM {table} WHERE id={row_id} (will ROLLBACK)",
            ))
        return queries

    # ──────────────────────────────────────────────────────────────
    # ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _get_columns(self, table: str) -> list[str]:
        """テーブルのカラム名リストを取得する."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s ORDER BY ordinal_position",
                    (table,),
                )
                return [r[0] for r in cur.fetchall()]
        except Exception:
            self.conn.rollback()
            return []

    @staticmethod
    def _values_to_literals(values: list) -> list[str]:
        """Python 値を SQL リテラル文字列に変換する."""
        result = []
        for v in values:
            if v is None:
                result.append("NULL")
            elif isinstance(v, (int, float)):
                result.append(str(v))
            else:
                # 文字列: シングルクォートをエスケープ
                escaped = str(v).replace("'", "''")
                result.append(f"'{escaped}'")
        return result

    @staticmethod
    def extract_where_clause(mv_sql: str) -> Optional[str]:
        """MV の CREATE SQL から WHERE 条件を抽出する."""
        match = re.search(r'\bWHERE\b\s+(.+?)(?:\s*;?\s*$)', mv_sql, re.IGNORECASE | re.DOTALL)
        if match:
            clause = match.group(1).strip().rstrip(";")
            return clause if len(clause) < 500 else None
        return None
