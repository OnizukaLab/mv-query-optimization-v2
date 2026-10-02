#!/usr/bin/env python3
"""
MV最適化ダッシュボード - FastAPI バックエンド

HTML版ダッシュボードにデータを提供するAPIサーバー。

起動方法:
    cd experiments/small_test_ver2/scripts
    source ../../../.venv/bin/activate
    uvicorn dashboard_api:app --host 0.0.0.0 --port 8000 --reload

SSHポートフォワード:
    ssh -L 8000:localhost:8000 user@server
    → ブラウザで http://localhost:8000 を開く
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import json
import re
import pickle
import sys
from typing import List, Dict, Any, Optional

# プロジェクトルートをPythonパスに追加（pickle内のsrcモジュール解決用）
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = EXP_DIR.parent.parent  # experiments/small_test_ver2 -> experiments -> project root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

app = FastAPI(title="MV最適化ダッシュボード API")

# ディレクトリパス
OUTPUT_DIR = EXP_DIR / "time_dependent_output"
JSON_DIR = EXP_DIR / "02_json"
PARSED_DIR = EXP_DIR / "03_parsed"
MIGRATION_DIR = EXP_DIR / "04_migration"
QUERIES_DIR = EXP_DIR / "01_queries"
STATIC_DIR = SCRIPT_DIR / "dashboard_static"

# キャッシュ用
_qp_cache: Dict[str, Any] = {}



def natural_sort_key(s):
    """自然数ソート用のキー関数"""
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', str(s))]


# 静的ファイルをマウント（存在する場合）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """ダッシュボードHTMLを返す"""
    html_path = SCRIPT_DIR / "dashboard.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>dashboard.html not found</h1>")


@app.get("/api/query-sets")
async def get_query_sets() -> List[str]:
    """利用可能なクエリセットを取得"""
    if not OUTPUT_DIR.exists():
        return []
    query_sets = [d.name for d in OUTPUT_DIR.iterdir() 
                  if d.is_dir() and not d.name.startswith('.') 
                  and d.name not in ['log', 'store_result', 'migration_plan']]
    return sorted(query_sets, key=natural_sort_key)


@app.get("/api/subfolders/{query_set}")
async def get_subfolders(query_set: str, path: str = "") -> Dict[str, Any]:
    """クエリセット内のサブフォルダ一覧を取得（パスベースのナビゲーション）
    
    Args:
        path: 現在のパス（例: "" or "result_sample1"）
    
    Returns:
        {
            "current_path": 現在のパス,
            "parent_path": 親パス（戻るボタン用）,
            "has_results": このフォルダに結果があるか,
            "folders": [{"name": "...", "path": "...", "has_results": bool, "has_children": bool}, ...]
        }
    """
    output_path = OUTPUT_DIR / query_set
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Query set not found")
    
    excluded = {'jobs', 'log', 'sin', 'garbage', 'rewritten_static', 'rewritten_static_bigsubs'}
    
    # 現在のパスを解決
    if path and path != "(root)":
        current_dir = output_path / path
        parent_path = "/".join(path.split("/")[:-1]) if "/" in path else "(root)"
    else:
        current_dir = output_path
        parent_path = ""
        path = "(root)"
    
    if not current_dir.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    
    # 現在のフォルダに結果があるか
    has_results = (
        any(current_dir.glob("td_mv_optimization_result_*.json")) or
        any(current_dir.glob("benchmark_results_*.json")) or
        any(current_dir.glob("static_mv_optimization_result_*.json"))
    )
    
    # サブフォルダを収集
    folders = []
    for d in current_dir.iterdir():
        if not d.is_dir() or d.name.startswith('.') or d.name in excluded:
            continue
        if not d.name.startswith('result_'):
            continue
        
        # このフォルダに結果があるか
        folder_has_results = (
            any(d.glob("td_mv_optimization_result_*.json")) or
            any(d.glob("benchmark_results_*.json")) or
            any(d.glob("static_mv_optimization_result_*.json"))
        )
        
        # サブフォルダがあるか
        has_children = any(
            child.is_dir() and child.name.startswith('result_') 
            for child in d.iterdir() 
            if not child.name.startswith('.')
        )
        
        folder_path = f"{path}/{d.name}" if path != "(root)" else d.name
        
        folders.append({
            "name": d.name,
            "path": folder_path,
            "has_results": folder_has_results,
            "has_children": has_children
        })
    
    # ソート
    folders.sort(key=lambda x: natural_sort_key(x['name']))
    
    return {
        "current_path": path,
        "parent_path": parent_path,
        "has_results": has_results,
        "folders": folders
    }


@app.get("/api/result-files/{query_set}")
async def get_result_files(query_set: str, subfolder: str = "") -> Dict[str, List[str]]:
    """結果ファイル一覧を取得"""
    if subfolder and subfolder != "(root)":
        output_path = OUTPUT_DIR / query_set / subfolder
    else:
        output_path = OUTPUT_DIR / query_set
    
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    
    # Dynamic最適化ファイル (td_mv_optimization_result)
    opt_files = [f.name for f in sorted(output_path.glob("td_mv_optimization_result_*.json"), 
                                         key=lambda f: natural_sort_key(f.name))]
    
    # Adaptive最適化ファイル (adaptive_mv_optimization_result)
    adaptive_opt_files = [f.name for f in sorted(output_path.glob("adaptive_mv_optimization_result_*.json"),
                                                   key=lambda f: natural_sort_key(f.name))]
    
    # Dynamicベンチマークファイル (adaptive/static以外)
    bench_files = [f.name for f in sorted(output_path.glob("benchmark_results_dynamic_*.json"),
                                          key=lambda f: natural_sort_key(f.name))]
    
    # Adaptiveベンチマークファイル
    adaptive_bench_files = [f.name for f in sorted(output_path.glob("benchmark_results_adaptive_*.json"),
                                                    key=lambda f: natural_sort_key(f.name))]
    
    # Static最適化ファイル
    static_files = [f.name for f in sorted(output_path.glob("static_mv_optimization_result_*.json"),
                                           key=lambda f: natural_sort_key(f.name))]
    
    # Staticベンチマークファイル
    static_bench_files = [f.name for f in sorted(output_path.glob("benchmark_results_static_*.json"),
                                                  key=lambda f: natural_sort_key(f.name))]
    
    return {
        "optimization": opt_files,
        "benchmark": bench_files,
        "static": static_files,
        "adaptive_optimization": adaptive_opt_files,
        "adaptive_benchmark": adaptive_bench_files,
        "static_benchmark": static_bench_files
    }


@app.get("/api/optimization-result/{query_set}/{filename}")
async def get_optimization_result(query_set: str, filename: str, subfolder: str = "") -> Dict:
    """最適化結果を取得"""
    if subfolder and subfolder != "(root)":
        filepath = OUTPUT_DIR / query_set / subfolder / filename
    else:
        filepath = OUTPUT_DIR / query_set / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # migration_analysisからMV詳細を抽出
    processed_timesteps = []
    
    # 全タイムステップのMV詳細を累積的に収集
    all_mv_details = {}  # mv_name -> {mv, size, cost}
    
    if 'migration_analysis' in data:
        for t_result in data['migration_analysis']:
            timestep = t_result.get('timestep', 0)
            mvs = t_result.get('selected_mvs', [])
            total_size = t_result.get('total_size', 0)
            mv_count = t_result.get('mv_count', len(mvs))
            
            # creation_detailsから詳細情報を取得して累積
            # initial_creation（タイムステップ0）
            if 'initial_creation' in t_result and 'creation_details' in t_result['initial_creation']:
                for detail in t_result['initial_creation']['creation_details']:
                    all_mv_details[detail['mv']] = detail
            
            # migration.creation_details（タイムステップ1以降）
            if 'migration' in t_result and 'creation_details' in t_result['migration']:
                for detail in t_result['migration']['creation_details']:
                    all_mv_details[detail['mv']] = detail
            
            # このタイムステップで選択されたMVの詳細を取得
            mv_details = []
            for mv in mvs:
                if isinstance(mv, str):
                    if mv in all_mv_details:
                        mv_details.append(all_mv_details[mv])
                    else:
                        # 詳細がない場合はサイズを推定
                        est_size = total_size / mv_count if mv_count > 0 else 0
                        mv_details.append({'mv': mv, 'size': est_size, 'cost': 0})
                else:
                    mv_details.append(mv)
            
            # MV名でソート
            mv_details.sort(key=lambda x: natural_sort_key(x.get('mv', '')))
            
            processed_timesteps.append({
                'timestep': int(timestep) if str(timestep).isdigit() else timestep,
                'mvs': mv_details,
                'mv_count': mv_count,
                'total_size': total_size,
                'storage_budget': t_result.get('storage_budget', 0),
                'utilization_percent': t_result.get('utilization_percent', 0)
            })
    
    # タイムステップでソート
    processed_timesteps.sort(key=lambda x: x['timestep'])
    
    # ファイル名からモードを判定
    mode_type = 'adaptive' if 'adaptive' in filename else 'dynamic'
    
    return {
        'type': mode_type,
        'timesteps': [str(t['timestep']) for t in processed_timesteps],
        'timestep_data': processed_timesteps,
        'summary': data.get('summary', {}),
        'objective': data.get('objective'),
        'workload_cost': data.get('workload_cost'),
        'migration_cost': data.get('migration_cost')
    }


@app.get("/api/static-result/{query_set}/{filename}")
async def get_static_result(query_set: str, filename: str, subfolder: str = "") -> Dict:
    """静的最適化結果を取得"""
    if subfolder and subfolder != "(root)":
        filepath = OUTPUT_DIR / query_set / subfolder / filename
    else:
        filepath = OUTPUT_DIR / query_set / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # migrationコスト情報を取得
    migration_costs_path = SCRIPT_DIR.parent / "04_migration" / query_set / "simple_migration_costs.json"
    migration_data = {}
    if migration_costs_path.exists():
        with open(migration_costs_path, 'r', encoding='utf-8') as f:
            migration_data = json.load(f)
            
    # 静的最適化結果を整形
    selected_mvs = data.get('selected_mvs', [])
    mv_details = []
    
    for mv in selected_mvs:
        size = 0
        cost = 0
        
        # migration_dataから情報を取得
        if mv in migration_data:
            # 基本的に [] (空集合) からの作成コスト/サイズを使用
            if "[]" in migration_data[mv]:
                details = migration_data[mv]["[]"]
                size = details.get("size", 0)
                cost = details.get("cost", 0)
            # または自分自身からの遷移情報があればそれを使用（稀なケース）
            elif f"['{mv}']" in migration_data[mv]:
                 details = migration_data[mv][f"['{mv}']"]
                 size = details.get("size", 0)
                 # costはマイグレーションコストなので0の可能性があるが、作成コストとしては不適切かも
                 # ここでは一旦sizeのみ取得し、costは他から取れなければ0
        
        mv_details.append({
            'mv': mv, 
            'size': size, 
            'cost': round(cost, 2)
        })
        
    # mv_details = [{'mv': mv, 'size': 0, 'cost': 0} for mv in selected_mvs]
    mv_details.sort(key=lambda x: natural_sort_key(x.get('mv', '')))
    
    # 合計を再計算
    calc_total_size = sum(m['size'] for m in mv_details)
    calc_total_cost = sum(m['cost'] for m in mv_details)
    
    return {
        'type': 'static',
        'algorithm': data.get('algorithm', 'static'),
        'timestep': data.get('timestep', 'N/A'),
        'selected_mvs': selected_mvs,
        'mv_count': data.get('mv_count', len(selected_mvs)),
        'total_size': calc_total_size, # 再計算値を使用
        'storage_budget': data.get('storage_budget', 0),
        'utilization_percent': (calc_total_size / data.get('storage_budget', 1) * 100) if data.get('storage_budget', 0) > 0 else 0,
        'objective_value': calc_total_cost, # 利得の合計としてコストを使用
        'execution_time': data.get('execution_time', 0),
        'mv_details': mv_details
    }


@app.get("/api/benchmark-result/{query_set}/{optimization_filename}")
async def get_benchmark_result(query_set: str, optimization_filename: str, subfolder: str = "") -> Dict:
    """最適化結果に対応するベンチマーク結果を取得。最適化ファイルの情報（選択MVなど）もマージする。"""
    
    # ファイル名からベンチマークファイルと最適化ファイルを特定するロジック
    # 入力は benchmark_results_*.json または *_mv_optimization_result_*.json のどちらも許容
    bench_filename = optimization_filename
    opt_filename = optimization_filename
    mode = "unknown"

    if "benchmark_results_" in optimization_filename:
        # 入力がベンチマーク結果ファイルの場合
        bench_filename = optimization_filename
        if "benchmark_results_adaptive_" in optimization_filename:
            opt_filename = optimization_filename.replace("benchmark_results_adaptive_", "adaptive_mv_optimization_result_")
            mode = "adaptive"
        elif "benchmark_results_dynamic_utility_" in optimization_filename:
            opt_filename = optimization_filename.replace("benchmark_results_dynamic_utility_", "dynamic_utility_optimization_result_")
            mode = "dynamic"
        elif "benchmark_results_dynamic_" in optimization_filename:
            opt_filename = optimization_filename.replace("benchmark_results_dynamic_", "td_mv_optimization_result_")
            mode = "dynamic"
        elif "benchmark_results_static_bigsubs_" in optimization_filename:
            opt_filename = optimization_filename.replace("benchmark_results_static_bigsubs_", "static_bigsubs_optimization_result_")
            mode = "static"
        elif "benchmark_results_static_" in optimization_filename:
            opt_filename = optimization_filename.replace("benchmark_results_static_", "static_mv_optimization_result_")
            mode = "static"
        
        # _noise{XX} サフィックスは最適化結果ファイルには存在しないため除去
        opt_filename = re.sub(r'_noise\d+\.json$', '.json', opt_filename)
    elif "_mv_optimization_result_" in optimization_filename or "_optimization_result_" in optimization_filename:
        # 入力が最適化結果ファイルの場合 (互換性のため維持)
        opt_filename = optimization_filename
        if "adaptive_mv_optimization_result_" in optimization_filename:
            bench_filename = optimization_filename.replace("adaptive_mv_optimization_result_", "benchmark_results_adaptive_")
            mode = "adaptive"
        elif "static_mv_optimization_result_" in optimization_filename:
            bench_filename = optimization_filename.replace("static_mv_optimization_result_", "benchmark_results_static_")
            mode = "static"
        elif "td_mv_optimization_result_" in optimization_filename:
            bench_filename = optimization_filename.replace("td_mv_optimization_result_", "benchmark_results_dynamic_")
            mode = "dynamic"

    # ファイルパス構築
    if subfolder and subfolder != "(root)":
        bench_filepath = OUTPUT_DIR / query_set / subfolder / bench_filename
        opt_filepath = OUTPUT_DIR / query_set / subfolder / opt_filename
    else:
        bench_filepath = OUTPUT_DIR / query_set / bench_filename
        opt_filepath = OUTPUT_DIR / query_set / opt_filename
    
    if not bench_filepath.exists():
        return {
            "found": False,
            "total_execution_time": 0,
            "timesteps": []
        }
    
    # データの読み込み
    with open(bench_filepath, 'r', encoding='utf-8') as f:
        bench_data = json.load(f)
        
    opt_data = {}
    if opt_filepath.exists():
        try:
            with open(opt_filepath, 'r', encoding='utf-8') as f:
                opt_data = json.load(f)
        except Exception:
            pass # 最適化ファイルが読めなくてもベンチマーク結果は返す

    timesteps = []
    total_query_time = 0
    total_migration_time = 0
    
    # タイムステップデータの構築
    bench_timesteps = bench_data.get("timestep_results", [])
    
    # 静的の場合の初期作成時間
    initial_creation = 0
    if mode == "static" or bench_data.get("mode") == "static":
        initial_creation = bench_data.get("initial_mv_creation_time", 0)
        total_migration_time += initial_creation

    for ts_res in bench_timesteps:
        ts_val = int(ts_res.get("timestep", 0))
        q_time = ts_res.get("queries", {}).get("total_time", 0)
        
        mig_time = 0
        if mode == "static":
            # 静的: 時間0のみ初期作成時間
            if ts_val == 0:
                mig_time = initial_creation
        else:
            # 動的: 各ステップのmigration時間
            mig_time = ts_res.get("migration", {}).get("time", 0)
            total_migration_time += mig_time

        total_query_time += q_time
        
        # 選択MV情報の取得 (opt_dataから)
        selected_mvs = []
        if "migration_analysis" in opt_data:
            # 動的最適化ファイル (td_mv_optimization_result)
            opt_ts = next((item for item in opt_data["migration_analysis"] if int(item.get("timestep", -1)) == ts_val), None)
            if opt_ts and "selected_mvs" in opt_ts:
                selected_mvs = [{"name": mv, "cost_gain": 0} for mv in opt_ts["selected_mvs"]]
        elif "timestep_results" in opt_data:
            # 互換性: timestep_results がある場合
            opt_ts = next((item for item in opt_data["timestep_results"] if int(item.get("timestep", -1)) == ts_val), None)
            if opt_ts and "selected_mvs" in opt_ts:
                selected_mvs = [{"name": mv, "cost_gain": 0} for mv in opt_ts["selected_mvs"]]
        elif "selected_mvs" in opt_data:
             # 静的最適化ファイルなど (トップレベル)
             selected_mvs = [{"name": mv, "cost_gain": 0} for mv in opt_data["selected_mvs"]]
        elif "node_list" in opt_data:
             # フォールバック
             selected_mvs = [{"name": mv, "cost_gain": 0} for mv in opt_data["node_list"]]

        timesteps.append({
            "timestep": ts_val,
            "query_time": q_time,
            "migration_time": mig_time,
            "selected_mvs": selected_mvs,
            "cost_gain": 0 # ベンチマーク結果には詳細なGain情報はないことが多い
        })

    return {
        "found": True,
        "mode": mode,
        "total_execution_time": total_query_time + total_migration_time,
        "total_query_time": total_query_time,
        "total_migration_time": total_migration_time,
        "timesteps": timesteps
    }




@app.get("/api/queries/{query_set}")
async def get_queries(query_set: str) -> List[str]:
    """クエリ一覧を取得"""
    json_dir = JSON_DIR / query_set
    if not json_dir.exists():
        raise HTTPException(status_code=404, detail="Query set not found")
    
    query_names = [f.stem for f in json_dir.glob("*.json")]
    return sorted(query_names, key=natural_sort_key)


@app.get("/api/root-nodes/{query_set}")
async def get_root_nodes(query_set: str) -> Dict[str, str]:
    """各クエリのルートノードIDを取得"""
    json_dir = JSON_DIR / query_set
    if not json_dir.exists():
        raise HTTPException(status_code=404, detail="Query set not found")
        
    result = {}
    for filepath in json_dir.glob("*.json"):
        query_name = filepath.stem
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # EXPLAIN構造の差異に対応
            if isinstance(data, list) and len(data) > 0:
                root = data[0].get('Plan')
            else:
                root = data.get('Plan')
                
            if root and 'node_id' in root:
                result[query_name] = root['node_id']
                
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            
    return result


@app.get("/api/mv-sizes/{query_set}")
async def get_mv_sizes(query_set: str) -> Dict[str, int]:
    """MV名(leaf_Xなど) -> サイズ(bytes) のマッピングを取得"""
    filepath = MIGRATION_DIR / query_set / "simple_migration_costs.json"
    if not filepath.exists():
        print(f"Warning: {filepath} not found")
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        result = {}
        for mv_name, info in data.items():
            # "[]" キーの size を取得 (ベース作成コスト)
            if "[]" in info:
                result[mv_name] = info["[]"].get("size", 0)
        return result
    except Exception as e:
        print(f"Error loading mv sizes: {e}")
        return {}


@app.get("/api/mv-costs/{query_set}")
async def get_mv_costs(query_set: str) -> Dict[str, float]:
    """MV名(leaf_Xなど) -> コスト のマッピングを取得"""
    filepath = MIGRATION_DIR / query_set / "simple_migration_costs.json"
    if not filepath.exists():
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        result = {}
        for mv_name, info in data.items():
            if "[]" in info:
                result[mv_name] = info["[]"].get("cost", 0)
        return result
    except Exception as e:
        print(f"Error loading mv costs: {e}")
        return {}


@app.get("/api/mv-costs/{query_set}/{query_name}")
async def get_mv_costs_query(query_set: str, query_name: str) -> Dict[str, float]:
    """クエリ名が含まれるリクエストに対応（ロジックは全MV取得と同じ）"""
    return await get_mv_costs(query_set)


@app.get("/api/subquery-costs/{query_set}")
async def get_subquery_costs(query_set: str) -> Dict[str, float]:
    """simple_migration_costs.jsonからcost（作成コスト）を取得"""
    filepath = MIGRATION_DIR / query_set / "simple_migration_costs.json"
    if not filepath.exists():
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        result = {}
        for mv_name, info in data.items():
            if "[]" in info:
                result[mv_name] = info["[]"].get("cost", 0)
        return result
    except Exception as e:
        print(f"Error loading subquery_costs: {e}")
        return {}


@app.get("/api/mv-utilities/{query_set}")
async def get_mv_utilities(query_set: str) -> Dict[str, float]:
    """MV名 -> 利得(utility) のマッピングを取得"""
    filepath = MIGRATION_DIR / query_set / "simple_migration_costs.json"
    if not filepath.exists():
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        result = {}
        for mv_name, info in data.items():
            if "[]" in info:
                result[mv_name] = info["[]"].get("utility", 0)
        return result
    except Exception as e:
        print(f"Error loading mv utilities: {e}")
        return {}


@app.get("/api/explain/{query_set}/{query_name}")
async def get_explain(query_set: str, query_name: str) -> Dict:
    """EXPLAIN JSONを取得"""
    filepath = JSON_DIR / query_set / f"{query_name}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # PostgreSQLのEXPLAIN出力は配列の最初の要素
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data


def _load_query_parser(query_set: str):
    """QueryParserオブジェクトをロード（キャッシュ付き）"""
    if query_set in _qp_cache:
        return _qp_cache[query_set]
    
    pkl_path = PARSED_DIR / query_set / "qp_class.pkl"
    if not pkl_path.exists():
        return None
    
    with open(pkl_path, 'rb') as f:
        qp = pickle.load(f)
    
    _qp_cache[query_set] = qp
    return qp


@app.get("/api/query-mv-usage/{query_set}/{query_name}")
async def get_query_mv_usage(query_set: str, query_name: str, selected_mvs: str = "") -> Dict:
    """特定のクエリが使用するノードと、選択されたMVとの交差を取得
    
    Args:
        query_set: クエリセット名
        query_name: クエリ名（例: "1a"）
        selected_mvs: カンマ区切りのMVリスト（例: "leaf_1,non_leaf_2"）
    
    Returns:
        {
            'query_nodes': クエリが使用する全ノード,
            'usable_mvs': 選択MVのうちこのクエリで使用可能なもの（包含関係フィルタ済み）
        }
    """
    qp = _load_query_parser(query_set)
    if qp is None:
        raise HTTPException(status_code=404, detail="QueryParser not found for this query set")
    
    # クエリ名からインデックスを取得
    try:
        query_idx = qp.query_files.index(query_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Query '{query_name}' not found")
    
    # このクエリが使用するノード（u_ij > 0）
    query_nodes = []
    for j, val in enumerate(qp.u_ij[query_idx]):
        if val > 0:
            query_nodes.append({
                'node_id': qp.node_list[j],
                'utility': float(val)
            })
    
    # 選択されたMVをパース
    selected_mv_list = [mv.strip() for mv in selected_mvs.split(',') if mv.strip()]
    
    # クエリが使用するノードのうち、選択MVに含まれるもの
    query_node_ids = set(n['node_id'] for n in query_nodes)
    usable_mvs = [mv for mv in selected_mv_list if mv in query_node_ids]
    
    # 包含関係を使って冗長なMVを除去
    if hasattr(qp, 'X') and qp.X is not None:
        filtered_mvs = []
        for mv in usable_mvs:
            if mv not in qp.node_list:
                continue
            mv_idx = qp.node_list.index(mv)
            
            # 他のMVに包含されているかチェック
            is_redundant = False
            for other_mv in usable_mvs:
                if other_mv == mv or other_mv not in qp.node_list:
                    continue
                other_idx = qp.node_list.index(other_mv)
                # X[other][mv]=1 なら other が mv を包含
                if qp.X[other_idx][mv_idx] == 1:
                    is_redundant = True
                    break
            
            if not is_redundant:
                filtered_mvs.append(mv)
        usable_mvs = filtered_mvs
    
    # 自然数順でソート
    query_nodes.sort(key=lambda x: natural_sort_key(x['node_id']))
    usable_mvs.sort(key=natural_sort_key)
    
    return {
        'query_name': query_name,
        'query_nodes': query_nodes,
        'usable_mvs': usable_mvs,
        'total_query_nodes': len(query_nodes),
        'total_usable_mvs': len(usable_mvs)
    }


@app.get("/api/frequency-files/{query_set}")
async def get_frequency_files(query_set: str) -> List[str]:
    """指定クエリセットの頻度ファイル一覧を取得"""
    query_dir = QUERIES_DIR / query_set
    if not query_dir.exists():
        return []
    
    files = [f.name for f in query_dir.glob("frequency_*.json")]
    return sorted(files, key=natural_sort_key)


@app.get("/api/all-frequency-files")
async def get_all_frequency_files() -> Dict[str, List[str]]:
    """全クエリセットの頻度ファイル一覧を階層化して取得"""
    result = {}
    if not QUERIES_DIR.exists():
        return result
    
    for d in QUERIES_DIR.iterdir():
        if d.is_dir() and not d.name.startswith('.'):
            files = [f.name for f in d.glob("frequency_*.json")]
            if files:
                result[d.name] = sorted(files, key=natural_sort_key)
                
    # クエリセット名でソート
    return {k: result[k] for k in sorted(result.keys(), key=natural_sort_key)}


@app.get("/api/frequency-data/{query_set}/{filename}")
async def get_frequency_data(query_set: str, filename: str) -> Dict:
    """頻度ファイルのデータを取得"""
    filepath = QUERIES_DIR / query_set / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Frequency file not found")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # クエリを奇数/偶数グループに分類
    import re
    queries = data.get('queries', {})
    odd_group = {}  # 奇数クエリ (1a, 3a, 5a, ...)
    even_group = {}  # 偶数クエリ (2a, 4a, 6a, ...)
    
    for query_name, frequencies in queries.items():
        # クエリ名から数字部分を抽出
        match = re.match(r'(\d+)', query_name)
        if match:
            query_num = int(match.group(1))
            if query_num % 2 == 1:
                odd_group[query_name] = frequencies
            else:
                even_group[query_name] = frequencies
    
    return {
        'description': data.get('description', ''),
        'note': data.get('note', ''),
        'odd_group': odd_group,
        'even_group': even_group,
        'total_queries': len(queries),
        'timesteps': len(next(iter(queries.values()), []))
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

