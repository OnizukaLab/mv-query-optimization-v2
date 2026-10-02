# フェーズ制御の使い方

実験の実行フェーズを細かく制御する方法を説明します。

## フェーズ一覧

実験は以下の5つのフェーズに分かれています：

1. **query_parsing** - クエリパース（EXPLAIN JSONの解析）
2. **optimization** - MV選択（ILP最適化）
3. **mv_creation** - MV作成（データベース）
4. **query_rewriting** - クエリ書き換え
5. **benchmark** - ベンチマーク実行（性能測定）

## 制御方法

### 方法1: YAML設定ファイル（推奨）

`config/default.yaml`または独自の設定ファイルでフェーズを制御できます。

#### 個別フェーズの有効/無効

```yaml
execution:
  phases:
    query_parsing: true
    optimization: true
    mv_creation: false     # MV作成をスキップ
    query_rewriting: true
    benchmark: false       # ベンチマークをスキップ
```

#### 範囲指定（start_from / end_at）

```yaml
execution:
  start_from: optimization    # 最適化から開始
  end_at: query_rewriting     # クエリ書き換えで終了
```

#### カスタム設定ファイルの使用

```bash
# カスタム設定ファイルを作成
cat > config/my_experiment.yaml << 'EOF'
execution:
  phases:
    query_parsing: false    # 既にパース済み
    optimization: true
    mv_creation: true
    query_rewriting: true
    benchmark: false

optimization:
  storage_limit_mb: 100     # 100MBに増量
EOF

# 実行時に指定
python scripts/run_experiment.py \
  --algorithms normal \
  --config config/my_experiment.yaml
```

### 方法2: コマンドラインオプション

#### --phases オプション（実行するフェーズを明示）

```bash
# 特定のフェーズのみ実行
python scripts/run_experiment.py \
  --algorithms normal \
  --phases optimization mv_creation

# 最適化とMV作成のみ実行（パースは既存キャッシュを使用）
python scripts/run_experiment.py \
  --algorithms normal \
  --phases optimization mv_creation query_rewriting
```

#### --start-from / --end-at オプション（範囲指定）

```bash
# 最適化から開始してクエリ書き換えで終了
python scripts/run_experiment.py \
  --algorithms normal \
  --start-from optimization \
  --end-at query_rewriting

# MV作成以降を実行
python scripts/run_experiment.py \
  --algorithms normal \
  --start-from mv_creation
```

#### レガシーオプション（後方互換性）

```bash
# 旧式（非推奨だが動作する）
python scripts/run_experiment.py \
  --algorithms normal \
  --skip-mv-creation \
  --skip-benchmark
```

## ユースケース別の実行例

### ケース1: 初回実行（全フェーズ）

```bash
# デフォルト設定で全フェーズを実行
python scripts/run_experiment.py --algorithms normal
```

### ケース2: クエリパースのみ（結果をキャッシュ）

```bash
# パースだけ実行してqp_class.pklを生成
python scripts/run_experiment.py \
  --algorithms normal \
  --phases query_parsing
```

### ケース3: 最適化とMV作成のみ

```bash
# パース結果を再利用して最適化とMV作成
python scripts/run_experiment.py \
  --algorithms normal bigsubs \
  --phases optimization mv_creation
```

### ケース4: クエリ書き換えとベンチマークのみ

```bash
# MVは既に作成済み、書き換えとベンチマークのみ実行
python scripts/run_experiment.py \
  --algorithms normal \
  --start-from query_rewriting
```

### ケース5: MV作成をスキップ（デバッグ用）

```bash
# 最適化とクエリ書き換えのみ（MV作成なし）
python scripts/run_experiment.py \
  --algorithms normal \
  --phases optimization query_rewriting
```

### ケース6: 複数アルゴリズムで異なる設定

```yaml
# config/fast_test.yaml
execution:
  phases:
    query_parsing: false     # キャッシュ使用
    optimization: true
    mv_creation: true
    query_rewriting: true
    benchmark: false         # ベンチマークスキップ

optimization:
  storage_limit_mb: 30      # 制限を厳しく
```

```bash
python scripts/run_experiment.py \
  --algorithms normal bigsubs utility \
  --config config/fast_test.yaml
```

## フェーズの依存関係

各フェーズには以下の依存関係があります：

```
query_parsing (必須: なし)
    ↓
optimization (必須: query_parsing の結果)
    ↓
mv_creation (必須: optimization の結果)
    ↓
query_rewriting (必須: optimization の結果、推奨: mv_creation)
    ↓
benchmark (必須: query_rewriting の結果)
```

### 注意点

- **query_parsing** をスキップする場合、`Output/qp_class.pkl` が必要
- **optimization** をスキップする場合、最適化結果の読み込み機能が必要（未実装）
- **mv_creation** をスキップしても **query_rewriting** は可能（テスト用）
- **benchmark** は **query_rewriting** の結果が必要

## 実行フェーズの確認

実行前に以下のような表示でフェーズの状態が確認できます：

```
============================================================
MV Query Optimization Experiment
============================================================
Algorithms: normal, bigsubs
Output: Output
Storage Limit: 50.00 MB
Execution Phases:
  ✓ query_parsing
  ✓ optimization
  ✗ mv_creation
  ✓ query_rewriting
  ✗ benchmark
============================================================
```

## 環境変数での制御（将来的な拡張）

将来的には環境変数でも制御可能にする予定：

```bash
export EXEC_PHASES="optimization,mv_creation,query_rewriting"
python scripts/run_experiment.py --algorithms normal
```

## トラブルシューティング

### エラー: "Query parser cache not found!"

**原因**: `query_parsing` フェーズをスキップしたが、キャッシュファイル `Output/qp_class.pkl` が存在しない

**解決策**:
```bash
# まずパースを実行
python scripts/run_experiment.py --phases query_parsing --algorithms normal

# その後、他のフェーズを実行
python scripts/run_experiment.py --start-from optimization --algorithms normal
```

### 警告: "Loading optimization results not yet implemented"

**原因**: `optimization` フェーズをスキップしたが、結果読み込み機能が未実装

**解決策**: 現時点では `optimization` フェーズは必須です

---

**作成日**: 2025年10月8日  
**バージョン**: 1.0
