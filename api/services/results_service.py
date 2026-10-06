"""Read-only access to experiment results under ``Output/``.

A *result set* is a directory holding one sub-directory per algorithm
(``<set>/<algo>/summary.json`` etc.). New runs live in ``Output/runs/<run_id>/`` together with a
``manifest.json`` describing their conditions. Results written before that layout are still
listed: ``Output`` itself (the latest run of each algorithm) and ``Output/<name>/``.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.utils.run_layout import (
    ROOT_SET_ID,
    ResultSetRef,
    RunManifest,
    find_result_set,
    is_algorithm_dir,
    iter_result_sets,
)

logger = logging.getLogger(__name__)

BASELINE = "none"


class ResultNotFoundError(KeyError):
    """Unknown result set."""


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        if path.exists():
            logger.warning(f"Unreadable result file {path}: {e}")
        return None


class ResultsService:
    """Lists result sets and builds algorithm comparisons."""

    def __init__(self, output_dir: Path):
        self._output = output_dir

    def _set(self, set_id: str) -> ResultSetRef:
        ref = find_result_set(self._output, set_id)
        if ref is None:
            raise ResultNotFoundError(set_id)
        return ref

    def _set_dir(self, set_id: str) -> Path:
        return self._set(set_id).path

    @staticmethod
    def _algorithms(set_dir: Path) -> list[Path]:
        return sorted(d for d in set_dir.iterdir() if is_algorithm_dir(d))

    @staticmethod
    def _manifest(ref: ResultSetRef) -> dict[str, Any] | None:
        m = RunManifest.read(ref.path) if ref.kind == "run" else None
        if m is None:
            return None
        wl = m.workload
        return {
            "status": m.status,
            "created_at": m.created_at,
            "finished_at": m.finished_at,
            "git_commit": m.git_commit,
            "workload": {k: wl.get(k) for k in ("id", "label", "num_queries", "query_selection_mode")},
            "params": m.params,
        }

    def list_sets(self) -> list[dict[str, Any]]:
        """All result sets with their algorithms, newest first."""
        sets = []
        for ref in iter_result_sets(self._output):
            algos = self._algorithms(ref.path)
            mtime = max(
                (f.stat().st_mtime for a in algos for f in a.glob("summary.json")),
                default=max(a.stat().st_mtime for a in algos),
            )
            sets.append(
                {
                    "id": ref.set_id,
                    "name": "Output (latest runs)" if ref.set_id == ROOT_SET_ID else ref.set_id,
                    "kind": ref.kind,
                    "algorithms": [a.name for a in algos],
                    "updated_at": mtime,
                    "manifest": self._manifest(ref),
                }
            )
        return sorted(sets, key=lambda s: s["updated_at"], reverse=True)

    def compare(self, set_id: str) -> dict[str, Any]:
        """Per-algorithm summary, benchmark, and optimization data plus derived speedups.

        Raises:
            ResultNotFoundError: If the set does not exist.
        """
        ref = self._set(set_id)
        algorithms = [self._load_algorithm(a) for a in self._algorithms(ref.path)]
        if not algorithms:
            raise ResultNotFoundError(set_id)

        base = next((a for a in algorithms if a["name"] == BASELINE), None)
        for a in algorithms:
            a["speedup_vs_baseline"] = self._speedup(a, base)
        return {
            "id": set_id,
            "kind": ref.kind,
            "manifest": self._manifest(ref),
            "algorithms": algorithms,
            "baseline": BASELINE if base else None,
            "warnings": self._warnings(algorithms),
        }

    def selected_views(self, set_id: str) -> dict[str, list[dict[str, Any]]]:
        """Views each algorithm selected (dicts with ``node_id``), keyed by algorithm name.

        Algorithms without a readable optimization result are omitted.

        Raises:
            ResultNotFoundError: If the set does not exist.
        """
        set_dir = self._set_dir(set_id)
        selected: dict[str, list[dict[str, Any]]] = {}
        for algo_dir in self._algorithms(set_dir):
            opt = _read_json(algo_dir / "optimization" / "result.json")
            views = (opt or {}).get("selected_views")
            if isinstance(views, list):
                selected[algo_dir.name] = [
                    v for v in views if isinstance(v, dict) and isinstance(v.get("node_id"), str)
                ]
        return selected

    @staticmethod
    def _speedup(algo: dict[str, Any], base: dict[str, Any] | None) -> float | None:
        """Baseline time / algorithm time, only when both ran the same workload."""
        if base is None or algo["name"] == BASELINE or not algo["benchmark"] or not base["benchmark"]:
            return None
        b, a = base["benchmark"], algo["benchmark"]
        same = b["total_queries"] == a["total_queries"] and b.get("workload_type") == a.get(
            "workload_type"
        )
        if not same or not a["total_time"]:
            return None
        return round(b["total_time"] / a["total_time"], 3)

    @staticmethod
    def _load_algorithm(d: Path) -> dict[str, Any]:
        summary = _read_json(d / "summary.json")
        bench = _read_json(d / "benchmark" / "benchmark_results.json")
        opt = _read_json(d / "optimization" / "result.json")
        return {
            "name": d.name,
            "summary": summary,
            "benchmark": (
                {k: v for k, v in bench.items() if k != "queries"} if bench is not None else None
            ),
            "optimization": (
                {k: v for k, v in opt.items() if k not in ("selected_views", "metadata")}
                | {"num_selected_views": opt.get("num_selected_views", len(opt.get("selected_views", [])))}
                if opt is not None
                else None
            ),
        }

    @staticmethod
    def _warnings(algorithms: list[dict[str, Any]]) -> list[str]:
        """Flag comparisons that are not apples-to-apples."""
        benches = [(a["name"], a["benchmark"]) for a in algorithms if a["benchmark"]]
        warnings = []
        if len({b["total_queries"] for _, b in benches}) > 1:
            detail = ", ".join(f"{n}={b['total_queries']}" for n, b in benches)
            warnings.append(f"Different query counts across algorithms ({detail})")
        if len({b.get("workload_type") for _, b in benches}) > 1:
            detail = ", ".join(f"{n}={b.get('workload_type')}" for n, b in benches)
            warnings.append(f"Different workloads across algorithms ({detail})")
        for name, b in benches:
            if b["failed"]:
                warnings.append(f"{name}: {b['failed']} queries failed")
        return warnings
