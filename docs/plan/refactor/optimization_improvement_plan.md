# マテリアライズドビュー最適化の改善計画

## 📅 作成日: 2025年11月17日

## 🔍 現状の問題分析

### 実験結果サマリー

2025年11月13日に実施したBigSubsとFrequencyの比較実験から、以下の重要な問題が明らかになった。

#### 定量的結果

| 指標 | BigSubs | Frequency | 差分 |
|------|---------|-----------|------|
| **選択されたMV数** | 115個 | 167個 | +52個 (45%増) |
| **総ストレージ使用量** | 17.64 MB | 25.51 MB | +7.87 MB (45%増) |
| **総ユーティリティ** | 1,786,864 | 2,653,498 | +866,634 (48%増) |
| **ワークロード実行時間** | **45.28秒** | **67.81秒** | **+22.53秒 (50%増)** |
| **平均クエリ実行時間** | **0.40秒** | **0.60秒** | **+0.20秒 (50%増)** |

### 発見された主要な問題

#### 1. 理論値と実測値の乖離

- **期待**: Frequencyはより高いユーティリティ（2,653,498）を獲得しているため、より高速に実行されるはず
- **現実**: BigSubsの方が33%高速（45.28秒 vs 67.81秒）
- **原因**: ILP最適化時にPostgreSQLのEXPLAINで取得したコストを使用しているが、実際にMVを使用してクエリを書き換えると実行プランが変化するため、最適化時のコスト見積もりと実際の実行コストが乖離する

#### 2. MV使用によるクエリ実行プランの変化

MVを使用するようにクエリを書き換えると、PostgreSQLのクエリオプティマイザが異なる実行プランを選択する。これにより、以下の問題が発生：

- **Index Scanの問題**: 元のクエリでindex scanを使用していても、MVにはindexが存在しないため、MVを使用すると別のjoin戦略（hash joinやseq scan）が選ばれる
- **Join順序の変更**: MVの統計情報に基づいて、オプティマイザが異なるjoin順序を選択
- **Nested Loopの利用不可**: MVにindexがないため、nested loop joinが使えなくなる

#### 3. MVが多すぎることによるオプティマイザの混乱

Frequencyで極端に遅くなったクエリの例：

| クエリID | BigSubs実行時間 | Frequency実行時間 | 悪化率 |
|---------|----------------|-------------------|--------|
| 21a | 0.03秒 | 9.61秒 | **320倍** |
| 26c | 0.89秒 | 11.28秒 | **13倍** |
| 27a | 0.04秒 | 4.88秒 | **122倍** |
| 27c | 0.08秒 | 7.09秒 | **89倍** |

**原因分析**:
- 167個のMVが存在すると、PostgreSQLオプティマイザが考慮すべき実行プランの候補が爆発的に増加
- より多くのMV選択肢があることで、オプティマイザが最適でないプランを選択する可能性が高まる
- 統計情報の精度が低いMVが混在すると、コスト見積もりが不正確になる

#### 4. MVの品質よりも量を優先してしまう問題

- **BigSubs**: 115個の厳選されたMVで効率的にカバー
- **Frequency**: 167個のMVを選択するが、中には実際の性能向上に寄与しないMVも含まれる

### 根本原因の特定

1. **最適化フェーズと実行フェーズの乖離**
   - ILP最適化で使用するコスト（`m_cost`, `u_ij`）はPostgreSQLのEXPLAINから取得している
   - しかし、最適化時のコスト取得では元のクエリ（MVを使わない状態）でEXPLAINを実行している
   - 実際にMVを使用してクエリを書き換えると、PostgreSQLオプティマイザが異なる実行プランを選択する
   - この実行プランの変化により、最適化時のコスト見積もりと実際の実行コストが大きく乖離する

2. **MV選択基準の単純さ**
   - 現在は「ユーティリティ最大化」のみを目標としている
   - MVの数、実行プランの安定性、オプティマイザへの影響などを考慮していない

3. **フィードバックループの欠如**
   - 選択したMVが実際にどのようなパフォーマンスをもたらすかの検証がない
   - 悪影響を与えるMVを特定・除外する仕組みがない

---

## 💡 改善提案

### 提案1: PostgreSQLヒント句による実行プラン制御

#### 概要
クエリ書き換え時にPostgreSQLのヒント句（`pg_hint_plan`拡張を使用）を追加し、実行プランを制御する。

#### メリット
- ✅ 既存のアーキテクチャに統合しやすい
- ✅ 開発工数が比較的少ない（2-3週間程度）
- ✅ 即座に効果を検証できる
- ✅ PostgreSQLの既存機能を活用

#### デメリット
- ❌ PostgreSQLはヒント句のサポートが限定的（拡張が必要）
- ❌ ヒント句は本質的な解決ではなく「パッチ」
- ❌ 他のDBMSへの移植性が低い
- ❌ Index scanの問題（indexが存在しないMV）は根本的に解決できない

#### 実装イメージ
```python
class HintInjector:
    def inject_hints(self, query, mvs, execution_plan):
        """MVを使用する際の最適なヒント句を生成"""
        hints = []
        
        # MVにはindexがないのでSeqScanを推奨
        for mv in mvs:
            hints.append(f"SeqScan({mv.view_id})")
        
        # Join戦略の指定
        if self._should_use_hash_join(execution_plan):
            hints.append("HashJoin(t1 t2)")
        
        hint_str = " ".join(hints)
        return f"/*+ {hint_str} */\n{query}"
```

#### 実装ステップ
1. `pg_hint_plan`拡張のインストール確認（Docker環境への追加）
2. ヒント句生成モジュールの作成（`src/rewrite/hint_injector.py`）
3. QueryRewriterへの統合
4. 実験実行と効果測定（BigSubs/Frequency両方で）
5. 結果の分析と文書化

#### 期待される効果
- ワークロード実行時間: 20-30%改善
- 特に悪化していたクエリ（21a, 26c, 27a, 27c）の改善

---

### 提案2: Wvlet論理プランベースの最適化

#### 概要
Wvletクエリエンジンを使用してクエリを論理プランレベルでパースし、論理プランのサブクエリから実体化ビュー候補を抽出する。

#### メリット
- ✅ 本質的な解決策：論理プランレベルで最適化
- ✅ Index scan問題を回避できる（論理プランにはindexの情報がない）
- ✅ 他のクエリエンジンへの拡張性が高い
- ✅ より正確なコスト見積もりが可能
- ✅ 研究としての新規性・価値が非常に高い

#### デメリット
- ❌ 開発工数が大きい（2-3ヶ月程度）
- ❌ Wvletの学習コストが必要
- ❌ PostgreSQLへのEXPLAINリクエストのオーバーヘッド
- ❌ アーキテクチャの大幅な変更が必要

#### アーキテクチャ
```
Query → Wvlet Parser → Logical Plan 
  → Subquery Extraction (論理プラン断片)
  → SQL Generation (各断片をSQLに変換)
  → PostgreSQL EXPLAIN (実際のコストを取得)
  → ILP Optimization (コスト付き論理プランで最適化)
  → MV Selection → Query Rewrite
```

#### 実装イメージ
```python
class WvletBasedOptimizer:
    def __init__(self):
        self.wvlet_parser = WvletParser()
        self.cost_estimator = PostgreSQLCostEstimator()
    
    def extract_mv_candidates(self, queries):
        """論理プランからMV候補を抽出"""
        candidates = []
        
        for query in queries:
            # Wvletで論理プランを取得
            logical_plan = self.wvlet_parser.parse(query)
            
            # 論理プランのサブツリーを列挙
            for subplan in self._enumerate_subplans(logical_plan):
                # サブプランをSQLに変換
                sql = self._logical_plan_to_sql(subplan)
                
                # PostgreSQLで実際のコストを取得
                cost = self.cost_estimator.get_cost(sql)
                
                candidates.append({
                    'logical_plan': subplan,
                    'sql': sql,
                    'cost': cost
                })
        
        return candidates
```

#### 実装ステップ
1. Wvletの調査と環境構築
2. 論理プランパーサーの実装
3. 論理プラン→SQL変換器の実装
4. PostgreSQL EXPLAIN統合
5. ILP最適化の再設計（論理プラン対応）
6. 実験と評価

#### 期待される効果
- Index scan問題の完全な解決
- より正確なコスト見積もり
- 研究論文としての価値が大幅に向上

---

### 提案3: ハイブリッド最適化フレームワーク

#### 概要
2段階の最適化を行う。第1段階でILPによる粗い最適化、第2段階で実際の実行コストに基づくファインチューニングを実施。

#### メリット
- ✅ 理論値と実測値のギャップを埋める
- ✅ PostgreSQLオプティマイザの実際の振る舞いを考慮
- ✅ 既存アーキテクチャの拡張で実装可能
- ✅ 段階的な改善が可能

#### デメリット
- ❌ 実行時間が増加（サンプリング戦略で軽減可能）
- ❌ 実装が複雑

#### アーキテクチャ
```
Stage 1 (ILP最適化):
  Query Parsing → MV Candidate Generation 
  → ILP (粗い選択, budget * 1.5) → Candidate MVs (150-200個)

Stage 2 (実行ベース絞り込み):
  Candidate MVs → MV Creation (試験的)
  → Sample Query Execution (代表クエリで実測)
  → Performance Evaluation
  → Greedy Refinement (悪影響のあるMVを除外)
  → Final MV Set (100-120個)
```

#### 実装イメージ
```python
class HybridOptimizer:
    def optimize(self, queries, budget):
        # Stage 1: ILP-based coarse selection
        candidate_mvs = self.ilp_optimizer.select_mvs(
            queries=queries,
            budget=budget * 1.5  # 余裕を持って多めに選択
        )
        
        print(f"Stage 1: Selected {len(candidate_mvs)} candidate MVs")
        
        # Stage 2: Execution-based refinement
        best_mvs = self._refine_by_execution(
            candidate_mvs=candidate_mvs,
            queries=queries,
            target_budget=budget
        )
        
        return best_mvs
    
    def _refine_by_execution(self, candidate_mvs, queries, target_budget):
        """実際の実行コストでMVを絞り込む"""
        # サンプルクエリを選択（全体の20%程度）
        sample_queries = self._select_sample_queries(queries, ratio=0.2)
        
        current_mvs = set(candidate_mvs)
        current_storage = sum(mv.size for mv in current_mvs)
        
        # MVを1つずつ除外して性能を評価（Greedy）
        while current_storage > target_budget:
            best_candidate = None
            best_improvement = 0
            
            for mv in current_mvs:
                # MVを除外した場合の性能を評価
                test_set = current_mvs - {mv}
                performance = self._measure_performance(test_set, sample_queries)
                
                # 除外しても性能が落ちない、または改善する場合
                if performance >= 0:
                    improvement = performance + mv.size  # ストレージも考慮
                    if improvement > best_improvement:
                        best_candidate = mv
                        best_improvement = improvement
            
            if best_candidate:
                current_mvs.remove(best_candidate)
                current_storage -= best_candidate.size
                print(f"Removed {best_candidate.view_id}, improvement: {best_improvement}")
            else:
                break
        
        return list(current_mvs)
    
    def _measure_performance(self, mvs, queries):
        """実際にMVを作成してクエリを実行し、性能を測定"""
        # テスト用のMVを作成
        self.mv_manager.create_views_temporary(mvs)
        
        total_time = 0
        for query in queries:
            # クエリを書き換えてMVを使用
            rewritten = self.rewriter.rewrite(query, mvs)
            
            # 実行時間を測定（EXPLAIN ANALYZEを使用）
            exec_time = self.executor.measure_execution_time(rewritten)
            total_time += exec_time
        
        # テスト用MVをクリーンアップ
        self.mv_manager.drop_views_temporary(mvs)
        
        return -total_time  # 小さいほど良いので負の値
```

#### 実装ステップ
1. サンプルクエリ選択ロジックの実装
2. 一時的なMV作成・削除機能の追加
3. 実行時間測定機能の追加
4. Greedy refinementアルゴリズムの実装
5. 実験と効果測定

#### 期待される効果
- ワークロード実行時間: 50-60%改善
- Frequencyでも良好な結果が得られる可能性

---

### 提案4: コスト推定モデルの機械学習化

#### 概要
PostgreSQLの実際の振る舞いを機械学習モデルで学習し、より正確なコスト推定を行う。

#### メリット
- ✅ PostgreSQLの実際の振る舞いを正確に反映
- ✅ Index scanなどの複雑な最適化も学習可能
- ✅ 研究としての新規性が非常に高い
- ✅ 長期的には最も高精度

#### デメリット
- ❌ 学習データの収集が必要（数千～数万のクエリ実行が必要）
- ❌ 実装コストが高い（2-3ヶ月）
- ❌ モデルの説明可能性が低い

#### アーキテクチャ
```
Historical Data Collection:
  Queries → Execute with various MV sets 
  → Record (query features, MV features, actual execution time)

Model Training:
  Feature Engineering (join数, selectivity, MV数, MV特性, etc.)
  → Gradient Boosting / Neural Network
  → Trained Cost Model

Optimization:
  Query → Extract Features → ML Cost Prediction
  → ILP with Learned Cost → Optimal MVs
```

#### 実装イメージ
```python
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

class LearnedCostEstimator:
    def __init__(self):
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=10,
            learning_rate=0.1
        )
        self.scaler = StandardScaler()
        self.is_trained = False
    
    def collect_training_data(self, queries, mv_candidates):
        """学習データを収集"""
        training_data = []
        
        for query in queries:
            # 様々なMVサブセットで実行
            for mv_subset in self._sample_mv_subsets(mv_candidates):
                features = self._extract_features(query, mv_subset)
                
                # 実際に実行して時間を測定
                actual_time = self._execute_and_measure(query, mv_subset)
                
                training_data.append({
                    'features': features,
                    'actual_time': actual_time
                })
        
        return training_data
    
    def _extract_features(self, query, mvs):
        """クエリとMVから特徴量を抽出"""
        features = []
        
        # クエリの特徴
        features.extend([
            len(query.tables),           # テーブル数
            len(query.joins),             # JOIN数
            query.selectivity,            # 選択率
            query.has_aggregation,        # 集約の有無
            query.has_subquery,           # サブクエリの有無
        ])
        
        # MVの特徴
        features.extend([
            len(mvs),                     # 使用MV数
            sum(mv.size for mv in mvs),   # 総ストレージ
            np.mean([mv.size for mv in mvs]) if mvs else 0,  # 平均サイズ
        ])
        
        # クエリとMVの関係性
        features.extend([
            self._calc_coverage(query, mvs),  # MVがカバーする範囲
            self._calc_overlap(mvs),          # MV間の重複度
        ])
        
        return np.array(features)
    
    def train(self, training_data):
        """モデルを学習"""
        X = np.array([d['features'] for d in training_data])
        y = np.array([d['actual_time'] for d in training_data])
        
        # 特徴量の正規化
        X_scaled = self.scaler.fit_transform(X)
        
        # モデル学習
        self.model.fit(X_scaled, y)
        self.is_trained = True
        
        print(f"Model trained on {len(training_data)} samples")
        print(f"Feature importance: {self.model.feature_importances_}")
    
    def predict_cost(self, query, mvs):
        """実行コストを予測"""
        if not self.is_trained:
            raise ValueError("Model not trained yet")
        
        features = self._extract_features(query, mvs)
        features_scaled = self.scaler.transform(features.reshape(1, -1))
        
        predicted_time = self.model.predict(features_scaled)[0]
        return predicted_time
```

#### 実装ステップ
1. 学習データ収集基盤の構築
2. 特徴量エンジニアリングの設計
3. モデルの選定と実装（GB, XGBoost, NN等）
4. 学習データの収集（1000-10000サンプル）
5. モデルの学習と評価
6. ILP最適化への統合
7. 実験と評価

#### 期待される効果
- 最も高精度なコスト推定が可能
- ワークロード実行時間: 70%以上の改善が期待できる

---

### 提案5: MV選択の多目的最適化

#### 概要
ユーティリティだけでなく、複数の目標を同時に最適化する（多目的最適化）。

#### 最適化目標
1. **ユーティリティ最大化**: 従来通り（query execution costの削減）
2. **MV数最小化**: オプティマイザの混乱を防ぐ
3. **実行プラン安定性最大化**: MVの組み合わせによる実行プランの変動を最小化
4. **ストレージ効率最大化**: サイズあたりのユーティリティ

#### メリット
- ✅ より現実的で実用的な最適化
- ✅ MVの数を自然に制限できる
- ✅ 実行プランの安定性を考慮できる
- ✅ 研究としての新規性が高い

#### デメリット
- ❌ 最適解の選択が複雑（トレードオフの決定）
- ❌ 計算コストが増加

#### 実装イメージ
```python
class MultiObjectiveOptimizer:
    def optimize(self, queries, budget):
        """Pareto最適解を求める"""
        # すべての実行可能な解を列挙（またはサンプリング）
        solutions = self._enumerate_solutions(queries, budget)
        
        # Pareto frontを計算
        pareto_front = self._compute_pareto_front(solutions)
        
        # トレードオフを考慮して最終解を選択
        best_solution = self._select_best_tradeoff(pareto_front)
        
        return best_solution
    
    def _compute_objectives(self, solution, queries):
        """複数の目標を計算"""
        mvs = solution.selected_mvs
        
        objectives = {
            # 目標1: ユーティリティ最大化（最大化）
            'utility': self._calc_utility(mvs, queries),
            
            # 目標2: MV数最小化（最小化→負の値で最大化に変換）
            'num_mvs': -len(mvs),
            
            # 目標3: 実行プラン安定性（最大化）
            'plan_stability': self._calc_plan_stability(mvs, queries),
            
            # 目標4: ストレージ効率（最大化）
            'storage_efficiency': self._calc_utility(mvs, queries) / sum(mv.size for mv in mvs)
        }
        
        return objectives
    
    def _calc_plan_stability(self, mvs, queries):
        """実行プランの安定性を計算"""
        # 各クエリについて、MVを使った場合と使わない場合の
        # 実行プランの類似度を計算
        stability_scores = []
        
        for query in queries:
            original_plan = self._get_query_plan(query, mvs=[])
            rewritten_plan = self._get_query_plan(query, mvs=mvs)
            
            # プランの類似度（join順序、scan方法などを比較）
            similarity = self._compute_plan_similarity(original_plan, rewritten_plan)
            stability_scores.append(similarity)
        
        return np.mean(stability_scores)
    
    def _compute_pareto_front(self, solutions):
        """Pareto最適解を抽出"""
        pareto_front = []
        
        for solution in solutions:
            is_dominated = False
            
            for other in solutions:
                if self._dominates(other, solution):
                    is_dominated = True
                    break
            
            if not is_dominated:
                pareto_front.append(solution)
        
        return pareto_front
    
    def _dominates(self, sol1, sol2):
        """sol1がsol2を支配するか判定"""
        obj1 = sol1.objectives
        obj2 = sol2.objectives
        
        # すべての目標でsol1 >= sol2 かつ 少なくとも1つでsol1 > sol2
        better_in_all = all(obj1[k] >= obj2[k] for k in obj1.keys())
        better_in_some = any(obj1[k] > obj2[k] for k in obj1.keys())
        
        return better_in_all and better_in_some
    
    def _select_best_tradeoff(self, pareto_front):
        """Pareto frontから最適なトレードオフ解を選択"""
        # 重み付け和で最終スコアを計算
        weights = {
            'utility': 0.5,           # 最重要
            'num_mvs': 0.2,
            'plan_stability': 0.2,
            'storage_efficiency': 0.1
        }
        
        best_solution = None
        best_score = -float('inf')
        
        for solution in pareto_front:
            score = sum(
                weights[k] * solution.objectives[k] 
                for k in weights.keys()
            )
            
            if score > best_score:
                best_score = score
                best_solution = solution
        
        return best_solution
```

#### 実装ステップ
1. 実行プラン安定性の定義と計算方法の設計
2. 多目的最適化フレームワークの実装
3. Pareto front計算の実装
4. トレードオフ選択ロジックの実装
5. 実験と評価

#### 期待される効果
- MVの数を適切に制限しつつ高いユーティリティを達成
- ワークロード実行時間: 50-60%改善

---

### 提案6: Adaptive MV Selection（動的MV選択）

#### 概要
クエリパターンに応じて、使用するMVサブセットを動的に選択する。

#### メリット
- ✅ クエリごとに最適なMVセットを使用
- ✅ 不要なMVによるオプティマイザの混乱を回避
- ✅ より細かい最適化が可能

#### デメリット
- ❌ MVの動的な有効化/無効化が必要（PostgreSQLでは困難）
- ❌ 実装が複雑
- ❌ オーバーヘッドが増加

#### 実装イメージ
```python
class AdaptiveMVSelector:
    def __init__(self):
        self.query_clusters = {}
        self.mv_profiles = {}
    
    def train(self, queries, all_mvs):
        """クエリをクラスタリングし、各クラスタの最適MVプロファイルを作成"""
        # クエリをクラスタリング（k-means等）
        clusters = self._cluster_queries(queries)
        
        for cluster_id, cluster_queries in clusters.items():
            # このクラスタに最適なMVサブセットを選択
            optimal_mvs = self._optimize_for_cluster(cluster_queries, all_mvs)
            self.mv_profiles[cluster_id] = optimal_mvs
    
    def select_mvs_for_query(self, query, all_mvs):
        """クエリに応じて最適なMVサブセットを選択"""
        cluster = self._classify_query(query)
        return self.mv_profiles.get(cluster, all_mvs)
```

#### 期待される効果
- クエリごとの最適化により、全体的な性能向上

---

### 提案7: Negative MV Optimization（逆説的アプローチ）

#### 概要
どのMVを選ぶかではなく、どのMVを除外すべきかを学習する。

#### メリット
- ✅ 有害なMVを特定・除外できる
- ✅ 実際のパフォーマンスに基づく選択
- ✅ 実装が比較的簡単

#### デメリット
- ❌ 多数の実行テストが必要

#### 実装イメージ
```python
class NegativeMVOptimizer:
    def optimize(self, candidate_mvs, queries):
        """悪影響を与えるMVを除外"""
        current_mvs = set(candidate_mvs)
        baseline_performance = self._measure_performance(current_mvs, queries)
        
        improved = True
        while improved:
            improved = False
            best_removal = None
            best_improvement = 0
            
            for mv in current_mvs:
                test_set = current_mvs - {mv}
                performance = self._measure_performance(test_set, queries)
                
                improvement = performance - baseline_performance
                if improvement > best_improvement:
                    best_removal = mv
                    best_improvement = improvement
            
            if best_removal:
                current_mvs.remove(best_removal)
                baseline_performance += best_improvement
                improved = True
                print(f"Removed {best_removal.view_id}, improvement: {best_improvement}")
        
        return list(current_mvs)
```

#### 期待される効果
- ワークロード実行時間: 40-50%改善
- Frequencyで選択された167個のMVから有害なものを除外

---

### 提案8: Query Rewrite Validator（書き換え検証）

#### 概要
MVを使った書き換えが本当に有益かを事前に検証し、悪化する場合は書き換えをスキップする。

#### メリット
- ✅ 実装が最も簡単（1週間程度）
- ✅ 即座に効果を確認できる
- ✅ リスクが最小
- ✅ 悪化するクエリを確実に防げる

#### デメリット
- ❌ 根本的な解決ではない
- ❌ EXPLAINのオーバーヘッド

---

### 提案9: MV Index Propagation（インデックス伝播）

#### 概要
MVを作成する際に、元のテーブルに存在するインデックスを自動的にMVにも作成する。これによりオプティマイザの実行プラン選択を安定化させる。

#### 背景と動機
現在の問題の根本原因は、MVを使った書き換え後に実行プランが変化することです。元のテーブルには多数のインデックスが存在しますが、MVには存在しないため、オプティマイザは異なるプラン（特にSeq ScanやHash Joinへの切り替え）を選択してしまいます。

```sql
-- 元のテーブル（インデックスあり）
SELECT * FROM movie_companies mc
JOIN title t ON mc.movie_id = t.id
-- → Index Scan on movie_id_movie_companies (高速)

-- MV使用後（インデックスなし）
SELECT * FROM mv_123
-- → Seq Scan on mv_123 (低速)
```

#### メリット
- ✅ 実装が比較的簡単（1-2週間）
- ✅ 実行プランの安定性向上
- ✅ Join操作の大幅な高速化
- ✅ 推定コストと実測の乖離を縮小
- ✅ 既存のコードへの影響が小さい

#### デメリット
- ❌ ストレージ使用量が20-50%増加
- ❌ MV作成時間が増加（数秒～数分/MV）
- ❌ すべてのインデックスが有効とは限らない
- ❌ 複合インデックスの判定が難しい

#### 実装イメージ
```python
class RewriteValidator:
    def __init__(self, db_connection):
        self.db = db_connection
        self.threshold = 1.1  # 10%以上悪化する場合は書き換えをスキップ
    
    def validate_and_rewrite(self, original_query, rewritten_query, mvs):
        """書き換えが有益かを検証"""
        # 元のクエリのコストを取得
        original_cost = self._get_explain_cost(original_query)
        
        # 書き換え後のクエリのコストを取得
        rewritten_cost = self._get_explain_cost(rewritten_query)
        
        # コストを比較
        if rewritten_cost > original_cost * self.threshold:
            print(f"Rewrite rejected: cost increased from {original_cost} to {rewritten_cost}")
            return original_query, False
        else:
            print(f"Rewrite accepted: cost decreased from {original_cost} to {rewritten_cost}")
            return rewritten_query, True
    
    def _get_explain_cost(self, query):
        """EXPLAINでクエリのコストを取得"""
        explain_query = f"EXPLAIN (FORMAT JSON) {query}"
        result = self.db.execute(explain_query)
        plan = result[0][0][0]['Plan']
        return plan['Total Cost']
```

#### 実装ステップ
1. EXPLAIN実行機能の追加（`src/database/connection.py`に追加）
2. RewriteValidatorクラスの作成
3. QueryRewriterへの統合
4. 実験と効果測定

#### 期待される効果
- ワークロード実行時間: 20-30%改善
- 特に悪化していたクエリ（21a, 26c等）の書き換えをスキップ

---

### 提案9: MV Index Propagation（続き）

#### インデックス作成コストの分析

IMDbデータセット（約5000万行）での実測例:
```sql
-- cast_info (36M rows)
CREATE INDEX movie_id_cast_info ON cast_info(movie_id);
-- 作成時間: 約45秒
-- インデックスサイズ: 約770MB

-- movie_info (15M rows)  
CREATE INDEX movie_id_movie_info ON movie_info(movie_id);
-- 作成時間: 約18秒
-- インデックスサイズ: 約323MB
```

**コスト分析:**
- 1つのMVあたり: 平均2-3個のインデックス
- 総インデックス作成時間: 115 MVs × 30秒 = 約1時間
- ストレージ増加: 17.64MB → 約26MB（+50%）
- **トレードオフ:** MV作成時間+1時間 vs 実行時間-30%（毎回の実行で節約）

#### 実装イメージ

```python
class MVIndexPropagator:
    """Propagate indexes from base tables to materialized views."""
    
    def __init__(self, db_connection, schema_provider):
        self.db = db_connection
        self.schema = schema_provider
    
    def get_table_indexes(self, table_name: str) -> list[IndexInfo]:
        """元のテーブルのインデックス情報を取得"""
        sql = """
            SELECT 
                i.relname as index_name,
                array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as columns,
                ix.indisunique as is_unique,
                am.amname as index_type
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = %s
                AND t.relkind = 'r'
                AND NOT ix.indisprimary  -- 主キーは除外
            GROUP BY i.relname, ix.indisunique, am.amname
        """
        results = self.db.fetch_all(sql, (table_name,))
        return [
            IndexInfo(name=r[0], columns=r[1], unique=r[2], type=r[3])
            for r in results
        ]
    
    def extract_mv_columns(self, mv_sql: str) -> set[str]:
        """MVのSELECT句から列名を抽出"""
        # CREATE MATERIALIZED VIEW mv AS SELECT col1, col2, ... FROM ...
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', mv_sql, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return set()
        
        select_clause = select_match.group(1)
        columns = set()
        
        # col AS alias, table.col, col の形式に対応
        for item in select_clause.split(','):
            item = item.strip()
            
            # AS aliasの場合はalias名を使用
            if ' AS ' in item.upper():
                alias = item.split(' AS ')[-1].strip()
                columns.add(alias)
            # table.colの場合はcol名を抽出
            elif '.' in item:
                col = item.split('.')[-1].strip()
                columns.add(col)
            else:
                columns.add(item)
        
        return columns
    
    def create_mv_indexes(self, mv_name: str, mv_sql: str, base_tables: list[str]) -> list[str]:
        """MVに必要なインデックスを作成"""
        mv_columns = self.extract_mv_columns(mv_sql)
        created_indexes = []
        
        for table in base_tables:
            # 元のテーブルのインデックスを取得
            table_indexes = self.get_table_indexes(table)
            
            for idx in table_indexes:
                # MVに同じ列が存在するかチェック
                if all(col in mv_columns for col in idx.columns):
                    # インデックスを作成
                    index_name = f"{mv_name}_{'_'.join(idx.columns)}_idx"
                    columns_str = ', '.join(idx.columns)
                    unique_clause = 'UNIQUE' if idx.unique else ''
                    
                    create_sql = f"""
                        CREATE {unique_clause} INDEX {index_name}
                        ON {mv_name} ({columns_str})
                    """
                    
                    try:
                        self.db.execute(create_sql)
                        created_indexes.append(index_name)
                        logger.info(f"Created index {index_name} on {mv_name}")
                    except Exception as e:
                        logger.warning(f"Failed to create index {index_name}: {e}")
        
        return created_indexes

# MVManagerへの統合
class MaterializedViewManager:
    def create_view_with_indexes(self, view: MaterializedView, base_tables: list[str]) -> bool:
        """インデックス付きでMVを作成"""
        # MV作成
        self.create_view_from_model(view)
        
        # インデックス伝播
        propagator = MVIndexPropagator(self.db, self.schema_provider)
        indexes = propagator.create_mv_indexes(view.view_id, view.create_sql, base_tables)
        
        logger.info(f"Created {len(indexes)} indexes on {view.view_id}")
        return True
```

#### 実装ステップ

1. **Phase 1: インデックス情報収集機能（2-3日）**
   - `MVIndexPropagator`クラスの実装
   - 元テーブルのインデックス情報を取得する機能
   - MVの列情報を解析する機能

2. **Phase 2: インデックス選択ロジック（3-4日）**
   - MVに存在する列のみを対象とする
   - 複合インデックスの処理
   - 主キー/ユニーク制約の扱い

3. **Phase 3: MV作成フローへの統合（2-3日）**
   - `MaterializedViewManager.create_view_with_indexes()`の実装
   - `scripts/run_experiment.py`のPhase 4への統合
   - エラーハンドリングとログ出力

4. **Phase 4: 実験と評価（3-5日）**
   - BigSubsとFrequencyで再実験
   - インデックス有無での性能比較
   - ストレージ使用量とクエリ速度のトレードオフ評価

#### スマートインデックス選択の拡張案

すべてのインデックスを盲目的にコピーするのではなく、有効なものだけを選択:

```python
class SmartIndexPropagator(MVIndexPropagator):
    """スマートにインデックスを選択"""
    
    def should_create_index(self, idx: IndexInfo, mv_sql: str, query_workload: list[str]) -> bool:
        """インデックスを作成すべきか判定"""
        # 1. MVに列が存在しない → スキップ
        mv_columns = self.extract_mv_columns(mv_sql)
        if not all(col in mv_columns for col in idx.columns):
            return False
        
        # 2. ワークロードでJOIN/WHERE条件に使われているか
        used_in_joins = self._is_used_in_joins(idx.columns, query_workload)
        used_in_where = self._is_used_in_where(idx.columns, query_workload)
        
        if not (used_in_joins or used_in_where):
            logger.debug(f"Index {idx.name} not used in workload, skipping")
            return False
        
        # 3. インデックスサイズがMVサイズに対して大きすぎないか
        # （MVが小さい場合、Seq Scanの方が速い可能性）
        estimated_mv_rows = self._estimate_mv_rows(mv_sql)
        if estimated_mv_rows < 10000:  # 1万行未満ならインデックス不要
            logger.debug(f"MV too small ({estimated_mv_rows} rows), index not needed")
            return False
        
        return True
```

#### 期待される効果

**シナリオ1: 全インデックスコピー**
- ワークロード実行時間: 30-40%改善
- ストレージ増加: +50%
- MV作成時間: +60分

**シナリオ2: スマート選択**
- ワークロード実行時間: 25-35%改善
- ストレージ増加: +25%
- MV作成時間: +25分

#### 他の提案との組み合わせ

- **提案8（Rewrite Validator）との併用**: インデックス作成後もValidatorで最終確認
- **提案1（Hint Injection）との比較**: インデックス伝播の方が安定性が高い
- **提案7（Negative MV）との組み合わせ**: インデックス付きMVでも悪化する場合を除外

---

## 🎯 推奨する実装優先順位

### 即効性と実装コストの評価

| 提案 | 実装期間 | 効果予測 | リスク | 研究価値 | 推奨度 |
|-----|---------|---------|-------|---------|--------|
| **8. Rewrite Validator** | 1週間 | 中（20-30%改善） | 低 | 中 | ★★★★★ |
| **7. Negative MV** | 2週間 | 高（40-50%改善） | 中 | 高 | ★★★★☆ |
| **1. ヒント句** | 2週間 | 中（30-40%改善） | 低 | 低 | ★★★★☆ |
| **5. 多目的最適化** | 4週間 | 高（50-60%改善） | 中 | 高 | ★★★★☆ |
| **3. ハイブリッド最適化** | 6週間 | 最高（60-70%改善） | 高 | 最高 | ★★★☆☆ |
| **4. ML Cost** | 8週間 | 最高（70%+改善） | 高 | 最高 | ★★★☆☆ |
| **6. Adaptive MV** | 4週間 | 中（30-40%改善） | 高 | 中 | ★★☆☆☆ |
| **2. Wvlet統合** | 10週間 | 高（50-60%改善） | 高 | 最高 | ★★☆☆☆ |

### フェーズ別実装計画

#### **フェーズ1: クイックウィン（2-3週間）**

**目標**: 即座に効果を確認し、問題の範囲を特定

**提案8: Query Rewrite Validator** [1週間]
- 最も実装が簡単
- 悪化するクエリを確実に防げる
- 効果測定が容易

**提案9: MV Index Propagation** [1-2週間]
- 実行プランの安定化
- Join操作の高速化
- 提案8と相補的な効果

**実装順序**:
```
Week 1: Rewrite Validator
  Day 1-2: EXPLAIN機能の実装とテスト
  Day 3-4: RewriteValidatorクラスの実装
  Day 5-6: QueryRewriterへの統合とテスト
  Day 7: 実験実行と結果分析

Week 2-3: MV Index Propagation
  Day 8-10: MVIndexPropagatorクラスの実装
  Day 11-13: インデックス選択ロジックの実装
  Day 14-15: MV作成フローへの統合
  Day 16-18: 実験と評価（Validator併用 vs Index Propagation vs 両方）
  Day 19-21: 結果分析とドキュメント作成
```

**期待される成果**:
- 21a, 26c, 27a, 27cなどの極端に遅くなるクエリを防ぐ（Validator）
- Join/WHERE条件を含むクエリの高速化（Index Propagation）
- 合計40-50%のワークロード実行時間改善
- 次のステップの判断材料を得る

---

#### **フェーズ2: 中期改善（2-4週間）**

**目標**: より本質的な改善を実施

**オプションA: 提案7（Negative MV） + 提案1（ヒント句）**
- 両方とも実装コストが比較的低い
- 相補的なアプローチ（除外と制御）
- 合計4週間程度

**オプションB: 提案5（多目的最適化）**
- より根本的なアプローチ
- 研究価値が高い
- 4週間程度

**推奨**: オプションA
- 段階的に改善できる
- リスクが分散される
- 両方の効果を論文で示せる

---

#### **フェーズ3: 長期改善（4-12週間, optional）**

**目標**: 最先端の研究成果を目指す

**選択肢**:
1. **提案3: ハイブリッド最適化** [6週間]
   - 理論と実践の統合
   - 高い改善効果が期待できる

2. **提案4: 機械学習ベースのコスト推定** [8週間]
   - 最も野心的
   - 研究としての価値が最も高い
   - 学習データの収集が必要

3. **提案2: Wvlet統合** [10週間]
   - 根本的な問題解決
   - 他のクエリエンジンへの拡張性

**推奨**: 論文の締め切りと研究の方向性に応じて決定
- 締め切りが近い場合: フェーズ2で終了し、論文執筆に集中
- 時間的余裕がある場合: 提案4（ML Cost）に挑戦

---

## 📝 次のアクションステップ

### 即座に実施すべきこと

1. **提案8（Rewrite Validator）と提案9（Index Propagation）の実装開始**
   ```bash
   # ブランチ作成
   git checkout -b feature/phase1-improvements
   
   # 実装ファイル作成
   touch src/rewrite/rewrite_validator.py
   touch src/rewrite/index_propagator.py
   touch tests/test_rewrite_validator.py
   touch tests/test_index_propagator.py
   ```

2. **実装計画の詳細化**
   - 各機能の詳細仕様を決定
   - テストケースの設計
   - 実験計画の策定（3パターン: Validator単独、Index単独、両方併用）

3. **環境の確認**
   - PostgreSQLのEXPLAIN機能の確認
   - 既存のQueryRewriterとの統合ポイントの確認
   - インデックス情報取得クエリのテスト

4. **インデックス作成コストの実測**
   ```sql
   -- サンプルMVでインデックス作成時間を計測
   \timing on
   CREATE INDEX test_idx ON sample_mv(movie_id);
   ```

### 今後の判断ポイント

**Week 1完了後（Rewrite Validator実装）**:
- Rewrite Validatorの効果を測定
- 20-30%の改善が見られた場合 → Index Propagationへ進む
- 改善が小さい場合 → 原因分析とValidator閾値の調整

**Week 3完了後（Index Propagation実装）**:
- インデックス有無での性能比較
- ストレージコストと実行時間のトレードオフ評価
- 40-50%の改善が見られた場合 → フェーズ2の計画を確定
- スマート選択の必要性を判断（全インデックス vs 選択的作成）
- 改善が不十分な場合 → 原因分析とアプローチの再検討

**フェーズ2完了後（4-5週間後）**:
- 累積の改善効果を評価
- 50%以上の改善が達成された場合 → 論文執筆へ
- 改善が不十分な場合 → フェーズ3の実施を検討

---

## 📚 参考文献・関連研究

### マテリアライズドビュー選択
1. Agrawal et al. (2000): "Automated Selection of Materialized Views and Indexes"
2. Gupta & Mumick (1999): "Materialized Views: Techniques, Implementations, and Applications"

### クエリ最適化
3. Selinger et al. (1979): "Access Path Selection in a Relational Database"
4. Chaudhuri (1998): "An Overview of Query Optimization in Relational Systems"

### 機械学習 × データベース
5. Marcus et al. (2019): "Neo: A Learned Query Optimizer"
6. Kipf et al. (2019): "Learned Cardinalities: Estimating Correlated Joins with Deep Learning"

### 多目的最適化
7. Deb et al. (2002): "A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II"

---

## 💬 議論・疑問点

### 技術的な懸念

1. **EXPLAIN ANALYZEのオーバーヘッド**
   - すべてのクエリでEXPLAINを実行するとオーバーヘッドが大きい
   - サンプリングや閾値によるフィルタリングが必要か？

2. **MVの動的な有効化/無効化**
   - PostgreSQLではMVの有効化/無効化が困難
   - セッション単位でのsearch_path変更で対応可能か？

3. **学習データの収集コスト**
   - ML Cost推定には大量の学習データが必要
   - どの程度のサンプル数が必要か？
   - データ収集の自動化をどう実現するか？

### 研究戦略

1. **論文の焦点**
   - どの提案を中心に論文を書くべきか？
   - 複数の提案を含める場合、どう構成するか？

2. **ベースライン**
   - BigSubsとFrequencyのどちらをベースラインにするか？
   - ベースラインなし（元のクエリ）も含めるべきか？

3. **評価指標**
   - ワークロード実行時間だけで十分か？
   - クエリごとの性能分布も示すべきか？
   - MVのメンテナンスコストも評価すべきか？

---

## 📊 実験計画

### 評価項目

1. **主要指標**
   - ワークロード総実行時間
   - 平均クエリ実行時間
   - MV数
   - 総ストレージ使用量

2. **副次指標**
   - クエリごとの性能変化（ヒストグラム）
   - 最悪ケースのクエリ実行時間
   - MVの利用率
   - 書き換え率（何%のクエリがMVを使用したか）

3. **開発指標**
   - 最適化実行時間
   - MV作成時間
   - クエリ書き換え時間

### 実験セットアップ

```yaml
experiments:
  baseline:
    - name: "No MV"
      description: "元のクエリをそのまま実行"
  
  current:
    - name: "BigSubs"
      description: "現行のBigSubs手法"
    - name: "Frequency"
      description: "現行のFrequency手法"
  
  phase1:
    - name: "BigSubs + Validator"
      description: "BigSubsにRewrite Validatorを適用"
    - name: "Frequency + Validator"
      description: "FrequencyにRewrite Validatorを適用"
  
  phase2:
    - name: "Frequency + Negative MV"
      description: "Frequencyで選択したMVから有害なものを除外"
    - name: "BigSubs + Hint"
      description: "BigSubsにヒント句を追加"
    - name: "Frequency + Hint"
      description: "Frequencyにヒント句を追加"
  
  phase3:
    - name: "Multi-objective"
      description: "多目的最適化による選択"
    - name: "Hybrid"
      description: "ハイブリッド最適化"
    - name: "ML Cost"
      description: "機械学習ベースのコスト推定"
```

### データ収集

各実験で以下のデータを収集:
```json
{
  "experiment_name": "BigSubs + Validator",
  "timestamp": "2025-11-17T10:00:00",
  "optimization": {
    "num_selected_mvs": 115,
    "total_storage_mb": 17.64,
    "total_utility": 1786864,
    "execution_time_sec": 0.69
  },
  "benchmark": {
    "total_queries": 113,
    "successful": 113,
    "failed": 0,
    "total_execution_time_sec": 45.28,
    "avg_execution_time_sec": 0.40,
    "queries": [
      {
        "query_id": "1a",
        "execution_time_sec": 0.02,
        "used_mvs": ["mv_leaf_12"],
        "rewrite_accepted": true
      }
    ]
  }
}
```

---

## 🎓 論文への反映

### タイトル案
1. "Bridging the Gap: Reconciling Theoretical Cost Models with Actual Query Performance in Materialized View Selection"
2. "Hybrid Materialized View Selection: Combining Integer Linear Programming with Execution-Based Refinement"
3. "Learning to Select Materialized Views: A Machine Learning Approach to Query Optimization"

### 論文構成案

1. **Introduction**
   - 問題の背景と重要性
   - 既存手法（BigSubs, Frequency）の課題
   - 本研究の貢献

2. **Related Work**
   - Materialized View Selection
   - Query Optimization
   - Machine Learning for Databases

3. **Problem Analysis**
   - 実験結果の詳細分析
   - 理論値と実測値の乖離
   - MVによる実行プランの変化

4. **Proposed Approach**
   - 選択したアプローチ（フェーズ1-3の結果に基づく）
   - アルゴリズムの詳細
   - 実装の詳細

5. **Experimental Evaluation**
   - 実験セットアップ
   - ベースラインとの比較
   - 性能分析
   - Ablation Study

6. **Discussion**
   - 各アプローチの利点と限界
   - 実用上の考慮事項
   - 将来の研究方向

7. **Conclusion**

---

## ✅ チェックリスト

### フェーズ1開始前
- [ ] このドキュメントのレビューと承認
- [ ] 実装する提案の最終決定（推奨: 提案8）
- [ ] 開発環境の確認とセットアップ
- [ ] Gitブランチの作成
- [ ] 実験計画の詳細化

### フェーズ1実装中
- [ ] EXPLAIN機能の実装
- [ ] RewriteValidatorクラスの実装
- [ ] ユニットテストの作成
- [ ] QueryRewriterへの統合
- [ ] 統合テスト

### フェーズ1完了時
- [ ] 実験の実行（BigSubs + Validator, Frequency + Validator）
- [ ] 結果の分析と文書化
- [ ] フェーズ2への進行可否の判断
- [ ] 中間報告の作成

---

## 📞 連絡先・レビュー

**作成者**: Anderson Kaina  
**作成日**: 2025年11月17日  
**バージョン**: 1.0  

**レビュアー**: （未定）  
**承認者**: （未定）

**更新履歴**:
- 2025-11-17: 初版作成
