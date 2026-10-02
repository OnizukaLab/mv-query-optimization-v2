"""
Result Loader Component

Loads and parses experiment results from output files.
"""

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.utils.data_processor import DataProcessor


class ResultLoader:
    """Loads experiment results from various file formats"""
    
    def __init__(self, output_dir: str = "Output"):
        # Handle relative paths - make them relative to project root
        output_path = Path(output_dir)
        if not output_path.is_absolute():
            output_path = project_root / output_dir
        self.output_dir = output_path
        print(f"[DEBUG] ResultLoader initialized with output_dir: {self.output_dir}")
        
    def list_experiments(self) -> List[Dict]:
        """List all available experiments
        
        Returns:
            List of experiment metadata dictionaries
        """
        experiments = []
        
        if not self.output_dir.exists():
            return experiments
        
        # Find all algorithm directories
        for algo_dir in self.output_dir.iterdir():
            if algo_dir.is_dir() and not algo_dir.name.startswith('.'):
                exp_data = self._load_experiment_metadata(algo_dir)
                if exp_data:
                    experiments.append(exp_data)
        
        # Sort by timestamp (newest first)
        experiments.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return experiments
    
    def _load_experiment_metadata(self, algo_dir: Path) -> Optional[Dict]:
        """Load metadata for an experiment
        
        Args:
            algo_dir: Path to algorithm directory
            
        Returns:
            Experiment metadata dictionary or None
        """
        try:
            # Check for summary.json first
            summary_file = algo_dir / 'summary.json'
            if summary_file.exists():
                with open(summary_file, 'r') as f:
                    summary_data = json.load(f)
                
                metadata = {
                    'algorithm': algo_dir.name,
                    'path': str(algo_dir),
                    'timestamp': summary_data.get('timestamp', self._get_directory_timestamp(algo_dir)),
                    'execution_time': summary_data.get('total_execution_time', 0),
                    'phases': summary_data.get('phases', {})
                }
                return metadata
            
            # Fallback: check for subdirectories indicating results
            has_results = False
            subdirs = ['optimization', 'benchmark', 'query_rewrite', 'mv_creation']
            
            for subdir in subdirs:
                if (algo_dir / subdir).exists():
                    has_results = True
                    break
            
            if has_results:
                metadata = {
                    'algorithm': algo_dir.name,
                    'path': str(algo_dir),
                    'timestamp': self._get_directory_timestamp(algo_dir)
                }
                return metadata
            
        except Exception as e:
            print(f"Error loading metadata for {algo_dir}: {e}")
        
        return None
    
    def _get_directory_timestamp(self, path: Path) -> str:
        """Get timestamp from directory modification time"""
        try:
            from datetime import datetime
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return 'Unknown'
    
    def load_optimization_results(self, algorithm: str) -> Optional[Dict]:
        """Load optimization results for an algorithm
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            Results dictionary or None
        """
        algo_dir = self.output_dir / algorithm
        results = {}
        
        # Load summary
        summary_file = algo_dir / 'summary.json'
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                results['summary'] = json.load(f)
                results['execution_times'] = results['summary'].get('phases', {})
        
        # Load optimization results
        opt_result_file = algo_dir / 'optimization' / 'result.json'
        if opt_result_file.exists():
            with open(opt_result_file, 'r') as f:
                opt_data = json.load(f)
                results['solution'] = opt_data
                # Extract key fields directly to results for easier access
                if 'selected_views' in opt_data:
                    results['selected_views'] = opt_data['selected_views']
                if 'total_utility' in opt_data:
                    results['total_utility'] = opt_data['total_utility']
                if 'total_storage' in opt_data:
                    results['total_storage'] = opt_data['total_storage']
                if 'total_storage_mb' in opt_data:
                    results['total_storage_mb'] = opt_data['total_storage_mb']
                if 'num_selected_views' in opt_data:
                    results['num_selected_views'] = opt_data['num_selected_views']
        
        # Load MV list CSV
        mv_list_file = algo_dir / 'optimization' / 'mv_list.csv'
        if mv_list_file.exists():
            results['mv_list_csv'] = str(mv_list_file)
        
        # Load benchmark results if available
        benchmark_file = algo_dir / 'benchmark' / 'benchmark_results.json'
        if benchmark_file.exists():
            with open(benchmark_file, 'r') as f:
                results['benchmark'] = json.load(f)
        
        return results if results else None
    
    def _load_baseline_times(self) -> Dict[str, float]:
        """Load baseline execution times from 'none' algorithm (no optimization)
        
        Returns:
            Dictionary mapping query_id to original execution time
        """
        baseline_times = {}
        none_benchmark = self.output_dir / 'none' / 'benchmark' / 'benchmark_results.json'
        
        if not none_benchmark.exists():
            print(f"[DEBUG] Baseline file not found: {none_benchmark}")
            return baseline_times
        
        try:
            with open(none_benchmark, 'r') as f:
                baseline_data = json.load(f)
            
            if 'queries' in baseline_data:
                for q in baseline_data['queries']:
                    query_id = q.get('query_id', '')
                    exec_time = q.get('execution_time', 0)
                    success = q.get('success', False)
                    # Include all successful queries, even with 0 execution time
                    if success:
                        baseline_times[query_id] = exec_time
                
                print(f"[DEBUG] Loaded {len(baseline_times)} baseline times from 'none' algorithm")
                # Print a few examples
                sample_keys = list(baseline_times.keys())[:5]
                for k in sample_keys:
                    print(f"[DEBUG]   {k}: {baseline_times[k]}")
        except Exception as e:
            print(f"Error loading baseline times: {e}")
        
        return baseline_times
    
    def load_query_performance(self, algorithm: str) -> Optional[List[Dict]]:
        """Load query performance data
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            List of query performance dictionaries
        """
        algo_dir = self.output_dir / algorithm
        
        # Load baseline times from 'none' algorithm (original, no optimization)
        baseline_times = self._load_baseline_times()
        
        # Try benchmark results first
        benchmark_file = algo_dir / 'benchmark' / 'benchmark_results.json'
        if benchmark_file.exists():
            with open(benchmark_file, 'r') as f:
                benchmark_data = json.load(f)
            
            # Check if it's the new format with 'queries' array
            if 'queries' in benchmark_data and isinstance(benchmark_data['queries'], list):
                performance = []
                
                for query in benchmark_data['queries']:
                    query_id = query.get('query_id', '')
                    exec_time = query.get('execution_time', 0)
                    
                    # Get original execution time from 'none' algorithm
                    original_time = baseline_times.get(query_id, 0)
                    
                    # Use DataProcessor.calculate_speedup for consistent speedup calculation
                    # This is the SINGLE SOURCE OF TRUTH
                    speedup = DataProcessor.calculate_speedup(original_time, exec_time)
                    
                    # For 'none' algorithm, speedup should be 1.0 (comparing to itself)
                    if algorithm == 'none':
                        speedup = 1.0
                    
                    perf = {
                        'query_id': query_id,
                        'original_cost': original_time,  # Original execution time (from 'none')
                        'rewritten_cost': exec_time,     # Rewritten query execution time
                        'improvement': original_time - exec_time if original_time > 0 else 0,
                        'speedup': speedup,
                        'execution_time': exec_time,
                        'success': query.get('success', True)
                    }
                    performance.append(perf)
                
                return performance if performance else None
            
            # Old format: dict of query_id -> data
            performance = []
            for query_id, data in benchmark_data.items():
                if isinstance(data, dict) and query_id not in ['total_queries', 'successful', 'failed', 'total_time', 'benchmark_elapsed', 'avg_time_per_query']:
                    original_cost = data.get('original_cost', 0)
                    rewritten_cost = data.get('rewritten_cost', 0)
                    speedup = DataProcessor.calculate_speedup(original_cost, rewritten_cost)
                    
                    perf = {
                        'query_id': query_id,
                        'original_cost': original_cost,
                        'rewritten_cost': rewritten_cost,
                        'improvement': original_cost - rewritten_cost,
                        'speedup': speedup
                    }
                    performance.append(perf)
            
            return performance if performance else None
        
        return None
    
    def load_mv_details(self, algorithm: str) -> Optional[List[Dict]]:
        """Load materialized view details
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            List of MV detail dictionaries
        """
        algo_dir = self.output_dir / algorithm
        
        # Try loading from optimization result first
        result_file = algo_dir / 'optimization' / 'result.json'
        if result_file.exists():
            with open(result_file, 'r') as f:
                result_data = json.load(f)
            
            selected_views = result_data.get('selected_views', [])
            total_storage = result_data.get('total_storage', 0)
            total_utility = result_data.get('total_utility', 0)
            
            if selected_views:
                mvs_list = []
                # Calculate average storage per MV
                avg_storage = total_storage / len(selected_views) if len(selected_views) > 0 else 0
                avg_utility = total_utility / len(selected_views) if len(selected_views) > 0 else 0
                
                for idx, view_id in enumerate(selected_views):
                    mv = {
                        'view_id': view_id,
                        'mv_id': f'mv_{view_id}',
                        'utility': avg_utility,  # Use average utility
                        'storage_size': avg_storage,  # Use average storage
                        'maintenance_cost': 0,
                        'used_by_queries': [],
                        'sql': f'View {view_id}',
                        'node_type': 'materialized_view'
                    }
                    mvs_list.append(mv)
                return mvs_list
        
        # Try CSV file as fallback
        csv_file = algo_dir / 'optimization' / 'mv_list.csv'
        if csv_file.exists():
            import csv
            mvs_list = []
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mv = {
                        'view_id': row.get('view_id', ''),
                        'mv_id': row.get('mv_id', ''),
                        'utility': float(row.get('utility', 0)),
                        'storage_size': float(row.get('storage_size', 0)),
                        'maintenance_cost': float(row.get('maintenance_cost', 0)),
                        'used_by_queries': [],
                        'sql': row.get('sql', ''),
                        'node_type': 'materialized_view'
                    }
                    mvs_list.append(mv)
            # Sort by utility (descending)
            mvs_list.sort(key=lambda x: x.get('utility', 0), reverse=True)
            return mvs_list if mvs_list else None
        
        return None
    
    def compare_algorithms(self, algorithms: List[str]) -> Dict:
        """Compare results across multiple algorithms
        
        Args:
            algorithms: List of algorithm names to compare
            
        Returns:
            Comparison data dictionary
        """
        comparison = {
            'algorithms': algorithms,
            'metrics': {},
            'queries': {}
        }
        
        for algo in algorithms:
            metadata = self._load_experiment_metadata(algo)
            results = self.load_optimization_results(algo)
            
            if results:
                # Extract key metrics
                selected_views = results.get('selected_views', [])
                comparison['metrics'][algo] = {
                    'num_views': results.get('num_selected_views', len(selected_views)),
                    'total_utility': results.get('total_utility', 0),
                    'storage_used_mb': results.get('total_storage_mb', 0),
                    'storage_used_bytes': results.get('total_storage', 0),
                    'optimization_time': metadata.get('execution_times', {}).get('optimization', 0) if metadata else 0
                }
                
                # Get query performance
                query_perf = self.load_query_performance(algo)
                if query_perf:
                    for qp in query_perf:
                        query_id = qp['query_id']
                        if query_id not in comparison['queries']:
                            comparison['queries'][query_id] = {}
                        comparison['queries'][query_id][algo] = qp
        
        return comparison
    
    def load_execution_summary(self, algorithm: str) -> Optional[Dict]:
        """Load comprehensive execution summary for an algorithm
        
        This includes timing for all phases, benchmark results summary,
        and MV creation statistics.
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            Comprehensive execution summary or None
        """
        algo_dir = self.output_dir / algorithm
        summary = {}
        
        # Load summary.json (phase timings)
        summary_file = algo_dir / 'summary.json'
        if summary_file.exists():
            try:
                with open(summary_file, 'r') as f:
                    summary_data = json.load(f)
                summary['total_execution_time'] = summary_data.get('total_execution_time', 0)
                summary['phases'] = summary_data.get('phases', {})
                summary['timestamp'] = summary_data.get('timestamp', '')
            except Exception as e:
                print(f"Error loading summary.json: {e}")
        
        # Load benchmark results
        benchmark_file = algo_dir / 'benchmark' / 'benchmark_results.json'
        if benchmark_file.exists():
            try:
                with open(benchmark_file, 'r') as f:
                    benchmark_data = json.load(f)
                summary['benchmark'] = {
                    'total_queries': benchmark_data.get('total_queries', 0),
                    'successful': benchmark_data.get('successful', 0),
                    'failed': benchmark_data.get('failed', 0),
                    'total_time': benchmark_data.get('total_time', 0),
                    'benchmark_elapsed': benchmark_data.get('benchmark_elapsed', 0),
                    'avg_time_per_query': benchmark_data.get('avg_time_per_query', 0),
                }
                # Get failed query details
                if 'queries' in benchmark_data:
                    failed_queries = [q for q in benchmark_data['queries'] if not q.get('success', True)]
                    summary['benchmark']['failed_queries'] = failed_queries
            except Exception as e:
                print(f"Error loading benchmark results: {e}")
        
        # Load MV creation log
        creation_log_file = algo_dir / 'mv_creation' / 'creation_log.json'
        if creation_log_file.exists():
            try:
                with open(creation_log_file, 'r') as f:
                    creation_data = json.load(f)
                summary['mv_creation'] = {
                    'total_mvs': creation_data.get('total_mvs', 0),
                    'created': creation_data.get('created', 0),
                    'failed': creation_data.get('failed', 0),
                    'total_time': creation_data.get('total_time', 0),
                }
                # Get failed MV details
                if 'mvs' in creation_data:
                    failed_mvs = [mv for mv in creation_data['mvs'] if mv.get('status') != 'SUCCESS']
                    summary['mv_creation']['failed_mvs'] = failed_mvs
                    
                    # Calculate total size of created MVs
                    total_size_mb = sum(mv.get('size_mb', 0) for mv in creation_data['mvs'] if mv.get('status') == 'SUCCESS')
                    summary['mv_creation']['total_size_mb'] = total_size_mb
            except Exception as e:
                print(f"Error loading MV creation log: {e}")
        
        return summary if summary else None
    
    def load_execution_plan(self, algorithm: str, query_id: str, plan_type: str = 'rewritten') -> Optional[Dict]:
        """Load execution plan for a query
        
        Args:
            algorithm: Algorithm name
            query_id: Query identifier
            plan_type: 'original' or 'rewritten'
            
        Returns:
            Execution plan dictionary or None
        """
        algo_dir = self.output_dir / algorithm
        plan_file = algo_dir / f'execution_plans/{query_id}_{plan_type}.json'
        
        if not plan_file.exists():
            return None
        
        with open(plan_file, 'r') as f:
            return json.load(f)
