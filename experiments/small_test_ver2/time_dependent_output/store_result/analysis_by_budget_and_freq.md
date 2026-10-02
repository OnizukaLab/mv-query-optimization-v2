# 容量制約とクエリ頻度の変化が MV 選択に与える影響 — 分析レポート

このレポートは、`store_result` フォルダにある複数の時間依存最適化結果（予め実行して得られた JSON 出力）を比較し、容量制約（ストレージ予算）およびクエリ頻度の変化がマテリアライズドビュー（MV）の選択、ワークロード効果（workload cost）、およびマイグレーションコストにどのように影響するかをまとめたものです。

対象ファイル（一覧）
- `1KB_ferq_ease.json` (budget ≒ 1 KB, "ease" freq)
- `1KB_freq_ver3.json` (budget ≒ 1 KB, freq ver3) — ※未添付のバリエーションがある場合は要参照
- `10KB_freq_cmp.json` (budget ≒ 10 KB, freq comparison)
- `10KB_freq_ver3.json` (budget ≒ 10 KB, freq ver3)
- `10KB_freq_ease.json` (budget ≒ 10 KB, freq ease)
- `100KB_freq_cmp.json` (budget ≒ 100 KB, freq comparison)
- `100KB_freq_ver3.json` (budget ≒ 100 KB, freq ver3)
- `100KB_freq_ease.json` (budget ≒ 100 KB, freq ease)

（注）上記ファイルは `experiments/small_test_ver2/time_dependent_output/store_result/` に保存されています。

---

## 手法（簡潔）
- 各 JSON の summary と objective, workload_cost, migration_cost を比較
- 主要指標:
  - objective（総目的値。小さいほど良い。ワークロード利得は負の値で表現）
  - workload_cost（利得の負値合計）
  - migration_cost（作成コスト合計）
  - total_mvs_created / total_mvs_deleted
  - avg_mvs_per_timestep
  - avg_storage_utilization（予算に対する使用率 %）
- 比較軸:
  1. 固定周波数シナリオ間での「容量差」 (1KB, 10KB, 100KB)
  2. 固定容量での「頻度シナリオ差」 (cmp / ver3 / ease)

---

## 要約（キー観察）
下表は、提供された JSON に記載されている主要値を抜粋したもの（元データの小数第2位を丸めて掲載）。

- 注: "より負" の workload_cost は「より多くの利得（コスト削減）を捕まえた」ことを意味します。

### 抜粋データ（主要項目）

- `1KB_ferq_ease.json`
  - storage_budget: 1,024 B
  - objective: ≒ -17.45
  - workload_cost: ≒ -27.35
  - migration_cost: ≒ 9.90
  - avg_mvs_per_timestep: 2.5
  - avg_storage_utilization: 73.44%
  - total_mvs_created: 4, deleted: 2

- `10KB_freq_cmp.json`
  - storage_budget: 10,240 B
  - objective: ≒ -1,766.92
  - workload_cost: ≒ -1,826.90
  - migration_cost: ≒ 59.98
  - avg_mvs_per_timestep: 8.5
  - avg_storage_utilization: 98.49%
  - total_mvs_created: 10, deleted: 2

- `10KB_freq_ver3.json`
  - storage_budget: 10,240 B
  - objective: ≒ -3,421.64
  - workload_cost: ≒ -3,488.20
  - migration_cost: ≒ 66.56
  - avg_mvs_per_timestep: 7.5
  - avg_storage_utilization: 96.55%
  - total_mvs_created: 11, deleted: 4

- `10KB_freq_ease.json`
  - storage_budget: 10,240 B
  - objective: ≒ -33.14
  - workload_cost: ≒ -76.15
  - migration_cost: ≒ 43.01
  - avg_mvs_per_timestep: 6.0
  - avg_storage_utilization: 66.72%
  - total_mvs_created: 9, deleted: 4

- `100KB_freq_cmp.json`
  - storage_budget: 102,400 B
  - objective: ≒ -1,853.91
  - workload_cost: ≒ -1,917.30
  - migration_cost: ≒ 63.39
  - avg_mvs_per_timestep: 9.0
  - avg_storage_utilization: 12.9%
  - total_mvs_created: 9, deleted: 0

- `100KB_freq_ver3.json`
  - storage_budget: 102,400 B
  - objective: ≒ -3,464.40
  - workload_cost: ≒ -3,527.79
  - migration_cost: ≒ 63.39
  - avg_mvs_per_timestep: 9.0
  - avg_storage_utilization: 12.9%
  - total_mvs_created: 9, deleted: 0

- `100KB_freq_ease.json`
  - storage_budget: 102,400 B
  - objective: ≒ -33.14
  - workload_cost: ≒ -56.15
  - migration_cost: ≒ 23.01
  - avg_mvs_per_timestep: 3.5
  - avg_storage_utilization: 2.44%
  - total_mvs_created: 6, deleted: 4


---

## 解析と考察
以下は、容量制約（1KB, 10KB, 100KB）と頻度案（cmp / ver3 / ease）がどのように結果を変えているかの要点です。

### 1) 容量制約の影響（同一頻度シナリオ内で）
- 小予算（1KB）
  - 選択可能な MV 数が非常に少なく、`avg_mvs_per_timestep` が小さい（例: 2.5）。
  - `avg_storage_utilization` は高め（73%）で、予算ぎりぎりに小MVを詰め込む傾向。
  - ワークロード利得は小さい（workload_cost の絶対値が小さい）。マイグレーションコストは小〜中程度。

- 中予算（10KB）
  - かなり多くの MV を選択できる（avg ≒ 6〜8.5）。
  - ほとんどのケースで storage_utilization は高（≈ 66–98%） → 予算が実稼働に合わせて使い切られている。
  - workload_cost の絶対値が大きくなり、得られる利得が増える（ver3 では特に大きい）。
  - migration_cost も増える傾向（より多くの MV を作るため）。

- 大予算（100KB）
  - 多くの MV を同時に保持できるため、`avg_mvs_per_timestep` はさらに上がるか（ただし dataset により飽和）
  - このセットでは storage_utilization が低く（例: 12.9% や 2.44%）、予算に余裕があることを示す。
  - 余裕があると、マイグレーションコストはケースにより増減：
    - 余裕があればMVを維持しやすく、作成/削除の頻度は下がる → migration_cost が相対的に小さくなるケースあり
    - しかし、頻度に対応して多数のMVを作れば migration_cost は増える

**結論（容量）**: 予算が増えるほどワークロード利得(負の仕事量)は大きく（より良い結果）なりやすい。ただし、運用コスト（migration_cost）も増える可能性がある。100KB のように予算が十分大きい場合は、MV を維持して頻繁な作成を避けられるので migration_cost が抑えられる場合もある。


### 2) 頻度シナリオの影響（同一容量内で）
- `ver3` シナリオ
  - 全体で最も大きな workload_cost（絶対値）のケースが多い（例: 10KB/100KB で非常に負が大きい）
  - すなわち、`ver3` の周波数設定は MV による利得を取りやすい配置（高頻度クエリと対応する MV が選ばれやすい）
  - 結果として objective が大幅改善され、migration_cost は場合によって増えるが総合利益が上回る

- `cmp` シナリオ
  - `ver3` よりは利得が小さいが、`ease` より高いケースもある（周波数分布の違いに依存）
  - 比較的バランスの取れた MV 選択

- `ease` シナリオ
  - 全体として workload_cost の絶対値が小さい（利得が小さい）
  - migration_cost も比較的小さい（頻繁に作り替える価値が低いので作成を抑えられる）
  - 結果的に objective はあまり改善しない

**結論（頻度）**: 周波数が MV による利得を大きくする傾向である場合（ver3）には、最適化は多くの MV を選択して利得を回収し、結果が大きく改善する。一方、頻度差が小さく利得が小さい場合（ease）では MV を作るコストが利益を上回りやすく、結果の改善は限定的。


### 3) マイグレーションコストとのトレードオフ
- 高頻度かつ適切に MV を選べる場合（workload_cost の絶対値が大きい）には、多少の migration_cost を支払ってでも MV を作成・移行する価値がある（ver3 のケース）。
- 低利得のシナリオでは（ease）migration_cost を抑えて MV の作成を控えるのが良く、結果として objective の改善は小さい。


### 4) MV 作成/削除のパターン
- 小予算 -> 頻繁に入れ替え（create/delete）が発生しやすい（作成数と削除数が両方出る）。
- 大予算 -> MV を長く保持できるため create/delete が少なくなり、総 migration_cost が下がることがある。

---

## 実務的示唆（Actionable advice）

1. **容量を決める前に頻度分布を分析**: 周期性やべき分布（ホットクエリ）を把握し、どの程度のストレージがあると利得が頭打ちになるかを評価する。
2. **コストモデルの整備**: マイグレーション（作成）コストだけでなく、削除コストや維持コスト（m_cost）も導入するとより現実的な意思決定が可能。
3. **動的予算割当て**: 需要が高い時間帯には一時的に予算を増やす（あるいは代替手段で利得を回収）など運用面の工夫。
4. **頻度データの正規化と単位統一**: 本実験では頻度は相対値（数値）として使っているが、QPS/QPM 等の物理単位に置き換えて評価しておくと実運用に適合しやすい。

---

## 附録: 参考で使った具体値（抜粋）
- 各 JSON から抜粋した `objective, workload_cost, migration_cost, avg_mvs_per_timestep, avg_storage_utilization, total_mvs_created/deleted` を上記に記載。

---

## 次のステップ（提案）
1. 各 JSON の `input_data.utility_matrix` と `input_data.query_frequencies` を完全展開し、クエリごとの利得寄与を可視化する（クエリ単位でどれだけ利得が得られているか）。
2. 削除コスト・維持コストを追加して再評価。
3. 複数タイムステップ（T>2）での長期トレードオフを評価。


---

作成: 自動生成レポート

