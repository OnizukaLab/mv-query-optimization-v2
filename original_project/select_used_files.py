import os
import csv
import shutil
from collections import Counter

# workloadsディレクトリ内の全サブフォルダ（0%-10%, 10%-20%, ... 90%-100%）を取得
workloads_root = "dataset/redbench/workloads"
subfolders = [os.path.join(workloads_root, d) for d in os.listdir(workloads_root) if os.path.isdir(os.path.join(workloads_root, d))]

# 各サブフォルダ内の3種類のCSVファイルをリストアップ
csv_files = []
for folder in subfolders:
    for name in ["high_variability.csv", "mid_variability.csv", "low_variability.csv"]:
        csv_path = os.path.join(folder, name)
        if os.path.isfile(csv_path):
            csv_files.append(csv_path)

# SQLファイルのルートディレクトリ
sql_root = "dataset/redbench"

# 出力先ディレクトリ
output_root = "used_queries"
os.makedirs(os.path.join(output_root, "job"), exist_ok=True)
os.makedirs(os.path.join(output_root, "ceb"), exist_ok=True)

used_files = set()
job_files = []
ceb_files = []

# CSVからファイルパスを抽出
for csv_file in csv_files:
    with open(csv_file, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            used_files.add(row["filepath"])
            if "/job/" in row["filepath"]:
                job_files.append(row["filepath"])
            elif "/ceb/" in row["filepath"]:
                ceb_files.append(row["filepath"])

# クエリ数を標準出力
print(f"全クエリ数: {len(job_files) + len(ceb_files)}")
print(f"jobクエリ数: {len(job_files)}")
print(f"cebクエリ数: {len(ceb_files)}")

# 重複数をカウント
job_counter = Counter(job_files)
ceb_counter = Counter(ceb_files)

job_duplicates = {k: v for k, v in job_counter.items() if v > 1}
ceb_duplicates = {k: v for k, v in ceb_counter.items() if v > 1}

print(f"job重複クエリ数: {len(job_duplicates)}")
print(f"ceb重複クエリ数: {len(ceb_duplicates)}")

# 重複情報をCSVに出力
job_dup_csv = os.path.join(output_root, "job", "job_duplicates.csv")
ceb_dup_csv = os.path.join(output_root, "ceb", "ceb_duplicates.csv")

with open(job_dup_csv, "w", newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["filepath", "count"])
    for k, v in job_duplicates.items():
        writer.writerow([k, v])

with open(ceb_dup_csv, "w", newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["filepath", "count"])
    for k, v in ceb_duplicates.items():
        writer.writerow([k, v])

# ファイルをコピー
for rel_path in used_files:
    abs_path = os.path.join(sql_root, rel_path)
    if not os.path.isfile(abs_path):
        print(f"Not found: {abs_path}")
        continue
    if "/job/" in rel_path:
        dest_dir = os.path.join(output_root, "job")
    elif "/ceb/" in rel_path:
        dest_dir = os.path.join(output_root, "ceb")
    else:
        continue
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(rel_path))
    shutil.copy2(abs_path, dest_path)
    # print(f"Copied: {abs_path} -> {dest_path}")