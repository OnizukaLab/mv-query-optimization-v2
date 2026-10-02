> **Note**: `research/` は非公開（ローカルのみ・Git管理外）。存在しない前提で作業すること。

# Materialized View Query Optimization - Development Manifest

> **Python**: 3.11+ | **PostgreSQL**: 18 (Docker) | **ILP Solver**: Gurobi 12.0.1  
> **Last Updated**: November 3, 2025

---

## 1. Project Overview

This project implements **ILP-based materialized view (MV) selection** for database query optimization, balancing query performance, storage constraints, and maintenance costs.

**Key Features**:
- 5 ILP algorithms (Normal, BigSubs, Utility, Utility-Capacity, Frequency)
- Automatic query rewriting to use selected MVs
- Benchmark support: RedBench, JOB, CEB
- Docker PostgreSQL with IMDb dataset (8GB+)

---

## 2. Codebase Structure

**Architecture**: Host (Python code + Gurobi) ↔ Docker (PostgreSQL + IMDb)
- Rationale: Fast iteration without container rebuilds

**Directory Structure**:

```
mv-query-optimization/
├── src/                          # Core source code (modularized)
│   ├── core/                     # Core domain logic
│   │   ├── models.py             # Data models (QueryNode, MaterializedView, etc.)
│   │   ├── query_manager.py     # Query plan structure management
│   │   └── query_parser.py      # JSON query plan parsing
│   │
│   ├── optimization/             # ILP optimization algorithms
│   │   ├── base.py               # BaseILPOptimizer (common logic)
│   │   ├── normal.py             # Normal ILP baseline
│   │   ├── bigsubs.py            # BigSubs algorithm
│   │   ├── utility_capacity.py  # Utility/Capacity ratio strategy
│   │   ├── utility.py            # Utility maximization strategy
│   │   ├── frequency.py          # Frequency-based strategy
│   │   └── factory.py            # OptimizerFactory for algorithm selection
│   │
│   ├── rewrite/                  # Query rewriting
│   │   ├── query_rewriter.py    # Main rewriting logic
│   │   ├── mv_generator.py      # CREATE MATERIALIZED VIEW SQL generation
│   │   └── sql_parser.py        # SQL parsing utilities
│   │
│   ├── benchmark/                # Benchmark execution
│   │   ├── executor.py           # Query execution
│   │   ├── workload.py           # Workload management
│   │   └── metrics.py            # Performance metrics collection
│   │
│   ├── database/                 # Database operations
│   │   ├── connection.py         # Connection pooling & management
│   │   ├── mv_manager.py         # MV creation/deletion
│   │   └── schema.py             # Schema introspection
│   │
│   └── utils/                    # Utilities
│       ├── logging_utils.py      # Centralized logging
│       ├── validators.py         # Input validation
│       └── file_utils.py         # File I/O helpers
│
├── scripts/                      # Executable scripts
│   ├── run_experiment.py         # Main experiment runner (CLI)
│   ├── rewrite_queries.py        # Query rewriting tool
│   ├── compare_algorithms.py     # Result comparison
│   └── setup_database.py         # Database initialization
│
├── tests/                        # Test suite (82% coverage)
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   ├── performance/              # Performance tests
│   └── fixtures/                 # Test data
│
├── config/                       # Configuration management
│   ├── settings.py               # Settings class (YAML + env vars)
│   ├── default.yaml              # Default configuration
│   └── experiments/              # Experiment-specific configs
│
├── data/                         # Database setup files
│   ├── schema.sql                # IMDb schema definition
│   ├── setup.sql                 # Database initialization
│   ├── insert_queries.sql        # Update workload
│   └── triggers.sql              # Maintenance cost tracking
│
├── dataset/                      # Benchmark datasets
│   ├── RED_JSON/                 # RedBench query plans (JSON)
│   ├── RED_SQL/                  # RedBench SQL queries
│   └── redbench/                 # RedBench framework
│
├── Output/                       # Experiment results (gitignored)
│   ├── experiments/              # Per-algorithm results
│   ├── logs/                     # Execution logs
│   └── artifacts/                # Intermediate files (qp_class.pkl, etc.)
│
├── docs/                         # Documentation
├── Dockerfile                    # PostgreSQL + IMDb setup
├── pyproject.toml                # Python project configuration
└── pytest.ini                    # Pytest configuration
```

**Key Modules**:
- `src/core/`: Query parsing, data models (`QueryNode`, `MaterializedView`)
- `src/optimization/`: 5 ILP algorithms (inherit from `BaseILPOptimizer`)
- `src/rewrite/`: Query rewriting, MV SQL generation
- `src/database/`: Connection pooling, MV management
- `scripts/`: Experiment runner, result comparison

---

## 3. Coding Style and Naming Conventions

**Tools**: Black (line-length=100), Ruff (linting), Mypy (type checking), Pytest (testing)

**Naming**:
- Modules: `snake_case` (e.g., `query_parser.py`)
- Classes: `PascalCase` (e.g., `QueryManager`)
- Functions/Methods: `snake_case` (e.g., `parse_query_plan()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`)
- Private: `_leading_underscore` (e.g., `_build_constraints()`)
- Math notation: `u_ij`, `z_j`, `b_j` allowed with comments

**Type Hints**: Mandatory for all public functions
```python
def parse_query_plan(json_path: str, query_id: int) -> QueryManager:
    """Parse query plan from JSON."""
    ...
```

**Docstrings**: Google-style, mandatory for public APIs
```python
def optimize(self, max_iter: int = 100) -> OptimizationResult:
    """Run ILP optimization.
    
    Args:
        max_iter: Maximum iterations
        
    Returns:
        OptimizationResult with selected MVs
        
    Raises:
        ILPSolverError: If Gurobi fails
    """
```

**Logging**: Use `logging` module, never `print()`
```python
logger = logging.getLogger(__name__)
logger.info(f"Starting optimization: {algo}")
```

**Error Handling**: Specific exceptions, no bare `except:`
```python
try:
    result = optimizer.solve()
except ILPSolverError as e:
    logger.error(f"ILP failed: {e}")
    raise
```

---

## 4. Testing and Git Workflow

**Test Coverage**: 82% (target: >80%)

```bash
pytest                    # Run all tests
pytest -m unit            # Unit tests only
pytest -m integration     # Integration tests (requires Docker)
pytest --cov=src          # Coverage report
```

**Branch Naming**:
- `feature/<description>` (e.g., `feature/add-greedy-init`)
- `fix/<issue>-<description>` (e.g., `fix/42-fix-leak`)
- `refactor/<component>` (e.g., `refactor/query-parser`)
- `docs/<topic>` (e.g., `docs/api-docs`)

**Commit Messages** (Conventional Commits):
```
feat(optimization): add greedy initialization
fix(database): handle connection timeout
refactor(core): extract query node models
docs(readme): update Python 3.11 requirements
```

**PR Checklist**:
- [ ] Tests pass and coverage maintained
- [ ] Code formatted (Black), linted (Ruff)
- [ ] Type hints and docstrings added
- [ ] No `print()` or bare `except:`
- [ ] Documentation updated
```

---

## 5. What AI Agents MUST NOT Do

**Code Quality**:
- ❌ `print()` for logging → ✅ Use `logging`
- ❌ Bare `except:` → ✅ Catch specific exceptions
- ❌ Hardcoded configs → ✅ Use `config/settings.py`
- ❌ Global variables → ✅ Pass via constructor
- ❌ Mutable defaults `def f(x=[])` → ✅ Use `None`

**Architecture**:
- ❌ Circular dependencies → ✅ Acyclic graph
- ❌ Direct DB access from optimization → ✅ Use `src/database/`
- ❌ Mix parsing + ILP logic → ✅ Separate modules
- ❌ Bypass config system → ✅ Use `get_settings()`

**Testing**:
- ❌ Skip tests for new features → ✅ 80%+ coverage
- ❌ Commit failing tests → ✅ Run `pytest` first
- ❌ Tests depend on Docker → ✅ Mark `@pytest.mark.integration`

**Git**:
- ❌ Commit to `main` → ✅ Use feature branches
- ❌ Commit `Output/`, `__pycache__/` → ✅ Check `.gitignore`
- ❌ Vague commits "fix bug" → ✅ Conventional Commits

## 6. Dependencies and Special Considerations

**Critical Dependencies**:
- Python 3.11+ (type hints require 3.10+ syntax)
- PostgreSQL 18 (Docker)
- Gurobi 12.0.1 (requires `gurobi.lic` in project root)
- psycopg2-binary, sqlparse, pandas, networkx

**Dev Tools**: Black, Ruff, Mypy, Pytest (82% coverage target)

**Gurobi License**:
- Academic license: Free from gurobi.com
- Place `gurobi.lic` in project root or set `GRB_LICENSE_FILE` env var

**Docker Design**: PostgreSQL only in container for fast iteration

**Benchmarks**:
- JOB: 113 queries (default)
- CEB: Extended JOB
- RedBench: Amazon Redshift simulation
- Configure: `config/default.yaml` → `query.use_ceb`

**Known Limitations**:
- Sequential MV creation (no parallelization)
- Static workload (no online adaptation)
- PostgreSQL-specific SQL dialect

---

## 7. Quick Reference

**Run Experiment**:
```bash
source .venv/bin/activate
docker start mv_postgres
python scripts/run_experiment.py --algorithms frequency
```

**Phase Control**:
```bash
# Run specific phases
--phases query_parsing optimization

# Start from specific phase
--start-from query_rewriting

# End at specific phase
--end-at mv_creation
```

**Common Commands**:
```bash
pytest                    # Run tests
black src/ tests/         # Format
ruff check src/           # Lint
docker logs mv_postgres   # DB logs
```

**Configuration Files**:
- `config/default.yaml` - Settings
- `pyproject.toml` - Tool configs
- `pytest.ini` - Test config

---

## 8. Research Management System (research/)

This repository uses a structured research logging system under `research/`.
When creating/updating files in this area, follow `.github/instructions/RESEARCH.instructions.md`.

**Core Files**:
- `research/RESEARCH_LOG.md`: Weekly-level narrative only (no task-level details)
- `research/INSIGHTS.md`: Cross-week durable insights
- `research/TASKS.md`: Lean active queue (`doing`, `blocked`, `parked`)
- `research/INDEX.md`: Cross-topic map (maintain once enough weeks accumulate)
- `research/threads/`: Lightweight topic route maps for frontier tracking

**Weekly Workflow**:
1. Start week: create `research/weekly/YYYY-WNN/` and weekly `RESEARCH_LOG.md`
2. During week: create task logs at `YYYY-MM-DD/HHMM_task-name.html`
3. After each task log: append one-line link entry in weekly `RESEARCH_LOG.md`
4. Close week: add `README.html`, rename week folder to `YYYY-WNN_theme-name`, and summarize in root `RESEARCH_LOG.md`

**Naming Rules**:
- Week folder (start): `YYYY-WNN`
- Week folder (closed): `YYYY-WNN_theme-name`
- Date folder: `YYYY-MM-DD`
- Task log: `HHMM_task-name.html`

**Operational Rules**:
- Keep weekly logs as one-line index entries for fast navigation.
- Put details in task HTML logs (`Goal`, `Results & Observations`, `Next Steps`).
- Use task statuses: `doing`, `done`, `blocked`, `parked`.
- Add `<meta name="relations">` when a task implements/extends/validates/refutes another log.
- Update `threads/` only when topic frontier/state actually changes.

**Related Instructions**:
- `research/**` baseline: `.github/instructions/RESEARCH.instructions.md`
- HTML task logs and weekly README style: `.github/instructions/RESEARCH-HTML.instructions.md`
- Root/threads markdown log conventions: `.github/instructions/RESEARCH-LOGFILES.instructions.md`

---

**Version**: 2.1 | **Updated**: Jun 5, 2026
