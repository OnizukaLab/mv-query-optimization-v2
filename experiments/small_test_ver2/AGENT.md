# Agent Manifest for `small_test_ver2`

## 1. Directory Overview
This directory (`experiments/small_test_ver2`) is an advanced research extension of the main MV Query Optimization project described in the root `AGENT.md` and `README.md`. 
Its primary research focus is **Materialized View (MV) selection optimization for time-varying workloads (時刻変化するワークロードを対象とした実体化ビュー選択の最適化)**.

**Environment**: The experimental environment (PostgreSQL, Gurobi ILP solver, Python version, etc.) is exactly the same as the root `mv-query-optimization` directory. Please refer to the root `AGENT.md` for environment details.

## 2. Directory Structure

- **Database Setup & Base Data**
  - `00_setup.sql` / `insert_queries.sql`: Schema initialization and baseline data insertion.
- **Pipeline Stages**
  - `01_queries/`: Raw SQL queries used for the test workload.
  - `02_json/`: Query execution plans exported as JSON.
  - `03_parsed/`: Intermediary representation of parsed queries.
  - `04_migration/` / `migration/`: Scripts and output targeting database migration/maintenance operations.
- **Core Optimization Pipeline**
  - `mv_generation/`: Logic or outputs for generating candidate materialized views based on workload.
  - `rewrite/`: Query rewriting using the selected MVs.
- **Support & Tooling**
  - `benchmark/`: Runner scripts for evaluating execution time or cost.
  - `core/` / `utils/` / `scripts/` / `tool/`: Reusable logics, helper functions, and CLI scripts specific to this experiment.
  - `small_docs/`: Documentation and notes specific to this small-scale test.
  - `tests/`: Unit or integration tests for this variant of the pipeline.
  - `time_dependent_output/`: Logs or outputs sensitive to time-based execution.
- **Configuration**
  - `config.yaml`: Configuration settings for the test runs (e.g., DB credentials, ILP params or timeouts).
  - `query_groups.json`: Workload grouping configurations.

## 3. Interaction Guidelines for AI Agents

1. **Project Integration**: This folder actively utilizes files and functions from outside this directory (e.g., the root project files). Do not treat it as highly isolated. When implementing features, proactively explore and utilize the core project's existing functions. Modifying files outside this directory is permitted and expected if it supports the research around time-varying workloads and the core architecture.
2. **Pipelines**: The flow generally follows numerical prefixes from `01_queries` -> `02_json` -> `03_parsed` -> `04_migration`. Ensure any changes to the data formats account for downstream directories within this time-dependent workload structure.
3. **Configurations**: Always refer to `config.yaml` for setting up DB connections, capacity limits, or utility parameters for these subsets.

## 4. Workflows

- **To run a full test**: Follow steps in `small_docs/` or run the overarching runner script in `scripts/`.
- **To add new test queries**: Place the `.sql` file in `01_queries/` and ensure the `query_groups.json` or equivalent configuration references them correctly.
