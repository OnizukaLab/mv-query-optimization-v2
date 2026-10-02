# Materialized View Query Optimization

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 18](https://img.shields.io/badge/postgresql-18-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

ILP（整数線形計画法）によるマテリアライズドビュー（MV）選択でクエリ実行時間を最適化するシステムです。

## 概要

- **クエリ解析**: PostgreSQL `EXPLAIN (FORMAT JSON)` のクエリプランを解析
- **MV選択**: ILP による 5 種類のアルゴリズム（下表）
- **クエリ書き換え**: 選択した MV を使うよう SQL を自動書き換え
- **メンテナンスコスト推定**: [pg_ivm](https://github.com/sraoss/pg_ivm) による差分更新（IVM）と `REFRESH` のコスト計測・推定（`src/maintenance/`）
- **ベンチマーク**: JOB / CEB / RedBench

| アルゴリズム (`--algorithms`) | 説明 |
|---|---|
| `none` | MV なし（ベースライン） |
| `normal` | 基本的な ILP 定式化 |
| `bigsubs` | BigSubs（確率的フリップ） |
| `utility` | 効用最大化 |
| `utility_capacity` | 効用/容量比最大化 |
| `frequency` | 頻度ベース選択 |

## セットアップ

構成: **ホスト**（Python + Gurobi）↔ **Docker**（PostgreSQL + IMDb）。コード修正のたびにコンテナを再ビルドする必要はありません。

### 前提条件

- Python 3.11 以上
- Docker Desktop
- Gurobi Optimizer 12.0.1（[アカデミックライセンス](https://www.gurobi.com/academia/academic-program-and-licenses/)は無料）

### 1. PostgreSQL（Docker）

```bash
# IMDb データを取得してイメージをビルド（初回 15〜20 分）
docker build -t mv_postgres:1.0 .

# 起動（初回はデータロードに 5〜10 分）
docker run -d --name mv_postgres -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data mv_postgres:1.0

# 接続確認
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT count(*) FROM title;"
```

接続情報（デフォルト）: `localhost:5432` / DB `imdbload` / ユーザー `postgres` / パスワード `pass`
（`config/default.yaml` の `database:` で変更可能）。

IVM 関連の実験（`src/maintenance/`, `scripts/measure_*`）では pg_ivm 拡張が必要です。
`data/setup.sql` を参照し、`CREATE EXTENSION pg_ivm;` を実行してください。

### 2. Python 環境

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # 開発用: pip install -r requirements-dev.txt
```

### 3. Gurobi ライセンス

取得した `gurobi.lic` をプロジェクトルートに置くか、`GRB_LICENSE_FILE` 環境変数でパスを指定します（`gurobi.lic` は `.gitignore` 済み）。

### 4. データセット

`dataset/RED_JSON/`, `dataset/RED_SQL/`（クエリプラン JSON / SQL）は容量の都合で Git 管理外です。
RedBench の生成手順（`dataset/redbench/README.md`）や JOB / CEB の配布元から用意してください。
ワークロード定義は `dataset/redbench/workloads/` を使用します。

## 使い方

### 実験の実行

```bash
source .venv/bin/activate
docker start mv_postgres

python scripts/run_experiment.py --algorithms frequency              # 単一
python scripts/run_experiment.py --algorithms normal bigsubs utility  # 複数
python scripts/run_experiment.py                                     # 全アルゴリズム
python scripts/run_experiment.py --algorithms normal --verbose
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--algorithms` | `none normal bigsubs utility utility_capacity frequency`（複数可） |
| `--workload-type` | `job` / `ceb` / `ceb-1a` / `redbench` / `redbench-job` / `redbench-ceb` |
| `--phases` / `--start-from` / `--end-at` | 実行フェーズの制御（下記） |
| `--storage-limit` | ストレージ上限 |
| `--insert-queries` | 更新クエリ数（メンテナンスコスト計算用） |
| `--config` | 設定 YAML を指定（`config/experiments/*.yaml` など） |
| `--no-warmup` | ベンチマーク前のキャッシュウォームアップを無効化 |
| `--output` | 出力ディレクトリ（デフォルト `Output`） |

実行フェーズ（順に実行）: `query_parsing` → `optimization` → `sql_generation` → `mv_creation` → `query_rewriting` → `benchmark`

```bash
python scripts/run_experiment.py --phases query_parsing optimization
python scripts/run_experiment.py --start-from query_rewriting
python scripts/run_experiment.py --end-at mv_creation
```

`--skip-mv-creation` / `--skip-rewrite` / `--skip-benchmark` は非推奨です（`--phases` を使用）。
全オプションは `python scripts/run_experiment.py --help` で確認できます。詳細は [scripts/README.md](scripts/README.md)、[docs/phase_control.md](docs/phase_control.md) を参照。

### RedBench ワークロードの実行

```bash
python scripts/run_redbench_workload.py --list
python scripts/run_redbench_workload.py --mode redbench-job --algorithm frequency
python scripts/run_redbench_workload.py --mode redbench-job --algorithm none --no-warmup
```

`--mode`: `job`（JOB 全クエリ）/ `ceb`（CEB 全クエリ）/ `redbench`（JOB+CEB 混在・グループ別）/ `redbench-job` / `redbench-ceb`。
`--algorithm` は `run_experiment.py` と同じ。その他 `--timeout`, `--output`, `--verbose` など。

### IVM / メンテナンスコスト実験

| スクリプト | 内容 |
|---|---|
| `scripts/measure_v10_mj.py`, `measure_v11_mj.py` | 1% サンプルの IMMV を作り IVM トリガー時間を計測し、フルサイズの `m_j`（秒/更新）を推定 |
| `scripts/measure_v10_refresh.py` | `REFRESH MATERIALIZED VIEW` 時間の計測と更新コスト推定 |
| `scripts/run_v12_zero_m_cost.py` | `m_cost=0` での bigsubs vs topk-F 比較 |
| `scripts/run_v13_bigsubs_no_mcost.py`, `run_v13_topku_topke.py` | `m_cost` なし BigSubs と topk 系の比較 |
| `scripts/compare_rewrite_plans.py` | 書き換え前後の `EXPLAIN ANALYZE` 比較 |
| `scripts/check_join_order_change.py` | 書き換え前後で結合順序が変化したクエリ数の集計 |

これらは `run_experiment.py` で対象アルゴリズムの MV が作成済みであること、および `Output/` 配下の成果物（`qp_class.pkl` 等）を前提とします。

### 結果の確認

結果は `Output/`（Git 管理外）に保存されます。

```
Output/
├── experiments/   # アルゴリズム別の結果
├── logs/          # 実行ログ
└── artifacts/     # 中間ファイル（qp_class.pkl など）
```

比較: `python scripts/compare_algorithms.py`。出力形式は [docs/output_files.md](docs/output_files.md) を参照。

### ダッシュボード（任意）

Streamlit ダッシュボードで実験の実行・結果比較ができます。

```bash
pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py
```

詳細は [dashboard/README.md](dashboard/README.md)。

## テスト・開発

```bash
pytest                      # 全テスト
pytest -m unit              # ユニットのみ（Docker 不要）
pytest -m integration       # 統合テスト（Docker 必須）
pytest --cov=src --cov-report=html

black src/ tests/           # フォーマット（line-length=100）
ruff check src/             # リント
mypy src/                   # 型チェック
```

コーディング規約・ブランチ/コミット規則は [AGENTS.md](AGENTS.md) を参照してください。

## プロジェクト構造

```
mv-query-optimization/
├── src/
│   ├── core/            # データモデル・クエリプラン解析
│   ├── optimization/    # ILP アルゴリズム（BaseILPOptimizer 継承）
│   ├── rewrite/         # クエリ書き換え・MV 生成 SQL
│   ├── maintenance/     # IVM / REFRESH のメンテナンスコスト推定
│   ├── estimation/      # カーディナリティ推定（NeuroCard 連携）
│   ├── benchmark/       # クエリ実行・ワークロード実行
│   ├── runners/         # 実験ランナー
│   ├── database/        # 接続管理・MV 管理・スキーマ
│   └── utils/
├── scripts/             # CLI スクリプト（実験・計測・比較）
├── config/              # settings.py, default.yaml, experiments/
├── tests/               # unit / integration / performance
├── data/                # スキーマ・初期化 SQL
├── dataset/             # ベンチマークデータ（RedBench など）
├── docs/                # ドキュメント
├── dashboard/           # Streamlit ダッシュボード
└── Output/              # 実験結果（自動生成・Git 管理外）
```

## Docker 運用

```bash
docker start mv_postgres            # 起動
docker stop mv_postgres             # 停止
docker logs -f mv_postgres          # ログ
docker exec -it mv_postgres psql -U postgres -d imdbload

# 完全再構築（データも削除されます）
docker rm -f mv_postgres && docker volume rm mv_postgres_data
docker build -t mv_postgres:1.0 .
```

### トラブルシューティング

- **コンテナが起動しない**: Docker Desktop の起動を確認（`open -a Docker`）。
- **DB に接続できない**: `docker ps | grep mv_postgres` と `docker logs mv_postgres | tail -50` を確認。接続情報は `config/default.yaml`。
- **Gurobi ライセンスエラー**: `gurobi.lic` の配置または `GRB_LICENSE_FILE` を確認。
- **Output が書き込めない**: `mkdir -p Output && chmod -R 755 Output`。

## 参考文献

- [Join Order Benchmark (JOB)](https://github.com/gregrahn/join-order-benchmark)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Gurobi Optimizer](https://www.gurobi.com/documentation/)
- [pg_ivm](https://github.com/sraoss/pg_ivm)

## ライセンス

研究目的で開発されています。

---

**開発者**: [Kaina3](https://github.com/Kaina3)
