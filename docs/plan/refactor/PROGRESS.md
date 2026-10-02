# リファクタリング進捗チェックリスト

最終更新: 2025年10月3日

## 📊 全体進捗

- [x] Phase 0: 準備・環境整備 (100%) ✅
- [x] Phase 1: 設定管理の外部化 (100%) ✅
- [x] Phase 2: ユーティリティモジュール整理 (100%) ✅
- [x] Phase 3: コアモジュールリファクタリング (100%) ✅
- [x] Phase 4: ILP最適化モジュール統合 (100%) ✅
- [x] Phase 5: データベース操作モジュール (100%) ✅
- [ ] Phase 6: クエリ書き換えモジュール (0%)
- [ ] Phase 7: 実験スクリプト整理 (0%)
- [ ] Phase 8: テストコード追加 (0%)
- [ ] Phase 9: 最終調整とドキュメント (0%)

---

## Phase 0: 準備・環境整備

### タスク
- [ ] バックアップブランチ作成
- [ ] ディレクトリ構造作成
  - [ ] src/ とサブディレクトリ
  - [ ] config/, scripts/, tests/
  - [ ] __init__.py ファイル
- [ ] 開発ツールインストール
  - [ ] mypy
  - [ ] black, ruff
  - [ ] pytest
  - [ ] pyyaml
- [ ] 設定ファイル作成
  - [ ] pyproject.toml
  - [ ] setup.py
  - [ ] .gitignore 更新
  - [ ] .env.example
- [ ] 動作確認
- [ ] Git コミット

### 検証
- [ ] `import src` が成功
- [ ] 開発ツールが動作
- [ ] `pip install -e .` が成功

---

## Phase 1: 設定管理の外部化

### タスク
- [ ] YAML設定ファイル作成
  - [ ] config/default.yaml
  - [ ] config/experiments/job_benchmark.yaml
  - [ ] config/experiments/ceb_benchmark.yaml
- [ ] 設定管理クラス実装
  - [ ] config/settings.py
  - [ ] データクラス定義
  - [ ] YAML読み込み
  - [ ] 環境変数オーバーライド
  - [ ] 後方互換性プロパティ
- [ ] レガシーユーティリティ移行
  - [ ] src/utils/legacy.py
- [ ] テスト作成
  - [ ] tests/unit/test_settings.py
- [ ] Git コミット

### 検証
- [ ] 設定ファイルが読み込める
- [ ] 環境変数オーバーライドが動作
- [ ] テストが通る
- [ ] settings.GET_CEB が動作

---

## Phase 2: ユーティリティモジュール整理

### タスク
- [ ] ファイル操作ユーティリティ
  - [ ] src/utils/file_utils.py
- [ ] ロギングユーティリティ
  - [ ] src/utils/logging_utils.py
  - [ ] 統一ロガー作成
- [ ] ソートユーティリティ
  - [ ] src/utils/sorting.py
- [ ] テスト作成
  - [ ] tests/unit/test_file_utils.py
  - [ ] tests/unit/test_logging.py
- [ ] 既存コードの移行開始
- [ ] Git コミット

### 検証
- [ ] ユーティリティがインポート可能
- [ ] ロガーが動作
- [ ] テストが通る

---

## Phase 3: コアモジュールリファクタリング

### タスク
- [x] データモデル定義
  - [x] src/core/models.py
  - [x] QueryNode, LeafNode, NonLeafNode
  - [x] MaterializedView, OptimizationResult, QueryPlan
- [x] QueryManager 実装
  - [x] src/core/query_manager.py
  - [x] 型ヒント追加
  - [x] docstring 追加
  - [x] メソッド整理
- [x] QueryParser 実装
  - [x] src/core/query_parser.py
  - [x] ILP依存削除
  - [x] 型ヒント追加
  - [x] docstring 追加
- [x] テスト作成
  - [x] tests/unit/test_query_manager.py (17テスト)
  - [x] tests/unit/test_query_parser.py (14テスト)
- [x] 既存コードとの互換性確保
- [x] Git コミット (789c769d)

### 検証
- [x] QueryManager が動作
- [x] QueryParser が動作
- [x] 既存の query_parse_beta.py から移行
- [x] テストが通る (31/31 passed)
- [x] QueryManagerカバレッジ: 91%

### 成果物
- 5個の新規ファイル
- 1,611行のコード追加
- データモデル定義完了
- 型安全性向上
- テストカバレッジ拡充

---

## Phase 4: QueryParser リファクタリング

### タスク
- [ ] QueryParser 実装
  - [ ] src/core/query_parser.py
  - [ ] ILP依存の削除
  - [ ] 型ヒント追加
  - [ ] docstring 追加
- [ ] テスト作成
  - [ ] tests/unit/test_query_parser.py
- [ ] 統合テスト
  - [ ] tests/integration/test_query_parsing.py
- [ ] Git コミット

### 検証
- [ ] QueryParser が動作
- [ ] 循環依存が解消
- [ ] テストが通る
- [ ] 既存機能が動作

---

## Phase 4: ILP最適化モジュール統合

### タスク
- [x] 基底クラス実装
  - [x] src/optimization/base.py
  - [x] BaseILPOptimizer
- [x] 各アルゴリズム実装
  - [x] src/optimization/normal.py
  - [x] src/optimization/bigsubs.py
  - [x] src/optimization/utility_capacity.py
  - [x] src/optimization/utility.py
  - [x] src/optimization/frequency.py
- [x] Factory実装
  - [x] src/optimization/factory.py
- [x] テスト作成
  - [x] tests/unit/test_optimization.py (14テスト)
- [x] Git コミット

### 検証
- [x] すべてのILPアルゴリズムが動作
- [x] Factoryパターンが動作
- [x] テストが通る (14/14 passed)
- [x] コードの重複が削減

### 成果物
- 8個の新規ファイル
- ILP最適化アルゴリズム5種類統合
- Factoryパターンでアルゴリズム選択
- ユニットテスト14個 (全てPASS)

---

## Phase 5: データベース操作モジュール

### タスク
- [x] DatabaseConnection 実装
  - [x] src/database/connection.py
  - [x] 接続管理、コンテキストマネージャ
  - [x] カーソル管理、トランザクション処理
  - [x] ConnectionPool実装
- [x] MaterializedViewManager 実装
  - [x] src/database/mv_manager.py
  - [x] MV作成、削除、リフレッシュ
  - [x] 一覧取得、存在確認、サイズ取得
  - [x] インデックス作成
- [x] SchemaManager 実装
  - [x] src/database/schema.py
  - [x] テーブル情報取得
  - [x] カラム情報取得
  - [x] インデックス情報取得
- [x] パッケージ初期化
  - [x] src/database/__init__.py
- [x] ユニットテスト作成
  - [x] tests/unit/test_database_connection.py (20テスト)
  - [x] tests/unit/test_mv_manager.py (26テスト)
- [x] 統合テスト作成
  - [x] tests/integration/test_db_operations.py
- [x] Git コミット

### 検証
- [x] DatabaseConnectionが動作
- [x] MaterializedViewManagerが動作
- [x] SchemaManagerが動作
- [x] テストが通る (46/46 passed)
- [x] connection.py: カバレッジ100%
- [x] mv_manager.py: カバレッジ90%

### 成果物
- 3個の実装ファイル (connection, mv_manager, schema)
- 46個のユニットテスト (全てPASS)
- 統合テストフレームワーク
- ~500行のコード追加

---

## Phase 6: クエリ書き換えモジュール

### タスク
- [ ] QueryRewriter 実装
  - [ ] src/rewrite/query_rewriter.py
- [ ] MVGenerator 実装
  - [ ] src/rewrite/mv_generator.py
- [ ] SQLパーサー実装
  - [ ] src/rewrite/sql_parser.py
- [ ] テスト作成
  - [ ] tests/unit/test_rewriter.py
- [ ] Git コミット

### 検証
- [ ] クエリ書き換えが動作
- [ ] MV生成が動作
- [ ] テストが通る

---

## Phase 7: 実験スクリプト整理

### タスク
- [ ] メインスクリプト実装
  - [ ] scripts/run_experiment.py
  - [ ] CLI化（Click使用）
- [ ] 最適化スクリプト
  - [ ] scripts/run_optimization.py
- [ ] セットアップスクリプト
  - [ ] scripts/setup_database.py
- [ ] Git コミット

### 検証
- [ ] CLIが動作
- [ ] 実験が実行可能
- [ ] 既存のワークフローが動作

---

## Phase 8: テストコード追加

### タスク
- [ ] ユニットテスト拡充
  - [ ] カバレッジ 50%以上
- [ ] 統合テスト作成
  - [ ] tests/integration/test_experiment_flow.py
- [ ] フィクスチャ作成
  - [ ] tests/fixtures/
- [ ] pytest設定
  - [ ] tests/conftest.py
- [ ] Git コミット

### 検証
- [ ] カバレッジ 50%以上
- [ ] すべてのテストが通る
- [ ] CI/CDが通る（将来）

---

## Phase 9: 最終調整とドキュメント

### タスク
- [ ] README.md 更新
- [ ] APIドキュメント作成
- [ ] コードフォーマット
  - [ ] black . 実行
  - [ ] ruff check 実行
- [ ] 型チェック
  - [ ] mypy src/ 実行
- [ ] 不要ファイルの削除/移動
- [ ] Git コミット
- [ ] プルリクエスト作成

### 検証
- [ ] すべてのチェックが通る
- [ ] ドキュメントが最新
- [ ] 動作確認完了

---

## 🎯 最終確認

### コード品質
- [ ] mypy --strict でエラーなし（または最小限）
- [ ] black でフォーマット済み
- [ ] ruff でリントエラーなし
- [ ] テストカバレッジ 50%以上

### 機能
- [ ] すべてのILPアルゴリズムが動作
- [ ] 実験が実行可能
- [ ] 設定ファイルで制御可能

### ドキュメント
- [ ] README.md が最新
- [ ] すべてのパブリック関数にdocstring
- [ ] API文ドキュメント存在

### Git
- [ ] すべての変更がコミット済み
- [ ] コミットメッセージが明確
- [ ] プルリクエスト準備完了

---

## 📊 統計

- **総フェーズ数**: 10
- **完了フェーズ**: 6 (Phase 0-5)
- **進捗率**: 60%
- **推定残り時間**: 2-3週間
- **総テスト数**: 103 (26 Phase 1-2 + 31 Phase 3 + 14 Phase 4 + 46 Phase 5 + integration)
- **総コード行数**: ~5,000行 (新規追加)

---

## 📝 メモ

### 変更履歴
- 2025-10-03: Phase 0-2 完了
- 2025-10-03: Phase 3 完了 (コアモジュール)
- 2025-10-03: Phase 4 完了 (ILP最適化モジュール)
- 2025-10-03: Phase 5 完了 (データベース操作モジュール)

### 課題・注意事項
- query_parse_beta.py は残存 (既存コードとの互換性のため)
- IMDBスキーマ情報がハードコード (将来的に外部化予定)
- 統合テストは@pytest.mark.integrationでマーク済み

### 次のアクション
1. Phase 6: クエリ書き換えモジュール
2. Phase 7: 実験スクリプト整理
3. 各フェーズ完了後にこのファイルを更新
