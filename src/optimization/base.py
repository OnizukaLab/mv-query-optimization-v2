"""Base class for ILP optimization algorithms.

This module provides the abstract base class that all ILP optimization
algorithms inherit from, defining common interfaces and shared functionality.
"""

import logging
from abc import ABC, abstractmethod

import gurobipy as gp

from config.settings import Settings

from ..core.models import MaterializedView, OptimizationResult
from ..core.query_manager import QueryManager

logger = logging.getLogger(__name__)


class BaseILPOptimizer(ABC):
    """Abstract base class for ILP-based materialized view selection.

    This class provides common functionality for all ILP optimization algorithms,
    including Gurobi model creation, constraint handling, and result processing.

    Attributes:
        qm: QueryManager instance containing query node information
        settings: Configuration settings
        s_num: Total number of subquery nodes
        m_cost: Maintenance cost for each node
        node_list: List of all node IDs
        B_max: Maximum storage budget
        b_j: Storage size for each node
        u_ij: Utility matrix [query_id][node_id]
        X: Inclusive dependency matrix
        q_s_list: Binary matrix of query-to-subquery relationships
        index_build_costs: Index build cost for each node (0 for non-Index Scan nodes)
        model: Gurobi optimization model
    """

    def __init__(
        self,
        qm: QueryManager,
        s_num: int,
        m_cost: list[float],
        node_list: list[str],
        B_max: float,
        b_j: list[int],
        u_ij: list[list[float]],
        X: list[list[int]],
        q_s_list: list[list[int]],
        query_files: list[str] | None = None,
        settings: Settings | None = None,
        index_build_costs: list[float] | None = None,
        gurobi_output: int = 0,
        gurobi_time_limit_sec: float | None = None,
    ) -> None:
        """Initialize the optimizer.

        Args:
            qm: QueryManager instance
            s_num: Total number of subquery nodes
            m_cost: Maintenance cost for each node
            node_list: List of all node IDs
            B_max: Maximum storage budget
            b_j: Storage size for each node
            u_ij: Utility matrix
            X: Dependency matrix
            q_s_list: Query-subquery relationship matrix
            query_files: List of query IDs corresponding to u_ij rows
            settings: Configuration settings (optional)
            index_build_costs: Index build cost for each node (optional)
                              Non-zero for Index Scan nodes that require index creation
            gurobi_output: Gurobi log level (0=off, 1=on)
            gurobi_time_limit_sec: Optional per-solve time limit in seconds
        """
        self.qm = qm
        self.settings = settings or Settings()
        self.s_num = s_num
        self.m_cost = m_cost
        self.node_list = node_list
        self.B_max = B_max
        self.b_j = b_j
        self.u_ij = u_ij
        self.X = X
        self.q_s_list = q_s_list
        self.query_files = query_files or []
        self.model: gp.Model | None = None
        # Sparse candidate utility index (for candidate-based solves)
        self._cand_pos_js_by_i: dict[int, list[int]] = {}
        self._cand_pos_is_by_j: dict[int, list[int]] = {}
        # インデックス作成コスト（未指定の場合は全て0）
        self.index_build_costs = index_build_costs or [0.0] * s_num
        self.gurobi_output = gurobi_output
        self.gurobi_time_limit_sec = gurobi_time_limit_sec

    def build_ilp_model(self, cand_i: list[int], cand_j: list[int]) -> tuple[dict, dict]:
        """Build the ILP model with decision variables and constraints.

        Creates a Gurobi model with:
        - y[i,j]: Binary variable indicating if query i uses MV j
        - z[j]: Binary variable indicating if MV j is materialized

        Args:
            cand_i: List of query indices that are MV candidates
            cand_j: List of subquery indices that are MV candidates

        Returns:
            Tuple of (y_variables, z_variables)
        """
        self.model = gp.Model(f"{self.__class__.__name__}")
        self.model.Params.OutputFlag = self.gurobi_output
        if self.gurobi_time_limit_sec is not None:
            self.model.Params.TimeLimit = self.gurobi_time_limit_sec

        # Decision variables
        y = {}
        for i in range(len(self.u_ij)):
            for j in range(len(self.b_j)):
                y[i, j] = self.model.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}")

        z = {}
        for j in range(len(self.b_j)):
            z[j] = self.model.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}")

        self.model.update()

        return y, z

    def build_ilp_model_with_candidates(
        self, cand_i: list[int], cand_j: list[int]
    ) -> tuple[dict, dict]:
        """Build ILP model with only candidate variables (original code behavior).

        This creates a smaller ILP problem by only creating variables for
        candidate queries and subqueries, matching the original implementation.

        Creates a Gurobi model with:
        - y[i,j]: Binary variable for candidate query i and candidate MV j
        - z[j]: Binary variable for candidate MV j

        Args:
            cand_i: List of query indices that are MV candidates
            cand_j: List of subquery indices that are MV candidates

        Returns:
            Tuple of (y_variables, z_variables) indexed by candidate positions
        """
        self.model = gp.Model(f"{self.__class__.__name__}")
        self.model.Params.OutputFlag = self.gurobi_output
        if self.gurobi_time_limit_sec is not None:
            self.model.Params.TimeLimit = self.gurobi_time_limit_sec

        # Build sparse utility index on candidate positions:
        # create y only for pairs where u_ij > 0.
        self._cand_pos_js_by_i = {i_idx: [] for i_idx in range(len(cand_i))}
        self._cand_pos_is_by_j = {j_idx: [] for j_idx in range(len(cand_j))}

        for i_idx in range(len(cand_i)):
            i_orig = cand_i[i_idx]
            for j_idx in range(len(cand_j)):
                j_orig = cand_j[j_idx]
                if self.u_ij[i_orig][j_orig] > 0:
                    self._cand_pos_js_by_i[i_idx].append(j_idx)
                    self._cand_pos_is_by_j[j_idx].append(i_idx)

        # Decision variables - only for sparse candidate pairs
        y = {}
        for i_idx, js in self._cand_pos_js_by_i.items():
            for j_idx in js:
                y[i_idx, j_idx] = self.model.addVar(vtype=gp.GRB.BINARY, name=f"y_{i_idx}_{j_idx}")

        z = {}
        for j in range(len(cand_j)):
            z[j] = self.model.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}")

        self.model.update()

        return y, z

    def add_common_constraints(
        self, y: dict, z: dict, cand_i: list[int], cand_j: list[int]
    ) -> None:
        """Add common constraints to the ILP model.

        Adds:
        1. Overlapping subexpression constraints
        2. Materialization dependency constraints (y[i,j] <= z[j])
        3. Storage budget constraint

        Args:
            y: Query-MV usage variables
            z: MV materialization variables
            cand_i: Candidate query indices
            cand_j: Candidate subquery indices
        """
        # Overlapping subexpression constraints
        for i in range(len(self.u_ij)):
            for j in range(len(self.b_j)):
                # If y[i,j]=1, then none of j's dependencies can be used
                self.model.addConstr(
                    y[i, j]
                    + gp.quicksum(y[i, u] * self.X[j][u] for u in range(len(self.b_j)))
                    / len(self.b_j)
                    <= 1
                )

                # y[i,j] can only be 1 if z[j]=1
                self.model.addConstr(y[i, j] <= z[j])

        # Storage budget constraint
        self.model.addConstr(
            gp.quicksum(self.b_j[j] * z[j] for j in range(len(self.b_j))) <= self.B_max
        )

    def add_constraints_with_candidates(
        self, y: dict, z: dict, cand_i: list[int], cand_j: list[int]
    ) -> None:
        """Add constraints using candidate indices (original code behavior).

        This matches the original implementation where constraints are only
        added for candidate queries and subqueries.

        Args:
            y: Query-MV usage variables (indexed by candidate positions)
            z: MV materialization variables (indexed by candidate positions)
            cand_i: Candidate query indices (original indices)
            cand_j: Candidate subquery indices (original indices)
        """
        # Build M: beneficial subqueries for each candidate query (sparse, by position)
        M = [list(self._cand_pos_js_by_i.get(i_idx, [])) for i_idx in range(len(cand_i))]

        # Overlapping subexpression constraints
        # For each query i and each beneficial subquery j in M[i],
        # prevent using j together with any of its descendants
        t = 0
        for i in range(len(cand_i)):
            for j in M[i]:
                # Get original node index for j
                orig_j = cand_j[j]
                
                # Find all descendants of orig_j among candidates
                # and create subsumption constraint
                descendant_indices = []
                for u in M[i]:  # Only check subqueries within the same query i
                    if u != j:  # Skip self
                        orig_u = cand_j[u]
                        if self.X[orig_j][orig_u] == 1:
                            descendant_indices.append(u)
                        
                        if self.X[orig_u][orig_j] == 1:
                            descendant_indices.append(u)
                
                # Only add constraint if there are descendants
                if descendant_indices:
                    # Constraint: if y[i,j]=1, then sum of y[i,u] for descendants must be 0
                    # Formulated as: y[i,j] + sum(y[i,u] for u in descendants) / |cand_j| <= 1
                    # The division by |cand_j| is a normalization factor from the original code
                    self.model.addConstr(
                        y[i, j]
                        + gp.quicksum(y[i, u] for u in descendant_indices)
                        / len(cand_j)
                        <= 1,
                        name=f"subsumption_{t}",
                    )
                
                # y[i,j] can only be 1 if z[j]=1
                self.model.addConstr(y[i, j] <= z[j], name=f"materialize_{t}")
                t += 1

        # Global subsumption constraints on z variables
        # Prevent materializing both a node and its descendants
        # This ensures subsumption is enforced across all queries
        
        """
        constraint_count = 0
        for j in range(len(cand_j)):
            orig_j = cand_j[j]
            
            # Find descendants of orig_j among candidates
            for u in range(len(cand_j)):
                if u != j:
                    orig_u = cand_j[u]
                    if self.X[orig_j][orig_u] == 1:
                        # Add pairwise constraint: cannot materialize both parent and child
                        self.model.addConstr(
                            z[j] + z[u] <= 1,
                            name=f"global_subsumption_{j}_{u}",
                        )
                        constraint_count += 1
        
        """
        
        # Storage budget constraint - use original indices
        self.model.addConstr(
            gp.quicksum(self.b_j[cand_j[j]] * z[j] for j in range(len(cand_j)))
            <= self.B_max,
            name="storage_budget",
        )

    def set_objective(self, y: dict, z: dict, cand_i: list[int], cand_j: list[int]) -> None:
        """Set the optimization objective function.

        Maximizes: total utility - maintenance cost - index build cost
        
        目的関数:
          maximize Σ(u_ij × y_ij) - Σ(z_j × m_cost_j) - Σ(z_j × index_build_cost_j)

        Args:
            y: Query-MV usage variables
            z: MV materialization variables
            cand_i: Candidate query indices (list of query indices)
            cand_j: Candidate subquery indices (list of subquery indices)
        """
        # Use full index ranges since y and z are defined for all i,j
        # The ILP solver will automatically handle variables with zero coefficients
        utility_terms = gp.quicksum(
            self.u_ij[i][j] * y[i, j] for i in range(len(self.u_ij)) for j in range(len(self.b_j))
        )
        
        maintenance_terms = gp.quicksum(z[j] * self.m_cost[j] for j in range(len(self.b_j)))
        
        # インデックス作成コスト
        index_build_terms = gp.quicksum(
            z[j] * self.index_build_costs[j] for j in range(len(self.b_j))
        )
        
        self.model.setObjective(
            utility_terms - maintenance_terms - index_build_terms,
            gp.GRB.MAXIMIZE,
        )

    def set_objective_with_candidates(
        self, y: dict, z: dict, cand_i: list[int], cand_j: list[int]
    ) -> None:
        """Set objective function using candidate indices (original code behavior).

        Maximizes: total utility - maintenance cost - index build cost
        Only considers candidate queries and subqueries.
        
        目的関数:
          maximize Σ(u_ij × y_ij) - Σ(z_j × m_cost_j) - Σ(z_j × index_build_cost_j)
        
        インデックス作成コストは、MVがマテリアライズされる場合(z_j=1)に
        そのMVがIndex Scanを使用する場合に発生する初期構築コスト。

        Args:
            y: Query-MV usage variables (indexed by candidate positions)
            z: MV materialization variables (indexed by candidate positions)
            cand_i: Candidate query indices (original indices)
            cand_j: Candidate subquery indices (original indices)
        """
        # Build utility component using candidate indices
        utility_terms = gp.quicksum(
            self.u_ij[cand_i[i_idx]][cand_j[j_idx]] * y[i_idx, j_idx]
            for (i_idx, j_idx) in y.keys()
        )

        # Build maintenance cost component using candidate indices
        maintenance_terms = gp.quicksum(
            z[j] * self.m_cost[cand_j[j]] for j in range(len(cand_j))
        )
        
        # Build index build cost component using candidate indices
        # インデックス作成コストは、MVをマテリアライズする際に一度だけ発生する初期コスト
        index_build_terms = gp.quicksum(
            z[j] * self.index_build_costs[cand_j[j]] for j in range(len(cand_j))
        )

        self.model.setObjective(
            utility_terms - maintenance_terms - index_build_terms, 
            gp.GRB.MAXIMIZE
        )

    def solve_ilp(self, y: dict, z: dict) -> tuple[list[list[int]], list[int], float]:
        """Solve the ILP model and extract results.

        Args:
            y: Query-MV usage variables
            z: MV materialization variables

        Returns:
            Tuple of (y_ij solution, z_j solution, objective value)
        """
        if self.model is None:
            raise RuntimeError("Model not built. Call build_ilp_model first.")

        self.model.optimize()

        # Extract solution
        ret_y = [[0] * len(self.b_j) for _ in range(len(self.u_ij))]
        ret_z = [0] * len(self.b_j)

        for j in range(len(self.b_j)):
            ret_z[j] = int(z[j].X)
            for i in range(len(self.u_ij)):
                ret_y[i][j] = int(y[i, j].X)

        obj_val = self.model.objVal

        return ret_y, ret_z, obj_val

    def solve_ilp_with_candidates(
        self, y: dict, z: dict, cand_i: list[int], cand_j: list[int]
    ) -> tuple[list[list[int]], list[int], float]:
        """Solve ILP and map results back to original indices (original code behavior).

        This solves the smaller ILP problem with only candidate variables,
        then maps the results back to the full index space.

        Args:
            y: Query-MV usage variables (indexed by candidate positions)
            z: MV materialization variables (indexed by candidate positions)
            cand_i: Candidate query indices (original indices)
            cand_j: Candidate subquery indices (original indices)

        Returns:
            Tuple of (y_ij solution, z_j solution, objective value)
            Solutions are in the original full index space.
        """
        if self.model is None:
            raise RuntimeError("Model not built. Call build_ilp_model_with_candidates first.")

        self.model.optimize()

        # Debug: Check if leaf_1 and non_leaf_2 are both selected
        leaf_1_idx = None
        non_leaf_2_idx = None
        for j in range(len(cand_j)):
            orig_j = cand_j[j]
            node_name = self.node_list[orig_j] if orig_j < len(self.node_list) else f"node_{orig_j}"
            if node_name == "leaf_1":
                leaf_1_idx = j
            elif node_name == "non_leaf_2":
                non_leaf_2_idx = j
        
        if leaf_1_idx is not None and non_leaf_2_idx is not None:
            z_leaf_1 = int(z[leaf_1_idx].X)
            z_non_leaf_2 = int(z[non_leaf_2_idx].X)
            if z_leaf_1 + z_non_leaf_2 > 1:
                print(f"WARNING: Constraint violated! Both leaf_1 and non_leaf_2 are selected")

        # Initialize solution arrays in full index space
        ret_y = [[0] * len(self.b_j) for _ in range(len(self.u_ij))]
        ret_z = [0] * len(self.b_j)

        # Extract solution from candidate variables and map to original indices
        for j_idx in range(len(cand_j)):
            j_orig = cand_j[j_idx]
            ret_z[j_orig] = int(z[j_idx].X)
            
            for i_idx in range(len(cand_i)):
                i_orig = cand_i[i_idx]
                ret_y[i_orig][j_orig] = int(y[i_idx, j_idx].X) if (i_idx, j_idx) in y else 0

        obj_val = self.model.objVal

        return ret_y, ret_z, obj_val

    def make_nodename_from_id(self, x_list: list[int]) -> list[str]:
        """Convert node indices to node names.

        Args:
            x_list: List of node indices

        Returns:
            List of node names
        """
        return [self.node_list[i] for i in x_list]

    def calculate_storage_used(self, z_j: list[int]) -> float:
        """Calculate total storage used by selected MVs.

        Args:
            z_j: Binary list indicating which MVs are materialized

        Returns:
            Total storage in bytes
        """
        return sum(self.b_j[j] * z_j[j] for j in range(len(z_j)))

    def get_materialized_views(
        self,
        z_j: list[int],
        generate_sql: bool = False,
        y_ij: list[list[int]] | None = None,
    ) -> list[MaterializedView]:
        """Create MaterializedView objects from solution.

        Args:
            z_j: Binary list indicating which MVs are materialized
            generate_sql: If True, generate CREATE SQL immediately (requires database).
                         If False (default), SQL will be generated later in sql_generation phase.
            y_ij: Query-MV usage solution. When given, each MV's ``usage_positions`` only holds
                the positions in queries where ``y_ij[query][node] == 1``, i.e. where the
                solution actually uses the MV. Without it every occurrence of the node in the
                workload is listed, which lets the rewriter apply overlapping MVs (a node and
                one of its descendants) to the same query, even though the ILP forbids that.

        Returns:
            List of MaterializedView objects
        """
        mvs = []
        
        # If SQL generation is requested, create MV generator
        mv_generator = None
        if generate_sql:
            from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
            
            # Build set of selected MV node IDs
            selected_node_ids = set()
            for j in range(len(z_j)):
                if z_j[j] == 1:
                    selected_node_ids.add(self.node_list[j])
            
            # Create MV generator with selected MVs info
            mv_generator = EnhancedMVGenerator(self.qm, selected_mvs=selected_node_ids)
        
        for j in range(len(z_j)):
            if z_j[j] == 1:
                node_id = self.node_list[j]
                
                # Generate SQL only if requested
                create_sql = ""
                if generate_sql and mv_generator:
                    try:
                        create_sql = mv_generator.generate_mv_sql(node_id)
                    except Exception as e:
                        logger = __import__('logging').getLogger(__name__)
                        logger.warning(f"Failed to generate SQL for {node_id}: {e}")
                        create_sql = f"-- Failed to generate SQL for {node_id}: {e}"
                
                positions = self.qm.subquery_positions.get(node_id, [])
                if y_ij is not None:
                    positions = [
                        pos for pos in positions if pos[0] < len(y_ij) and y_ij[pos[0]][j] == 1
                    ]
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,
                    size=self.b_j[j],
                    maintenance_cost=self.m_cost[j],
                    usage_positions=positions,
                )
                mvs.append(mv)
        if y_ij is not None:
            self._warn_nested_usage(mvs)
        return mvs

    def _warn_nested_usage(self, mvs: list[MaterializedView]) -> None:
        """Log queries that use an MV together with a node it contains (should never happen)."""
        index = {n: j for j, n in enumerate(self.node_list)}
        by_query: dict[int, set[int]] = {}
        for mv in mvs:
            for q, _ in mv.usage_positions:
                by_query.setdefault(q, set()).add(index[mv.node_id])
        for q, js in by_query.items():
            nested = [(a, b) for a in js for b in js if a != b and self.X[a][b] == 1]
            if nested:
                a, b = nested[0]
                logger.warning(
                    f"Query {q} uses nested MVs {self.node_list[a]} and {self.node_list[b]} "
                    f"({len(nested)} pair(s)); the rewrite may be wrong"
                )

    @abstractmethod
    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates (algorithm-specific).

        Different algorithms may have different strategies for
        selecting initial candidate sets.

        Returns:
            Tuple of (cand_i, cand_j) where:
                cand_i: Candidate query indices
                cand_j: Candidate subquery indices
        """
        pass

    @abstractmethod
    def optimize(self, **kwargs) -> OptimizationResult:
        """Run the optimization algorithm (algorithm-specific).

        This is the main entry point for each algorithm.
        Subclasses must implement their specific optimization logic.

        Returns:
            OptimizationResult with selected MVs and metrics
        """
        pass

    def create_result(
        self,
        y_ij: list[list[int]],
        z_j: list[int],
        obj_val: float,
        execution_time: float,
        generate_sql: bool = False,
        **metadata,
    ) -> OptimizationResult:
        """Create an OptimizationResult from algorithm output.

        Args:
            y_ij: Query-MV usage solution
            z_j: MV materialization solution
            obj_val: Objective function value
            execution_time: Time taken in seconds
            generate_sql: If True, generate CREATE SQL immediately (requires database).
                         If False (default), SQL will be generated later in sql_generation phase.
            **metadata: Additional algorithm-specific metadata

        Returns:
            OptimizationResult object
        """
        selected_mvs = self.get_materialized_views(z_j, generate_sql=generate_sql, y_ij=y_ij)
        total_storage = self.calculate_storage_used(z_j)

        return OptimizationResult(
            algorithm=self.__class__.__name__,
            selected_views=selected_mvs,
            total_utility=obj_val,
            total_storage=total_storage,
            execution_time=execution_time,
            metadata={"y_ij": y_ij, "z_j": z_j, "node_list": self.node_list, "query_files": self.query_files, **metadata},
        )
