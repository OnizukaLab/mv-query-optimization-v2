import json
from pathlib import Path

def load_result(mode, query_set='job'):
    path = Path(f"experiments/small_test_ver2/time_dependent_output/{query_set}/benchmark_results_{mode}.json")
    if not path.exists():
        print(f"Warning: {path} does not exist")
        return None
    with open(path, 'r') as f:
        return json.load(f)

def analyze_results():
    modes = ['baseline', 'static', 'dynamic']
    results = {}
    
    print("=== Benchmark Comparison Report ===\n")
    
    # Load results
    for mode in modes:
        res = load_result(mode)
        if res:
            results[mode] = res
    
    if not results:
        print("No results found.")
        return

    # 1. Overall Summary
    print("1. Overall Summary")
    print(f"{'Mode':<10} | {'Total Time (s)':<15} | {'Query Time (s)':<15} | {'Migration/Init (s)':<20}")
    print("-" * 65)
    
    for mode in modes:
        if mode not in results:
            continue
        r = results[mode]
        summary = r['summary']
        
        total_time = summary.get('total_benchmark_time', 0)
        query_time = summary.get('total_query_time', 0)
        
        mig_time = 0
        if mode == 'dynamic':
            mig_time = summary.get('total_migration_time', 0)
        elif mode == 'static':
            mig_time = summary.get('initial_mv_creation_time', 0)
            
        print(f"{mode:<10} | {total_time:<15.2f} | {query_time:<15.2f} | {mig_time:<20.2f}")
    
    print("\n")
    
    # 2. Timestep Breakdown
    print("2. Timestep Breakdown (Query Execution Time)")
    print(f"{'Timestep':<10} | {'Baseline (s)':<15} | {'Static (s)':<15} | {'Dynamic (s)':<15}")
    print("-" * 60)
    
    timesteps = results['baseline']['timesteps'] if 'baseline' in results else []
    if not timesteps and 'dynamic' in results:
        timesteps = results['dynamic']['timesteps']
        
    for i, ts in enumerate(timesteps):
        times = []
        for mode in modes:
            if mode in results:
                # Find timestep result
                ts_res = next((r for r in results[mode]['timestep_results'] if r['timestep'] == ts), None)
                if ts_res:
                    times.append(f"{ts_res['queries']['total_time']:.2f}")
                else:
                    times.append("N/A")
            else:
                times.append("-")
        
        print(f"{ts:<10} | {times[0]:<15} | {times[1]:<15} | {times[2]:<15}")

    print("\n")
    
    # 3. Detailed Analysis
    print("3. Analysis")
    
    # Compare Dynamic vs Baseline
    if 'dynamic' in results and 'baseline' in results:
        dyn_q = results['dynamic']['summary']['total_query_time']
        base_q = results['baseline']['summary']['total_query_time']
        diff = base_q - dyn_q
        ratio = base_q / dyn_q if dyn_q > 0 else 0
        
        print(f"- Dynamic vs Baseline (Query Time):")
        if diff > 0:
            print(f"  Dynamic is faster by {diff:.2f}s ({ratio:.2f}x speedup)")
        else:
            print(f"  Baseline is faster by {-diff:.2f}s (Dynamic is {dyn_q/base_q:.2f}x slower)")
            
    # Compare Dynamic vs Static
    if 'dynamic' in results and 'static' in results:
        dyn_q = results['dynamic']['summary']['total_query_time']
        stat_q = results['static']['summary']['total_query_time']
        
        print(f"- Dynamic vs Static (Query Time):")
        if stat_q > dyn_q:
            print(f"  Dynamic is faster by {stat_q - dyn_q:.2f}s")
        else:
            print(f"  Static is faster by {dyn_q - stat_q:.2f}s")

if __name__ == "__main__":
    analyze_results()
