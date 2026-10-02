#!/usr/bin/env python3
"""Compare query execution times between Dynamic and Static MV approaches for specific timesteps."""

import json
from pathlib import Path
from collections import defaultdict

# Paths
base_dir = Path("/home/masuda/projects/mv-query-optimization/experiments/small_test_ver2/time_dependent_output/job/result_1G_hash")
dynamic_file = base_dir / "benchmark_results_dynamic_16_peak.json"
static_file = base_dir / "benchmark_results_dynamic_16_peakp.json"

# Filter timesteps 1-3 only
TIMESTEP_FILTER = [10]

# Load JSON files
with open(dynamic_file, 'r', encoding='utf-8') as f:
    dynamic_data = json.load(f)

with open(static_file, 'r', encoding='utf-8') as f:
    static_data = json.load(f)

# Collect query times by query_file
query_times = defaultdict(lambda: {'dynamic': [], 'static': []})

# Process dynamic results
for timestep_result in dynamic_data['timestep_results']:
    timestep_idx = timestep_result.get('timestep_index', -1)
    # Filter by timestep
    if timestep_idx not in TIMESTEP_FILTER:
        continue
    if 'queries' in timestep_result and 'queries' in timestep_result['queries']:
        for query in timestep_result['queries']['queries']:
            query_id = query.get('query_id', 'unknown')
            exec_time = query.get('avg_time', 0)
            query_times[query_id]['dynamic'].append(exec_time)

# Process static results
for timestep_result in static_data['timestep_results']:
    timestep_idx = timestep_result.get('timestep_index', -1)
    # Filter by timestep
    if timestep_idx not in TIMESTEP_FILTER:
        continue
    if 'queries' in timestep_result and 'queries' in timestep_result['queries']:
        for query in timestep_result['queries']['queries']:
            query_id = query.get('query_id', 'unknown')
            exec_time = query.get('avg_time', 0)
            query_times[query_id]['static'].append(exec_time)

# Calculate statistics
results = []
for query_id, times in query_times.items():
    dynamic_times = times['dynamic']
    static_times = times['static']
    
    if not dynamic_times or not static_times:
        continue
    
    # Calculate averages
    avg_dynamic = sum(dynamic_times) / len(dynamic_times)
    avg_static = sum(static_times) / len(static_times)
    
    # Calculate total times
    total_dynamic = sum(dynamic_times)
    total_static = sum(static_times)
    
    # Calculate difference
    diff = avg_dynamic - avg_static
    abs_diff = abs(diff)
    
    # Calculate ratio
    if avg_static > 0:
        ratio = avg_dynamic / avg_static
    else:
        ratio = float('inf') if avg_dynamic > 0 else 1.0
    
    results.append({
        'query_id': query_id,
        'count': len(dynamic_times),
        'avg_dynamic': avg_dynamic,
        'avg_static': avg_static,
        'total_dynamic': total_dynamic,
        'total_static': total_static,
        'diff': diff,
        'abs_diff': abs_diff,
        'ratio': ratio,
        'faster': 'Dynamic' if diff < 0 else 'Static'
    })

# Sort by absolute difference
results.sort(key=lambda x: x['abs_diff'], reverse=True)

# Calculate total times for filtered timesteps
total_dynamic_time = sum(r['total_dynamic'] for r in results)
total_static_time = sum(r['total_static'] for r in results)

# Display results
print("\n" + "="*100)
print(f"クエリ実行時間比較: Dynamic MV vs Static MV (タイムステップ {TIMESTEP_FILTER})")
print("="*100)

print(f"\n総クエリ数: {len(results)}")
print(f"Dynamic総実行時間: {total_dynamic_time:.2f}s")
print(f"Static総実行時間: {total_static_time:.2f}s")
print(f"差: {total_dynamic_time - total_static_time:.2f}s")

print("\n" + "="*100)
print("実行時間差が大きいクエリ TOP 20")
print("="*100)
print(f"{'Query':<15} {'回数':>4} {'Dynamic平均':>12} {'Static平均':>12} {'差':>10} {'比率':>8} {'速い方':<10}")
print("-"*100)

for i, r in enumerate(results[:20], 1):
    query_name = r['query_id']
    print(f"{query_name:<15} {r['count']:>4} {r['avg_dynamic']:>11.3f}s {r['avg_static']:>11.3f}s "
          f"{r['diff']:>9.3f}s {r['ratio']:>7.2f}x {r['faster']:<10}")

print("\n" + "="*100)
print("Dynamicが速いクエリ TOP 10")
print("="*100)
dynamic_faster = [r for r in results if r['diff'] < 0]
dynamic_faster.sort(key=lambda x: x['diff'])

print(f"{'Query':<15} {'回数':>4} {'Dynamic平均':>12} {'Static平均':>12} {'差':>10} {'比率':>8}")
print("-"*100)
for i, r in enumerate(dynamic_faster[:10], 1):
    query_name = r['query_id']
    print(f"{query_name:<15} {r['count']:>4} {r['avg_dynamic']:>11.3f}s {r['avg_static']:>11.3f}s "
          f"{r['diff']:>9.3f}s {r['ratio']:>7.2f}x")

print("\n" + "="*100)
print("Staticが速いクエリ TOP 10")
print("="*100)
static_faster = [r for r in results if r['diff'] > 0]
static_faster.sort(key=lambda x: x['diff'], reverse=True)

print(f"{'Query':<15} {'回数':>4} {'Dynamic平均':>12} {'Static平均':>12} {'差':>10} {'比率':>8}")
print("-"*100)
for i, r in enumerate(static_faster[:10], 1):
    query_name = r['query_id']
    print(f"{query_name:<15} {r['count']:>4} {r['avg_dynamic']:>11.3f}s {r['avg_static']:>11.3f}s "
          f"{r['diff']:>9.3f}s {r['ratio']:>7.2f}x")

print("\n" + "="*100)
print("統計サマリー")
print("="*100)
print(f"Dynamicが速いクエリ: {len(dynamic_faster)} / {len(results)} ({len(dynamic_faster)/len(results)*100:.1f}%)")
print(f"Staticが速いクエリ: {len(static_faster)} / {len(results)} ({len(static_faster)/len(results)*100:.1f}%)")
print(f"平均差 (Dynamic - Static): {sum(r['diff'] for r in results) / len(results):.3f}s")
