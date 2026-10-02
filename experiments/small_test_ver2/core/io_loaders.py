"""I/O loaders for time-dependent optimization.

This module provides utilities to load JSON/pickle data required for
time-dependent materialized view optimization with migration costs.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import pickle
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def load_qp_inputs(base_dir: str, query_set: str = "job_like") -> dict:
    """
    Load optimization inputs from qp_class.pkl.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)

    Returns:
        Dictionary with keys:
            - s_num: Number of subqueries
            - node_list: List of node IDs
            - b_j: List of storage sizes for each MV candidate
            - u_ij: 2D list of utility (benefit) for query i using MV j
            - X: 2D list (J×J) of inclusion relationships
    """
    # Priority: time_dependent_output/qp_class.pkl (9 queries)
    pkl_path = os.path.join(base_dir, "03_parsed", query_set, "qp_class.pkl")

    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"qp_class.pkl not found in {pkl_path}")
    
    logger.info(f"Loading qp_class.pkl from {pkl_path}")

    with open(pkl_path, "rb") as pf:
        pkl = pickle.load(pf)
    
    # Extract attributes from pickle
    data = {}
    for k in ("s_num", "node_list", "m_cost", "b_j", "u_ij", "X", "q_s_list"):
        if hasattr(pkl, k):
            data[k] = getattr(pkl, k)
        elif isinstance(pkl, dict) and k in pkl:
            data[k] = pkl[k]

    # Fallback for missing fields
    node_list = data.get("node_list") or []
    J = len(node_list)
    I = len(data.get("u_ij") or []) or len(data.get("q_s_list") or [])

    data.setdefault("s_num", J)
    data.setdefault("b_j", data.get("b_j") or [1] * J)
    data.setdefault("u_ij", data.get("u_ij") or [[0.0] * J for _ in range(I or 1)])
    # X: inclusion matrix (J×J)
    data.setdefault("X", data.get("X") or [[0] * J for _ in range(J)])

    return {
        "s_num": int(data.get("s_num", J)),
        "node_list": node_list,
        "b_j": list(map(float, data.get("b_j", [1] * J))),
        "u_ij": data.get("u_ij"),
        "X": data.get("X"),
    }


def load_timesteps_and_frequencies(base_dir: str, query_set: str = "job_like", freq_suffix: str = "") -> Tuple[List[str], Dict[str, List[float]]]:
    """
    Extract timesteps and query frequencies from frequency_time_dependent.json.
    
    Supports two formats:
    1. New format: {"queries": {"1a.sql": [f0, f1, f2], ...}}
    2. Old format: {"timesteps": [{"time_id": "t0", "frequencies": {...}}, ...]}

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        query_set: Query set name (e.g., "job", "job_like", "explicit_join")
        freq_suffix: Frequency file suffix (e.g., "_16_2", "_16_4")

    Returns:
        Tuple of (timestep_names, frequency_dict)
        - timestep_names: List of timestep IDs (e.g., ["0", "1", "2"])
        - frequency_dict: Dict mapping timestep ID to list of query frequencies
    """
    freq_filename = f"frequency_time_dependent{freq_suffix}.json"
    freq_path = os.path.join(base_dir, "01_queries", query_set, freq_filename)
    if not os.path.exists(freq_path):
        logger.warning(f"frequency_time_dependent.json not found in {freq_path}, using defaults")
        return ["0", "1"], {"0": [1.0], "1": [1.0]}

    with open(freq_path, "r", encoding="utf-8") as f:
        freq_data = json.load(f)

    # Check for new format (queries key with list values)
    queries_data = freq_data.get("queries", {})
    if queries_data:
        logger.info(f"Loading frequencies from new format (queries-based)")
        
        # Helper for natural sort (to match QueryParser's behavior)
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", s)]
        
        # Get all query names sorted naturally
        query_names = sorted(queries_data.keys(), key=natural_sort_key)
        
        # Get number of timesteps from first query's frequency list
        if not query_names:
            logger.warning("No queries found in frequency_time_dependent.json")
            return ["0", "1"], {"0": [1.0], "1": [1.0]}
        
        first_query_freqs = queries_data[query_names[0]]
        num_timesteps = len(first_query_freqs)
        
        # Generate timestep names: "0", "1", "2", ...
        timesteps = [str(i) for i in range(num_timesteps)]
        
        # Build frequency_dict: {time_id: [freq for each query]}
        frequencies = {}
        for t_idx in range(num_timesteps):
            time_id = str(t_idx)
            freq_list = []
            for query_name in query_names:
                query_freqs = queries_data[query_name]
                if t_idx < len(query_freqs):
                    freq_list.append(float(query_freqs[t_idx]))
                else:
                    # Fallback if frequency list is shorter
                    freq_list.append(0.0)
            frequencies[time_id] = freq_list
        
        logger.info(f"Loaded {len(query_names)} queries with {num_timesteps} timesteps")
        return timesteps, frequencies
    
    # Fall back to old format (timesteps-based)
    timestep_data = freq_data.get("timesteps", [])
    if not timestep_data:
        logger.warning("No timesteps or queries found in frequency_time_dependent.json")
        return ["0", "1"], {"0": [1.0], "1": [1.0]}

    logger.info(f"Loading frequencies from old format (timesteps-based)")
    timesteps = []
    frequencies = {}

    for ts_entry in timestep_data:
        time_id = ts_entry.get("time_id")
        if not time_id:
            continue

        timesteps.append(time_id)
        frequencies_dict = ts_entry.get("frequencies", {})
        
        # Sort by query filename (query1.json, query2.json, ...)
        query_files = sorted(
            frequencies_dict.keys(), 
            key=lambda x: int(x.replace("query", "").replace(".json", ""))
        )
        freq_list = [float(frequencies_dict.get(qf, 1.0)) for qf in query_files]
        frequencies[time_id] = freq_list

    return timesteps, frequencies

# 今は使っていない
def load_query_frequency(
    base_dir: str, timesteps: List[str], query_count: int
) -> Dict[str, List[float]]:
    """
    DEPRECATED: Use load_timesteps_and_frequencies instead.
    
    Load query frequency for each timestep from frequency_time_dependent.json.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        timesteps: List of timestep names
        query_count: Number of queries (I)

    Returns:
        Dictionary mapping timestep name to list of frequencies (length I)
    """
    logger.warning("load_query_frequency is deprecated, use load_timesteps_and_frequencies")
    timesteps_loaded, frequencies = load_timesteps_and_frequencies(base_dir)
    
    # Ensure correct length for all timesteps
    result = {}
    for t in timesteps:
        if t in frequencies:
            freq_list = frequencies[t]
            if len(freq_list) < query_count:
                freq_list.extend([1.0] * (query_count - len(freq_list)))
            elif len(freq_list) > query_count:
                freq_list = freq_list[:query_count]
            result[t] = freq_list
        else:
            result[t] = [1.0] * query_count
    
    return result


def parse_migration_costs(
    base_dir: str, node_list: List[str], query_set: str = "job_like", migration_file: str = "migration_costs.json"
) -> Dict[int, List[Tuple[Tuple[int, ...], float]]]:
    """
    Parse migration costs JSON into recipe format.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        node_list: List of node IDs (from qp_class.pkl) for index mapping
        query_set: Query set name (e.g., "job_like", "explicit_join")
        migration_file: Name of migration cost file (e.g., "migration_costs.json" or "simple_migration_costs.json")

    Returns:
        Dictionary mapping j (MV index) to list of (recipe_tuple, cost)
        where recipe_tuple is a tuple of dependency indices.
    """

    path = os.path.join(base_dir, "04_migration", query_set, migration_file)

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    idx = {node_id: j for j, node_id in enumerate(node_list)}
    mig: Dict[int, List[Tuple[Tuple[int, ...], float]]] = {}

    for node_id, mapping in raw.items():
        j = idx.get(node_id)
        if j is None:
            logger.debug(f"Node {node_id} not found in node_list, skipping")
            continue

        recipes: List[Tuple[Tuple[int, ...], float]] = []
        for k_str, cost in mapping.items():
            try:
                ids = ast.literal_eval(k_str)
                if not isinstance(ids, list):
                    ids = []
            except Exception:
                ids = []

            dep_indices: List[int] = []
            for dep_node_id in ids:
                dep_j = idx.get(dep_node_id)
                if dep_j is not None:
                    dep_indices.append(dep_j)
                else:
                    logger.debug(f"Dependency {dep_node_id} not found in node_list for {node_id}")

            recipes.append((tuple(sorted(dep_indices)), float(cost)))

        # Add fallback empty recipe (full build) if not present
        if not any(len(r[0]) == 0 for r in recipes):
            logger.warning(f"Node {node_id} has no full-build recipe (empty list), adding with inf cost")
            recipes.append((tuple(), float("inf")))

        mig[j] = recipes

    return mig


def parse_migration_costs_and_sizes(
    base_dir: str, 
    node_list: List[str], 
    query_set: str = "job_like"
) -> Tuple[Dict[int, List[Tuple[Tuple[int, ...], float]]], List[float]]:
    """
    Parse migration costs JSON and extract both recipe costs and MV sizes.
    
    DEPRECATED: Use load_full_build_costs_and_sizes() for simplified optimization.
    This function is kept for backward compatibility with complex migration scenarios.
    
    This function loads from simple_migration_costs.json which contains
    enhanced data from Phase 5 including cost, rows, width, and size.
    
    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        node_list: List of node IDs (from qp_class.pkl) for index mapping
        query_set: Query set name (e.g., "job_like", "explicit_join")
    
    Returns:
        Tuple of (recipes_dict, size_list)
        - recipes_dict: Dictionary mapping j (MV index) to list of (recipe_tuple, cost)
        - size_list: List of sizes for each MV (indexed by j)
    """
    path = os.path.join(base_dir, "04_migration", query_set, "simple_migration_costs.json")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"simple_migration_costs.json not found at {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    
    idx = {node_id: j for j, node_id in enumerate(node_list)}
    mig: Dict[int, List[Tuple[Tuple[int, ...], float]]] = {}
    
    # Initialize size list with default values
    b_j = [1.0] * len(node_list)
    
    for node_id, mapping in raw.items():
        j = idx.get(node_id)
        if j is None:
            logger.debug(f"Node {node_id} not found in node_list, skipping")
            continue
        
        recipes: List[Tuple[Tuple[int, ...], float]] = []
        
        for k_str, data in mapping.items():
            try:
                ids = ast.literal_eval(k_str)
                if not isinstance(ids, list):
                    ids = []
            except Exception:
                ids = []
            
            # Extract cost from the data structure
            if isinstance(data, dict):
                cost = float(data.get("cost", 0.0))
                # Extract size from empty dependency recipe (full build from base tables)
                if len(ids) == 0:
                    size = float(data.get("size", 1.0))
                    b_j[j] = size
            else:
                # Fallback for old format (just cost as float)
                cost = float(data)
            
            dep_indices: List[int] = []
            for dep_node_id in ids:
                dep_j = idx.get(dep_node_id)
                if dep_j is not None:
                    dep_indices.append(dep_j)
                else:
                    logger.debug(f"Dependency {dep_node_id} not found in node_list for {node_id}")
            
            recipes.append((tuple(sorted(dep_indices)), cost))
        
        # Add fallback empty recipe (full build) if not present
        if not any(len(r[0]) == 0 for r in recipes):
            logger.warning(f"Node {node_id} has no full-build recipe (empty list), adding with inf cost")
            recipes.append((tuple(), float("inf")))
        
        mig[j] = recipes
    
    logger.info(f"Loaded migration costs and sizes for {len(mig)} nodes")
    logger.info(f"Size range: min={min(b_j):.2f}, max={max(b_j):.2f}, avg={sum(b_j)/len(b_j):.2f}")
    
    return mig, b_j


def load_full_build_costs_and_sizes(
    base_dir: str,
    node_list: List[str],
    query_set: str = "job"
) -> Tuple[Dict[int, float], Dict[int, float], List[float]]:
    """
    simple_migration_costs.jsonから[]レシピ(フルビルド)のコスト、利得、サイズを読み込む。
    
    簡略化版最適化では依存レシピを使用しないため、
    フルビルド（空の依存関係 '[]'）のデータのみが必要。
    これにより、parse_migration_costs_and_sizes()の複雑な処理を回避できる。
    
    Args:
        base_dir: 実験ディレクトリ (e.g., experiments/small_test_ver2)
        node_list: ノードIDのリスト (qp_class.pklから取得)
        query_set: クエリセット名 (e.g., "job", "job_like")
    
    Returns:
        Tuple of (migration_costs, utilities, sizes)
        - migration_costs: Dict[int, float] - {j: 作成コスト（読み取り+書き込み）}
        - utilities: Dict[int, float] - {j: 利得（読み取りコストのみ）}
        - sizes: List[float] - 各MVのサイズ (インデックスj)
    """
    path = os.path.join(base_dir, "04_migration", query_set, "simple_migration_costs.json")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"simple_migration_costs.json not found at {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    
    idx = {node_id: j for j, node_id in enumerate(node_list)}
    migration_costs: Dict[int, float] = {}
    utilities: Dict[int, float] = {}
    sizes = [1.0] * len(node_list)
    
    for node_id, recipes in raw.items():
        j = idx.get(node_id)
        if j is None:
            logger.debug(f"Node {node_id} not found in node_list, skipping")
            continue
        
        # []キー（フルビルド）を探す
        full_build = recipes.get("[]")
        if full_build and isinstance(full_build, dict):
            migration_costs[j] = float(full_build.get("cost", 0.0))
            # utility があればそれを使用、なければ cost にフォールバック（後方互換性）
            utilities[j] = float(full_build.get("utility", full_build.get("cost", 0.0)))
            sizes[j] = float(full_build.get("size", 1.0))
        else:
            logger.warning(f"Node {node_id} has no valid full-build recipe")
            migration_costs[j] = float("inf")
            utilities[j] = float("inf")
    
    logger.info(f"Loaded {len(migration_costs)} full-build costs and utilities")
    logger.info(f"Size range: min={min(sizes):.2f}, max={max(sizes):.2f}, avg={sum(sizes)/len(sizes):.2f}")
    
    return migration_costs, utilities, sizes

