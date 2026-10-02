# プロジェクト概要

## 1. プロジェクトの目的

このプロジェクトは、**マテリアライズドビュー（Materialized View）の選択最適化**を行うシステムです。データベースクエリのパフォーマンスを向上させるため、複数のILP（整数線形計画法）ベースのアルゴリズムを用いて、どのサブクエリをマテリアライズドビューとして保存すべきかを決定します。

### 主要な目標
- **クエリ実行時間の削減**: 頻繁に使用されるサブクエリを事前計算して保存することで、クエリの応答時間を改善
- **ストレージ制約の考慮**: 限られたストレージ容量の中で最適なマテリアライズドビューセットを選択
- **複数のアルゴリズム比較**: 異なる戦略（頻度ベース、利得ベース、容量ベースなど）の性能を実験的に評価

## 2. システムアーキテクチャ

### 2.1 環境構成

このプロジェクトは、開発効率とデバッグ容易性を考慮した以下の構成で動作します:

```
┌─────────────────────────────────────────────────────────────┐
│                    ホストマシン                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Python 3.11+ 実行環境                                │  │
│  │  - プロジェクトコード                                  │  │
│  │  - ILP最適化エンジン (Gurobi)                         │  │
│  │  - クエリ解析・書き換え処理                            │  │
│  │  - 実験スクリプト                                      │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │ psycopg2 (localhost:5432)              │
│                   ▼                                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Docker コンテナ                            │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  PostgreSQL 18                                 │  │  │
│  │  │  - IMDBデータベース (8GB+)                      │  │  │
│  │  │  - マテリアライズドビュー                        │  │  │
│  │  │  - クエリ実行エンジン                           │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**この構成の利点:**
- ✅ コード変更が即座に反映（再ビルド不要）
- ✅ IDE/エディタでのデバッグが容易
- ✅ Dockerはデータベースのみに特化（軽量）
- ✅ 開発環境のカスタマイズが柔軟

### 2.2 主要コンポーネント

```
┌─────────────────────────────────────────────────────────────┐
│                    クエリワークロード                          │
│              (JOB/CEB Benchmark Queries)                     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              クエリパーサー (query_parse_beta.py)             │
│  - クエリプランの解析                                          │
│  - サブクエリの抽出と識別                                       │
│  - コスト計算                                                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│          ILP最適化エンジン (compare_bata.py)                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  5つのアルゴリズム:                                    │   │
│  │  1. Normal (基本ILP)                                 │   │
│  │  2. BigSubs (大きなサブクエリ優先)                     │   │
│  │  3. Utility-Capacity Based (利得/容量比)              │   │
│  │  4. Utility Based (利得優先)                          │   │
│  │  5. Frequency Based (頻度優先)                        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│          クエリ書き換え (query_rewrite_beta.py)               │
│  - 選択されたマテリアライズドビューを使用                        │
│  - クエリの最適化された形式への変換                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│           PostgreSQLデータベース (Docker)                     │
│  - マテリアライズドビューの作成                                │
│  - クエリの実行                                               │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│       性能評価 (scripts/run_experiment.py)                    │
│  - RedBenchベンチマーク実行                                   │
│  - 実行時間の測定                                             │
│  - 結果の比較                                                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 主要クラスとモジュール

#### QueryManager (`query_parse_beta.py`)
- **役割**: クエリプランの構造を管理
- **主要機能**:
  - サブクエリの識別とユニークID生成
  - リーフノード（テーブルスキャン）の管理
  - 非リーフノード（JOIN等）の管理
  - コストとサイズの追跡

#### QueryParser (`query_parse_beta.py`)
- **役割**: JSONフォーマットのクエリプランを解析
- **主要機能**:
  - クエリプランの深さ優先探索
  - サブクエリの抽出
  - メンテナンスコストの計算

## 3. 処理フロー

### 3.1 全体の実験フロー (`scripts/run_experiment.py`)

```
1. 環境準備
   ├─> Dockerコンテナ起動確認 (PostgreSQL)
   ├─> Python仮想環境アクティベート
   └─> 出力ディレクトリ作成

2. ILP最適化実行 (オプション: --initialize)
   └─> compare_bata.py を実行
       ├─> クエリパース
       ├─> 5つのILPアルゴリズムを実行
       └─> 各アルゴリズムの結果を Output/<ilp_type>/mv_y_list.csv に保存

3. 各ILPタイプごとにループ (none, normal, bigsubs, utility_capacity, utility, frequency)
   ├─> MVファイルクリーンアップ
   │   └─> Output/query_rewrite/mv/ をクリア
   │   └─> データベースから既存MVを削除
   │
   ├─> MVスクリプト生成 (re_sql_exe.py <ilp> mv)
   │   └─> 選択されたマテリアライズドビューのCREATE文を生成
   │
   ├─> MVの作成 (run_mv.sh) ※スキップ可能
   │   └─> PostgreSQLでマテリアライズドビューを実際に作成
   │   └─> タイムアウトしたMVをリストから削除
   │
   ├─> クエリ書き換え (re_sql_exe.py <ilp>) ※スキップ可能
   │   └─> 元のクエリをMVを使用する形に書き換え
   │
   ├─> 書き換えたクエリの実行 (execute_rewritten.py)
   │   └─> 全ての書き換えられたクエリをホストから実行
   │   └─> localhost:5432 経由でPostgreSQLに接続
   │
   ├─> ワークロード設定 (setup_rewritten.py) ※スキップ可能
   │   └─> RedBench用のワークロードファイルを準備
   │
   └─> RedBenchベンチマーク実行 ※スキップ可能
       └─> dataset/redbench/ で性能測定
       └─> 結果を Output/redbench/<ilp>.out に保存

4. 完了
   └─> 各ILPの実行時間と結果を表示
```

**実行オプション:**
```bash
# 基本実行
python scripts/run_experiment.py --algorithms normal

# 複数アルゴリズム
python scripts/run_experiment.py --algorithms normal bigsubs utility

# スキップオプション
python scripts/run_experiment.py --algorithms normal \
  --skip-mv-creation \     # MV作成をスキップ
  --skip-rewrite \         # クエリ書き換えをスキップ  
  --skip-benchmark         # ベンチマークをスキップ

# 詳細ログ
python scripts/run_experiment.py --algorithms normal --verbose
```

### 3.2 クエリパースフロー

```
1. JSONクエリプランの読み込み
   └─> dataset/RED_JSON/ から読み込み

2. 各クエリの深さ優先探索
   ├─> リーフノード (Seq Scan等) の処理
   │   └─> テーブル名、フィルタ条件を抽出
   │   └─> ユニークIDを生成またはマッピング
   │
   └─> 非リーフノード (Hash Join等) の処理
       └─> 子ノードのIDから複合キーを生成
       └─> ユニークIDを生成またはマッピング

3. コスト計算
   ├─> 実行コスト (total_cost)
   ├─> サブクエリサイズ (推定行数)
   ├─> メンテナンスコスト (INSERT時の更新コスト)
   └─> 利得計算 (u_ij: クエリiがビューjを使った場合のコスト削減)

4. 出力データ構造の生成
   └─> qp_class.pkl に保存
```

### 3.3 ILP最適化フロー

各ILPアルゴリズム (`ILP_*_beta.py`) は以下の流れで動作:

```
1. 初期化 (initialize関数)
   ├─> Utility-Capacity: (利得 - コスト/サイズ) の降順で選択
   ├─> Utility: (利得 - コスト) の降順で選択
   └─> Frequency: 出現頻度の降順で選択

2. 反復的改善 (proposed関数)
   ├─> 近傍探索 (neighbor_search)
   │   ├─> 現在のMV候補の親ノードを探索
   │   └─> 候補セットを拡張
   │
   ├─> ILP問題の定義
   │   ├─> 決定変数: y[i,j] (クエリiがMV jを使用), z[j] (MV jを作成)
   │   ├─> 目的関数: maximize(Σu_ij*y_ij - Σm_cost*z_j)
   │   └─> 制約: ストレージ容量、重複サブクエリ
   │
   ├─> Gurobiソルバーで最適化
   │
   └─> 収束判定
       └─> 改善がなければ終了

3. 結果出力
   └─> mv_y_list.csv に選択されたMVを保存
```

### 3.4 クエリ書き換えフロー (`query_rewrite_beta.py`)

```
1. 選択されたMVリストの読み込み
   └─> Output/<ilp_type>/mv_y_list.csv

2. 各クエリごとに処理
   ├─> クエリiで使用可能なMVを特定
   │   └─> mv_y_list[i] から取得
   │
   ├─> 元のSQLクエリを解析
   │   └─> FROM句、WHERE句の抽出
   │
   ├─> MVで置き換え可能なサブクエリを検索
   │   ├─> リーフノード: テーブルスキャンをMVに置換
   │   └─> 非リーフノード: JOIN結果をMVに置換
   │
   └─> 書き換えたクエリを保存
       └─> Output/query_rewrite/re_sql/<ilp_type>/

3. MV作成SQLの生成 (mv_make関数)
   └─> CREATE MATERIALIZED VIEW 文を生成
   └─> Output/query_rewrite/mv/ に保存
```

## 4. データフロー

### 4.1 入力データ

| データ | パス | 説明 |
|-------|------|------|
| クエリワークロード | `Output/RED_WORKLOADS/` | RedBenchのワークロード定義（CSV） |
| クエリJSON | `dataset/RED_JSON/` | PostgreSQLのEXPLAIN出力（JSON形式） |
| スキーマ定義 | `data/schema.sql` | IMDbデータベーススキーマ |
| 挿入クエリ | `data/insert_queries.sql` | 更新ワークロード |

### 4.2 中間データ

| データ | パス | 説明 |
|-------|------|------|
| パーサー状態 | `Output/qp_class.pkl` | QueryParserの永続化オブジェクト |
| MV選択結果 | `Output/<ilp>/mv_y_list.csv` | 各ILPで選択されたMV |
| 書き換えクエリ | `Output/query_rewrite/re_sql/<ilp>/` | MVを使用した最適化クエリ |
| MV定義 | `Output/query_rewrite/mv/` | CREATE MATERIALIZED VIEW文 |

### 4.3 出力データ

| データ | パス | 説明 |
|-------|------|------|
| ILP結果 | `Output/compare_bata.out` | 各ILPの最適化結果 |
| MV作成ログ | `Output/experiment/run_mv/<ilp>.out` | MV作成時のログ |
| クエリ実行結果 | `Output/query_rewrite/<ilp>.out` | 書き換えクエリの実行結果 |
| ベンチマーク結果 | `Output/redbench/<ilp>.out` | RedBenchの性能測定結果 |

## 5. 主要アルゴリズム

### 5.1 ILPアルゴリズム一覧

| アルゴリズム | ファイル | 初期化戦略 | 特徴 |
|------------|---------|-----------|------|
| Normal | `ILP_normal_beta.py` | 全候補から選択 | ベースライン手法 |
| BigSubs | `ILP_bigsubs_beta.py` | 大きなサブクエリ優先 | ストレージ効率重視 |
| Utility-Capacity | `ILP_proposed_u_b_beta.py` | (利得-コスト)/サイズ | バランス型 |
| Utility | `ILP_proposed_u_beta.py` | 利得-コスト | 利得最大化 |
| Frequency | `ILP_proposed_f_beta.py` | 出現頻度 | キャッシュ的アプローチ |

### 5.2 ILP問題の定式化

**決定変数:**
- `y[i,j]`: クエリ i が マテリアライズドビュー j を使用するか (binary)
- `z[j]`: マテリアライズドビュー j を作成するか (binary)

**目的関数:**
```
maximize: Σ(u_ij * y_ij) - Σ(m_cost_j * z_j)

where:
  u_ij = クエリiがMV jを使用した場合のコスト削減量
  m_cost_j = MV jの作成・維持コスト
```

**制約条件:**
1. **ストレージ制約**: `Σ(b_j * z_j) ≤ B_max`
2. **利用制約**: `y[i,j] ≤ z[j]` (作成されていないMVは使えない)
3. **重複排除制約**: サブクエリの包含関係を考慮

## 6. 技術スタック

### 6.1 言語とフレームワーク
- **Python 3.11+**: メイン開発言語
- **PostgreSQL 18**: データベースエンジン (Dockerコンテナ)
- **Gurobi 12.0**: ILP最適化ソルバー
- **Docker**: PostgreSQLコンテナ管理

### 6.2 主要ライブラリ
- `gurobipy==12.0.1`: 整数線形計画法ソルバー
- `psycopg2-binary`: PostgreSQL接続ドライバ
- `sqlparse`: SQLパーシング
- `regex`: 正規表現処理
- `pickle`: オブジェクト永続化
- `pandas`: データ分析
- `matplotlib`: グラフ可視化
- `networkx`: グラフアルゴリズム
- `duckdb`: 軽量データベース（分析用）

### 6.3 ベンチマーク
- **RedBench**: データベース更新ワークロードベンチマーク
- **JOB (Join Order Benchmark)**: 複雑なJOINクエリ集
- **CEB**: クエリベンチマーク拡張
- **IMDb データセット**: Internet Movie Database (約8GB)

## 7. 設定とパラメータ

### 7.1 主要設定 (`utils.py`)
```python
GET_CEB = True  # CEB使用フラグ (False: JOBのみ)
```

### 7.2 最適化パラメータ (`compare_bata.py`)
```python
q_num = 113              # クエリ数 (JOBの場合)
insert_query = 1000      # INSERT実行回数
B_max = 50 * 1024 * 1024 # ストレージ上限 (50MB)
```

## 8. 実行手順

### 8.1 環境セットアップ

#### PostgreSQLコンテナの起動
```bash
# Dockerイメージのビルド（初回のみ、15-20分程度）
docker build -t mv_postgres:1.0 .

# コンテナ起動（初回はデータロードに5-10分程度）
docker run -d \
  --name mv_postgres \
  -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data \
  mv_postgres:1.0

# 起動確認
docker ps
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT count(*) FROM title;"
```

#### Python環境のセットアップ
```bash
# Python 3.11以上を確認
python --version

# 仮想環境作成
python -m venv .venv

# 仮想環境アクティベート
source .venv/bin/activate  # macOS/Linux

# 依存パッケージインストール
pip install --upgrade pip
pip install -r requirements.txt

# データベース接続確認
python -c "import psycopg2; conn = psycopg2.connect(host='localhost', port=5432, database='imdbload', user='postgres', password='pass'); print('✓ DB接続成功')"
```

#### Gurobiライセンス設定
```bash
# gurobi.lic をプロジェクトルートに配置
# または環境変数を設定
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

### 8.2 実験実行

#### 基本的な実験
```bash
# 仮想環境をアクティベート（毎回必要）
source .venv/bin/activate

# 単一アルゴリズムで実験
python scripts/run_experiment.py --algorithms normal

# 複数アルゴリズムで実験
python scripts/run_experiment.py --algorithms normal bigsubs utility

# 全アルゴリズムで実験
python scripts/run_experiment.py --algorithms none normal bigsubs utility_capacity utility frequency

# 詳細ログ付き実験
python scripts/run_experiment.py --algorithms normal --verbose
```

#### 実験オプション
```bash
# CSV比較を初期化してから実験
python scripts/run_experiment.py --algorithms normal --initialize

# MV作成をスキップ（デバッグ用）
python scripts/run_experiment.py --algorithms normal --skip-mv-creation

# クエリ書き換えをスキップ
python scripts/run_experiment.py --algorithms normal --skip-rewrite

# ベンチマークをスキップ
python scripts/run_experiment.py --algorithms normal --skip-benchmark
```

### 8.3 個別コンポーネントの実行

#### ILP最適化のみ実行
```bash
python compare_bata.py
# 結果: Output/<ilp_type>/mv_y_list.csv
```

#### 特定のILPでMV作成
```bash
# MV作成スクリプト生成
python re_sql_exe.py frequency mv

# データベースにMV作成
bash run_mv.sh frequency

# クエリ書き換え
python re_sql_exe.py frequency
```

#### データベース管理
```bash
# コンテナ起動/停止
docker start mv_postgres
docker stop mv_postgres
docker restart mv_postgres

# ログ確認
docker logs mv_postgres

# データベース接続
docker exec -it mv_postgres psql -U postgres -d imdbload
```

## 9. 出力の見方

### 9.1 ILP結果の読み方
```
ILP_frequency_based
result_Utility = 12345.67  # 総利得 - 総コスト
result_b = 48000000        # 使用ストレージ（バイト）
Time: 123.45              # 実行時間（秒）
```

### 9.2 MVリスト (`mv_y_list.csv`)
各行がクエリに対応し、そのクエリで使用するMVのIDがリストされる:
```csv
leaf_15,non_leaf_42
leaf_3,leaf_7,non_leaf_8
NONE
```

## 10. 既知の課題と改善点

### 10.1 現在の課題
- ファイル名のタイポ (`compare_bata.py` → `compare_beta.py`)
- 変数名が不明瞭 (`u_ij`, `b_j`, `qm` など)
- コードの重複が多い
- ハードコードされた設定値
- グローバル変数の多用
- テストコードが不足
- エラーハンドリングが不十分

### 10.2 改善済みの項目 ✅
- **Docker構成の最適化**: PostgreSQL専用コンテナに分離
  - 開発効率の向上（コード変更が即座に反映）
  - デバッグの容易性
  - ビルド時間の短縮
  
- **IMDBデータの自動セットアップ**: Dockerfile内で自動ダウンロード・ロード
  - 手動セットアップが不要
  - 環境構築の簡素化
  
- **実験実行スクリプトの統一**: `scripts/run_experiment.py`
  - CLIインターフェース
  - 柔軟なオプション設定
  - 詳細ログ出力

- **依存パッケージの明確化**: `requirements.txt`の整備
  - バージョン固定
  - Python 3.11+対応

### 10.3 今後の改善方向性
1. **プロジェクト構造の再編成**
   - モジュール化の推進
   - src/配下への統合
   
2. **設定ファイルの外部化**
   - config.yaml による設定管理
   - 環境変数のサポート
   
3. **命名規則の統一**
   - PEP 8準拠
   - 型ヒントの追加
   
4. **テストカバレッジの向上**
   - ユニットテストの追加
   - 統合テストの実装
   
5. **ドキュメントの充実**
   - API仕様書
   - アルゴリズム詳細ドキュメント

## 11. 今後の拡張可能性

- **動的ワークロードへの対応**
  - オンラインMV選択アルゴリズム
  - ワークロード変化の検出と再最適化
  
- **インクリメンタルMVの更新戦略**
  - pg_ivm (Incremental View Maintenance) の統合
  - 差分更新による高速化
  
- **分散データベースへの対応**
  - シャーディング環境での最適化
  - 分散MVの配置戦略
  
- **機械学習による選択戦略の改善**
  - クエリパターンの学習
  - 予測ベースのMV選択
  
- **リアルタイムクエリ最適化**
  - クエリ実行中の動的書き換え
  - アダプティブMV管理

## 12. トラブルシューティング

### 12.1 Docker関連

**Q: Dockerコンテナが起動しない**
```bash
# Docker Desktopの起動確認
open -a Docker  # macOS
docker ps       # 起動確認
```

**Q: データベースに接続できない**
```bash
# ポート確認
docker port mv_postgres

# コンテナログ確認
docker logs mv_postgres | tail -50

# コンテナ再起動
docker restart mv_postgres
```

### 12.2 Python環境関連

**Q: パッケージのインストールに失敗する**
```bash
# Python バージョン確認（3.11以上が必要）
python --version

# 仮想環境を再作成
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Q: Gurobiライセンスエラー**
```bash
# ライセンスファイルの確認
ls -la gurobi.lic

# 環境変数の設定
export GRB_LICENSE_FILE=$(pwd)/gurobi.lic

# ライセンスの確認
python -c "import gurobipy; print(gurobipy.gurobi.version())"
```

### 12.3 実験実行関連

**Q: 実験結果が出力されない**
```bash
# 出力ディレクトリの作成
mkdir -p Output/{experiment/{run_mv,mv_create},query_rewrite,redbench}
chmod -R 755 Output/

# 権限確認
ls -la Output/
```

**Q: MVタイムアウトエラー**
- 大きなMVの作成にはメモリと時間が必要
- `B_max`（ストレージ上限）を調整
- PostgreSQLの`work_mem`を増やす

---

**作成日**: 2025年10月7日  
**バージョン**: 2.0  
**最終更新**: 2025年10月7日  
**メンテナー**: [Kaina3](https://github.com/Kaina3)

**変更履歴:**
- v2.0 (2025-10-07): Docker構成を更新、実行手順を刷新、トラブルシューティング追加
- v1.0 (2025-10-03): 初版作成
