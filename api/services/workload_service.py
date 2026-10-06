"""In-memory index of the JOB workload: which plan nodes (MV candidates) each query contains.

The parser is pure/offline (about 0.2 s for the 113 JOB queries), so the index is built lazily
on first use instead of being persisted. Node ids (``leaf_8``, ``non_leaf_97``...) identify
structurally identical plan nodes across queries; they are only valid for this workload parse.
"""

import contextlib
import copy
import io
import json
import logging
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from config.settings import Settings
from src.core.models import MaterializedView
from src.core.parse_exporter import ParseExporter
from src.core.query_parser import QueryParser
from src.rewrite.query_rewriter import QueryRewriter
from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator

logger = logging.getLogger(__name__)


class NodeNotFoundError(KeyError):
    """Unknown node id."""


class WorkloadIndex:
    """Parses the JOB workload once and answers node/query questions."""

    def __init__(self, settings: Settings, project_root: Path):
        s = copy.deepcopy(settings)
        s.benchmark.type = "job"
        s.benchmark.query_selection_mode = "all_job"
        s.query.use_ceb = False
        for attr in ("queries_dir", "sql_dir", "workloads_dir"):
            p = Path(getattr(s.benchmark, attr))
            setattr(s.benchmark, attr, str(p if p.is_absolute() else project_root / p))
        self._settings = s
        self._lock = threading.Lock()
        self._qp: QueryParser | None = None
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._node_pos: dict[str, int] = {}
        self._query_pos: dict[str, int] = {}

    def _ensure(self) -> QueryParser:
        with self._lock:
            if self._qp is None:
                self._build()
            assert self._qp is not None
            return self._qp

    def _build(self) -> None:
        s = self._settings
        qp = QueryParser(s)
        with contextlib.redirect_stdout(io.StringIO()):  # the parser prints progress
            qp.query_parse(0, s.benchmark.queries_dir, s.optimization.insert_queries, sql_dir=s.benchmark.sql_dir)
            job_dir = Path(s.benchmark.queries_dir) / "job"
            files = [str(job_dir / f"{qid}.json") for qid in qp.query_files]
            with tempfile.TemporaryDirectory() as tmp:
                ParseExporter(qp.qm).annotate_query_files(files, tmp)
                for qid in qp.query_files:
                    data = json.loads((Path(tmp) / f"{qid}.json").read_text())
                    plan = data[0]["Plan"] if isinstance(data, list) else data.get("Plan", data)
                    self._snapshots[qid] = plan
        self._node_pos = {n: j for j, n in enumerate(qp.node_list)}
        self._query_pos = {q: i for i, q in enumerate(qp.query_files)}
        self._qp = qp
        logger.info(f"Workload index built: {len(qp.query_files)} queries, {len(qp.node_list)} nodes")

    def snapshot(self, query_id: str) -> dict[str, Any]:
        """Stored plan of a query, annotated with ``node_id`` on every node, plus share counts.

        Raises:
            NodeNotFoundError: If the query is not part of the workload.
        """
        qp = self._ensure()
        if query_id not in self._snapshots:
            raise NodeNotFoundError(query_id)
        plan = self._snapshots[query_id]
        counts: dict[str, int] = {}

        def visit(n: dict[str, Any]) -> None:
            nid = n.get("node_id")
            if nid in self._node_pos:
                counts[nid] = sum(qp.q_s_list[i][self._node_pos[nid]] for i in range(len(qp.query_files)))
            for c in n.get("Plans", []):
                visit(c)

        visit(plan)
        return {"plan": plan, "shared_counts": counts}

    def node(self, node_id: str) -> dict[str, Any]:
        """Details of one MV candidate node and the queries that contain it.

        Raises:
            NodeNotFoundError: If unknown.
        """
        qp = self._ensure()
        j = self._node_pos.get(node_id)
        if j is None:
            raise NodeNotFoundError(node_id)
        info = qp.qm.get_node_info(node_id) or {}
        occurrences: dict[int, int] = {}
        for q_idx, _pos in info.get("positions", []):
            occurrences[q_idx] = occurrences.get(q_idx, 0) + 1
        queries = [
            {
                "id": qp.query_files[i],
                "occurrences": occurrences.get(i, 1),
                "utility": qp.u_ij[i][j],
            }
            for i in range(len(qp.query_files))
            if qp.q_s_list[i][j]
        ]
        return {
            "node_id": node_id,
            "kind": info.get("type"),
            "operator": info.get("operator"),
            "table": info.get("table"),
            "alias": info.get("alias"),
            "filter": info.get("filter"),
            "children": info.get("children"),
            "cost": info.get("cost"),
            "size_bytes": qp.b_j[j],
            "width": info.get("width"),
            "maintenance_cost": qp.m_cost[j],
            "total_utility": sum(q["utility"] for q in queries),
            "queries": queries,
            "mv_sql": self._mv_sql(qp, node_id),
        }

    @staticmethod
    def _mv_sql(qp: QueryParser, node_id: str) -> str | None:
        try:
            return EnhancedMVGenerator(qp.qm).generate_mv_sql(node_id).strip() or None
        except Exception as e:  # generator is best-effort for display
            logger.warning(f"MV SQL generation failed for {node_id}: {e}")
            return None

    # ---- what-if building blocks -------------------------------------------------------

    def query_index(self, query_id: str) -> int:
        """Position of a query in the parsed workload (the index used by usage_positions)."""
        self._ensure()
        try:
            return self._query_pos[query_id]
        except KeyError:
            raise NodeNotFoundError(query_id) from None

    def query_ids(self) -> list[str]:
        """Query ids in workload order (position i is the query index used by usage_positions)."""
        return list(self._ensure().query_files)

    def node_positions(self, node_id: str) -> list[tuple[int, int]]:
        """(query index, position) pairs where the node occurs; [] if unknown."""
        qp = self._ensure()
        info = qp.qm.get_node_info(node_id) if node_id in self._node_pos else None
        return [(int(q), int(p)) for q, p in (info or {}).get("positions", [])]

    def node_size_bytes(self, node_id: str) -> int:
        """Estimated materialized size of a node."""
        qp = self._ensure()
        return int(qp.b_j[self._node_pos[node_id]])

    def views_consistent(self, views: list[dict[str, Any]]) -> bool:
        """True if stored selected views match this parse (same node ids and usage positions).

        Result files written by a different workload or parser version number nodes differently.
        """
        self._ensure()
        for v in views:
            if v.get("node_id") not in self._node_pos:
                return False
            known = set(self.node_positions(v["node_id"]))
            if not {(int(q), int(p)) for q, p in v.get("usage_positions", [])} <= known:
                return False
        return True

    def build_rewrite(self, query_id: str, node_ids: list[str]) -> tuple[str, list[dict[str, Any]]]:
        """Rewrite one query to use the given MV nodes.

        Returns:
            (rewritten SQL, MV definitions with ``node_id``, ``create_sql``, ``index_sql``).

        Raises:
            NodeNotFoundError: Unknown query or node.
        """
        qp = self._ensure()
        q_idx = self.query_index(query_id)
        chosen = set(node_ids)
        generator = EnhancedMVGenerator(qp.qm, selected_mvs=chosen)
        views: list[MaterializedView] = []
        definitions: list[dict[str, Any]] = []
        for node_id in node_ids:
            if node_id not in self._node_pos:
                raise NodeNotFoundError(node_id)
            create_sql, index_sql = generator.generate_mv_and_index_sql(node_id)
            positions = [[q, p] for q, p in self.node_positions(node_id) if q == q_idx]
            views.append(
                MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,
                    size=self.node_size_bytes(node_id),
                    maintenance_cost=0.0,
                    usage_positions=positions,
                    index_sql=index_sql,
                )
            )
            definitions.append({"node_id": node_id, "create_sql": create_sql, "index_sql": index_sql})
        rewritten = QueryRewriter(self._settings).rewrite_queries(views)[query_id]
        return rewritten.strip(), definitions

    def queries_with_node(self, node_id: str) -> list[str]:
        """Ids of the queries whose plan contains the node.

        Raises:
            NodeNotFoundError: If the node is unknown.
        """
        qp = self._ensure()
        j = self._node_pos.get(node_id)
        if j is None:
            raise NodeNotFoundError(node_id)
        return [qp.query_files[i] for i in range(len(qp.query_files)) if qp.q_s_list[i][j]]

    def original_sql(self, query_id: str) -> str:
        """Original SQL text of a workload query."""
        self.query_index(query_id)
        return (Path(self._settings.benchmark.sql_dir) / "job" / f"{query_id}.sql").read_text().strip()

    def mv_select_sql(self, node_id: str) -> str | None:
        """The SELECT that defines the node as a standalone MV (nothing else selected)."""
        qp = self._ensure()
        if node_id not in self._node_pos:
            raise NodeNotFoundError(node_id)
        create = EnhancedMVGenerator(qp.qm, selected_mvs={node_id}).generate_mv_sql(node_id)
        m = re.search(r"\bAS\s+(SELECT\b.*)$", create, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip().rstrip(";").strip() if m else None
