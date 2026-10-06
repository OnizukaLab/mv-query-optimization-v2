"""On-disk layout of experiment results.

Every experiment gets its own directory so runs never overwrite or mix with each other::

    Output/
    ├── runs/<run_id>/              # one experiment (all algorithms of one invocation)
    │   ├── manifest.json           # conditions the run was started with
    │   └── <algorithm>/...         # optimization/, sql/, benchmark/, query_rewrite/, summary.json
    └── artifacts/<workload_id>_i<N>/   # parse results shared by runs on the same workload
        ├── qp_class.pkl, qp_class_metadata.json, parse_statistics.json
        ├── parsed/                 # annotated query plans
        └── bj_calibrated.json

A workload is identified by the *content* of the query files it resolves to (see
``compute_workload_id``), not by a name or path, so renaming a folder does not invalidate caches
and editing a query file does.
"""

import hashlib
import json
import logging
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNS_DIRNAME = "runs"
ARTIFACTS_DIRNAME = "artifacts"
MANIFEST_NAME = "manifest.json"
ROOT_SET_ID = "_root"
WORKLOAD_ID_LENGTH = 12

# Directories under Output/ that are never result sets.
_NON_SET_DIRS = frozenset({RUNS_DIRNAME, ARTIFACTS_DIRNAME, "web_jobs", "web_cache", "logs"})
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESULT_FILES = ("summary.json", "benchmark/benchmark_results.json", "optimization/result.json")


# ---- workload identity ---------------------------------------------------------------------


def resolve_workload_files(settings: Any) -> tuple[list[str], dict[str, int]]:
    """Query plan files the parser loads for ``settings`` and how often each is used.

    Mirrors ``QueryParser.query_parse``: the same selection and the same natural sort order, which
    is the query index used by ``usage_positions``. Frequencies matter too (RedBench repeats
    queries), so both are part of a workload's identity.

    Returns:
        ``(files in parse order, {file: frequency})``.
    """
    from src.utils.legacy import (
        get_all_ceb_queries,
        get_all_job_queries,
        get_red_queries,
        natural_sort_key,
    )

    bench = settings.benchmark
    if bench.query_selection_mode == "all_job":
        files, freq = get_all_job_queries(bench.queries_dir)
    elif bench.query_selection_mode == "all_ceb":
        files, freq = get_all_ceb_queries(
            bench.queries_dir, bench.ceb_template, limit=getattr(bench, "ceb_limit", None)
        )
    else:
        files, freq = get_red_queries(bench.queries_dir, bench.workloads_dir, bench.type == "ceb")
    return sorted(files, key=natural_sort_key), dict(freq)


def compute_workload_id(
    files: list[str], base_dir: str | Path, frequencies: dict[str, int] | None = None
) -> str:
    """Short content hash of an ordered list of query files.

    Two runs share a workload id exactly when they load the same files (relative to
    ``base_dir``) with the same bytes and usage frequencies in the same order.

    Args:
        files: Query plan files in parse order.
        base_dir: Directory the files' identity is taken relative to (e.g. ``queries_dir``).
        frequencies: How often each file is used in the workload (default 1).

    Returns:
        Hex digest prefix of ``WORKLOAD_ID_LENGTH`` characters.
    """
    base = Path(base_dir).resolve()
    digest = hashlib.sha256()
    for f in files:
        p = Path(f).resolve()
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            rel = p.as_posix()
        digest.update(f"{rel}\0{(frequencies or {}).get(f, 1)}\0".encode())
        digest.update(hashlib.sha256(p.read_bytes()).digest())
    return digest.hexdigest()[:WORKLOAD_ID_LENGTH]


def workload_label(workload_type: str | None, settings: Any) -> str:
    """Human-readable workload name for run ids and the dashboard (not an identifier)."""
    if workload_type:
        label = workload_type
    else:
        label = f"{settings.benchmark.query_selection_mode}-{settings.benchmark.type}"
    if workload_type == "ceb-1a":
        label = f"ceb-{settings.benchmark.ceb_template}"
        limit = getattr(settings.benchmark, "ceb_limit", None)
        if limit is not None:
            label += f"-{limit}"
    return label


# ---- run ids and directories ---------------------------------------------------------------


def new_run_id(label: str, now: float | None = None) -> str:
    """``YYYYMMDD-HHMMSS_<label>``; sorts chronologically."""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return f"{stamp}_{_slug(label)}"


def validate_run_id(run_id: str) -> str:
    """Return ``run_id`` if it is safe to use as a directory name.

    Raises:
        ValueError: If it could escape ``Output/runs/`` or is otherwise malformed.
    """
    if not _RUN_ID_RE.match(run_id) or run_id in (".", ".."):
        raise ValueError(f"Invalid run id: {run_id!r}")
    return run_id


def runs_root(output_root: str | Path) -> Path:
    """``<output_root>/runs``."""
    return Path(output_root) / RUNS_DIRNAME


def run_dir(output_root: str | Path, run_id: str) -> Path:
    """Directory of one run (not created)."""
    return runs_root(output_root) / validate_run_id(run_id)


def artifacts_dir(output_root: str | Path, workload_id: str, insert_queries: int) -> Path:
    """Parse-cache directory for a workload (not created).

    ``insert_queries`` is part of the key because maintenance costs in the parse result depend on it.
    """
    return Path(output_root) / ARTIFACTS_DIRNAME / f"{workload_id}_i{insert_queries}"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "run"


# ---- manifest ------------------------------------------------------------------------------


@dataclass
class RunManifest:
    """Conditions and status of one run, stored as ``manifest.json``."""

    run_id: str
    created_at: float
    status: str  # running | completed | failed
    workload: dict[str, Any]  # id, label, type, query_selection_mode, num_queries, ...
    params: dict[str, Any]  # algorithms, phases, storage_limit_bytes, insert_queries, warmup
    git_commit: str | None = None
    finished_at: float | None = None
    algorithms_done: list[str] = field(default_factory=list)
    algorithms_failed: list[str] = field(default_factory=list)

    def write(self, directory: Path) -> None:
        """Write ``manifest.json`` into ``directory`` (created if needed)."""
        directory.mkdir(parents=True, exist_ok=True)
        (directory / MANIFEST_NAME).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False)
        )

    @classmethod
    def read(cls, directory: Path) -> "RunManifest | None":
        """Load a run's manifest; ``None`` if absent or unreadable."""
        try:
            data = json.loads((directory / MANIFEST_NAME).read_text())
            return cls(**data)
        except (OSError, json.JSONDecodeError, TypeError) as e:
            if (directory / MANIFEST_NAME).exists():
                logger.warning(f"Unreadable manifest in {directory}: {e}")
            return None


def git_commit(cwd: str | Path | None = None) -> str | None:
    """Current commit hash (``-dirty`` suffix when the tree has local changes); ``None`` outside git."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{head}-dirty" if dirty else head


# ---- result sets ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultSetRef:
    """A directory holding one sub-directory per algorithm."""

    set_id: str
    path: Path
    kind: str  # "run" | "legacy"


def is_algorithm_dir(d: Path) -> bool:
    """True if ``d`` looks like ``<set>/<algorithm>/`` (has result files)."""
    return d.is_dir() and any((d / f).exists() for f in _RESULT_FILES)


def iter_result_sets(output_root: str | Path) -> list[ResultSetRef]:
    """Every result set under ``output_root``, runs first.

    Besides ``runs/<run_id>/`` this includes the pre-``runs/`` layout: ``Output/`` itself
    (``_root``, the latest run of each algorithm) and named directories directly under it.
    Sets with no algorithm results are skipped.
    """
    root = Path(output_root)
    if not root.is_dir():
        return []

    def has_results(d: Path) -> bool:
        return any(is_algorithm_dir(c) for c in d.iterdir())

    sets: list[ResultSetRef] = []
    runs = runs_root(root)
    if runs.is_dir():
        sets += [
            ResultSetRef(d.name, d, "run")
            for d in sorted(runs.iterdir())
            if d.is_dir() and not d.name.startswith(".") and has_results(d)
        ]
    if has_results(root):
        sets.append(ResultSetRef(ROOT_SET_ID, root, "legacy"))
    sets += [
        ResultSetRef(d.name, d, "legacy")
        for d in sorted(root.iterdir())
        if d.is_dir()
        and not d.name.startswith(".")
        and d.name not in _NON_SET_DIRS
        and has_results(d)
    ]
    return sets


def find_result_set(output_root: str | Path, set_id: str) -> ResultSetRef | None:
    """Resolve a set id without trusting it as a path; ``None`` if unknown."""
    if "/" in set_id or "\\" in set_id or set_id.startswith("."):
        return None
    return next((s for s in iter_result_sets(output_root) if s.set_id == set_id), None)
