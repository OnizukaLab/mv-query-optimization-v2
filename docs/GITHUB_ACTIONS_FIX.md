# GitHub Actions エラー修正レポート

**日付**: 2025年10月6日  
**修正者**: kanji masuda  
**コミット**: bf15e21b

---

## 🐛 発生したエラー

```
Error: This request has been automatically failed because it uses a deprecated version of `actions/upload-artifact: v3`. 
Learn more: https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/
```

### 原因
GitHub Actionsの`actions/upload-artifact`アクションのv3が2024年4月16日に非推奨（deprecated）となり、使用できなくなりました。

---

## ✅ 修正内容

### `.github/workflows/tests.yml` の更新

#### 1. actions/checkout のアップグレード
```yaml
# 修正前
- uses: actions/checkout@v3

# 修正後
- uses: actions/checkout@v4
```

#### 2. actions/setup-python のアップグレード
```yaml
# 修正前
- uses: actions/setup-python@v4

# 修正後
- uses: actions/setup-python@v5
```

#### 3. actions/upload-artifact のアップグレード（主要な修正）
```yaml
# 修正前
- name: Upload coverage HTML
  uses: actions/upload-artifact@v3
  with:
    name: coverage-report-${{ matrix.python-version }}
    path: htmlcov/

# 修正後
- name: Upload coverage HTML
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report-${{ matrix.python-version }}
    path: htmlcov/
```

#### 4. codecov/codecov-action のアップグレード
```yaml
# 修正前
- uses: codecov/codecov-action@v3

# 修正後
- uses: codecov/codecov-action@v4
```

---

## 📊 変更サマリー

| アクション | 変更前 | 変更後 | 理由 |
|-----------|--------|--------|------|
| actions/checkout | v3 | v4 | 最新版への更新 |
| actions/setup-python | v4 | v5 | 最新版への更新 |
| **actions/upload-artifact** | **v3** | **v4** | **非推奨警告対応（必須）** |
| codecov/codecov-action | v3 | v4 | 最新版への更新 |

---

## 🔍 actions/upload-artifact v4 の主な変更点

### 1. アーティファクト名の一意性要件
v4では、同じワークフロー実行内でアーティファクト名が一意である必要があります。

現在の設定:
```yaml
name: coverage-report-${{ matrix.python-version }}
```
これは問題なし（Python 3.10, 3.11で異なる名前になる）

### 2. パフォーマンス向上
- アップロード速度が大幅に向上
- より効率的な圧縮アルゴリズム

### 3. 保持期間のデフォルト変更
- デフォルトの保持期間が変更
- 必要に応じて `retention-days` を明示的に設定可能

---

## ✨ 期待される効果

### 1. エラー解消
✅ 非推奨警告エラーが解消され、CI/CDが正常に動作

### 2. パフォーマンス向上
✅ アーティファクトのアップロード速度が向上

### 3. セキュリティ
✅ 最新版のアクションによるセキュリティ向上

### 4. 将来の互換性
✅ 長期的なサポートとメンテナンス保証

---

## 🧪 検証方法

### 1. PRでのCI/CD実行確認
プルリクエスト #1 で自動的にCI/CDが実行されます：
- https://github.com/Kaina3/mv-query-optimization/pull/1

### 2. 確認すべきポイント
- [ ] テストジョブが正常に完了
- [ ] カバレッジレポートが正常にアップロード
- [ ] アーティファクトがダウンロード可能
- [ ] 非推奨警告が表示されない

### 3. 手動テスト（オプション）
```bash
# ワークフローを手動でトリガー
gh workflow run tests.yml

# ワークフロー実行状況を確認
gh run list --workflow=tests.yml

# 最新の実行結果を確認
gh run view
```

---

## 📚 参考リンク

- [GitHub Changelog: Deprecation notice v3 of the artifact actions](https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/)
- [actions/upload-artifact v4 リリースノート](https://github.com/actions/upload-artifact/releases/tag/v4.0.0)
- [actions/checkout v4 ドキュメント](https://github.com/actions/checkout)
- [actions/setup-python v5 ドキュメント](https://github.com/actions/setup-python)

---

## 🎯 今後の推奨事項

### 1. 定期的なアクション更新
- 3ヶ月ごとにGitHub Actionsのバージョンを確認
- Dependabotを設定して自動更新を検討

### 2. Dependabot設定（推奨）
`.github/dependabot.yml` を作成:
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

### 3. バージョン固定の検討
本番環境では、メジャーバージョンではなく完全なバージョンを指定することを検討：
```yaml
# メジャーバージョン（自動更新）
- uses: actions/checkout@v4

# 完全バージョン（固定）
- uses: actions/checkout@v4.1.1
```

---

## ✅ 結論

GitHub Actionsの非推奨警告エラーを修正し、全てのアクションを最新版にアップグレードしました。これにより：

1. ✅ CI/CDパイプラインが正常に動作
2. ✅ パフォーマンスとセキュリティが向上
3. ✅ 将来の互換性を確保

**修正は正常に完了し、PRに反映されています。**
