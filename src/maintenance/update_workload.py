"""IMDB テーブルへの安全な更新クエリ生成.

FK 整合性を壊さずに INSERT/UPDATE/DELETE を生成する。
計測は必ず BEGIN/ROLLBACK で囲むため本番データは変更されない。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# IMDB テーブルごとの安全な更新クエリ定義
# - UPDATE: FK 以外のカラムを変更する (整合性リスクなし)
# - INSERT: 既存行をコピーして新しい id で挿入 (FK 先の値を流用)
# - DELETE: 既存行を削除 (ROLLBACK で戻す)
_SAFE_UPDATE_TEMPLATES: dict[str, str] = {
    # movie_keyword は FK カラムのみ → サンプルテーブルなら FK 制約なし、keyword_id を小変更
    "movie_keyword":    "UPDATE {table} SET keyword_id = keyword_id + 9999999 WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # cast_info は note カラムあり
    "cast_info":        "UPDATE {table} SET note = 'ivm_test' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # movie_info は info カラムあり
    "movie_info":       "UPDATE {table} SET info = left(info,50) || '_t' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # movie_companies は note カラムあり
    "movie_companies":  "UPDATE {table} SET note = 'ivm_test' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # title は md5sum カラムあり
    "title":            "UPDATE {table} SET md5sum = 'ivm_test_md5' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # name は md5sum カラムあり
    "name":             "UPDATE {table} SET md5sum = 'ivm_test_md5' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # keyword は phonetic_code カラムあり
    "keyword":          "UPDATE {table} SET phonetic_code = 'IVM' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    # company_name は md5sum カラムあり
    "company_name":     "UPDATE {table} SET md5sum = 'ivm_test_md5' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "person_info":      "UPDATE {table} SET info = left(info,50) || '_t' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "char_name":        "UPDATE {table} SET md5sum = 'ivm_test_md5' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "info_type":        "UPDATE {table} SET info = info WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "company_type":     "UPDATE {table} SET kind = kind WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "kind_type":        "UPDATE {table} SET kind = kind WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "link_type":        "UPDATE {table} SET link = link WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "role_type":        "UPDATE {table} SET role = role WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "aka_name":         "UPDATE {table} SET md5sum = md5sum WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "aka_title":        "UPDATE {table} SET md5sum = md5sum WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "complete_cast":    "UPDATE {table} SET status_id = status_id WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "movie_info_idx":   "UPDATE {table} SET info = left(info,50) || '_t' WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "comp_cast_type":   "UPDATE {table} SET kind = kind WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
    "movie_link":       "UPDATE {table} SET link_type_id = link_type_id WHERE id = (SELECT id FROM {table} LIMIT 1 OFFSET {offset})",
}

# テーブルごとの更新頻度 (正規化、合計1.0)
# IMDB/JOB ベースの相対頻度として定義
DEFAULT_UPDATE_FREQUENCY: dict[str, float] = {
    "movie_keyword":   0.28,
    "cast_info":       0.22,
    "movie_info":      0.18,
    "movie_companies": 0.12,
    "title":           0.08,
    "name":            0.06,
    "keyword":         0.02,
    "company_name":    0.02,
    "person_info":     0.01,
    "char_name":       0.01,
}


@dataclass
class UpdateOperation:
    """1件の更新操作."""
    table_name: str
    op_type: str       # "UPDATE" | "INSERT" | "DELETE"
    sql: str           # BEGIN/ROLLBACK は含まない; サンプルテーブル名を使用
    offset: int = 0    # OFFSET 値 (試行ごとに変える)


@dataclass
class UpdateWorkload:
    """IMDB テーブルへの更新クエリ集合.

    サンプルテーブル名へのマッピングを受け取り、各テーブルに
    n_trials 件の UPDATE クエリを生成する。

    Args:
        table_mapping: {orig_name: sample_table_name}  (例: {"movie_keyword": "_ivm_s_movie_keyword"})
        n_trials:      1テーブルあたりの試行回数
    """
    table_mapping: dict[str, str]
    n_trials: int = 10
    ops: list[UpdateOperation] = field(default_factory=list)

    def __post_init__(self):
        self._generate()

    def _generate(self):
        self.ops.clear()
        for orig_table, sample_table in self.table_mapping.items():
            tmpl = _SAFE_UPDATE_TEMPLATES.get(orig_table)
            if tmpl is None:
                # 不明なテーブルはスキップ
                continue
            for i in range(self.n_trials):
                sql = tmpl.format(table=sample_table, offset=i * 100)
                self.ops.append(UpdateOperation(
                    table_name=orig_table,
                    op_type="UPDATE",
                    sql=sql,
                    offset=i * 100,
                ))

    def ops_for_table(self, table_name: str) -> list[UpdateOperation]:
        return [op for op in self.ops if op.table_name == table_name]

    @staticmethod
    def rename_sql_tables(sql: str, table_mapping: dict[str, str]) -> str:
        """SQL 内のテーブル名をサンプルテーブル名に置換する。

        テーブル名を置換するのは2文脈のみ:
          1. FROM/JOIN/カンマ直後のテーブル参照: "FROM name AS n", ", name AS n"
          2. テーブル修飾カラム参照: "name.id" → "sample.id"
        WHERE 句の非修飾カラム参照 ("name ~~ '%Angel%'" の name 等) は置換しない。
        これはテーブル名とカラム名が同名の場合 (name.name, title.title) に誤置換
        されるのを防ぐための対処。
        """
        parts = re.split(r"('(?:[^']|'')*')", sql)
        processed = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                processed.append(part)
            else:
                for orig, sample in sorted(table_mapping.items(), key=lambda x: -len(x[0])):
                    esc = re.escape(orig)
                    # 文脈1: FROM/JOIN/, の直後のテーブル参照
                    part = re.sub(
                        r'((?:FROM|JOIN|,)\s+)' + esc + r'\b',
                        lambda m, s=sample: m.group(1) + s,
                        part, flags=re.IGNORECASE
                    )
                    # 文脈2: テーブル修飾カラム参照 (orig.col)
                    part = re.sub(
                        r'(?<![.\w])' + esc + r'(?=\.)',
                        sample, part
                    )
                processed.append(part)
        return ''.join(processed)
