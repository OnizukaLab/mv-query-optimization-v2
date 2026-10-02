"""MV SQL の CTE フラット展開ユーティリティ.

ivm_experiment.py と ivm_cost_estimator.py の両方が使う共通関数。

non-leaf ノードは他の MV を参照するため、pg_ivm で IMMV を作成するには
すべての依存を展開してベーステーブルだけを参照する単一 SQL に変換する必要がある。

変換の3ステップ:
  1. collect_ctes_flat()    : 依存 MV をトポロジカル順にフラット CTE へ収集
  2. fix_leaked_aliases()   : CTE 内部エイリアスが外部クエリで使われている場合を修正
  3. expand_star_selects()  : cte.* を明示カラムへ展開してカラム名重複を防ぐ
"""
from __future__ import annotations

import re
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# 低レベルヘルパー
# ──────────────────────────────────────────────────────────────────────────────

def get_immv_body(node_id: str, plans: dict) -> Optional[str]:
    """MV の CREATE SQL から SELECT 本体を取り出す."""
    sql = plans.get(node_id, {}).get("[]", "")
    match = re.search(r'\bAS\b\s+(SELECT\b.+)', sql, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).rstrip(";").strip()
    return None


# ──────────────────────────────────────────────────────────────────────────────
# CTE フラット収集
# ──────────────────────────────────────────────────────────────────────────────

def collect_ctes_flat(root_id: str, plans: dict) -> tuple[dict, Optional[str]]:
    """root_id が依存する全 MV をフラットな CTE として収集する.

    旧実装は再帰的に CTE を入れ子にしていたため
    ``WITH n128 AS (WITH leaf AS (...) SELECT ...)`` のような
    ネスト構造になり PostgreSQL が拒否していた。
    本関数は全依存を依存順にトップレベルへ展開する。

    Returns:
        (ctes_ordered, root_body):
            ctes_ordered  … {mv_id: raw_body} (依存順, root_id 自身は含まない)
            root_body     … root_id の SELECT 本体
    """
    ctes: dict[str, str] = {}

    def collect(node_id: str, depth: int = 0) -> None:
        if depth > 10 or node_id in ctes:
            return
        body = get_immv_body(node_id, plans)
        if body is None:
            return
        # 依存先を先に追加 → トポロジカル順が保たれる
        for ref_id in re.findall(r'\b((?:leaf|non_leaf)_\d+)\b', body):
            collect(ref_id, depth + 1)
        ctes[node_id] = body

    root_body = get_immv_body(root_id, plans)
    if root_body is None:
        return {}, None

    # root_id 自体は最終 SELECT になるので依存先のみ収集
    for ref_id in re.findall(r'\b((?:leaf|non_leaf)_\d+)\b', root_body):
        collect(ref_id)

    return ctes, root_body


# ──────────────────────────────────────────────────────────────────────────────
# CTE エイリアス修正
# ──────────────────────────────────────────────────────────────────────────────

def fix_leaked_aliases(outer_body: str, ctes: dict[str, str]) -> str:
    """外部クエリで未定義になっている CTE 内部エイリアスを外部エイリアスへ置換する.

    例:
      non_leaf_129 の WHERE 句が ``k.id`` を使うが、``k`` は non_leaf_128 の内部
      エイリアス (``FROM keyword AS k``) であり外部スコープには存在しない。
      外部 FROM に ``non_leaf_128 AS non_leaf_128`` があるので
      ``k.id`` → ``non_leaf_128.id`` へ書き換える。
    """
    # 外部 FROM 句のエイリアスを収集: {alias: referenced_table_or_cte}
    outer_aliases: dict[str, str] = {}
    for m in re.finditer(r'\b(\w+)\s+AS\s+(\w+)', outer_body, re.IGNORECASE):
        outer_aliases[m.group(2)] = m.group(1)

    # 外部クエリ中の alias.col パターンをすべて収集
    used_aliases = set(re.findall(r'\b([a-z_][a-z0-9_]*)\.[a-z_]', outer_body, re.IGNORECASE))
    undefined = used_aliases - set(outer_aliases.keys())
    if not undefined:
        return outer_body

    # CTE ごとの内部 FROM エイリアスを収集: {inner_alias: cte_name}
    inner_to_cte: dict[str, str] = {}
    for cte_name, cte_body in ctes.items():
        for m in re.finditer(r'\b(\w+)\s+AS\s+(\w+)', cte_body, re.IGNORECASE):
            inner_to_cte[m.group(2)] = cte_name

    # 未定義エイリアスを対応する外部エイリアスへ置換
    fixed = outer_body
    for alias in undefined:
        cte_name = inner_to_cte.get(alias)
        if cte_name is None:
            continue
        # 外部 FROM で cte_name がどのエイリアスで参照されているか
        outer_alias = cte_name  # デフォルトは CTE 名そのまま
        for oa, tbl in outer_aliases.items():
            if tbl == cte_name:
                outer_alias = oa
                break
        fixed = re.sub(r'(?<![.\w])' + re.escape(alias) + r'\.', outer_alias + '.', fixed)

    return fixed


# ──────────────────────────────────────────────────────────────────────────────
# cte.* 展開
# ──────────────────────────────────────────────────────────────────────────────

def expand_star_selects(outer_body: str, ctes: dict[str, str]) -> str:
    """SELECT 句の ``cte_name.*`` を明示エイリアス付きカラムへ展開する.

    IMMV はカラム名が一意である必要があるため、
    ``table.*`` を ``table.col AS table_col`` 形式に展開して重複を防ぐ。
    例: ``non_leaf_128.*`` → ``non_leaf_128.id AS non_leaf_128_id, ...``
    """
    for cte_name, cte_body in ctes.items():
        star_pat = re.escape(cte_name) + r'\.\*'
        if not re.search(star_pat, outer_body):
            continue

        # CTE の SELECT 句から最初の FROM より前を取り出してカラム名を列挙
        sel_match = re.search(
            r'\bSELECT\b\s+(.+?)\s+\bFROM\b', cte_body, re.IGNORECASE | re.DOTALL
        )
        if not sel_match:
            continue

        col_names: list[str] = []
        for item in sel_match.group(1).split(','):
            item = item.strip()
            alias_m = re.search(r'\bAS\s+(\w+)\s*$', item, re.IGNORECASE)
            if alias_m:
                col_names.append(alias_m.group(1))
            else:
                col_m = re.search(r'(?:\w+\.)?(\w+)\s*$', item)
                if col_m:
                    col_names.append(col_m.group(1))

        if not col_names:
            continue

        # cte.* → cte.col AS cte_col (プレフィックス付きで衝突を回避)
        explicit = ', '.join(f'{cte_name}.{c} AS {cte_name}_{c}' for c in col_names)
        outer_body = re.sub(star_pat, explicit, outer_body)

    return outer_body


# ──────────────────────────────────────────────────────────────────────────────
# メインエントリポイント
# ──────────────────────────────────────────────────────────────────────────────

def expand_mv_sql(node_id: str, plans: dict) -> Optional[str]:
    """MV の SQL を CTE でフラットに展開してベーステーブルのみを参照する SQL を生成する.

    leaf ノード: SELECT 本体をそのまま返す。
    non-leaf ノード: 依存 MV を WITH 句でフラット展開 + エイリアス修正 + .* 展開 を適用。

    Returns:
        展開済み SELECT 本体（WITH 句を含む場合あり）。
        展開失敗時は None。
    """
    ctes, root_body = collect_ctes_flat(node_id, plans)
    if root_body is None:
        return None
    if not ctes:
        # leaf ノード: CTE なし、そのまま返す
        return root_body

    root_body = fix_leaked_aliases(root_body, ctes)
    root_body = expand_star_selects(root_body, ctes)

    cte_parts = [f"{mv_id} AS (\n  {sql}\n)" for mv_id, sql in ctes.items()]
    return "WITH " + ",\n".join(cte_parts) + "\n" + root_body
