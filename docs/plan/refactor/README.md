# リファクタリング実行計画 - 全体概要

## 📋 概要

このディレクトリには、mv-query-optimizationプロジェクトの段階的リファクタリング計画が含まれています。
各ファイルは独立した実行可能な単位として設計されており、LLMに順番に実行させることができます。

## 🎯 目標

1. **コード品質の向上**: 型ヒント、docstring、命名規則の統一
2. **保守性の向上**: モジュール化、責務の分離
3. **テスタビリティの向上**: ユニットテスト、統合テストの追加
4. **拡張性の向上**: 将来的なRustハイブリッド化への準備

## 📊 全体スケジュール

| フェーズ | 期間 | 内容 | 重要度 |
|---------|------|------|--------|
| Phase 0 | 1-2日 | 準備・環境整備 | ⭐⭐⭐⭐⭐ |
| Phase 1 | 2-3日 | 設定管理の外部化 | ⭐⭐⭐⭐⭐ |
| Phase 2 | 3-5日 | ユーティリティモジュール整理 | ⭐⭐⭐⭐ |
| Phase 3 | 5-7日 | コアモジュール（QueryManager）のリファクタリング | ⭐⭐⭐⭐⭐ |
| Phase 4 | 5-7日 | コアモジュール（QueryParser）のリファクタリング | ⭐⭐⭐⭐⭐ |
| Phase 5 | 7-10日 | ILP最適化モジュールの統合 | ⭐⭐⭐⭐⭐ |
| Phase 6 | 5-7日 | クエリ書き換えモジュールのリファクタリング | ⭐⭐⭐⭐ |
| Phase 7 | 3-5日 | 実験スクリプトの整理 | ⭐⭐⭐ |
| Phase 8 | 5-7日 | テストコードの追加 | ⭐⭐⭐⭐ |
| Phase 9 | 2-3日 | ドキュメント整備と最終調整 | ⭐⭐⭐ |

**総期間**: 約 6-8週間

## 📁 ファイル構成

```
docs/plan/
├── README.md                          # このファイル
├── 00_preparation.md                  # Phase 0: 準備
├── 01_config_management.md            # Phase 1: 設定管理
├── 02_utility_modules.md              # Phase 2: ユーティリティ
├── 03_query_manager_refactor.md       # Phase 3: QueryManager
├── 04_query_parser_refactor.md        # Phase 4: QueryParser
├── 05_ilp_optimization_refactor.md    # Phase 5: ILP最適化
├── 06_query_rewrite_refactor.md       # Phase 6: クエリ書き換え
├── 07_experiment_scripts_refactor.md  # Phase 7: 実験スクリプト
├── 08_testing.md                      # Phase 8: テスト追加
├── 09_finalization.md                 # Phase 9: 最終調整
└── PROGRESS.md                        # 進捗管理チェックリスト
```

## 🚀 実行方法

### 基本原則

1. **順番に実行**: 必ず 00 → 01 → ... → 09 の順番で実行
2. **検証**: 各フェーズ完了後に動作確認とテスト実行
3. **コミット**: 各フェーズごとに git commit
4. **ロールバック**: 問題があれば前のフェーズに戻る

### LLMへの指示方法

```
次のファイルの内容を読んで、指示に従って実行してください：
docs/plan/00_preparation.md

完了したら、次のファイルを実行します：
docs/plan/01_config_management.md
```

### 手動実行の場合

```bash
# 1. 各フェーズのファイルを開く
cat docs/plan/00_preparation.md

# 2. 指示に従って実行

# 3. チェックリストを確認
# PROGRESS.mdで該当フェーズをチェック

# 4. コミット
git add .
git commit -m "Phase 0: 準備完了"

# 5. 次のフェーズへ
cat docs/plan/01_config_management.md
```

## ✅ 各フェーズの依存関係

```
Phase 0 (準備)
    ↓
Phase 1 (設定管理) ← 他のフェーズの基盤
    ↓
Phase 2 (ユーティリティ) ← Phase 3-7 で使用
    ↓
Phase 3 (QueryManager) ← Phase 4, 5 で使用
    ↓
Phase 4 (QueryParser) ← Phase 5, 6 で使用
    ↓
Phase 5 (ILP最適化) ← Phase 7 で使用
    ↓
Phase 6 (クエリ書き換え) ← Phase 7 で使用
    ↓
Phase 7 (実験スクリプト)
    ↓
Phase 8 (テスト) ← すべての検証
    ↓
Phase 9 (最終調整)
```

## 🎨 各フェーズの特徴

### Phase 0: 準備（必須）
- プロジェクト構造の作成
- 開発ツールの導入
- **スキップ不可**

### Phase 1: 設定管理（必須）
- グローバル変数の削除
- YAML設定ファイルの導入
- **後続フェーズの基盤**

### Phase 2: ユーティリティ（必須）
- 共通関数の整理
- ロギングの統一
- **すべてのモジュールで使用**

### Phase 3-6: コアリファクタリング（必須）
- 各モジュールの改善
- 型ヒント追加
- **プロジェクトの中核**

### Phase 7: 実験スクリプト（重要）
- CLIの改善
- 実行フローの整理

### Phase 8: テスト（重要）
- 品質保証
- リグレッション防止

### Phase 9: 最終調整（推奨）
- ドキュメント整備
- クリーンアップ

## ⚠️ 注意事項

### 破壊的変更への対応

1. **バックアップ**: 各フェーズ開始前にブランチ作成
   ```bash
   git checkout -b backup/before-phase-X
   git checkout fix/20251003-refactoring
   ```

2. **テスト**: 各フェーズ後に既存機能が動作することを確認
   ```bash
   # 簡易テスト
   python -c "from src.core.query_manager import QueryManager; print('OK')"
   ```

3. **ロールバック**: 問題があれば戻る
   ```bash
   git reset --hard HEAD~1
   ```

### 並行作業の禁止

- 複数フェーズを同時に実行しない
- 1つのフェーズを完全に完了してから次へ

### 検証の重要性

各フェーズ完了後、必ず以下を確認：
- [ ] インポートエラーがない
- [ ] 型チェックが通る（mypy）
- [ ] 既存の実験スクリプトが動作する
- [ ] git statusがクリーン

## 📈 進捗追跡

`PROGRESS.md`ファイルで進捗を管理します：

```markdown
- [x] Phase 0: 準備
- [ ] Phase 1: 設定管理
- [ ] Phase 2: ユーティリティ
...
```

## 🔧 トラブルシューティング

### Q: インポートエラーが発生した
```bash
# Pythonパスの確認
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# または
pip install -e .
```

### Q: 既存のコードが動かない
```bash
# 前のコミットに戻る
git log --oneline
git reset --hard <commit-hash>
```

### Q: どのフェーズまで完了したか分からない
```bash
# PROGRESS.mdを確認
cat docs/plan/PROGRESS.md

# または git log
git log --oneline
```

## 🎓 成功の指標

### Phase 0-2 完了後
- [ ] config/settings.py が動作
- [ ] src/utils/ モジュールがインポート可能

### Phase 3-6 完了後
- [ ] すべてのコアモジュールが新構造に移行
- [ ] 型ヒントが全関数に付与
- [ ] docstringが全パブリック関数に付与

### Phase 7-9 完了後
- [ ] テストカバレッジ 50%以上
- [ ] mypy --strict でエラーなし
- [ ] 実験が正常に実行可能

## 📞 サポート

各フェーズの詳細な手順は個別のファイルを参照してください。
不明点があれば、該当フェーズのファイル内の「トラブルシューティング」セクションを確認してください。

---

**作成日**: 2025年10月3日  
**最終更新**: 2025年10月3日  
**ステータス**: 準備完了
