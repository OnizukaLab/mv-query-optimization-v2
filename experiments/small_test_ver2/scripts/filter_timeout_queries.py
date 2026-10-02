"""タイムアウトしたクエリをクエリフォルダから除外するスクリプト。

使い方:
    python3 filter_timeout_queries.py \\
        --benchmark-json <sequential_benchmark_results.json> \\
        --src-dir  experiments/small_test_ver2/01_queries/cluster_55_25_26_3 \\
        --out-dir  experiments/small_test_ver2/01_queries/cluster_55_25_26_3_filtered \\
        --freq-name frequency_time_dependent_cluster_55.json

タイムアウト判定:
  success == False かつ error に "timeout" を含む
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="タイムアウトクエリの除外")
    parser.add_argument("--benchmark-json", required=True, help="sequential_benchmark_results.json")
    parser.add_argument("--src-dir", required=True, help="元クエリフォルダ (cluster_55_25_26_3 等)")
    parser.add_argument("--out-dir", required=True, help="出力先フォルダ")
    parser.add_argument(
        "--freq-name",
        default="frequency_time_dependent_cluster_55.json",
        help="頻度JSONのファイル名",
    )
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- タイムアウトしたクエリ名を収集 ---
    with open(args.benchmark_json, "r", encoding="utf-8") as f:
        bench = json.load(f)

    timeout_names: set[str] = set()
    for q in bench.get("queries", []):
        if not q.get("success", True):
            error = q.get("error", "") or ""
            if "timeout" in error.lower():
                # query_name は "82548" 等, ファイル名は "82548.sql"
                timeout_names.add(q["query_name"] + ".sql")

    print(f"[INFO] Timed-out queries found: {len(timeout_names)}")

    # --- タイムアウトしたSQLのnormalized内容セットを作成 ---
    # (src_dirのファイル名とbenchmarkのquery_nameが一致しないケースに備えて内容でも照合)
    timeout_norms: set[str] = set()
    for fname in timeout_names:
        # benchmarkはdir1のファイルを参照しているが、src_dirはmergedフォルダ
        # -> src_dirに同名ファイルがあればその内容を記録
        src_file = src_dir / fname
        if src_file.exists():
            timeout_norms.add(normalize_sql(src_file.read_text(encoding="utf-8")))

    print(f"[INFO] Timeout SQL contents identified: {len(timeout_norms)}")

    # --- SQLファイルをコピー（タイムアウトを除外）---
    excluded_fnames: set[str] = set()
    copied = 0
    for sql_file in sorted(src_dir.glob("*.sql")):
        norm = normalize_sql(sql_file.read_text(encoding="utf-8"))
        if norm in timeout_norms or sql_file.name in timeout_names:
            excluded_fnames.add(sql_file.name)
            continue
        shutil.copy2(sql_file, out_dir / sql_file.name)
        copied += 1

    print(f"[INFO] Copied SQL files: {copied}")
    print(f"[INFO] Excluded SQL files: {len(excluded_fnames)}")

    # --- 頻度JSONをコピー（除外クエリを削除）---
    freq_src = src_dir / args.freq_name
    if freq_src.exists():
        with freq_src.open("r", encoding="utf-8") as f:
            freq_data = json.load(f)

        original_queries = freq_data.get("queries", {})
        filtered_queries = {
            k: v
            for k, v in original_queries.items()
            if k not in excluded_fnames
        }

        removed_count = len(original_queries) - len(filtered_queries)
        freq_data["queries"] = filtered_queries
        freq_data["description"] = freq_data.get("description", "") + f" [filtered: {len(excluded_fnames)} timeout queries removed]"

        out_freq = out_dir / args.freq_name
        out_freq.write_text(json.dumps(freq_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] Freq JSON: {len(original_queries)} -> {len(filtered_queries)} entries (removed {removed_count})")
    else:
        print(f"[WARN] Freq JSON not found: {freq_src}")

    print(f"\n[OK] Output: {out_dir}")
    print(f"[OK] Excluded queries:")
    for fname in sorted(excluded_fnames):
        print(f"       {fname}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
