"""2つのクエリフォルダを1つにマージするスクリプト。

- 同じSQL内容のファイルは1つに集約（ファイル名はdir1優先）
- 頻度JSONはタイムステップを結合（dir1の12ステップ + dir2の12ステップ = 24ステップ）
- dir1にしかないクエリ: [freq_dir1..., 0, 0, ...(dir2分)]
- dir2にしかないクエリ: [0, 0, ...(dir1分), freq_dir2...]

使い方:
    python3 merge_query_folders.py \\
        --dir1 experiments/small_test_ver2/01_queries/cluster_55_25_3 \\
        --dir2 experiments/small_test_ver2/01_queries/cluster_55_26_3 \\
        --out  experiments/small_test_ver2/01_queries/cluster_55_25_26_3 \\
        --freq-name frequency_time_dependent_cluster_55.json
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
    parser = argparse.ArgumentParser(description="2つのクエリフォルダをマージ")
    parser.add_argument("--dir1", required=True, help="1日目のクエリフォルダ (例: cluster_55_25_3)")
    parser.add_argument("--dir2", required=True, help="2日目のクエリフォルダ (例: cluster_55_26_3)")
    parser.add_argument("--out", required=True, help="出力先フォルダ")
    parser.add_argument(
        "--freq-name",
        default="frequency_time_dependent_cluster_55.json",
        help="頻度JSONのファイル名 (両フォルダ共通)",
    )
    args = parser.parse_args()

    dir1 = Path(args.dir1)
    dir2 = Path(args.dir2)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 頻度JSONを読み込む ---
    freq1_path = dir1 / args.freq_name
    freq2_path = dir2 / args.freq_name
    freq1: dict[str, list[int]] = load_freq_json(freq1_path) if freq1_path.exists() else {}
    freq2: dict[str, list[int]] = load_freq_json(freq2_path) if freq2_path.exists() else {}

    # タイムステップ数を確認
    n1 = len(next(iter(freq1.values()), []))
    n2 = len(next(iter(freq2.values()), []))
    print(f"[INFO] dir1 timesteps: {n1}, dir2 timesteps: {n2}")

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

    # --- 頻度を結合 ---
    # canonical_fname -> [freq_dir1(12 steps), freq_dir2(12 steps)]
    merged_freq: dict[str, list[int]] = {}

    # dir1の頻度を登録
    for fname, freqs in freq1.items():
        norm = dir1_fname_to_norm.get(fname)
        if norm is None:
            # freqJSONにあるがSQLファイルが存在しない場合はスキップ
            continue
        canonical = sql_to_canonical[norm][0]
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * n1 + [0] * n2
        for i, v in enumerate(freqs):
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
            merged_freq[canonical] = [0] * n1 + [0] * n2
        for i, v in enumerate(freqs):
            merged_freq[canonical][n1 + i] += v

    # dir1にあってfreqJSONに載っていないクエリも補完
    for norm, (canonical, _) in sql_to_canonical.items():
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * (n1 + n2)

    # --- SQLファイルを出力 ---
    for norm, (canonical, raw) in sql_to_canonical.items():
        (out_dir / canonical).write_text(raw, encoding="utf-8")

    print(f"[INFO] SQL files written: {len(sql_to_canonical)}")

    # --- 頻度JSONを出力 ---
    freq_payload = {
        "description": (
            f"Merged from {dir1.name} ({n1} steps) + {dir2.name} ({n2} steps) = {n1+n2} steps"
        ),
        "note": "queries format: filename -> frequency list per timestep",
        "queries": dict(sorted(merged_freq.items())),
    }
    out_freq_path = out_dir / args.freq_name
    out_freq_path.write_text(json.dumps(freq_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Frequency JSON written: {out_freq_path}")
    print(f"[INFO] Total timesteps: {n1 + n2}")

    # --- サマリー ---
    only_dir1 = sum(
        1 for norm, (canonical, _) in sql_to_canonical.items()
        if canonical in freq1 or canonical in dir1_fname_to_norm.values()
        and canonical not in dir2_fname_to_canonical.values()
    )
    print(f"[OK] Done. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
