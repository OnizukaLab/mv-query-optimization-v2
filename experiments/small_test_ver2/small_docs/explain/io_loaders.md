# load

### `load_timesteps_and_frequencies(base_dir: str) -> Tuple[List[str], Dict[str, List[float]]]`

#### **目的**
- `frequency_time_dependent.json` ファイルからタイムステップ名とクエリ頻度を抽出する。
- 時刻変化ワークロードの最適化で、各タイムステップごとのクエリ実行頻度を取得するために使用。

#### **引数**
- `base_dir: str`: ベースディレクトリ（例: small_test_ver2）。この配下の `01_queries/frequency_time_dependent.json` を読み込む。

#### **戻り値**
- `Tuple[List[str], Dict[str, List[float]]]`: 2つの要素のタプル
  - 第1要素: タイムステップ名のリスト（例: `["0", "1"]`）
  - 第2要素: タイムステップ名をキーとした辞書。各値はクエリ頻度のリスト（例: `{"0": [500, 5, 100, ...], "1": [5, 700, 200, ...]}`）

#### **処理の詳細**
1. **ファイル読み込み**: `base_dir/01_queries/frequency_time_dependent.json` を開き、JSONデータをロード。
2. **タイムステップ抽出**: JSONの `"timesteps"` 配列から各エントリの `"time_id"` を取得し、リストに追加。
3. **頻度抽出**: 各タイムステップの `"frequencies"` 辞書からクエリファイル名（`query1.json` など）を数値順にソート。
4. **リスト作成**: ソートされたクエリファイルごとに頻度を取得（デフォルト1.0）。リストとして保存。
5. **デフォルト処理**: ファイルが存在しない場合やデータが空の場合、デフォルト値（`["t0", "t1"]` と各1.0の頻度）を返す。

#### **重要なポイント**
- **ソート**: クエリファイル名を `query1.json` → `query2.json` の順にソートして一貫性を確保。
- **デフォルト値**: ファイルが見つからない場合や頻度が未定義の場合、警告ログを出力し、デフォルト値を使用。
- **使用例**: このメソッドの戻り値は `TimeDependentOptimizer` の初期化でクエリ頻度として渡される。
- **依存関係**: `frequency_time_dependent.json` の構造に依存（`"timesteps"` 配列、各エントリの `"time_id"` と `"frequencies"`）。

# parse_migration_costs

以下は、`parse_migration_costs` メソッドの行レベルでの詳細な解説です。コードの各行（または論理的なブロック）を順に説明し、目的、処理内容、重要なポイントを記載します。行番号はメソッドの開始（`def parse_migration_costs`）を1行目としてカウントします。

### メソッド全体の概要
- **目的**: `migration_costs.json` を読み込み、MV（マテリアライズドビュー）ごとのレシピ（依存関係とコスト）をインデックスベースの辞書形式に変換。
- **入力**: JSONファイルのパスとノードIDリスト。
- **出力**: MVインデックスをキーとしたレシピリストの辞書。
- **依存**: `ast.literal_eval` でJSONキーをパース、`logging` でデバッグ出力。

```python
def parse_migration_costs(
    path: str, node_list: List[str]
) -> Dict[int, List[Tuple[Tuple[int, ...], float]]]:
    """
    Parse migration_costs.json into recipe format.

    Args:
        path: Path to migration_costs.json
        node_list: List of node IDs (from qp_class)

    Returns:
        Dictionary mapping j (MV index) to list of (recipe_tuple, cost)
        where recipe_tuple is a tuple of dependency indices.
    """
```
- **行1-3**: 関数定義。引数 `path`（ファイルパス）と `node_list`（ノードIDリスト）、戻り値の型ヒント。
- **行4-12**: ドキュメント文字列（docstring）。メソッドの説明、引数、戻り値の詳細を記述。Sphinxスタイルでフォーマット。

```python
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
```
- **行13-14**: JSONファイルを読み込み。`path` のファイルをUTF-8エンコーディングで開き、`json.load` で辞書形式にロード。`raw` はJSONの生データ（例: `{"leaf_1": {"[]": 1.62, "['leaf_1']": 0.0}, ...}`）。

```python
    idx = {node_id: j for j, node_id in enumerate(node_list)}
```
- **行15**: インデックスマップ作成。`node_list` の各ノードIDをインデックス（0, 1, 2, ...）にマッピングした辞書を作成（例: `{"leaf_1": 0, "non_leaf_1": 18, ...}`）。これでノードIDを数値インデックスに変換可能。

```python
    mig: Dict[int, List[Tuple[Tuple[int, ...], float]]] = {}
```
- **行16**: 結果辞書の初期化。MVインデックスをキー、レシピリストを値とする辞書。レシピは `(依存インデックスタプル, コスト)` のタプルリスト。

```python
    for node_id, mapping in raw.items():
```
- **行17**: JSONの各エントリをループ。`node_id` はMVノードID（例: `"leaf_1"`）、`mapping` はそのレシピ辞書（例: `{"[]": 1.62, "['leaf_1']": 0.0}`）。

```python
        j = idx.get(node_id)
        if j is None:
            logger.debug(f"Node {node_id} not found in node_list, skipping")
            continue
```
- **行18-21**: ノードIDをインデックスに変換。`idx.get(node_id)` でインデックスを取得。見つからない場合、デバッグログを出力して次のノードへスキップ（`node_list` にないノードは無視）。

```python
        recipes: List[Tuple[Tuple[int, ...], float]] = []
```
- **行22**: レシピリストの初期化。このMVの全レシピを格納するリスト。

```python
        for k_str, cost in mapping.items():
```
- **行23**: レシピ辞書の各エントリをループ。`k_str` はレシピキー（例: `"['leaf_1']"`）、`cost` はコスト値（例: `0.0`）。

```python
            try:
                ids = ast.literal_eval(k_str)
                if not isinstance(ids, list):
                    ids = []
            except Exception:
                ids = []
```
- **行24-29**: レシピキーをパース。`ast.literal_eval` で文字列をPythonオブジェクトに変換（例: `"['leaf_1']"` → `['leaf_1']`）。リストでない場合やパース失敗時は空リストにフォールバック。安全なエラーハンドリング。

```python
            dep_indices: List[int] = []
            for dep_node_id in ids:
                dep_j = idx.get(dep_node_id)
                if dep_j is not None:
                    dep_indices.append(dep_j)
```
- **行30-34**: 依存ノードをインデックスに変換。`ids` の各依存ノードIDを `idx` でインデックスに変換。見つからない依存はスキップ（`dep_j is None` の場合）。

```python
            recipes.append((tuple(sorted(dep_indices)), float(cost)))
```
- **行35**: レシピを追加。依存インデックスのタプル（ソート済み）とコストをタプルとして `recipes` に追加（例: `((0,), 0.0)`）。

```python
        # Add fallback empty recipe (full build) if not present
        if not any(len(r[0]) == 0 for r in recipes):
            logger.warning(f"Node {node_id} has no full-build recipe (empty list), adding with inf cost")
            recipes.append((tuple(), float("inf")))
```
- **行36-39**: フォールバックレシピの追加。空レシピ（フルビルド、`()`）が存在しない場合、無限大コストで追加。警告ログを出力。

```python
        mig[j] = recipes
```
- **行40**: 結果辞書に格納。MVインデックス `j` をキーとして `recipes` を値に設定。

```python
    return mig
```
- **行41**: 最終結果を返す。すべてのMVのレシピ辞書。

### 重要なポイント（全体）
- **エラーハンドリング**: `ast.literal_eval` の例外や未知ノードをログで処理し、堅牢性確保。
- **データ変換**: 文字列ベースのJSONをインデックスベースの辞書に変換。ソートで一貫性を維持。
- **フォールバック**: フルビルドレシピがない場合の自動追加（コスト無限大で生成を抑止）。
- **パフォーマンス**: ループが多いが、ノード数が数十程度なので問題なし。
- **使用例**: `mig[0] = [((0,), 0.0), ((), 1.62)]`（leaf_1のレシピ: 自己依存コスト0、フルビルドコスト1.62）。