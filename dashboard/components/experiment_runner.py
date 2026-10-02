"""
Experiment Runner Component

Manages the execution of optimization experiments.
"""

import streamlit as st
import subprocess
import threading
import queue
import time
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class ExperimentRunner:
    """Manages experiment execution and progress tracking"""
    
    # Phase markers with step numbers from run_experiment.py
    PHASE_MARKERS = {
        "[1/6] Parsing queries": ("query_parsing", 1),
        "[1/6] Skipping query parsing": ("query_parsing", 1),
        "[2/6] Running": ("optimization", 2),
        "[2/6] Skipping optimization": ("optimization", 2),
        "[3/6] Generating": ("sql_generation", 3),
        "[3/6] Skipping SQL generation": ("sql_generation", 3),
        "[4/6] Creating MVs": ("mv_creation", 4),
        "[4/6] Skipping MV creation": ("mv_creation", 4),
        "[5/6] Rewriting queries": ("query_rewriting", 5),
        "[5/6] Skipping query rewriting": ("query_rewriting", 5),
        "[6/6] Executing benchmark": ("benchmark", 6),
        "[6/6] Skipping benchmark": ("benchmark", 6),
    }
    
    def __init__(self):
        self.is_running = False
        self.current_phase = None
        self.current_phase_step = 0
        self.current_algorithm = None
        self.current_algorithm_idx = 0
        self.total_algorithms = 1
        self.progress = 0.0
        self.log_queue = queue.Queue()
        self.process = None
        self.thread = None
        self.start_time = None
        self.phase_start_time = None
        self.phase_progress = {}  # Track progress within each phase
        self.mv_creation_progress = {"current": 0, "total": 0}
        self.benchmark_progress = {"current": 0, "total": 0}
        self.last_log_lines = []  # Keep track of recent logs for context
        
    def run_experiment(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """Run experiment in background thread
        
        Args:
            algorithms: List of algorithm names to run
            storage_limit_mb: Storage limit in MB
            phases: Dictionary of phase names to boolean (enabled/disabled)
            settings: Additional settings dictionary (includes 'insert_queries', 'output_dir', 'verbose')
            on_progress: Callback for progress updates
            on_complete: Callback for completion
            on_error: Callback for errors
        """
        if self.is_running:
            raise RuntimeError("Experiment is already running")
        
        self.is_running = True
        self.progress = 0.0
        self.start_time = time.time()
        self.total_algorithms = len(algorithms)
        self.current_algorithm_idx = 0
        self.phase_progress = {}
        self.mv_creation_progress = {"current": 0, "total": 0}
        self.benchmark_progress = {"current": 0, "total": 0}
        self.last_log_lines = []
        
        # Start background thread
        self.thread = threading.Thread(
            target=self._run_experiment_thread,
            args=(algorithms, storage_limit_mb, phases, settings, on_progress, on_complete, on_error),
            daemon=True
        )
        self.thread.start()
        
    def _run_experiment_thread(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict,
        on_progress: Optional[Callable],
        on_complete: Optional[Callable],
        on_error: Optional[Callable]
    ):
        """Background thread for running experiment"""
        try:
            # Build command
            cmd = self._build_command(algorithms, storage_limit_mb, phases, settings)
            
            self.log_queue.put(f"[INFO] Starting experiment...\n")
            self.log_queue.put(f"[INFO] Algorithms: {', '.join(algorithms)}\n")
            self.log_queue.put(f"[INFO] Storage limit: {storage_limit_mb} MB\n")
            self.log_queue.put(f"[INFO] Insert queries: {settings.get('insert_queries', 1000)}\n")
            self.log_queue.put(f"[INFO] Workload: {settings.get('workload_type', 'redbench-job')}\n")
            self.log_queue.put(f"[INFO] Enabled phases: {', '.join([k for k, v in phases.items() if v])}\n")
            self.log_queue.put(f"[DEBUG] Command: {' '.join(cmd)}\n")
            
            # Run subprocess
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(project_root)
            )
            
            # Stream output
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.log_queue.put(line)
                    self._parse_progress(line)
                    if on_progress:
                        on_progress(self.progress, self.current_phase, self.current_algorithm)
            
            # Wait for completion
            return_code = self.process.wait()
            
            if return_code == 0:
                self.log_queue.put("[INFO] Experiment completed successfully\n")
                if on_complete:
                    on_complete()
            else:
                error_msg = f"Experiment failed with return code {return_code}"
                self.log_queue.put(f"[ERROR] {error_msg}\n")
                if on_error:
                    on_error(error_msg)
                    
        except Exception as e:
            error_msg = f"Exception during experiment: {str(e)}"
            self.log_queue.put(f"[ERROR] {error_msg}\n")
            if on_error:
                on_error(error_msg)
        finally:
            self.is_running = False
            self.process = None
            
    def _build_command(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict
    ) -> List[str]:
        """Build command line arguments for run_experiment.py"""
        cmd = [
            sys.executable,
            str(project_root / "scripts" / "run_experiment.py"),
            "--algorithms"
        ] + algorithms
        
        # Add enabled phases using --phases flag
        enabled_phases = [phase_name for phase_name, enabled in phases.items() if enabled]
        if enabled_phases:
            cmd.append("--phases")
            cmd.extend(enabled_phases)
        
        # Add other settings
        if settings.get('output_dir'):
            cmd.extend(["--output", settings['output_dir']])
            
        if settings.get('insert_queries') is not None:
            cmd.extend(["--insert-queries", str(settings['insert_queries'])])
            
        if settings.get('verbose'):
            cmd.append("--verbose")
        
        # Add workload configuration
        if settings.get('workload_type'):
            cmd.extend(["--workload-type", settings['workload_type']])
            
        return cmd
    
    def _parse_progress(self, line: str):
        """Parse log line to extract progress information"""
        # Keep track of recent lines for context
        self.last_log_lines.append(line)
        if len(self.last_log_lines) > 20:
            self.last_log_lines.pop(0)
        
        # Parse algorithm start
        if "Running ILP:" in line:
            algo_name = line.split("Running ILP:")[1].strip()
            self.current_algorithm = algo_name
            self.phase_start_time = time.time()
            self.current_phase_step = 0
        
        # Parse algorithm completion
        if "Completed" in line and "in" in line and "seconds" in line:
            # Algorithm completed, move to next
            self.current_algorithm_idx += 1
            
        # Parse phase markers
        for marker, (phase, step) in self.PHASE_MARKERS.items():
            if marker in line:
                self.current_phase = phase
                self.current_phase_step = step
                self.phase_start_time = time.time()
                self.phase_progress[phase] = 0.0
                break
        
        # Parse MV creation progress: "[idx/total] Creating mv_xxx..."
        mv_match = re.search(r'\[(\d+)/(\d+)\]\s+Creating\s+(leaf_|non_leaf_|mv_)', line)
        if mv_match:
            current = int(mv_match.group(1))
            total = int(mv_match.group(2))
            self.mv_creation_progress = {"current": current, "total": total}
            if total > 0:
                self.phase_progress['mv_creation'] = (current / total) * 100.0
        
        # Parse MV creation success/failure
        if "✓" in line and self.current_phase == 'mv_creation':
            self.mv_creation_progress["current"] += 0  # Already updated by the [idx/total] pattern
        
        # Parse selected MVs count for optimization phase
        if "Selected" in line and "materialized views" in line:
            self.phase_progress['optimization'] = 100.0
            
        # Parse SQL generation progress
        if "Generated SQL for" in line:
            self.phase_progress['sql_generation'] = 100.0
            
        # Parse query rewriting progress
        if "Rewritten" in line and "queries to" in line:
            self.phase_progress['query_rewriting'] = 100.0
        
        # Parse benchmark progress
        benchmark_match = re.search(r'Executed\s+(\d+)/(\d+)\s+queries', line, re.IGNORECASE)
        if benchmark_match:
            current = int(benchmark_match.group(1))
            total = int(benchmark_match.group(2))
            self.benchmark_progress = {"current": current, "total": total}
            if total > 0:
                self.phase_progress['benchmark'] = (current / total) * 100.0
        
        # Parse benchmark query progress: "Query X/Y (Z%)" format
        query_progress_match = re.search(r'Query\s+(\d+)/(\d+)\s+\([\d.]+%\)', line, re.IGNORECASE)
        if query_progress_match:
            current = int(query_progress_match.group(1))
            total = int(query_progress_match.group(2))
            self.benchmark_progress = {"current": current, "total": total}
            if total > 0 and self.current_phase == 'benchmark':
                self.phase_progress['benchmark'] = (current / total) * 100.0
        
        # Also match "[X/Y]" pattern (legacy format)
        legacy_query_match = re.search(r'\[(\d+)/(\d+)\]', line)
        if legacy_query_match and self.current_phase == 'benchmark':
            current = int(legacy_query_match.group(1))
            total = int(legacy_query_match.group(2))
            self.benchmark_progress = {"current": current, "total": total}
            if total > 0:
                self.phase_progress['benchmark'] = (current / total) * 100.0
        
        # Parse benchmark completion
        if "Benchmark Summary" in line:
            self.phase_progress['benchmark'] = 100.0
        
        # Calculate overall progress based on current algorithm and phase
        self._calculate_overall_progress()
    
    def _calculate_overall_progress(self):
        """Calculate overall progress percentage"""
        # Each algorithm contributes equally to the total progress
        algo_weight = 100.0 / max(1, self.total_algorithms)
        
        # Calculate progress within current algorithm (6 phases)
        phase_weight = algo_weight / 6.0
        
        # Progress from completed algorithms
        completed_algo_progress = self.current_algorithm_idx * algo_weight
        
        # Progress from completed phases in current algorithm
        completed_phase_progress = (self.current_phase_step - 1) * phase_weight if self.current_phase_step > 0 else 0
        
        # Progress within current phase
        current_phase_progress = self.phase_progress.get(self.current_phase, 0.0) / 100.0 * phase_weight if self.current_phase else 0
        
        self.progress = completed_algo_progress + completed_phase_progress + current_phase_progress
        self.progress = min(100.0, max(0.0, self.progress))
                
    def stop_experiment(self):
        """Stop running experiment"""
        if self.process:
            self.process.terminate()
            self.log_queue.put("[INFO] Experiment stopped by user\n")
            self.is_running = False
            
    def get_logs(self, max_lines: int = 100) -> List[str]:
        """Get recent log lines
        
        Args:
            max_lines: Maximum number of lines to return
            
        Returns:
            List of log lines
        """
        logs = []
        try:
            while not self.log_queue.empty() and len(logs) < max_lines:
                try:
                    logs.append(self.log_queue.get_nowait())
                except queue.Empty:
                    break
        except Exception as e:
            logs.append(f"[ERROR] Failed to get logs: {str(e)}\n")
        return logs
    
    def get_status(self) -> Dict:
        """Get current experiment status
        
        Returns:
            Dictionary with status information
        """
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        # Estimate remaining time based on progress
        if self.progress > 0:
            estimated_total = elapsed / (self.progress / 100.0)
            remaining = estimated_total - elapsed
        else:
            remaining = None
        
        return {
            'is_running': self.is_running,
            'current_phase': self.current_phase,
            'current_phase_step': self.current_phase_step,
            'current_algorithm': self.current_algorithm,
            'current_algorithm_idx': self.current_algorithm_idx,
            'total_algorithms': self.total_algorithms,
            'progress': self.progress,
            'phase_progress': self.phase_progress.copy(),
            'elapsed_time': elapsed,
            'estimated_remaining': remaining,
            'mv_creation_progress': self.mv_creation_progress.copy(),
            'benchmark_progress': self.benchmark_progress.copy(),
        }
    
    def get_detailed_progress(self) -> Dict:
        """Get detailed progress information for UI display
        
        Returns:
            Dictionary with detailed progress information
        """
        status = self.get_status()
        
        # Format elapsed time
        elapsed = status['elapsed_time']
        elapsed_str = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}"
        
        # Format remaining time
        if status['estimated_remaining'] is not None and status['estimated_remaining'] > 0:
            remaining = status['estimated_remaining']
            remaining_str = f"~{int(remaining // 60)}:{int(remaining % 60):02d}"
        else:
            remaining_str = "計算中..."
        
        # Get phase display name
        phase_names = {
            'query_parsing': 'クエリ解析',
            'optimization': 'ILP最適化',
            'sql_generation': 'SQL生成',
            'mv_creation': 'MV作成',
            'query_rewriting': 'クエリ書換え',
            'benchmark': 'ベンチマーク',
        }
        
        current_phase_name = phase_names.get(status['current_phase'], '準備中')
        
        # Phase-specific details
        phase_detail = ""
        if status['current_phase'] == 'mv_creation':
            mv_prog = status['mv_creation_progress']
            if mv_prog['total'] > 0:
                phase_detail = f"({mv_prog['current']}/{mv_prog['total']} MVs)"
        elif status['current_phase'] == 'benchmark':
            bm_prog = status['benchmark_progress']
            if bm_prog['total'] > 0:
                phase_detail = f"({bm_prog['current']}/{bm_prog['total']} クエリ)"
        
        return {
            'algorithm': status['current_algorithm'] or '開始中...',
            'algorithm_progress': f"{status['current_algorithm_idx'] + 1}/{status['total_algorithms']}",
            'phase': current_phase_name,
            'phase_step': f"{status['current_phase_step']}/6",
            'phase_detail': phase_detail,
            'overall_progress': status['progress'],
            'elapsed_time': elapsed_str,
            'remaining_time': remaining_str,
            'phase_progress': status['phase_progress'],
        }
