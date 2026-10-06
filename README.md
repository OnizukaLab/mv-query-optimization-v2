# Materialized View Query Optimization

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 18](https://img.shields.io/badge/postgresql-18-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**English** | **[日本語](README.ja.md)**

A system that speeds up query execution by selecting materialized views (MVs) with integer linear programming (ILP).

## Overview

- **Query analysis**: parses PostgreSQL `EXPLAIN (FORMAT JSON)` query plans
- **MV selection**: five ILP-based algorithms (see table below)
- **Query rewriting**: automatically rewrites SQL to use the selected MVs
- **Maintenance cost estimation**: measures and estimates the cost of incremental view maintenance ([pg_ivm](https://github.com/sraoss/pg_ivm)) and `REFRESH` (`src/maintenance/`)
- **Benchmarks**: JOB / CEB / RedBench

| Algorithm (`--algorithms`) | Description |
|---|---|
| `none` | No MVs (baseline) |
| `normal` | Basic ILP formulation |
| `bigsubs` | BigSubs (probabilistic flipping) |
| `utility` | Utility maximization |
| `utility_capacity` | Utility / capacity ratio maximization |
| `frequency` | Frequency-based selection |

## Setup

Architecture: **host** (Python + Gurobi) ↔ **Docker** (PostgreSQL + IMDb). Code changes never require rebuilding the container.

### Prerequisites

- Python 3.11+
- Docker Desktop
- Gurobi Optimizer 12.0.1 (free [academic license](https://www.gurobi.com/academia/academic-program-and-licenses/) available)

### 1. PostgreSQL (Docker)

```bash
# Download IMDb data and build the image (15-20 min on first build)
docker build -t mv_postgres:1.0 .

# Start the container (5-10 min to load data on first start)
docker run -d --name mv_postgres -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data mv_postgres:1.0

# Verify
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT count(*) FROM title;"
```

Default connection: `localhost:5432` / database `imdbload` / user `postgres` / password `pass`
(configurable under `database:` in `config/default.yaml`).

The IVM experiments (`src/maintenance/`, `scripts/measure_*`) require the pg_ivm extension.
See `data/setup.sql` and run `CREATE EXTENSION pg_ivm;`.

### 2. Python environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # for development: pip install -r requirements-dev.txt
```

### 3. Gurobi license

Place your `gurobi.lic` in the project root, or point to it with the `GRB_LICENSE_FILE` environment variable (`gurobi.lic` is git-ignored).

### 4. Datasets

`dataset/` is not tracked in Git because of its size. Prepare it yourself:

- `dataset/RED_JSON/` and `dataset/RED_SQL/`: query plan JSON / SQL files
- `dataset/redbench/`: RedBench (see its README for generation steps); workload definitions are read from `dataset/redbench/workloads/`

JOB / CEB queries come from their upstream distributions.

## Usage

### Running experiments

```bash
source .venv/bin/activate
docker start mv_postgres

python scripts/run_experiment.py --algorithms frequency              # single algorithm
python scripts/run_experiment.py --algorithms normal bigsubs utility  # several
python scripts/run_experiment.py                                     # all algorithms
python scripts/run_experiment.py --algorithms normal --verbose
```

Main options:

| Option | Description |
|---|---|
| `--algorithms` | `none normal bigsubs utility utility_capacity frequency` (multiple allowed) |
| `--workload-type` | `job` / `ceb` / `ceb-1a` / `redbench` / `redbench-job` / `redbench-ceb` |
| `--phases` / `--start-from` / `--end-at` | Control which phases run (see below) |
| `--storage-limit` | Storage limit for selected MVs |
| `--insert-queries` | Number of update queries (for maintenance cost) |
| `--config` | Path to a settings YAML (e.g. `config/experiments/*.yaml`) |
| `--no-warmup` | Disable the cache warmup before benchmarking |
| `--output` | Output directory (default: `Output`) |

Phases (executed in order): `query_parsing` → `optimization` → `sql_generation` → `mv_creation` → `query_rewriting` → `benchmark`

```bash
python scripts/run_experiment.py --phases query_parsing optimization
python scripts/run_experiment.py --start-from query_rewriting
python scripts/run_experiment.py --end-at mv_creation
```

`--skip-mv-creation`, `--skip-rewrite` and `--skip-benchmark` are deprecated; use `--phases`.
Run `python scripts/run_experiment.py --help` for all options. See also [scripts/README.md](scripts/README.md) and [docs/phase_control.md](docs/phase_control.md).

### Running RedBench workloads

```bash
python scripts/run_redbench_workload.py --list
python scripts/run_redbench_workload.py --mode redbench-job --algorithm frequency
python scripts/run_redbench_workload.py --mode redbench-job --algorithm none --no-warmup
```

`--mode`: `job` (all JOB queries) / `ceb` (all CEB queries) / `redbench` (JOB + CEB, grouped) / `redbench-job` / `redbench-ceb`.
`--algorithm` takes the same values as `run_experiment.py`. Other options include `--timeout`, `--output` and `--verbose`.

### IVM / maintenance-cost experiments

| Script | Purpose |
|---|---|
| `scripts/measure_v10_mj.py`, `measure_v11_mj.py` | Build 1% sample IMMVs, time the IVM triggers, and extrapolate the full-size per-update cost `m_j` (sec/update) |
| `scripts/measure_v10_refresh.py` | Time `REFRESH MATERIALIZED VIEW` and estimate update cost |
| `scripts/run_v12_zero_m_cost.py` | bigsubs vs. topk-F with `m_cost=0` |
| `scripts/run_v13_bigsubs_no_mcost.py`, `run_v13_topku_topke.py` | BigSubs without `m_cost` vs. topk variants |
| `scripts/compare_rewrite_plans.py` | Compare `EXPLAIN ANALYZE` before/after rewriting |
| `scripts/check_join_order_change.py` | Count queries whose join order changed after rewriting |

These assume the MVs of the target algorithm have already been created via `run_experiment.py`, and that artifacts such as `qp_class.pkl` exist under `Output/`.

### Results

Each `run_experiment.py` invocation writes to its own directory under `Output/` (git-ignored), so runs never overwrite or mix with each other:

```
Output/
├── runs/<run_id>/            # one experiment, e.g. 20261006-154300_job
│   ├── manifest.json         # workload, storage limit, insert count, git commit, status
│   └── <algorithm>/          # optimization/, sql/, benchmark/, query_rewrite/, summary.json
└── artifacts/<workload_id>_i<N>/   # parse results (qp_class.pkl, parsed/, bj_calibrated.json)
```

- `--run-id` names the run (default `<timestamp>_<workload>`); pass an existing id with `--phases` / `--start-from` to continue that run. A run is bound to one workload.
- The *workload id* is a hash of the query files actually loaded (content, order, usage frequency), not of a folder name, so equal ids mean the same workload. Parse results are cached per workload id and `--insert-queries`, and shared by runs on that workload.
- All materialized views in the database are dropped before each algorithm starts.
- Results written before this layout (`Output/<algorithm>/`) are still listed by the dashboard as legacy sets.

Compare algorithms with `python scripts/compare_algorithms.py`. Output formats are described in [docs/output_files.md](docs/output_files.md).

### Dashboard (optional)

A Streamlit dashboard lets you run experiments and compare results.

```bash
pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py
```

See [dashboard/README.md](dashboard/README.md).

## Testing and development

```bash
pytest                      # all tests
pytest -m unit              # unit tests only (no Docker needed)
pytest -m integration       # integration tests (requires Docker)
pytest --cov=src --cov-report=html

black src/ tests/           # format (line-length=100)
ruff check src/             # lint
mypy src/                   # type check
```

Coding conventions and the branch/commit workflow are documented in [AGENTS.md](AGENTS.md).

## Project structure

```
mv-query-optimization/
├── src/
│   ├── core/            # data models, query-plan parsing
│   ├── optimization/    # ILP algorithms (subclasses of BaseILPOptimizer)
│   ├── rewrite/         # query rewriting, MV-creation SQL
│   ├── maintenance/     # IVM / REFRESH maintenance-cost estimation
│   ├── estimation/      # cardinality estimation (NeuroCard integration)
│   ├── benchmark/       # query and workload execution
│   ├── runners/         # experiment runners
│   ├── database/        # connections, MV management, schema
│   └── utils/
├── scripts/             # CLI scripts (experiments, measurements, comparisons)
├── config/              # settings.py, default.yaml, experiments/
├── tests/               # unit / integration / performance
├── data/                # schema and initialization SQL
├── experiments/         # experiment inputs and intermediate artifacts
├── dataset/             # benchmark data (not tracked; see Setup)
├── docs/                # documentation
├── dashboard/           # Streamlit dashboard
├── original_project/    # original (pre-refactoring) implementation
└── Output/              # experiment results (generated, not tracked)
```

## Docker operations

```bash
docker start mv_postgres            # start
docker stop mv_postgres             # stop
docker logs -f mv_postgres          # logs
docker exec -it mv_postgres psql -U postgres -d imdbload

# Full rebuild (this deletes the data!)
docker rm -f mv_postgres && docker volume rm mv_postgres_data
docker build -t mv_postgres:1.0 .
```

### Troubleshooting

- **Container does not start**: make sure Docker Desktop is running (`open -a Docker` on macOS).
- **Cannot connect to the DB**: check `docker ps | grep mv_postgres` and `docker logs mv_postgres | tail -50`; connection settings live in `config/default.yaml`.
- **Gurobi license error**: check the location of `gurobi.lic` or `GRB_LICENSE_FILE`.
- **Cannot write to Output**: `mkdir -p Output && chmod -R 755 Output`.

## References

- [Join Order Benchmark (JOB)](https://github.com/gregrahn/join-order-benchmark)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Gurobi Optimizer](https://www.gurobi.com/documentation/)
- [pg_ivm](https://github.com/sraoss/pg_ivm)

## License

Developed for research purposes.

---

**Author**: [Kaina3](https://github.com/Kaina3)
