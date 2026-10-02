
# Original Query
						QUERY PLAN     
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Aggregate  (cost=3836.83..3836.84 rows=1 width=96) (actual time=58.135..58.138 rows=1.00 loops=1)
   Buffers: shared hit=81396 read=6863
   ->  Nested Loop  (cost=8.81..3836.82 rows=1 width=48) (actual time=5.985..57.960 rows=1410.00 loops=1)
         Join Filter: (ml.movie_id = t.id)
         Buffers: shared hit=81396 read=6863
         ->  Nested Loop  (cost=8.38..3836.32 rows=1 width=47) (actual time=5.937..56.498 rows=1816.00 loops=1)
               Join Filter: (ct.id = mc.company_type_id)
               Rows Removed by Join Filter: 95
               Buffers: shared hit=74138 read=6857
               ->  Nested Loop  (cost=8.38..3835.26 rows=1 width=51) (actual time=5.932..55.556 rows=1911.00 loops=1)
                     Buffers: shared hit=72227 read=6857
                     ->  Nested Loop  (cost=7.96..3834.80 rows=1 width=36) (actual time=5.511..51.355 rows=4365.00 loops=1)
                           Join Filter: (mc.movie_id = ml.movie_id)
                           Buffers: shared hit=54797 read=6827
                           ->  Nested Loop  (cost=7.53..3834.22 rows=1 width=24) (actual time=5.461..50.008 rows=684.00 loops=1)
                                 Join Filter: (mi.movie_id = ml.movie_id)
                                 Buffers: shared hit=51387 read=6821
                                 ->  Nested Loop  (cost=7.09..3832.49 rows=1 width=20) (actual time=3.386..43.230 rows=199.00 loops=1)
                                       Join Filter: (lt.id = ml.link_type_id)
                                       Rows Removed by Join Filter: 303
                                       Buffers: shared hit=48837 read=6590
                                       ->  Seq Scan on link_type lt  (cost=0.00..1.23 rows=1 width=16) (actual time=0.014..0.017 rows=2.00 loops=1)
                                             Filter: ((link)::text ~~ '%follow%'::text)
                                             Rows Removed by Filter: 16
                                             Buffers: shared hit=1
                                       ->  Nested Loop  (cost=7.09..3831.14 rows=10 width=12) (actual time=2.185..21.587 rows=251.00 loops=2)
                                             Buffers: shared hit=48836 read=6590
                                             ->  Nested Loop  (cost=6.80..3816.68 rows=34 width=4) (actual time=2.177..17.359 rows=10544.00 loops=2)
                                                   Buffers: shared hit=6591 read=6589
                                                   ->  Seq Scan on keyword k  (cost=0.00..2685.12 rows=1 width=4) (actual time=1.045..4.040 rows=1.00 loops=2)
                                                         Filter: (keyword = 'sequel'::text)
                                                         Rows Removed by Filter: 134169
                                                         Buffers: shared hit=1008 read=1008
                                                   ->  Bitmap Heap Scan on movie_keyword mk  (cost=6.80..1128.50 rows=306 width=8) (actual time=1.113..12.691 rows=10544.00 loops=2)
                                                         Recheck Cond: (k.id = keyword_id)
                                                         Heap Blocks: exact=11140
                                                         Buffers: shared hit=5583 read=5581
                                                         ->  Bitmap Index Scan on keyword_id_movie_keyword  (cost=0.00..6.73 rows=306 width=0) (actual time=0.614..0.614 rows=10544.00 loops=2)
                                                               Index Cond: (keyword_id = k.id)
                                                               Index Searches: 2
                                                               Buffers: shared hit=13 read=11
                                             ->  Index Scan using movie_id_movie_link on movie_link ml  (cost=0.29..0.38 rows=5 width=8) (actual time=0.000..0.000 rows=0.02 loops=21088)
                                                   Index Cond: (movie_id = mk.movie_id)
                                                   Index Searches: 21088
                                                   Buffers: shared hit=42245 read=1
                                 ->  Index Scan using movie_id_movie_info on movie_info mi  (cost=0.43..1.72 rows=1 width=4) (actual time=0.033..0.034 rows=3.44 loops=199)
                                       Index Cond: (movie_id = mk.movie_id)
                                       Filter: (info = ANY ('{Sweden,Norway,Germany,Denmark,Swedish,Denish,Norwegian,German}'::text[]))
                                       Rows Removed by Filter: 17
                                       Index Searches: 199
                                       Buffers: shared hit=2550 read=231
                           ->  Index Scan using movie_id_movie_companies on movie_companies mc  (cost=0.43..0.54 rows=3 width=12) (actual time=0.001..0.001 rows=6.38 loops=684)
                                 Index Cond: (movie_id = mk.movie_id)
                                 Filter: (note IS NULL)
                                 Rows Removed by Filter: 2
                                 Index Searches: 684
                                 Buffers: shared hit=3410 read=6
                     ->  Index Scan using company_name_pkey on company_name cn  (cost=0.42..0.46 rows=1 width=23) (actual time=0.001..0.001 rows=0.44 loops=4365)
                           Index Cond: (id = mc.company_id)
                           Filter: (((country_code)::text <> '[pl]'::text) AND ((name ~~ '%Film%'::text) OR (name ~~ '%Warner%'::text)))
                           Rows Removed by Filter: 1
                           Index Searches: 4365
                           Buffers: shared hit=17430 read=30
               ->  Seq Scan on company_type ct  (cost=0.00..1.05 rows=1 width=4) (actual time=0.000..0.000 rows=1.00 loops=1911)
                     Filter: ((kind)::text = 'production companies'::text)
                     Rows Removed by Filter: 1
                     Buffers: shared hit=1911
         ->  Index Scan using title_pkey on title t  (cost=0.43..0.49 rows=1 width=21) (actual time=0.001..0.001 rows=0.78 loops=1816)
               Index Cond: (id = mk.movie_id)
               Filter: ((production_year >= 1950) AND (production_year <= 2000))
               Rows Removed by Filter: 0
               Index Searches: 1816
               Buffers: shared hit=7258 read=6
 Planning:
   Buffers: shared hit=749 read=57
 Planning Time: 19.570 ms
 Execution Time: 58.582 ms
(77 rows)



# Query rewrited by Frequency


                                                                                                 QUERY PLAN                                                                                                 
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Aggregate  (cost=57881.16..57881.17 rows=1 width=96) (actual time=12841.675..12841.684 rows=1.00 loops=1)
   Buffers: shared hit=1802763 read=20543
   ->  Nested Loop  (cost=25644.22..57881.15 rows=1 width=47) (actual time=441.764..12841.225 rows=1410.00 loops=1)
         Join Filter: (leaf_101.id = leaf_100.company_id)
         Rows Removed by Join Filter: 146305348
         Buffers: shared hit=1802763 read=20543
         ->  Hash Join  (cost=25644.22..55852.31 rows=1 width=33) (actual time=154.702..259.188 rows=3029.00 loops=1)
               Hash Cond: (leaf_99.id = ml.movie_id)
               Buffers: shared hit=43495 read=19962
               ->  Seq Scan on leaf_99  (cost=0.00..26776.66 rows=915044 width=21) (actual time=1.238..72.255 rows=910581.00 loops=1)
                     Filter: ((production_year >= 1950) AND (production_year <= 2000))
                     Buffers: shared read=13051
               ->  Hash  (cost=25644.21..25644.21 rows=1 width=32) (actual time=150.469..150.477 rows=4198.00 loops=1)
                     Buckets: 8192 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 323kB
                     Buffers: shared hit=43495 read=6911
                     ->  Nested Loop  (cost=1139.38..25644.21 rows=1 width=32) (actual time=30.298..150.003 rows=4198.00 loops=1)
                           Join Filter: (mi.movie_id = ml.movie_id)
                           Buffers: shared hit=43495 read=6911
                           ->  Hash Join  (cost=1138.94..25635.54 rows=5 width=28) (actual time=29.316..145.780 rows=962.00 loops=1)
                                 Hash Cond: (ml.link_type_id = lt.id)
                                 Buffers: shared hit=29501 read=6911
                                 ->  Nested Loop  (cost=1137.71..25634.01 rows=88 width=20) (actual time=29.256..145.620 rows=1052.00 loops=1)
                                       Buffers: shared hit=29500 read=6911
                                       ->  Hash Join  (cost=1137.42..25511.13 rows=289 width=12) (actual time=29.234..140.750 rows=11915.00 loops=1)
                                             Hash Cond: (leaf_100.company_type_id = leaf_4.id)
                                             Buffers: shared hit=5582 read=6911
                                             ->  Hash Join  (cost=1136.39..25505.05 rows=578 width=16) (actual time=16.334..138.470 rows=14331.00 loops=1)
                                                   Hash Cond: (leaf_100.movie_id = mk.movie_id)
                                                   Buffers: shared hit=5582 read=6910
                                                   ->  Seq Scan on leaf_100  (cost=0.00..19602.73 rows=1269373 width=12) (actual time=0.687..62.998 rows=1271989.00 loops=1)
                                                         Filter: (note IS NULL)
                                                         Buffers: shared read=6909
                                                   ->  Hash  (cost=1132.57..1132.57 rows=306 width=4) (actual time=15.621..15.623 rows=10544.00 loops=1)
                                                         Buckets: 16384 (originally 1024)  Batches: 1 (originally 1)  Memory Usage: 499kB
                                                         Buffers: shared hit=5582 read=1
                                                         ->  Nested Loop  (cost=6.80..1132.57 rows=306 width=4) (actual time=3.196..14.586 rows=10544.00 loops=1)
                                                               Buffers: shared hit=5582 read=1
                                                               ->  Seq Scan on leaf_98  (cost=0.00..1.01 rows=1 width=4) (actual time=0.891..0.892 rows=1.00 loops=1)
                                                                     Filter: (keyword = 'sequel'::text)
                                                                     Buffers: shared read=1
                                                               ->  Bitmap Heap Scan on movie_keyword mk  (cost=6.80..1128.50 rows=306 width=8) (actual time=2.300..12.553 rows=10544.00 loops=1)
                                                                     Recheck Cond: (keyword_id = leaf_98.id)
                                                                     Heap Blocks: exact=5570
                                                                     Buffers: shared hit=5582
                                                                     ->  Bitmap Index Scan on keyword_id_movie_keyword  (cost=0.00..6.73 rows=306 width=0) (actual time=1.498..1.499 rows=10544.00 loops=1)
                                                                           Index Cond: (keyword_id = leaf_98.id)
                                                                           Index Searches: 1
                                                                           Buffers: shared hit=12
                                             ->  Hash  (cost=1.01..1.01 rows=1 width=4) (actual time=1.007..1.008 rows=1.00 loops=1)
                                                   Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                                   Buffers: shared read=1
                                                   ->  Seq Scan on leaf_4  (cost=0.00..1.01 rows=1 width=4) (actual time=1.002..1.002 rows=1.00 loops=1)
                                                         Filter: ((kind)::text = 'production companies'::text)
                                                         Buffers: shared read=1
                                       ->  Index Scan using movie_id_movie_link on movie_link ml  (cost=0.29..0.38 rows=5 width=8) (actual time=0.000..0.000 rows=0.09 loops=11915)
                                             Index Cond: (movie_id = mk.movie_id)
                                             Index Searches: 11915
                                             Buffers: shared hit=23918
                                 ->  Hash  (cost=1.23..1.23 rows=1 width=16) (actual time=0.037..0.037 rows=2.00 loops=1)
                                       Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                       Buffers: shared hit=1
                                       ->  Seq Scan on link_type lt  (cost=0.00..1.23 rows=1 width=16) (actual time=0.015..0.018 rows=2.00 loops=1)
                                             Filter: ((link)::text ~~ '%follow%'::text)
                                             Rows Removed by Filter: 16
                                             Buffers: shared hit=1
                           ->  Index Scan using movie_id_movie_info on movie_info mi  (cost=0.43..1.72 rows=1 width=4) (actual time=0.003..0.004 rows=4.36 loops=962)
                                 Index Cond: (movie_id = mk.movie_id)
                                 Filter: (info = ANY ('{Sweden,Norway,Germany,Denmark,Swedish,Denish,Norwegian,German}'::text[]))
                                 Rows Removed by Filter: 18
                                 Index Searches: 962
                                 Buffers: shared hit=13994
         ->  Seq Scan on leaf_101  (cost=0.00..1426.29 rows=48205 width=22) (actual time=0.001..2.946 rows=48302.00 loops=3029)
               Filter: (((country_code)::text <> '[pl]'::text) AND ((name ~~ '%Film%'::text) OR (name ~~ '%Warner%'::text)))
               Buffers: shared hit=1759268 read=581
 Planning:
   Buffers: shared hit=579 read=7
 Planning Time: 10.974 ms
 Execution Time: 12841.904 ms
(78 rows)
---

# 実行プラン分析

## 📊 実行時間の比較

| 指標 | オリジナルクエリ | MV使用後 | 悪化率 |
|------|-----------------|----------|--------|
| **実行時間** | 58.582 ms | 12841.904 ms | **219倍悪化** |
| 総行処理数 | 1,410行 | 1,410行 | 同じ |
| Buffer Hits | 81,396 | 1,802,763 | 22倍増加 |
| Buffer Reads | 6,863 | 20,543 | 3倍増加 |

## 🔍 根本原因の特定

### 原因1: **致命的なNested Loop with Seq Scan**

**オリジナルクエリ（高速）:**
```
Nested Loop (cost=8.81..3836.82)
  -> Index Scan using title_pkey (0.001ms/loop, 1816 loops)
  -> Index Scan using movie_id_movie_companies (0.001ms/loop, 4365 loops)
```
- **インデックスを使用した効率的な結合**
- Nested Loopは内側のテーブルがインデックスを使える場合に高速

**MV使用後（超低速）:**
```
Nested Loop (cost=25644.22..57881.15)
  Join Filter: (leaf_101.id = leaf_100.company_id)
  Rows Removed by Join Filter: 146,305,348  ← ★ 1億4630万行を除外！
  -> Hash Join ... (3,029 rows)
  -> Seq Scan on leaf_101 (48,302 rows/loop × 3,029 loops)  ← ★ 超巨大なループ
```

**問題の構造:**
```
外側: 3,029行
内側: 48,302行（leaf_101: company_name MV）
  → Cross Join状態: 3,029 × 48,302 = 146,311,458行
  → Join Filter後: 1,410行（99.999%が無駄！）
```

### 原因2: **インデックスの欠如**

| テーブル/MV | 使用されるべき列 | インデックスの有無 | 結果 |
|------------|-----------------|------------------|------|
| `company_name` (元テーブル) | `id` (PK), `country_code`, `name` | ✅ Primary Key | Index Scan |
| `leaf_101` (MV) | `id`, `country_code`, `name` | ❌ なし | **Seq Scan** |
| `title` (元テーブル) | `id` (PK), `production_year` | ✅ Primary Key | Index Scan |
| `leaf_99` (MV) | `id`, `production_year` | ❌ なし | **Seq Scan** |

**影響:**
- `leaf_101`（company_name MV）: 48,302行を3,029回Seq Scan
- 総スキャン回数: **146,311,458行**（1億4630万行！）
- 1回のScan: 約2.9ms → 3,029回 × 2.9ms = **約8,800秒分の無駄**

### 原因3: **Join順序の変化**

**オリジナル（最適）:**
```
1. keyword='sequel'でフィルタ (1行)
2. movie_keyword経由でmovie絞り込み (10,544行)
3. movie_linkでさらに絞り込み (251行)
4. movie_infoで絞り込み (684行)
5. company_nameをIndex Scanで結合 (4,365行 → 1,410行)
   ↑ この時点で小さいので効率的
```

**MV使用後（非最適）:**
```
1. 複数のHash Joinで中間結果を生成 (3,029行)
2. company_name MV（leaf_101）を最後にNested Loopで結合
   ↑ この時点でMVが大きすぎる（48,302行）
   ↑ インデックスがないのでSeq Scan
   ↑ 3,029回ループ = 完全なカーシアン積
```

## 🎯 具体的な問題点

### 問題1: オプティマイザの誤判断

```sql
-- オプティマイザの推定
Hash Join (cost=25644.22..57881.15 rows=1)  -- 1行と推定

-- 実際の実行
actual time=441.764..12841.225 rows=1410.00  -- 実際は1,410行
```

**原因:**
- MVの統計情報が不正確
- JOIN条件の選択性を過小評価
- `leaf_101` (company_name MV) のサイズを考慮できていない

### 問題2: Seq Scanの多重ループ

```
Seq Scan on leaf_101 
  (cost=0.00..1426.29 rows=48,205)
  actual time=0.001..2.946 rows=48,302.00 loops=3029  ← ★ 3,029回繰り返し
```

**計算:**
- 1回のScan: 2.946ms
- 3,029回: 2.946ms × 3,029 = **約8,920ms**（実行時間の約70%）

**なぜこうなったか:**
- `leaf_101.id`にインデックスがない
- オプティマイザは「Nested Loop + Index Scan」を選べない
- 結果として「Nested Loop + Seq Scan」という最悪の組み合わせに

### 問題3: 行数の爆発的増加

```
Rows Removed by Join Filter: 146,305,348
```

**これは何を意味するか:**
- 3,029行 × 48,302行 = 146,311,458行のカーシアン積を生成
- その後JOIN条件でフィルタリングして1,410行に減少
- **99.999%の行が無駄に処理された**

## 💡 解決策

### 即座に実施すべき対策

#### 1. **MVにインデックスを作成**（提案9）

```sql
-- leaf_101 (company_name MV) に主キーインデックス
CREATE UNIQUE INDEX leaf_101_id_idx ON leaf_101(id);

-- フィルタ条件用のインデックス
CREATE INDEX leaf_101_country_name_idx ON leaf_101(country_code, name);

-- leaf_99 (title MV) に主キーインデックス
CREATE UNIQUE INDEX leaf_99_id_idx ON leaf_99(id);

-- フィルタ条件用のインデックス
CREATE INDEX leaf_99_production_year_idx ON leaf_99(production_year);
```

**期待される効果:**
- Seq Scan → Index Scan に変更
- 3,029回のループが各0.001msに短縮
- 実行時間: 12,841ms → **約50ms**（250倍高速化）

#### 2. **Rewrite Validatorで書き換えをスキップ**（提案8）

```python
# 書き換え前にEXPLAINで検証
original_cost = 3836.84  # オリジナルのコスト
rewritten_cost = 57881.17  # 書き換え後のコスト

if rewritten_cost > original_cost * 1.1:  # 10%以上悪化
    print("Rewrite rejected: using original query")
    return original_query
```

**期待される効果:**
- このクエリは書き換えをスキップ
- オリジナルの58msで実行

#### 3. **MVの統計情報を更新**

```sql
-- MVの統計情報を収集
ANALYZE leaf_101;
ANALYZE leaf_99;
ANALYZE leaf_100;
ANALYZE leaf_98;
ANALYZE leaf_4;
```

## 📈 推定される改善効果

| 対策 | 実行時間 | 改善率 |
|------|---------|--------|
| 現状（MV使用） | 12,841 ms | - |
| 対策1: インデックス作成 | **50 ms** | 256倍高速化 |
| 対策2: 書き換えスキップ | **58 ms** | 221倍高速化 |
| 対策3: 統計情報更新 | 8,000 ms | 1.6倍改善（不十分） |
| **対策1+2併用** | **50 ms** | **256倍高速化** |

## 🔬 技術的考察

### なぜオリジナルは速かったのか？

1. **適切なインデックス利用**
   - すべてのJOINでIndex Scanを使用
   - Nested Loopの内側テーブルにインデックスがある

2. **最適なJoin順序**
   - 選択性の高いフィルタから開始（keyword='sequel'）
   - 徐々に行数を削減（134,170 → 1 → 10,544 → 251 → 1,410）

3. **効率的なBuffer使用**
   - 小さな中間結果セット
   - キャッシュヒット率が高い

### なぜMV使用後は遅くなったのか？

1. **インデックスの喪失**
   - MVは元のテーブルのインデックスを継承しない
   - PostgreSQLのMATERIALIZED VIEWは自動的にインデックスを作成しない

2. **オプティマイザの判断ミス**
   - MVの統計情報が不完全
   - インデックスがないため、Seq Scanしか選択肢がない
   - Nested Loop + Seq Scanは最悪の組み合わせ

3. **Join順序の悪化**
   - 大きなテーブル（leaf_101: 48,302行）を内側にした Nested Loop
   - カーシアン積の生成（146百万行）

## 📚 学術的意義

この分析は、**MV最適化研究における重要な問題**を明確に示しています:

1. **コスト推定の限界**
   - ILP最適化で使用したコスト（3,836.84）は正確だった
   - しかし、MV使用後のコスト（57,881.17）は推定値の220倍悪化した
   - **根本原因**: インデックスの有無を考慮していない

2. **MVとインデックスの関係**
   - 既存研究ではMV選択のみに焦点
   - **本研究の貢献**: MVにインデックスを伝播する必要性を実証

3. **実行プラン変化の予測困難性**
   - 静的コスト分析では捉えられない
   - **提案**: 実行時検証（Rewrite Validator）の必要性

---

## 結論

**Frequencyアルゴリズムで選択されたMVは理論的には有益だが、インデックスの欠如により実行時に219倍悪化した。**

**重要な発見:**
- MVのUtility値は高くても、インデックスがないと逆効果
- オプティマイザはインデックスの有無で全く異なるプランを選択
- **提案9（MV Index Propagation）の実装が最優先課題**
