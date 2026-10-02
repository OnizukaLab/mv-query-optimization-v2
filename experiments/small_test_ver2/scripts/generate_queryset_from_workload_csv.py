"""workload.csv から small_test_ver2 用クエリセットを生成する。

生成物:
- 01_queries/<query_set>/*.sql
- 01_queries/<query_set>/frequency_time_dependent<suffix>.json

主用途:
- 期間を絞った時系列ワークロードの作成
- CEB系クエリを軽量化 (SELECT COUNT(*) 化 + ORDER BY/HAVING/GROUP BY/LIMIT 除去)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def normalize_sql_key(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def ensure_semicolon(sql: str) -> str:
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql


def protect_single_quoted_literals(sql: str) -> tuple[str, list[str]]:
    literals: list[str] = []

    def replace_literal(match: re.Match[str]) -> str:
        literals.append(match.group(0))
        return f"__SQL_LITERAL_{len(literals)-1}__"

    protected = re.sub(r"'(?:[^']|'')*'", replace_literal, sql, flags=re.DOTALL)
    return protected, literals


def restore_single_quoted_literals(sql: str, literals: list[str]) -> str:
    restored = sql
    for i, literal in enumerate(literals):
        restored = restored.replace(f"__SQL_LITERAL_{i}__", literal)
    return restored


def strip_trailing_clauses_outside_literals(sql: str) -> str:
    protected, literals = protect_single_quoted_literals(sql)

    stripped = re.sub(r"\s+having\s+.+$", "", protected, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"\s+group\s+by\s+.+$", "", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"\s+order\s+by\s+.+$", "", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"\s+limit\s+\d+\s*$", "", stripped, flags=re.IGNORECASE)

    return restore_single_quoted_literals(stripped, literals)


def format_sql_like_cluster53(sql: str) -> str:
    sql = ensure_semicolon(sql)
    s = re.sub(r"\s+", " ", sql).strip()
    s = s[:-1].strip()  # remove trailing ';' temporarily

    upper = s.upper()
    from_pos = upper.find(" FROM ")
    where_pos = upper.find(" WHERE ")

    select_part = s
    from_part = ""
    where_part = ""

    if from_pos >= 0:
        select_part = s[:from_pos].strip()
        if where_pos >= 0:
            from_part = s[from_pos + 6:where_pos].strip()
            where_part = s[where_pos + 7:].strip()
        else:
            from_part = s[from_pos + 6:].strip()

    lines: list[str] = []

    # SELECT 句
    if select_part.upper().startswith("SELECT ") and "," in select_part:
        body = select_part[7:].strip()
        cols = [c.strip() for c in body.split(",")]
        if cols:
            for idx, c in enumerate(cols):
                suffix = "," if idx < len(cols) - 1 else ""
                if idx == 0:
                    lines.append(f"SELECT {c}{suffix}")
                else:
                    lines.append(f"       {c}{suffix}")
        else:
            lines.append(select_part)
    else:
        lines.append(select_part)

    # FROM 句
    if from_part:
        tables = [t.strip() for t in from_part.split(",")]
        if tables:
            for idx, t in enumerate(tables):
                suffix = "," if idx < len(tables) - 1 else ""
                if idx == 0:
                    lines.append(f"FROM {t}{suffix}")
                else:
                    lines.append(f"     {t}{suffix}")

    # WHERE 句
    if where_part:
        conds = [c.strip() for c in re.split(r"\sAND\s", where_part)]
        if conds:
            lines.append(f"WHERE {conds[0]}")
            for c in conds[1:]:
                lines.append(f"  AND {c}")

    return "\n".join(lines) + ";\n"


def is_likely_ceb(row: dict[str, str], sql: str) -> bool:
    num_aggs = row.get("num_aggregations", "")
    try:
        if float(num_aggs) > 0:
            return True
    except ValueError:
        pass

    low = sql.lower()
    return (
        " group by " in low
        or " having " in low
        or " order by " in low
    )


def rewrite_ceb_to_count(sql: str) -> str:
    body = sql.strip().rstrip(";")
    low = body.lower()
    from_match = re.search(r"\bfrom\b", low)
    if not from_match:
        return ensure_semicolon(sql)

    rewritten = "SELECT COUNT(*) " + body[from_match.start():]
    rewritten = strip_trailing_clauses_outside_literals(rewritten)

    return ensure_semicolon(rewritten)


def has_distinct_on(sql: str) -> bool:
    return re.search(r"\bDISTINCT\s+ON\s*\(", sql, flags=re.IGNORECASE) is not None


def rewrite_to_count(sql: str) -> str:
    body = sql.strip().rstrip(";")
    low = body.lower()
    from_match = re.search(r"\bfrom\b", low)
    if not from_match:
        return ensure_semicolon(sql)

    rewritten = "SELECT COUNT(*) " + body[from_match.start():]
    rewritten = strip_trailing_clauses_outside_literals(rewritten)

    return ensure_semicolon(rewritten)


def build_time_bins(start: datetime, end: datetime, step_hours: int) -> list[tuple[datetime, datetime]]:
    bins: list[tuple[datetime, datetime]] = []
    cur = start
    step = timedelta(hours=step_hours)
    while cur <= end:
        nxt = cur + step
        bins.append((cur, min(nxt, end + timedelta(microseconds=1))))
        cur = nxt
    return bins


def bin_index(ts: datetime, bins: list[tuple[datetime, datetime]]) -> int:
    for idx, (start, end_exclusive) in enumerate(bins):
        if start <= ts < end_exclusive:
            return idx
    return -1


def derive_name_from_benchmark_filepath(filepath: str) -> str:
    path = filepath.replace("\\", "/")
    return Path(path).name


def ensure_unique_filename(candidate: str, used_names: set[str]) -> str:
    if candidate not in used_names:
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix or ".sql"
    i = 2
    while True:
        alt = f"{stem}_{i}{suffix}"
        if alt not in used_names:
            return alt
        i += 1


def load_mappings_from_queries_json(
    queries_json_path: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, bool], dict[str, bool]]:
    with queries_json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    hash_to_name: dict[str, str] = {}
    qid_to_name: dict[str, str] = {}
    hash_to_is_ceb: dict[str, bool] = {}
    qid_to_is_ceb: dict[str, bool] = {}
    for entry in data:
        redset_query = entry.get("redset_query", {})
        qid = str(redset_query.get("query_id", "")).strip()
        qhash = str(entry.get("query_hash", "")).strip()
        filepath = str(entry.get("filepath", "")).strip()
        if not qid or not filepath:
            continue

        name = derive_name_from_benchmark_filepath(filepath)
        qid_to_name[qid] = name
        is_ceb_source = "/ceb/" in filepath.replace("\\", "/")
        qid_to_is_ceb[qid] = is_ceb_source
        if qhash:
            hash_to_name[qhash] = name
            hash_to_is_ceb[qhash] = is_ceb_source
    return hash_to_name, qid_to_name, hash_to_is_ceb, qid_to_is_ceb


def main() -> int:
    parser = argparse.ArgumentParser(description="workload.csv から query_set を生成")
    parser.add_argument("--csv-path", required=True, help="入力 workload.csv")
    parser.add_argument("--output-query-dir", required=True, help="出力先 01_queries/<query_set> ディレクトリ")
    parser.add_argument("--start", required=True, help="開始時刻 (例: 2024-05-25T00:00:00)")
    parser.add_argument("--end", required=True, help="終了時刻 (例: 2024-05-26T23:59:59)")
    parser.add_argument("--step-hours", type=int, default=4, help="タイムステップ時間(時)")
    parser.add_argument("--freq-suffix", default="", help="frequency_time_dependent<suffix>.json の suffix")
    parser.add_argument("--sanitize-ceb", action="store_true", help="CEB系クエリを COUNT(*) 化")
    parser.add_argument(
        "--sanitize-distinct-on",
        action="store_true",
        help="DISTINCT ON を含むクエリを SELECT COUNT(*) 化",
    )
    parser.add_argument("--query-prefix", default="q", help="出力SQL名プレフィックス")
    parser.add_argument(
        "--queries-json-path",
        default="",
        help="Redbench の queries.json (query_id から JOB/CEB ファイル名を引く)",
    )
    parser.add_argument(
        "--preserve-filenames-from-dir",
        default="",
        help="元ファイル名を引き継ぐための参照ディレクトリ (01_queries/cluster_53 など)",
    )
    parser.add_argument("--clean-output", action="store_true", help="出力先の既存 .sql を削除してから生成")
    parser.add_argument("--freq-only", action="store_true", help="SQLファイルを出力せず頻度JSONのみを出力する")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    out_dir = Path(args.output_query_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.clean_output:
        for old_sql in out_dir.glob("*.sql"):
            old_sql.unlink()

    ref_name_map: dict[str, str] = {}
    used_ref_names: set[str] = set()
    used_generated_names: set[str] = set()
    if args.preserve_filenames_from_dir:
        ref_dir = Path(args.preserve_filenames_from_dir)
        if ref_dir.exists():
            for ref_sql in sorted(ref_dir.glob("*.sql")):
                raw = ref_sql.read_text(encoding="utf-8")
                key = normalize_sql_key(raw)
                if key not in ref_name_map:
                    ref_name_map[key] = ref_sql.name

    hash_to_benchmark_name: dict[str, str] = {}
    qid_to_benchmark_name: dict[str, str] = {}
    hash_to_is_ceb: dict[str, bool] = {}
    qid_to_is_ceb: dict[str, bool] = {}
    if args.queries_json_path:
        (
            hash_to_benchmark_name,
            qid_to_benchmark_name,
            hash_to_is_ceb,
            qid_to_is_ceb,
        ) = load_mappings_from_queries_json(Path(args.queries_json_path))

    start_ts = parse_ts(args.start)
    end_ts = parse_ts(args.end)
    if end_ts < start_ts:
        raise ValueError("--end must be >= --start")

    bins = build_time_bins(start_ts, end_ts, args.step_hours)
    n_bins = len(bins)

    # dedupe_key -> output filename
    # - default: canonical SQL
    # - queries.json がある場合: source query name（同名は同一クエリ扱い）
    sql_to_file: OrderedDict[str, str] = OrderedDict()
    file_to_sql: dict[str, str] = {}
    file_to_freq: dict[str, list[int]] = {}
    file_to_is_ceb: dict[str, bool] = {}
    name_source_counter = {"queries_json_hash": 0, "queries_json_qid": 0, "reference_dir": 0, "query_id": 0, "fallback": 0}

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_ts = row.get("arrival_timestamp", "")
            raw_sql = (row.get("sql", "") or "").strip()
            if not raw_ts or not raw_sql:
                continue

            ts = parse_ts(raw_ts)
            if ts < start_ts or ts > end_ts:
                continue

            idx = bin_index(ts, bins)
            if idx < 0:
                continue

            qid = (row.get("query_id", "") or "").strip()
            exact_hash = (row.get("exact_repetition_hash", "") or "").strip()
            source_is_ceb = None
            if exact_hash in hash_to_is_ceb:
                source_is_ceb = hash_to_is_ceb[exact_hash]
            elif qid in qid_to_is_ceb:
                source_is_ceb = qid_to_is_ceb[qid]

            raw_sql_with_semicolon = ensure_semicolon(raw_sql)
            if source_is_ceb is None:
                source_is_ceb = is_likely_ceb(row, raw_sql_with_semicolon)

            raw_key = normalize_sql_key(raw_sql)

            preferred_name = ""
            if exact_hash in hash_to_benchmark_name:
                preferred_name = hash_to_benchmark_name[exact_hash]
            elif qid in qid_to_benchmark_name:
                preferred_name = qid_to_benchmark_name[qid]

            # queries.json がある場合、同じ source 名は同一クエリとして集約
            dedupe_key = raw_key
            if args.queries_json_path and preferred_name:
                dedupe_key = f"name::{preferred_name.lower()}"

            if dedupe_key not in sql_to_file:
                fname = ""

                if exact_hash in hash_to_benchmark_name:
                    candidate = hash_to_benchmark_name[exact_hash]
                    candidate = ensure_unique_filename(candidate, used_generated_names | used_ref_names)
                    fname = candidate
                    name_source_counter["queries_json_hash"] += 1

                if not fname and qid in qid_to_benchmark_name:
                    candidate = qid_to_benchmark_name[qid]
                    candidate = ensure_unique_filename(candidate, used_generated_names | used_ref_names)
                    fname = candidate
                    name_source_counter["queries_json_qid"] += 1

                if not fname and raw_key in ref_name_map and ref_name_map[raw_key] not in used_ref_names:
                    fname = ref_name_map[raw_key]
                    used_ref_names.add(fname)
                    name_source_counter["reference_dir"] += 1

                if not fname:
                    if qid:
                        candidate = f"{qid}.sql"
                        if candidate not in used_generated_names and candidate not in used_ref_names:
                            fname = candidate
                            name_source_counter["query_id"] += 1
                    if not fname:
                        fname = f"{args.query_prefix}{len(sql_to_file)+1:04d}.sql"
                        name_source_counter["fallback"] += 1
                used_generated_names.add(fname)
                sql_to_file[dedupe_key] = fname
                file_to_sql[fname] = raw_sql_with_semicolon
                file_to_freq[fname] = [0] * n_bins
                file_to_is_ceb[fname] = bool(source_is_ceb)

            fname = sql_to_file[dedupe_key]
            file_to_freq[fname][idx] += 1

    if not args.freq_only:
        for fname, sql in file_to_sql.items():
            sql_to_write = ensure_semicolon(sql)
            if args.sanitize_ceb and file_to_is_ceb.get(fname, False):
                sql_to_write = rewrite_ceb_to_count(sql_to_write)
            if args.sanitize_distinct_on and has_distinct_on(sql_to_write):
                sql_to_write = rewrite_to_count(sql_to_write)
            formatted_sql = format_sql_like_cluster53(sql_to_write)
            (out_dir / fname).write_text(formatted_sql, encoding="utf-8")

    freq_payload = {
        "description": f"Generated from {csv_path.name} ({start_ts.isoformat()} to {end_ts.isoformat()}, {args.step_hours}h bins)",
        "note": "queries format: filename -> frequency list per timestep",
        "queries": dict(sorted(file_to_freq.items(), key=lambda x: x[0])),
    }

    freq_name = f"frequency_time_dependent{args.freq_suffix}.json"
    freq_path = out_dir / freq_name
    freq_path.write_text(json.dumps(freq_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] output_dir: {out_dir}")
    print(f"[OK] queries: {len(file_to_sql)}")
    print(f"[OK] timesteps: {n_bins}")
    print(f"[OK] frequency_file: {freq_path}")
    print(f"[OK] name_sources: {name_source_counter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
