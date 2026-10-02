# Original Project Files

このディレクトリには、リファクタリング前の元のプロジェクトファイルが保管されています。

## 移動日
2025年10月6日

## 目的
リファクタリングプラン(`docs/refactoring_plan.md`)に基づき、プロジェクト構造を再編成しました。
元のファイルは参照用としてこのディレクトリに保管されています。

## 含まれるファイル

### ILPアルゴリズム実装
- `ILP_normal_beta.py` - Normal ILP (→ `src/optimization/normal.py`)
- `ILP_bigsubs_beta.py` - BigSubs ILP (→ `src/optimization/bigsubs.py`)
- `ILP_proposed_u_beta.py` - Utility ILP (→ `src/optimization/utility.py`)
- `ILP_proposed_u_b_beta.py` - Utility-Capacity ILP (→ `src/optimization/utility_capacity.py`)
- `ILP_proposed_f_beta.py` - Frequency ILP (→ `src/optimization/frequency.py`)

### クエリ処理
- `query_parse_beta.py` - クエリパーサー (→ `src/core/query_parser.py`, `src/core/query_manager.py`)
- `query_rewrite_beta.py` - クエリ書き換え (→ `src/rewrite/`)

### 比較・実験スクリプト
- `compare_bata.py` - 最適化アルゴリズム比較 (タイポあり)
- `compare_capacity.py` - キャパシティ比較
- `compare_insertquery.py` - INSERT クエリ比較
- `compare_topk_beta.py` - Top-K 比較
- `experiment.py` - 実験実行スクリプト

### ユーティリティ
- `utils.py` - ユーティリティ関数 (→ `src/utils/`)
- `alpha_measure.py` - Alpha 測定
- `count_sql.py` - SQL カウント
- `execute_rewritten.py` - 書き換えクエリ実行
- `re_sql_exe.py` - SQL 再実行
- `remove_mv.py` - MV 削除
- `select_used_files.py` - 使用ファイル選択
- `setup_rewritten.py` - 書き換えセットアップ
- `sql_to_wvlet.py` - SQL to Wvlet 変換
- `sqljson.py` - SQL JSON 処理
- `test.py` - テストスクリプト
- `make_each_sqlfile.py` - SQL ファイル生成

### シェルスクリプト
- `delete_mv.sh` - MV 削除スクリプト
- `make_dirs.sh` - ディレクトリ作成
- `run_1_mv.sh` - 1つのMV実行
- `run_mv.sh` - MV実行
- `run_re_sql.sh` - 書き換えSQL実行
- `run_sql.sh` - SQL実行

### その他
- `get_del.sql` - 削除SQL
- `__pycache__/` - Python キャッシュファイル

## 新しい構造との対応

新しいプロジェクト構造については、`docs/refactoring_plan.md`を参照してください。

主な変更点:
- モジュール化: 機能ごとに`src/`配下に整理
- 設定の外部化: `config/`ディレクトリに集約
- テストの追加: `tests/`ディレクトリを新設
- 型ヒントとドキュメント: すべてのモジュールに追加
- 循環依存の解消: 適切な依存関係の設計

## 注意事項

⚠️ これらのファイルは**参照用**です。新しい開発では`src/`配下のモジュールを使用してください。

## 削除について

プロジェクトが安定し、新しい構造での動作が十分に確認できた後は、このディレクトリを削除しても問題ありません。
ただし、削除前にGitの履歴に残っていることを確認してください。
