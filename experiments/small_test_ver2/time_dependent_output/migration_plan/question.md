     QUERY PLAN
--------------------------------------------------------------------
 Hash Join  (cost=1.68..4.43 rows=74 width=57)
   Hash Cond: (leaf_3.product_id = leaf_4.product_id)
   ->  Seq Scan on leaf_3  (cost=0.00..1.74 rows=74 width=25)
   ->  Hash  (cost=1.30..1.30 rows=30 width=32)
         ->  Seq Scan on leaf_4  (cost=0.00..1.30 rows=30 width=32)
(5 行)

            QUERY PLAN
------------------------------------------------------------------------
 Hash Join  (cost=1.68..4.43 rows=74 width=57)
   Hash Cond: (leaf_3.product_id = non_leaf_4.product_id)
   ->  Seq Scan on leaf_3  (cost=0.00..1.74 rows=74 width=25)
   ->  Hash  (cost=1.30..1.30 rows=30 width=32)
         ->  Seq Scan on non_leaf_4  (cost=0.00..1.30 rows=30 width=32)
(5 行)

leaf_4を使う場合でもnon_leaf_4を使う場合でもコストは変わらない
{
              "Node Type": "Hash",
              "Parent Relationship": "Inner",　　<- non_leaf_4
              "Parallel Aware": false,
              "Async Capable": false,
              "Startup Cost": 1.3,
              "Total Cost": 1.3,
              "Plan Rows": 30,
              "Plan Width": 14,
              "Disabled": false,
              "Plans": [
                {
                  "Node Type": "Seq Scan",
                  "Parent Relationship": "Outer",  <- leaf_4
                  "Parallel Aware": false,
                  "Async Capable": false,
                  "Relation Name": "products",
                  "Alias": "p",
                  "Startup Cost": 0.0,
                  "Total Cost": 1.3,
                  "Plan Rows": 30,
                  "Plan Width": 14,
                  "Disabled": false
                }
              ]
            }