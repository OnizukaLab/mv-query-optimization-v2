# マイグレーションコストの計算方法について考える

## 理想的な手法　全てのマイグレーションプランに対しMVを作成しexplainを実行する
非現実的
```json
"non_leaf_100": {
    "['non_leaf_100']": 0.0,
    "['leaf_39', 'non_leaf_99']": 2.53,
    "['non_leaf_99']": 174.48,
    "['leaf_38', 'leaf_39', 'non_leaf_98']": 461628.79,
    "['leaf_38', 'non_leaf_98']": 461635.0,
    "['leaf_39', 'non_leaf_98']": 164.7,
    "['non_leaf_98']": 180.36,
    "['leaf_38', 'leaf_39', 'leaf_41', 'non_leaf_88']": 461705.74,
    "['leaf_38', 'leaf_41', 'non_leaf_88']": 461752.31,
    "['leaf_39', 'leaf_41', 'non_leaf_88']": 2169.86,
    "['leaf_41', 'non_leaf_88']": 2453.68,
    "['leaf_38', 'leaf_39', 'non_leaf_88']": 461688.34,
    "['leaf_38', 'non_leaf_88']": 461734.27,
    "['leaf_39', 'non_leaf_88']": 282.82,
    "['non_leaf_88']": 287.79,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": 513163.11,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_41']": 516402.68,
    "['leaf_14', 'leaf_37', 'leaf_39', 'leaf_41']": 51633.82,
    "['leaf_14', 'leaf_37', 'leaf_41']": 51444.23,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39']": 513181.74,
    "['leaf_14', 'leaf_37', 'leaf_38']": 512063.86,
    "['leaf_14', 'leaf_37', 'leaf_39']": 51439.89,
    "['leaf_14', 'leaf_37']": 51441.56,
    "['leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": 462872.64,
    "['leaf_37', 'leaf_38', 'leaf_41']": 464991.55,
    "['leaf_37', 'leaf_39', 'leaf_41']": 1236.58,
    "['leaf_37', 'leaf_41']": 1252.24,
    "['leaf_37', 'leaf_38', 'leaf_39']": 461825.07,
    "['leaf_37', 'leaf_38']": 465140.63,
    "['leaf_37', 'leaf_39']": 1364.27,
    "['leaf_37']": 1369.23,
    "['leaf_14', 'leaf_38', 'leaf_39', 'leaf_41']": 513695.73,
    "['leaf_14', 'leaf_38', 'leaf_41']": 516930.66,
    "['leaf_14', 'leaf_39', 'leaf_41']": 51962.51,
    "['leaf_14', 'leaf_41']": 51979.16,
    "['leaf_14', 'leaf_38', 'leaf_39']": 513689.8,
    "['leaf_14', 'leaf_38']": 512571.92,
    "['leaf_14', 'leaf_39']": 51947.96,
    "['leaf_14']": 51949.62,
    "['leaf_38', 'leaf_39', 'leaf_41']": 465020.61,
    "['leaf_38', 'leaf_41']": 464991.13,
    "['leaf_39', 'leaf_41']": 2172.47,
    "['leaf_41']": 3935.35,
    "['leaf_38', 'leaf_39']": 461824.51,
    "['leaf_38']": 465541.31,
    "['leaf_39']": 2617.6,
    "[]": 3922.57
  },
```
## 手法１
もとのクエリプランから各ノードのコストを取得し、
実体化したいノードのコストからそのプランでそのノードが依存するMVのコストの合計を引く

```json
"non_leaf_100": {
    "['non_leaf_100']": 0.0,
    "['leaf_39', 'non_leaf_99']": 0.0,
    "['non_leaf_99']": 0.4600000000000364,
    "['leaf_38', 'leaf_39', 'non_leaf_98']": 0.47999999999956344,
    "['leaf_38', 'non_leaf_98']": 0.9399999999995998,
    "['leaf_39', 'non_leaf_98']": 1.8599999999996726,
    "['non_leaf_98']": 2.319999999999709,
    "['leaf_38', 'leaf_39', 'leaf_41', 'non_leaf_88']": 16.65000000000009,
    "['leaf_38', 'leaf_41', 'non_leaf_88']": 17.110000000000127,
    "['leaf_39', 'leaf_41', 'non_leaf_88']": 18.0300000000002,
    "['leaf_41', 'non_leaf_88']": 18.490000000000236,
    "['leaf_38', 'leaf_39', 'non_leaf_88']": 17.139999999999873,
    "['leaf_38', 'non_leaf_88']": 17.59999999999991,
    "['leaf_39', 'non_leaf_88']": 18.519999999999982,
    "['non_leaf_88']": 18.980000000000018,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": 19.670000000000073,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_41']": 20.13000000000011,
    "['leaf_14', 'leaf_37', 'leaf_39', 'leaf_41']": 21.050000000000182,
    "['leaf_14', 'leaf_37', 'leaf_41']": 21.51000000000022,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39']": 20.159999999999854,
    "['leaf_14', 'leaf_37', 'leaf_38']": 20.61999999999989,
    "['leaf_14', 'leaf_37', 'leaf_39']": 21.539999999999964,
    "['leaf_14', 'leaf_37']": 22.0,
    "['leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": 1229.17,
    "['leaf_37', 'leaf_38', 'leaf_41']": 1229.63,
    "['leaf_37', 'leaf_39', 'leaf_41']": 1230.5500000000002,
    "['leaf_37', 'leaf_41']": 1231.0100000000002,
    "['leaf_37', 'leaf_38', 'leaf_39']": 1229.6599999999999,
    "['leaf_37', 'leaf_38']": 1230.12,
    "['leaf_37', 'leaf_39']": 1231.04,
    "['leaf_37']": 1231.5,
    "['leaf_14', 'leaf_38', 'leaf_39', 'leaf_41']": 2704.79,
    "['leaf_14', 'leaf_38', 'leaf_41']": 2705.25,
    "['leaf_14', 'leaf_39', 'leaf_41']": 2706.17,
    "['leaf_14', 'leaf_41']": 2706.63,
    "['leaf_14', 'leaf_38', 'leaf_39']": 2705.2799999999997,
    "['leaf_14', 'leaf_38']": 2705.74,
    "['leaf_14', 'leaf_39']": 2706.66,
    "['leaf_14']": 2707.12,
    "['leaf_38', 'leaf_39', 'leaf_41']": 3914.29,
    "['leaf_38', 'leaf_41']": 3914.75,
    "['leaf_39', 'leaf_41']": 3915.67,
    "['leaf_41']": 3916.13,
    "['leaf_38', 'leaf_39']": 3914.7799999999997,
    "['leaf_38']": 3915.24,
    "['leaf_39']": 3916.16,
    "[]": 3916.62
  },
```

## 手法2
MVを使用しないマイグレーションプランについてはすべてexplainでコストを取得
依存するMVのあるプランは、生成したいMVのコストからそのプランで依存するMVのコストの合計を引く
    - かなり大きなマイナスのになっているプランが多い
    - MVを作成するプランはもとのクエリプランとは違うため

```json
"non_leaf_100": {
    "['non_leaf_100']": 0.0,
    "['leaf_39', 'non_leaf_99']": -78398.67,
    "['non_leaf_99']": 6.5,
    "['leaf_38', 'leaf_39', 'non_leaf_98']": -693479.8200000001,
    "['leaf_38', 'non_leaf_98']": -615074.6500000001,
    "['leaf_39', 'non_leaf_98']": -78396.9,
    "['non_leaf_98']": 8.269999999999982,
    "['leaf_38', 'leaf_39', 'leaf_41', 'non_leaf_88']": -743639.8700000001,
    "['leaf_38', 'leaf_41', 'non_leaf_88']": -665234.7000000001,
    "['leaf_39', 'leaf_41', 'non_leaf_88']": -128556.94999999998,
    "['leaf_41', 'non_leaf_88']": -50151.78,
    "['leaf_38', 'leaf_39', 'non_leaf_88']": -693463.1600000001,
    "['leaf_38', 'non_leaf_88']": -615057.9900000001,
    "['leaf_39', 'non_leaf_88']": -78380.23999999999,
    "['non_leaf_88']": 24.93000000000029,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": -812146.6500000001,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_41']": -733741.4800000001,
    "['leaf_14', 'leaf_37', 'leaf_39', 'leaf_41']": -197063.72999999998,
    "['leaf_14', 'leaf_37', 'leaf_41']": -118658.56,
    "['leaf_14', 'leaf_37', 'leaf_38', 'leaf_39']": -761969.9400000001,
    "['leaf_14', 'leaf_37', 'leaf_38']": -683564.7700000001,
    "['leaf_14', 'leaf_37', 'leaf_39']": -146887.02,
    "['leaf_14', 'leaf_37']": -68481.84999999999,
    "['leaf_37', 'leaf_38', 'leaf_39', 'leaf_41']": -742427.3500000001,
    "['leaf_37', 'leaf_38', 'leaf_41']": -664022.18,
    "['leaf_37', 'leaf_39', 'leaf_41']": -127344.43,
    "['leaf_37', 'leaf_41']": -48939.26,
    "['leaf_37', 'leaf_38', 'leaf_39']": -692250.6400000001,
    "['leaf_37', 'leaf_38']": -613845.4700000001,
    "['leaf_37', 'leaf_39']": -77167.71999999999,
    "['leaf_37']": 1237.4500000000003,
    "['leaf_14', 'leaf_38', 'leaf_39', 'leaf_41']": -809461.5300000001,
    "['leaf_14', 'leaf_38', 'leaf_41']": -731056.3600000001,
    "['leaf_14', 'leaf_39', 'leaf_41']": -194378.61,
    "['leaf_14', 'leaf_41']": -115973.44,
    "['leaf_14', 'leaf_38', 'leaf_39']": -759284.8200000001,
    "['leaf_14', 'leaf_38']": -680879.6500000001,
    "['leaf_14', 'leaf_39']": -144201.9,
    "['leaf_14']": -65796.73,
    "['leaf_38', 'leaf_39', 'leaf_41']": -739742.2300000001,
    "['leaf_38', 'leaf_41']": -661337.06,
    "['leaf_39', 'leaf_41']": -124659.31,
    "['leaf_41']": -46254.14,
    "['leaf_38', 'leaf_39']": -689565.5200000001,
    "['leaf_38']": -611160.3500000001,
    "['leaf_39']": -74482.59999999999,
    "[]": 3922.57
  },
```

## 手法３　
仮想MVを作成する手法
たしかに精度は上がりそうだがデータベースのシステムカタログ？をいじるため危険
実用的ではない
まだ試していないが、、

## 手法４
全てのノードのついてマイグレーションを考えるのではなく、より大まかに、プランが変わらなそうなノードを候補として考える
手法1とほぼ同じ
やはり本来のコストとの間に大きな差がある、、
```json
{
    "粗粒度MVマイグレーションプラン列挙（Aggregate, Hash Join, Sort, Materializeのみ）":{
        "non_leaf_250": {
            "['non_leaf_250']": 0.0,
            "['non_leaf_248']": 581.6800000000512,
            "['non_leaf_157']": 552071.48,
            "[]": 590011.25
        },
        "non_leaf_251": {
            "['non_leaf_251']": 0.0,
            "['non_leaf_250']": 1052.2099999999627,
            "['non_leaf_248']": 1633.890000000014,
            "['non_leaf_157']": 553123.69,
            "[]": 591063.46
        }
    },
    "すべてのプランをexplainしたマイグレーションプラン":{
        "non_leaf_250": {
            "['non_leaf_250']": 0.0,
            "['non_leaf_248']": 11.89,
            "['non_leaf_157']": 686258.44,
            "[]": 665909.34
        },
        "non_leaf_251": {
            "['non_leaf_251']": 0.0,
            "['non_leaf_250']": 1.1,
            "['non_leaf_248']": 11.89,
            "['non_leaf_157']": 686258.44,
            "[]": 665909.34
        }
    }
}
```

#　問題点
もともとのクエリの実行プランとMV作成の実行プランがどうしても異なってしまう
leaf_3の例 Index Scan が原因
1. 元のクエリプラン
    ```json
    {
        "node_id": "leaf_3",
        "Node Type": "Index Scan",
        "Parent Relationship": "Inner",
        "Parallel Aware": false,
        "Async Capable": false,
        "Scan Direction": "Forward",
        "Index Name": "movie_id_movie_companies",
        "Relation Name": "movie_companies",
        "Alias": "mc",
        "Startup Cost": 0.43,
        "Total Cost": 0.62,
        "Plan Rows": 1,
        "Plan Width": 32,
        "Disabled": false,
        "Index Cond": "(movie_id = mi_idx.movie_id)",
        "Filter": "((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ((note ~~ '%(co-production)%'::text) OR (note ~~ '%(presents)%'::text)))"
    }
    ```
2. MV作成のプラン
    ```json
    {
    "no_mv": {
        "plan_key": "[]",
        "sql": "CREATE MATERIALIZED VIEW leaf_3 AS\nSELECT mc.id, mc.movie_id, mc.company_id, mc.company_type_id, mc.note\nFROM movie_companies AS mc\nWHERE ((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ((note ~~ '%(co-production)%'::text) OR (note ~~ '%(presents)%'::text)));",
        "explain_json": {
        "Plan": {
            "Node Type": "Gather",
            "Parallel Aware": false,
            "Async Capable": false,
            "Startup Cost": 1000.0,
            "Total Cost": 40151.0,
            "Plan Rows": 13021,
            "Plan Width": 40,
            "Disabled": false,
            "Workers Planned": 2,
            "Single Copy": false,
            "Plans": [
            {
                "Node Type": "Seq Scan",
                "Parent Relationship": "Outer",
                "Parallel Aware": true,
                "Async Capable": false,
                "Relation Name": "movie_companies",
                "Alias": "mc",
                "Startup Cost": 0.0,
                "Total Cost": 37848.9,
                "Plan Rows": 5425,
                "Plan Width": 40,
                "Disabled": false,
                "Filter": "((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ((note ~~ '%(co-production)%'::text) OR (note ~~ '%(presents)%'::text)))"
            }
            ]
        }
        },
        "cost": 40151.0
    }
    }
    ```

    実行プランによる影響をどう考慮するか？
    実行プランが変わりにくいノードを選ぶか？

                    
