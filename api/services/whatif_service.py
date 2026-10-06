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
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg2

from api.services.plan_service import PlanError
from api.services.workload_service import NodeNotFoundError, WorkloadIndex
from config.settings import DatabaseConfig
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

LARGE_MV_BYTES = 256 * 1024 * 1024
MAX_MV_BYTES = 8 * 1024**3  # refused outright: a transient MV this big could fill the disk
BASELINE_ALGORITHM = "none"


class WhatIfBusyError(RuntimeError):
    """Another what-if is already running."""


class LargeMVError(RuntimeError):
    """The MVs would be large; the caller must confirm."""

    def __init__(self, size_bytes: int):
        super().__init__(f"Creating these MVs needs about {size_bytes / 1024**2:.0f} MB")
        self.size_bytes = size_bytes


class TooLargeError(ValueError):
    """The MVs are too large to build even transiently."""


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
        self._size_cache: dict[str, dict[str, Any]] = {}

    def estimate_mv(self, node_id: str) -> dict[str, Any]:
        """Planner estimate (rows x width) of the node's MV, from EXPLAIN of its defining SELECT.

        The model's b_j can be off by orders of magnitude (a parameterized index-scan leaf is
        modelled as a few bytes but materializes as the whole table), so size guards use this.
        Falls back to b_j when EXPLAIN is unavailable.
        """
        if node_id in self._size_cache:
            return self._size_cache[node_id]
        select = self._workload.mv_select_sql(node_id)
        est: dict[str, Any] = {"node_id": node_id, "rows": None, "width": None, "source": "model"}
        est["est_bytes"] = self._workload.node_size_bytes(node_id)
        if select:
            db = DatabaseConnection(dataclasses.replace(self._db, timeout=15))
            try:
                conn = db.get_connection()
                conn.set_session(readonly=True, autocommit=False)
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"EXPLAIN (FORMAT JSON) {select}")
                        plan = cur.fetchone()[0][0]["Plan"]
                finally:
                    conn.rollback()
                est.update(
                    rows=plan["Plan Rows"],
                    width=plan["Plan Width"],
                    est_bytes=int(plan["Plan Rows"] * plan["Plan Width"]),
                    source="planner",
                )
            except psycopg2.Error as e:
                logger.info(f"MV size EXPLAIN failed for {node_id}: {str(e).splitlines()[0]}")
            finally:
                db.close()
        self._size_cache[node_id] = est
        return est

    def _check_size(self, nodes: list[str], confirm_large: bool) -> int:
        size = sum(self.estimate_mv(n)["est_bytes"] for n in nodes)
        if size > MAX_MV_BYTES:
            raise TooLargeError(f"Estimated {size / 1024**3:.1f} GB exceeds the {MAX_MV_BYTES // 1024**3} GB limit")
        if size > LARGE_MV_BYTES and not confirm_large:
            raise LargeMVError(size)
        return size

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

        self._check_size(nodes, confirm_large)
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
            d["est_size_bytes"] = self.estimate_mv(d["node_id"])["est_bytes"]
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

    def _scratch(
        self,
        definitions: list[dict[str, Any]],
        work: Callable[[Any, list[dict[str, Any]]], Any],
        timeout_s: int,
    ) -> Any:
        """Create ``definitions`` in a throw-away schema, run ``work(cursor, mv_stats)``, roll back.

        ``mv_stats`` holds per-MV build time and actual size (measured before the rollback).
        """
        schema = f"whatif_{uuid.uuid4().hex[:8]}"  # generated here, never user input
        db = DatabaseConnection(dataclasses.replace(self._db, timeout=timeout_s))
        stats: list[dict[str, Any]] = []
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
                        cur.execute("SELECT pg_total_relation_size(%s::regclass)", (f"{schema}.{d['node_id']}",))
                        stats.append(
                            {
                                "node_id": d["node_id"],
                                "create_seconds": round(time.time() - t0, 2),
                                "actual_size_bytes": cur.fetchone()[0],
                            }
                        )
                    return work(cur, stats)
            finally:
                conn.rollback()  # always: nothing may persist
        except psycopg2.Error as e:
            logger.warning(f"What-if failed: {e}")
            raise PlanError(str(e).strip()) from e
        finally:
            db.close()

    def _run_scratch(
        self, definitions: list[dict[str, Any]], sql: str, analyze: bool, timeout_s: int
    ) -> dict[str, Any]:
        options = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"

        def work(cur: Any, stats: list[dict[str, Any]]) -> dict[str, Any]:
            cur.execute(f"EXPLAIN ({options}) {sql}")
            explained = cur.fetchone()[0][0]
            return {
                "plan": explained["Plan"],
                "planning_time_ms": explained.get("Planning Time"),
                "execution_time_ms": explained.get("Execution Time"),
                "mvs": stats,
            }

        return self._scratch(definitions, work, timeout_s)

    # ---- per-node what-if over all sharing queries ---------------------------------------

    def node_whatif(
        self,
        node_id: str,
        analyze: bool = False,
        confirm_large: bool = False,
        force: bool = False,
        timeout_s: int = 300,
        query_timeout_s: int = 30,
        max_queries: int = 60,
    ) -> dict[str, Any]:
        """Materialize one node and compare every query that contains it, before vs after.

        One scratch MV serves all queries. With ``analyze`` each query is also executed (each
        statement limited to ``query_timeout_s``; a timeout yields null times, not a failure).

        Raises:
            InvalidSelectionError: Unknown node.
            LargeMVError: Estimated size above the threshold without confirmation.
            WhatIfBusyError: Another what-if is running.
            PlanError: PostgreSQL error.
        """
        try:
            query_ids = self._workload.queries_with_node(node_id)
        except NodeNotFoundError as e:
            raise InvalidSelectionError(f"Unknown node {node_id}") from e
        query_ids = query_ids[:max_queries]
        key = hashlib.sha1(f"node|{node_id}|{analyze}".encode()).hexdigest()[:20]
        cache_file = self._cache / f"{key}.json"
        if not force and cache_file.exists():
            return {**json.loads(cache_file.read_text()), "cached": True}
        size = self._check_size([node_id], confirm_large)
        if not self._busy.acquire(blocking=False):
            raise WhatIfBusyError("Another what-if is running")
        try:
            rewrites: dict[str, str] = {}
            definitions: list[dict[str, Any]] = []
            for q in query_ids:
                rewrites[q], definitions = self._workload.build_rewrite(q, [node_id])
            originals = {q: self._workload.original_sql(q) for q in query_ids}
            rows = self._scratch(
                definitions,
                lambda cur, stats: self._compare_queries(cur, stats, originals, rewrites, analyze, query_timeout_s),
                timeout_s,
            )
        finally:
            self._busy.release()

        results = rows["queries"]
        total_before = sum(r["cost_before"] for r in results)
        total_after = sum(r["cost_after"] for r in results)
        out = {
            "node_id": node_id,
            "analyzed": analyze,
            "computed_at": time.time(),
            "mv": {**rows["mv"], "est_size_bytes": size},
            "queries": results,
            "total_cost_before": total_before,
            "total_cost_after": total_after,
            "truncated": len(self._workload.queries_with_node(node_id)) > len(query_ids),
        }
        self._cache.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out))
        return {**out, "cached": False}

    @staticmethod
    def _compare_queries(
        cur: Any,
        stats: list[dict[str, Any]],
        originals: dict[str, str],
        rewrites: dict[str, str],
        analyze: bool,
        query_timeout_s: int,
    ) -> dict[str, Any]:
        options = "ANALYZE, FORMAT JSON" if analyze else "FORMAT JSON"
        cur.execute(f"SET LOCAL statement_timeout = '{int(query_timeout_s)}s'")

        def explain(sql: str) -> dict[str, Any] | None:
            cur.execute("SAVEPOINT q")  # a timeout must not poison the whole transaction
            try:
                cur.execute(f"EXPLAIN ({options}) {sql}")
                result = cur.fetchone()[0][0]
                cur.execute("RELEASE SAVEPOINT q")
                return result
            except psycopg2.Error as e:
                logger.info(f"What-if explain skipped: {str(e).splitlines()[0]}")
                cur.execute("ROLLBACK TO SAVEPOINT q")
                return None

        rows = []
        for q, original in originals.items():
            before, after = explain(original), explain(rewrites[q])
            if before is None or after is None:
                continue
            rows.append(
                {
                    "query_id": q,
                    "cost_before": before["Plan"]["Total Cost"],
                    "cost_after": after["Plan"]["Total Cost"],
                    "time_before_ms": before.get("Execution Time"),
                    "time_after_ms": after.get("Execution Time"),
                    "uses_mv": any(
                        r == stats[0]["node_id"] for r in _relations(after["Plan"])
                    ),
                }
            )
        return {"mv": stats[0], "queries": rows}

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
