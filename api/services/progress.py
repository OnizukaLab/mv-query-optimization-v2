"""Progress extraction from ``scripts/run_experiment.py`` log output."""

import re
from dataclasses import dataclass, field
from typing import Any

# Log markers emitted by run_experiment.py -> (phase name, step number)
PHASE_MARKERS: dict[str, tuple[str, int]] = {
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

TOTAL_PHASES = 6

_MV_CREATE = re.compile(r"\[(\d+)/(\d+)\]\s+Creating\s+(?:leaf_|non_leaf_|mv_)")
_EXECUTED = re.compile(r"Executed\s+(\d+)/(\d+)\s+queries", re.IGNORECASE)
_QUERY_PROGRESS = re.compile(r"Query\s+(\d+)/(\d+)\s+\([\d.]+%\)", re.IGNORECASE)
_LEGACY = re.compile(r"\[(\d+)/(\d+)\]")
_COMPLETED = re.compile(r"Completed .+ in [\d.]+ seconds")


@dataclass
class ProgressTracker:
    """Incrementally derives overall progress from log lines."""

    total_algorithms: int = 1
    current_algorithm: str | None = None
    algorithms_done: int = 0
    current_phase: str | None = None
    phase_step: int = 0
    phase_progress: dict[str, float] = field(default_factory=dict)
    progress: float = 0.0

    def feed(self, line: str) -> None:
        """Update state from one log line."""
        if "Running ILP:" in line:
            self.current_algorithm = line.split("Running ILP:", 1)[1].strip()
            self.phase_step = 0
            self.current_phase = None
            self.phase_progress = {}

        if _COMPLETED.search(line):
            self.algorithms_done += 1

        for marker, (phase, step) in PHASE_MARKERS.items():
            if marker in line:
                self.current_phase, self.phase_step = phase, step
                self.phase_progress[phase] = 0.0
                break

        self._feed_counts(line)
        self._recompute()

    def _feed_counts(self, line: str) -> None:
        if m := _MV_CREATE.search(line):
            self._set_ratio("mv_creation", m)
        if "Selected" in line and "materialized views" in line:
            self.phase_progress["optimization"] = 100.0
        if "Generated SQL for" in line:
            self.phase_progress["sql_generation"] = 100.0
        if "Rewritten" in line and "queries to" in line:
            self.phase_progress["query_rewriting"] = 100.0
        if m := _EXECUTED.search(line) or _QUERY_PROGRESS.search(line):
            self._set_ratio("benchmark", m)
        elif self.current_phase == "benchmark" and (m := _LEGACY.search(line)):
            self._set_ratio("benchmark", m)
        if "Benchmark Summary" in line:
            self.phase_progress["benchmark"] = 100.0

    def _set_ratio(self, phase: str, m: re.Match[str]) -> None:
        current, total = int(m.group(1)), int(m.group(2))
        if total > 0:
            self.phase_progress[phase] = min(current / total * 100.0, 100.0)

    def _recompute(self) -> None:
        algo_weight = 100.0 / max(1, self.total_algorithms)
        phase_weight = algo_weight / TOTAL_PHASES
        done = min(self.algorithms_done, self.total_algorithms) * algo_weight
        finished_phases = max(self.phase_step - 1, 0) * phase_weight
        within = (
            self.phase_progress.get(self.current_phase, 0.0) / 100.0 * phase_weight
            if self.current_phase
            else 0.0
        )
        self.progress = min(100.0, max(0.0, done + finished_phases + within))

    def snapshot(self) -> dict[str, Any]:
        """Serializable view of the current progress."""
        return {
            "progress": round(self.progress, 1),
            "current_algorithm": self.current_algorithm,
            "algorithms_done": self.algorithms_done,
            "total_algorithms": self.total_algorithms,
            "current_phase": self.current_phase,
            "phase_step": self.phase_step,
            "phase_progress": {k: round(v, 1) for k, v in self.phase_progress.items()},
        }
