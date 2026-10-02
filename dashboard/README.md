# MV Query Optimization Dashboard

Streamlitベースの実体化ビュー最適化実験用Webダッシュボード

## 📋 概要

このダッシュボードは、実体化ビュー(Materialized View)の選択最適化実験を視覚化・管理するためのWebアプリケーションです。従来のCLI操作から脱却し、直感的なGUIで実験の設定・実行・結果分析が可能です。

### 主な機能

- 🚀 **実験実行**: GUIから簡単に実験を設定・実行
- 📊 **結果分析**: アルゴリズム間の比較分析と可視化
- 🔍 **クエリ分析**: 個別クエリのパフォーマンス詳細分析
- 📦 **MV Explorer**: 実体化ビューの詳細情報と選択プロセス
- ⚙️ **設定管理**: データベース接続やパス設定の管理

## 🛠️ インストール

### 前提条件

- Python 3.10以上
- PostgreSQLデータベース（実験用）
- 既存のmv-query-optimizationプロジェクト

### ダッシュボード専用パッケージのインストール

```bash
# ダッシュボード専用の依存パッケージをインストール
pip install -r requirements-dashboard.txt
```

インストールされる主なパッケージ:
- streamlit (Webアプリフレームワーク)
- plotly (インタラクティブグラフ)
- graphviz (実行プラン可視化)
- pandas (データ処理)

## 🚀 起動方法

### 基本的な起動

```bash
# プロジェクトのルートディレクトリで実行
streamlit run dashboard/app.py
```

ブラウザが自動的に開き、`http://localhost:8501`でダッシュボードにアクセスできます。

### カスタムポートで起動

```bash
streamlit run dashboard/app.py --server.port 8502
```

### 自動リロードを有効にして起動（開発時）

```bash
streamlit run dashboard/app.py --server.runOnSave true
```

## 📖 使い方

### 1. ホーム画面（実験実行）

#### 実験の設定

1. **アルゴリズムの選択**
   - Normal, BigSubs, Frequency, Utility, Utility+Capacityから選択
   - 複数選択可能
   - None (Baseline)でベースライン測定も可能

2. **ストレージ制限の設定**
   - スライダーで10MB〜500MBの範囲で設定

3. **実行フェーズの選択**
   - Query Parsing: クエリ構造の解析
   - ILP Optimization: 最適化アルゴリズムの実行
   - SQL Generation: MV用SQL生成
   - MV Creation: データベースへのMV作成
   - Query Rewriting: クエリ書き換え
   - Benchmark: パフォーマンス測定

4. **実験の実行**
   - 「🚀 Run Experiment」ボタンをクリック
   - 実行タブで進行状況をリアルタイム確認

#### 設定の保存・読み込み

- **保存**: 「💾 Save Configuration」で設定をJSON形式で保存
- **読み込み**: 「📂 Load Configuration」で保存済み設定を読み込み

### 2. 結果分析画面

#### アルゴリズム比較

1. 比較したいアルゴリズムを選択
2. 主要メトリクス（MV数、Utility、ストレージ）を確認
3. グラフで視覚的に比較

#### 表示されるグラフ

- **Overview**: アルゴリズム比較棒グラフ
- **Performance**: Utility vs Storage散布図、クエリパフォーマンスヒートマップ
- **Storage**: ストレージ分布と使用状況

#### 結果のエクスポート

- CSV形式でエクスポート
- グラフをPNG形式で保存
- 結果をZIP形式でアーカイブ

### 3. クエリ分析画面

#### パフォーマンス分析

1. アルゴリズムを選択
2. クエリ一覧で個別クエリのSpeedupを確認
3. フィルタリングと並び替えで詳細分析

#### クエリ詳細

- Original CostとRewritten Costの比較
- Speedup Factor（改善率）
- 使用された実体化ビューの一覧
- パフォーマンス評価と推奨事項

### 4. MV Explorer画面

#### 実体化ビュー一覧

- Utility順、Storage順で並び替え
- 最小Utilityでフィルタリング
- 各MVの詳細情報を表示

#### MV詳細分析

- Utility、Storage Size、使用クエリ数
- SQL定義の表示
- 使用しているクエリの一覧

### 5. 設定画面

#### データベース設定

- ホスト、ポート、データベース名、ユーザー名
- タイムアウト設定
- 接続テスト機能

#### パス設定

- 出力ディレクトリ
- クエリディレクトリ
- SQLディレクトリ
- ワークロードディレクトリ

#### UI設定

- テーマ（Light/Dark/Auto）
- グラフスタイル
- プライマリカラー
- デバッグログ、自動保存、キャッシュ設定

## 📁 ディレクトリ構造

```
dashboard/
├── __init__.py
├── app.py                      # メインアプリケーション
├── pages/
│   ├── 1_🏠_Home.py           # ホーム・実験実行
│   ├── 2_📊_Results.py        # 結果分析
│   ├── 3_🔍_Query_Analysis.py # クエリ詳細分析
│   ├── 4_📦_MV_Explorer.py    # MV詳細
│   └── 5_⚙️_Settings.py      # 設定管理
├── components/
│   ├── __init__.py
│   ├── experiment_runner.py   # 実験実行ロジック
│   ├── progress_tracker.py    # 進行状況トラッキング
│   ├── result_loader.py       # 結果読み込み
│   └── visualizations.py      # 可視化コンポーネント
├── styles/
│   └── main.css              # カスタムCSS
└── utils/
    ├── __init__.py
    ├── session_state.py      # セッション状態管理
    ├── data_processor.py     # データ処理
    └── file_manager.py       # ファイル管理
```

## 🎨 カスタマイズ

### テーマのカスタマイズ

`.streamlit/config.toml`を編集:

```toml
[theme]
primaryColor = "#667eea"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

### CSSのカスタマイズ

`dashboard/styles/main.css`を編集してスタイルを変更できます。

## 🔧 トラブルシューティング

### ダッシュボードが起動しない

```bash
# Streamlitが正しくインストールされているか確認
pip show streamlit

# 再インストール
pip install --upgrade streamlit
```

### ポートが使用中

```bash
# 別のポートを指定
streamlit run dashboard/app.py --server.port 8502
```

### 実験結果が表示されない

1. `Output/`ディレクトリに結果ファイルがあるか確認
2. 設定画面で正しいOutput Directoryが設定されているか確認
3. 少なくとも1つの実験が完了しているか確認

### データベース接続エラー

1. PostgreSQLが起動しているか確認
2. 設定画面で接続情報を確認
3. 「🔗 Test Database Connection」で接続テスト

## 📊 パフォーマンス

### 推奨環境

- CPU: 2コア以上
- RAM: 4GB以上
- ブラウザ: Chrome, Firefox, Safari（最新版）

### 大規模データセット

100以上のクエリや多数のMVを扱う場合:
- ページング機能を活用
- フィルタリングで表示データを制限
- 必要に応じてデータをエクスポートして分析

## 🐛 既知の問題

- 実験実行中にブラウザをリロードするとセッション情報が失われる
- 大量のログ出力時にUIが一時的に重くなる場合がある
- 一部のブラウザで日本語表示に問題がある可能性

## 🤝 コントリビューション

改善提案やバグレポートは歓迎します:
1. Issueを作成
2. フォークしてプルリクエスト

## 📝 ライセンス

このダッシュボードはmv-query-optimizationプロジェクトの一部です。

## 📞 サポート

問題が発生した場合:
1. このREADMEのトラブルシューティングセクションを確認
2. GitHubでIssueを作成
3. プロジェクトのドキュメントを参照

## 🎉 更新履歴

### v1.0.0 (2025-11-18)
- 初回リリース
- 基本的な実験実行・結果分析機能
- 5つのメインページ実装
- リアルタイム進行状況表示
- 包括的な可視化機能

---

**Built with ❤️ using Streamlit**
