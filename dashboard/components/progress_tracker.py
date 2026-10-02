"""
Progress Tracker Component

Tracks experiment execution progress and status.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum


class PhaseStatus(Enum):
    """Enumeration of phase statuses"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseInfo:
    """Information about an execution phase"""
    name: str
    display_name: str
    status: PhaseStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    progress: float = 0.0
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate phase duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def status_icon(self) -> str:
        """Get emoji icon for status"""
        icons = {
            PhaseStatus.PENDING: "⏳",
            PhaseStatus.RUNNING: "🔄",
            PhaseStatus.COMPLETED: "✅",
            PhaseStatus.FAILED: "❌",
            PhaseStatus.SKIPPED: "⏭️"
        }
        return icons.get(self.status, "❓")


class ProgressTracker:
    """Tracks progress of experiment execution"""
    
    PHASE_NAMES = {
        'query_parsing': 'Query Parsing',
        'optimization': 'ILP Optimization',
        'sql_generation': 'SQL Generation',
        'mv_creation': 'MV Creation',
        'query_rewriting': 'Query Rewriting',
        'benchmark': 'Benchmark Execution'
    }
    
    def __init__(self, algorithms: List[str], enabled_phases: Dict[str, bool]):
        """Initialize progress tracker
        
        Args:
            algorithms: List of algorithm names to run
            enabled_phases: Dictionary of phase names to enabled status
        """
        self.algorithms = algorithms
        self.enabled_phases = enabled_phases
        self.current_algorithm_idx = 0
        self.phases: Dict[str, PhaseInfo] = {}
        
        # Initialize phases
        for phase_key, display_name in self.PHASE_NAMES.items():
            if enabled_phases.get(phase_key, True):
                status = PhaseStatus.PENDING
            else:
                status = PhaseStatus.SKIPPED
            
            self.phases[phase_key] = PhaseInfo(
                name=phase_key,
                display_name=display_name,
                status=status
            )
    
    @property
    def current_algorithm(self) -> Optional[str]:
        """Get current algorithm being processed"""
        if 0 <= self.current_algorithm_idx < len(self.algorithms):
            return self.algorithms[self.current_algorithm_idx]
        return None
    
    @property
    def overall_progress(self) -> float:
        """Calculate overall progress percentage"""
        if not self.algorithms:
            return 0.0
        
        total_phases = len([p for p in self.phases.values() if p.status != PhaseStatus.SKIPPED])
        if total_phases == 0:
            return 0.0
        
        completed_phases = len([p for p in self.phases.values() if p.status == PhaseStatus.COMPLETED])
        current_phase_progress = sum(p.progress for p in self.phases.values() if p.status == PhaseStatus.RUNNING)
        
        algo_progress = (completed_phases + current_phase_progress) / total_phases
        algo_weight = (self.current_algorithm_idx + algo_progress) / len(self.algorithms)
        
        return algo_weight * 100.0
    
    def start_phase(self, phase_name: str):
        """Mark phase as started
        
        Args:
            phase_name: Name of the phase
        """
        if phase_name in self.phases:
            self.phases[phase_name].status = PhaseStatus.RUNNING
            self.phases[phase_name].start_time = datetime.now()
            self.phases[phase_name].progress = 0.0
    
    def update_phase_progress(self, phase_name: str, progress: float):
        """Update phase progress
        
        Args:
            phase_name: Name of the phase
            progress: Progress percentage (0-100)
        """
        if phase_name in self.phases:
            self.phases[phase_name].progress = min(100.0, max(0.0, progress))
    
    def complete_phase(self, phase_name: str, success: bool = True):
        """Mark phase as completed
        
        Args:
            phase_name: Name of the phase
            success: Whether phase completed successfully
        """
        if phase_name in self.phases:
            self.phases[phase_name].status = PhaseStatus.COMPLETED if success else PhaseStatus.FAILED
            self.phases[phase_name].end_time = datetime.now()
            self.phases[phase_name].progress = 100.0 if success else 0.0
    
    def next_algorithm(self):
        """Move to next algorithm"""
        self.current_algorithm_idx += 1
        
        # Reset phases for next algorithm
        for phase in self.phases.values():
            if phase.status not in [PhaseStatus.SKIPPED]:
                phase.status = PhaseStatus.PENDING
                phase.start_time = None
                phase.end_time = None
                phase.progress = 0.0
    
    def get_phase_summary(self) -> List[Dict]:
        """Get summary of all phases
        
        Returns:
            List of phase summary dictionaries
        """
        summary = []
        for phase in self.phases.values():
            summary.append({
                'name': phase.display_name,
                'status': phase.status.value,
                'status_icon': phase.status_icon,
                'progress': phase.progress,
                'duration': phase.duration,
                'is_running': phase.status == PhaseStatus.RUNNING
            })
        return summary
    
    def get_status_summary(self) -> Dict:
        """Get overall status summary
        
        Returns:
            Status summary dictionary
        """
        completed_phases = [p for p in self.phases.values() if p.status == PhaseStatus.COMPLETED]
        failed_phases = [p for p in self.phases.values() if p.status == PhaseStatus.FAILED]
        
        return {
            'current_algorithm': self.current_algorithm,
            'algorithm_progress': f"{self.current_algorithm_idx + 1}/{len(self.algorithms)}",
            'overall_progress': self.overall_progress,
            'completed_phases': len(completed_phases),
            'failed_phases': len(failed_phases),
            'total_phases': len([p for p in self.phases.values() if p.status != PhaseStatus.SKIPPED])
        }
