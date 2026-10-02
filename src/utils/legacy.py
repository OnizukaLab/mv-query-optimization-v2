"""Legacy utility functions for backward compatibility."""

import os
import re
from pathlib import Path


def get_all_job_queries(source_path: str) -> tuple[list[str], dict[str, int]]:
    """
    Get all JOB query JSON files from the directory.
    
    Args:
        source_path: Path to the JSON files directory
        
    Returns:
        Tuple of (query_paths, query_count_dict)
        - query_paths: List of all JOB JSON files
        - query_count_dict: Dictionary with count 1 for each file
    """
    query_paths = []
    query_count = {}
    
    job_dir = Path(source_path) / "job"
    if not job_dir.exists():
        return [], {}
    
    for json_file in sorted(job_dir.glob("*.json")):
        query_path = str(json_file)
        query_paths.append(query_path)
        query_count[query_path] = 1
    
    return query_paths, query_count


def get_all_ceb_queries(source_path: str, template: str = "1a", limit: int = None) -> tuple[list[str], dict[str, int]]:
    """
    Get all CEB query JSON files from the directory for a specific template.
    
    Args:
        source_path: Path to the JSON files directory (e.g., dataset/RED_JSON)
        template: CEB template to load (e.g., "1a", "2a", "3b")
        limit: Maximum number of queries to load (None = all)
        
    Returns:
        Tuple of (query_paths, query_count_dict)
        - query_paths: List of all CEB JSON files for the template
        - query_count_dict: Dictionary with count 1 for each file
    """
    query_paths = []
    query_count = {}
    
    ceb_dir = Path(source_path) / "ceb" / template
    if not ceb_dir.exists():
        print(f"Warning: CEB directory not found: {ceb_dir}")
        return [], {}
    
    # 自然順ソートでファイルを取得
    all_files = sorted(ceb_dir.glob("*.json"), key=lambda f: natural_sort_key(f.name))
    if limit is not None:
        all_files = all_files[:limit]
    for json_file in all_files:
        query_path = str(json_file)
        query_paths.append(query_path)
        query_count[query_path] = 1
    
    if limit is not None:
        print(f"CEB query limit applied: {len(query_paths)}/{len(list(ceb_dir.glob('*.json')))} queries loaded")
    
    return query_paths, query_count


def get_red_queries(
    source_path: str, workloads_dir: str, get_ceb: bool = False
) -> tuple[list[str], dict[str, int]]:
    """
    Get all query JSON files used in RedBench workloads.

    Args:
        source_path: Path to the JSON files
        workloads_dir: Path to the RedBench workloads directory
        get_ceb: If False, returns JOB queries only; if True, returns CEB queries

    Returns:
        Tuple of (query_paths, query_count_dict)
        - query_paths: List of all JSON files used in redbench
        - query_count_dict: Dictionary with number of occurrences of each file
    """
    query_paths = []
    query_count = {}

    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename)) as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path + "/job/" + line.split(",")[0].split("/")[-1]
                    query_path = query_path.split(".")[0] + ".json"
                else:
                    query_path = source_path + "/" + "/".join(line.split(",")[0].split("/")[2:])
                    query_path = query_path.split(".")[0] + ".json"

                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue

                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


def get_red_queries_sql(
    source_path: str, workloads_dir: str, get_ceb: bool = False
) -> tuple[list[str], dict[str, int]]:
    """
    Get all query SQL files used in RedBench workloads.

    Args:
        source_path: Path to the SQL files
        workloads_dir: Path to the RedBench workloads directory
        get_ceb: If False, returns JOB queries only; if True, returns CEB queries

    Returns:
        Tuple of (query_paths, query_count_dict)
        - query_paths: List of all SQL files used in redbench
        - query_count_dict: Dictionary with number of occurrences of each file
    """
    query_paths = []
    query_count = {}

    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename)) as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path + "/job/" + line.split(",")[0].split("/")[-1]
                else:
                    query_path = source_path + "/" + "/".join(line.split(",")[0].split("/")[2:])

                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue

                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


def natural_sort_key(s: str) -> list:
    """
    Natural sorting key for strings with numbers.

    Args:
        s: String to create sort key for

    Returns:
        List of mixed integers and strings for natural sorting

    Example:
        >>> sorted(['file1.txt', 'file10.txt', 'file2.txt'], key=natural_sort_key)
        ['file1.txt', 'file2.txt', 'file10.txt']
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", s)]


def get_red_queries_to_file(
    source_path: str,
    workloads_dir: str,
    get_ceb: bool = False,
    output_file: str = "red_queries.csv",
) -> tuple[list[str], dict[str, int]]:
    """
    Get all query JSON files for RedBench and write to CSV file.

    This function writes a CSV file with all queries used and how many times
    they are used in redbench.

    Args:
        source_path: Path to the JSON files
        workloads_dir: Path to the RedBench workloads directory
        get_ceb: If False, returns JOB queries only; if True, returns CEB queries
        output_file: Output CSV file path (default: "red_queries.csv")

    Returns:
        Tuple of (query_paths, query_count_dict)
        - query_paths: Sorted list of all JSON files used in redbench
        - query_count_dict: Dictionary with number of occurrences of each file
    """
    query_paths = []
    query_count = {}

    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename)) as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path + "/job/" + line.split(",")[0].split("/")[-1]
                    query_path = query_path.split(".")[0] + ".json"
                else:
                    query_path = source_path + "/" + "/".join(line.split(",")[0].split("/")[2:])
                    query_path = query_path.split(".")[0] + ".json"

                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue

                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    # Sort naturally
    query_paths = sorted(query_paths, key=natural_sort_key)

    # Write to CSV
    with open(output_file, "w+", newline="") as f:
        for line in query_paths:
            f.write(line + "," + str(query_count[line]) + "\n")

    return query_paths, query_count
