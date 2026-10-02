# データベースセットアップガイド

## 概要

`setup_database.py` スクリプトを使用して、2種類のデータベースを簡単にセットアップできます。

1. **small_test**: 小規模テストデータベース (3テーブル、約280レコード)
2. **imdb**: IMDb データベース (21テーブル、大規模データセット)

## 前提条件

- PostgreSQL 18 がインストールされている
- `psql` コマンドが使用可能
- IMDb の場合: CSV データファイルが `data/` ディレクトリに存在する

## 使用方法

### 1. 小規模テストデータベースのセットアップ

```bash
# 基本的な使い方
python experiments/small_test_ver2/scripts/setup_database.py --type small_test

# カスタムユーザーを指定
python experiments/small_test_ver2/scripts/setup_database.py --type small_test --user myuser
```

**作成されるデータベース:**
- データベース名: `mv_small_test`
- テーブル: `users`, `products`, `orders`
- データ量: ユーザー50件、商品30件、注文200件

### 2. IMDb データベースのセットアップ

```bash
# 基本的な使い方
python experiments/small_test_ver2/scripts/setup_database.py --type imdb

# psqlのフルパスを指定する場合 (Windows)
python experiments/small_test_ver2/scripts/setup_database.py --type imdb --psql-path "C:\Program Files\PostgreSQL\18\bin\psql.exe"
```

**作成されるデータベース:**
- データベース名: `imdbload`
- テーブル: 21テーブル (aka_name, aka_title, cast_info, ...)
- データ量: 数百万レコード

**⚠️ 重要:** IMDb セットアップには、以下のCSVファイルが `data/` ディレクトリに必要です:
- aka_name.csv
- aka_title.csv
- cast_info.csv
- char_name.csv
- comp_cast_type.csv
- company_name.csv
- company_type.csv
- complete_cast.csv
- info_type.csv
- keyword.csv
- kind_type.csv
- link_type.csv
- movie_companies.csv
- movie_info.csv
- movie_info_idx.csv
- movie_keyword.csv
- movie_link.csv
- name.csv
- person_info.csv
- role_type.csv
- title.csv

## コマンドラインオプション

| オプション | 説明 | デフォルト値 |
|-----------|------|-------------|
| `--type` | データベースタイプ (`small_test` または `imdb`) | **必須** |
| `--psql-path` | psql コマンドのパス | `psql` |
| `--user` | PostgreSQL ユーザー名 | `postgres` |
| `--data-dir` | IMDb データディレクトリのパス | `<project_root>/data` |

## セットアップ後の設定

データベースをセットアップした後、`config.yaml` を編集してください。

### small_test の場合

```yaml
database:
  database: mv_small_test
  database_type: small_test
```

### IMDb の場合

```yaml
database:
  database: imdbload
  database_type: imdb
```

## トラブルシューティング

### psql コマンドが見つからない

**Windows の場合:**
```bash
python setup_database.py --type small_test --psql-path "C:\Program Files\PostgreSQL\18\bin\psql.exe"
```

**環境変数に追加:**
PostgreSQL の bin ディレクトリを PATH に追加してください。

### IMDb データロードでエラーが発生

1. CSV ファイルが `data/` ディレクトリに存在するか確認
2. ファイル名が正しいか確認 (例: `aka_name.csv`)
3. PostgreSQL にディレクトリへのアクセス権限があるか確認

### パスワード入力を求められる

`.pgpass` ファイルを設定するか、環境変数 `PGPASSWORD` を設定してください:

```bash
# Windows (cmd)
set PGPASSWORD=your_password

# Windows (PowerShell)
$env:PGPASSWORD="your_password"

# Linux/Mac
export PGPASSWORD=your_password
```

## 実行例

### 成功例 (small_test)

```
============================================================
データベースセットアップスクリプト
============================================================
データベースタイプ: small_test
PostgreSQL ユーザー: postgres
psql パス: psql

============================================================
小規模テストデータベース (mv_small_test) のセットアップを開始します
============================================================
実行コマンド: psql -U postgres -f C:\...\00_setup.sql
...
✅ 小規模テストデータベースのセットアップが完了しました
   データベース名: mv_small_test
   テーブル数: 3 (users, products, orders)

============================================================
✅ セットアップが正常に完了しました
============================================================
```

### 成功例 (IMDb)

```
============================================================
データベースセットアップスクリプト
============================================================
データベースタイプ: imdb
PostgreSQL ユーザー: postgres
psql パス: psql

============================================================
IMDb データベース (imdbload) のセットアップを開始します
============================================================
データディレクトリ: C:\...\data

ステップ1: データベースを作成します...
✅ データベース imdbload を作成しました

ステップ2: スキーマを作成します...
✅ スキーマを作成しました

ステップ3: データをロードします...
⚠️  注意: CSVファイルが data/ ディレクトリに存在する必要があります
...
✅ IMDb データベースのセットアップが完了しました
   データベース名: imdbload

============================================================
✅ セットアップが正常に完了しました
============================================================
```

## 関連ファイル

- `experiments/small_test_ver2/00_setup.sql`: 小規模テストDB用SQLスクリプト
- `data/schema.sql`: IMDb スキーマ定義
- `data/setup.sql`: IMDb データロードスクリプト
- `experiments/small_test_ver2/config.yaml`: 実験設定ファイル

## 次のステップ

1. データベースのセットアップが完了したら、`config.yaml` を編集
2. 実験スクリプトを実行:
   ```bash
   python experiments/small_test_ver2/scripts/run_experiment_normal.py --query-set <query_set_name>
   ```
