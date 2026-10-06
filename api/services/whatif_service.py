"""What-if planning: plan a query as if some plan nodes were materialized.

The MVs are created inside a transaction that is *always rolled back*, in a throw-away schema
that shadows ``public`` through ``search_path``. Nothing persists, and MV names cannot clash
with real MVs left in the database by an experiment. Only server-generated DDL is executed.
"""

import dataclasses
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg2

from api.services.plan_service import PlanError
from api.services.workload_service import NodeNotFoundError, WorkloadIndex
from config.settings import DatabaseConfig
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

LARGE_MV_BYTES = 256 * 1024 * 1024
BASELINE_ALGORITHM = "none"


class WhatIfBusyError(RuntimeError):
    """Another what-if is already running."""


class LargeMVError(RuntimeError):
    """The MVs would be large; the caller must confirm."""

    def __init__(self, size_bytes: int):
        super().__init__(f"Creating these MVs needs about {size_bytes / 1024**2:.0f} MB")
        self.size_bytes = size_bytes


class InvalidSelectionError(ValueError):
    """Node ids are not part of the query."""


def _relations(plan: dict[str, Any]) -> set[str]:
    found = {plan["Relation Name"]} if "Relation Name" in plan else set()
    for child in plan.get("Plans", []):
        found |= _relations(child)
    return found


class WhatIfService:
    """Plans queries with hypothetical materialized views and lists experiment MV selections."""

    def __init__(self, workload: WorkloadIndex, db_config: DatabaseConfig, output_dir: Path, cache_dir: Path):
        self._workload = workload
        self._db = db_config
        self._output = output_dir
        self._cache = cache_dir
        self._busy = threading.Lock()
        self._views_cache: dict[tuple[str, float], tuple[bool, list[dict[str, Any]]]] = {}

    # ---- planning ----------------------------------------------------------------------

    def plan_with_mvs(
        self,
        query_id: str,
        node_ids: list[str],
        analyze: bool = False,
        confirm_large: bool = False,
        force: bool = False,
        timeout_s: int = 300,
    ) -> dict[str, Any]:
        """EXPLAIN the query rewritten onto ``node_ids`` with those MVs created transiently.

        Raises:
            InvalidSelectionError: Empty/unknown nodes or nodes not in the query.
            LargeMVError: Estimated MV size exceeds the threshold and ``confirm_large`` is False.
            WhatIfBusyError: Another what-if is running.
            PlanError: PostgreSQL error.
        """
        nodes = sorted(set(node_ids))
        self._validate(query_id, nodes)
        key = hashlib.sha1(f"{query_id}|{','.join(nodes)}|{analyze}".encode()).hexdigest()[:20]
        cache_file = self._cache / f"{key}.json"
        if not force and cache_file.exists():
            return {**json.loads(cache_file.read_text()), "cached": True}

        size = sum(self._workload.node_size_bytes(n) for n in nodes)
        if size > LARGE_MV_BYTES and not confirm_large:
            raise LargeMVError(size)
        if not self._busy.acquire(blocking=False):
            raise WhatIfBusyError("Another what-if is running")
        try:
            rewritten, definitions = self._workload.build_rewrite(query_id, nodes)
            result = self._run_scratch(definitions, rewritten, analyze, timeout_s)
        finally:
            self._busy.release()

        for d in result["mvs"]:
            d["referenced_in_sql"] = bool(re.search(rf"\b{re.escape(d['node_id'])}\b", rewritten))
            d["used_in_plan"] = d["node_id"] in _relations(result["plan"])
            d["est_size_bytes"] = self._workload.node_size_bytes(d["node_id"])
        out = {
            "query_id": query_id,
            "node_ids": nodes,
            "rewritten_sql": rewritten,
            "analyzed": analyze,
            "computed_at": time.time(),
            **result,
        }
        self._cache.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out))
        return {**out, "cached": False}

    def _validate(self, query_id: str, nodes: list[str]) -> None:
        if not nodes:
            raise InvalidSelectionError("Select at least one node")
        try:
            q_idx = self._workload.query_index(query_id)
        except NodeNotFoundError as e:
            raise InvalidSelectionError(f"Unknown query {query_id}") from e
        for n in nodes:
            if not any(q == q_idx for q, _ in self._workload.node_positions(n)):
                raise InvalidSelectionError(f"Node {n} does not occur in query {query_id}")

    def _run_scratch(
        self, definitions: list[dict[str, Any]], sql: str, analyze: bool, timeout_s: int
    ) -> dict[str, Any]:
        schema = f"whatif_{uuid.uuid4().hex[:8]}"  # generated here, never user input
        db = DatabaseConnection(dataclasses.replace(self._db, timeout=timeout_s))
        mvs: list[dict[str, Any]] = []
        try:
            conn = db.get_connection()
            conn.set_session(readonly=False, autocommit=False)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"CREATE SCHEMA {schema}")
                    cur.execute(f"SET LOCAL search_path = {schema}, public")
                    for d in definitions:
                        t0 = time.time()
                        cur.execute(d["create_sql"])
                        if d["index_sql"]:
                            cur.execute(d["index_sql"])
                        cur.execute(f"ANALYZE {d['node_id']}")
                        mvs.append({"node_id": d["node_id"], "create_seconds": round(time.time() - t0, 2)})
                    options = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
                    cur.execute(f"EXPLAIN ({options}) {sql}")
                    explained = cur.fetchone()[0][0]
            finally:
                conn.rollback()  # always: nothing may persist
        except psycopg2.Error as e:
            logger.warning(f"What-if failed: {e}")
            raise PlanError(str(e).strip()) from e
        finally:
            db.close()
        return {
            "plan": explained["Plan"],
            "planning_time_ms": explained.get("Planning Time"),
            "execution_time_ms": explained.get("Execution Time"),
            "mvs": mvs,
        }

    # ---- experiment selections ---------------------------------------------------------

    def selections_for_query(self, query_id: str) -> list[dict[str, Any]]:
        """MV sets chosen by past experiments that touch this query, newest first.

        Only result files consistent with the current workload numbering are offered.
        """
        q_idx = self._workload.query_index(query_id)
        found = []
        if not self._output.exists():
            return found
        for set_dir in [self._output, *sorted(p for p in self._output.iterdir() if p.is_dir())]:
            for algo_dir in sorted(p for p in set_dir.iterdir() if p.is_dir()):
                result = algo_dir / "optimization" / "result.json"
                if not result.exists():
                    continue
                ok, views = self._load_views(result)
                if not ok:
                    continue
                used = sorted(
                    v["node_id"] for v in views if any(p[0] == q_idx for p in v.get("usage_positions", []))
                )
                if not used:
                    continue
                found.append(
                    {
                        "set_id": "_root" if set_dir == self._output else set_dir.name,
                        "algorithm": algo_dir.name,
                        "node_ids": used,
                        "updated_at": result.stat().st_mtime,
                        "measured": self._measured(set_dir, algo_dir.name, query_id),
                    }
                )
        return sorted(found, key=lambda s: s["updated_at"], reverse=True)

    def _load_views(self, result: Path) -> tuple[bool, list[dict[str, Any]]]:
        key = (str(result), result.stat().st_mtime)
        if key not in self._views_cache:
            try:
                views = json.loads(result.read_text()).get("selected_views", [])
                ok = isinstance(views, list) and bool(views) and self._workload.views_consistent(views)
            except (OSError, json.JSONDecodeError, TypeError, KeyError):
                views, ok = [], False
            self._views_cache[key] = (ok, views if ok else [])
        return self._views_cache[key]

    @staticmethod
    def _query_time(bench: Path, query_id: str) -> float | None:
        try:
            rows = json.loads(bench.read_text()).get("queries", [])
        except (OSError, json.JSONDecodeError):
            return None
        times = [r["execution_time"] for r in rows if r.get("query_id") == query_id and r.get("success")]
        return sum(times) / len(times) if times else None

    def _measured(self, set_dir: Path, algorithm: str, query_id: str) -> dict[str, float | None]:
        """Recorded execution time of the query in this experiment vs the no-MV baseline."""
        with_mv = self._query_time(set_dir / algorithm / "benchmark" / "benchmark_results.json", query_id)
        base = self._query_time(set_dir / BASELINE_ALGORITHM / "benchmark" / "benchmark_results.json", query_id)
        return {"with_mvs_s": with_mv, "baseline_s": base}
