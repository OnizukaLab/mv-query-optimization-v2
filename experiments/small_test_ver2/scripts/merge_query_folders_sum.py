"""2つのクエリフォルダを1つにマージするスクリプト（頻度を合算版）。

- 同じSQL内容のファイルは1つに集約（ファイル名はdir1優先）
- 頻度JSONはタイムステップを増やさず、同じタイムステップの要素同士を加算（sum）する
- dir1にしかないクエリ: freq_dir1
- dir2にしかないクエリ: freq_dir2
- 両方にあるクエリ: freq_dir1 + freq_dir2 (要素ごとの和)

使い方:
    python3 experiments/small_test_ver2/scripts/merge_query_folders_sum.py \
        --dir1 experiments/small_test_ver2/01_queries/cluster_55_join_12 \
        --dir2 experiments/small_test_ver2/01_queries/cluster_55_join_05_25 \
        --out  experiments/small_test_ver2/01_queries/cluster_55_join_12_25 \
        --freq-name frequency_time_dependent.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def load_freq_json(path: Path) -> dict[str, list[int]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("queries", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="2つのクエリフォルダをマージ（頻度合算版）")
    parser.add_argument("--dir1", required=True, help="1つ目のクエリフォルダ")
    parser.add_argument("--dir2", required=True, help="2つ目のクエリフォルダ")
    parser.add_argument("--out", required=True, help="出力先フォルダ")
    parser.add_argument(
        "--freq-name",
        default="frequency_time_dependent.json",
        help="頻度JSONのファイル名 (両フォルダ共通)",
    )
    parser.add_argument("--freq-name1", help="dir1の頻度JSON名 (指定がない場合は --freq-name を使用)")
    parser.add_argument("--freq-name2", help="dir2の頻度JSON名 (指定がない場合は --freq-name を使用)")
    args = parser.parse_args()

    dir1 = Path(args.dir1)
    dir2 = Path(args.dir2)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 頻度JSONを読み込む ---
    freq_name1 = args.freq_name1 if args.freq_name1 else args.freq_name
    freq_name2 = args.freq_name2 if args.freq_name2 else args.freq_name
    freq1_path = dir1 / freq_name1
    freq2_path = dir2 / freq_name2
    freq1: dict[str, list[int]] = load_freq_json(freq1_path) if freq1_path.exists() else {}
    freq2: dict[str, list[int]] = load_freq_json(freq2_path) if freq2_path.exists() else {}


    # タイムステップ数を確認
    n1 = len(next(iter(freq1.values()), []))
    n2 = len(next(iter(freq2.values()), []))
    print(f"[INFO] dir1 timesteps: {n1}, dir2 timesteps: {n2}")
    
    max_steps = max(n1, n2)

    # --- SQLファイルを読み込み、内容でdedup ---
    # normalized_sql -> (canonical_fname, sql_content)
    sql_to_canonical: dict[str, tuple[str, str]] = {}

    # dir1のファイル名を正引き: fname -> normalized_sql
    dir1_fname_to_norm: dict[str, str] = {}

    print(f"[INFO] Reading dir1: {dir1}")
    for sql_file in sorted(dir1.glob("*.sql")):
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        fname = sql_file.name
        dir1_fname_to_norm[fname] = norm
        if norm not in sql_to_canonical:
            sql_to_canonical[norm] = (fname, raw)

    # dir2のファイル名を正引き: fname -> canonical_fname (in sql_to_canonical)
    dir2_fname_to_canonical: dict[str, str] = {}

    print(f"[INFO] Reading dir2: {dir2}")
    for sql_file in sorted(dir2.glob("*.sql")):
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        fname = sql_file.name
        if norm not in sql_to_canonical:
            # dir2にしかないクエリ → dir2のファイル名を使う
            sql_to_canonical[norm] = (fname, raw)
        canonical_fname = sql_to_canonical[norm][0]
        dir2_fname_to_canonical[fname] = canonical_fname

    print(f"[INFO] Unique queries total: {len(sql_to_canonical)}")

    # --- 頻度を結合（要素ごとの合算） ---
    # canonical_fname -> [freq_dir1 + freq_dir2]
    merged_freq: dict[str, list[int]] = {}

    # dir1の頻度を登録
    for fname, freqs in freq1.items():
        norm = dir1_fname_to_norm.get(fname)
        if norm is None:
            continue
        canonical = sql_to_canonical[norm][0]
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps
        for i, v in enumerate(freqs):
            if i < max_steps:
                merged_freq[canonical][i] += v

    # dir2の頻度を登録
    for fname, freqs in freq2.items():
        sql_file = dir2 / fname
        if not sql_file.exists():
            continue
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        canonical = sql_to_canonical[norm][0]
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps
        for i, v in enumerate(freqs):
            if i < max_steps:
                merged_freq[canonical][i] += v

    # freqJSONに載っていないクエリも補完
    for norm, (canonical, _) in sql_to_canonical.items():
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps

    # --- SQLファイルを出力 ---
    for norm, (canonical, raw) in sql_to_canonical.items():
        (out_dir / canonical).write_text(raw, encoding="utf-8")

    print(f"[INFO] SQL files written: {len(sql_to_canonical)}")

    # --- 頻度JSONを出力 ---
    freq_payload = {
        "description": (
            f"Merged by SUMMING frequencies from {dir1.name} and {dir2.name} ({max_steps} steps)"
        ),
        "note": "queries format: filename -> frequency list per timestep",
        "queries": dict(sorted(merged_freq.items())),
    }
    out_freq_path = out_dir / args.freq_name
    out_freq_path.write_text(json.dumps(freq_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Frequency JSON written: {out_freq_path}")
    print(f"[INFO] Total timesteps: {max_steps}")

    print(f"[OK] Done. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
