-- 全てのMaterialized Viewに対してANALYZEを実行
-- 統計情報を更新して、正確なコスト推定を行う

-- Leaf MVs
ANALYZE leaf_1;
ANALYZE leaf_3;
ANALYZE leaf_8;
ANALYZE leaf_9;
ANALYZE leaf_11;
ANALYZE leaf_15;
ANALYZE leaf_18;

-- Non-leaf MVs
ANALYZE non_leaf_10;
ANALYZE non_leaf_20;
ANALYZE non_leaf_23;
ANALYZE non_leaf_31;

-- 結果確認: 統計情報の更新日時とタプル数
SELECT 
    schemaname,
    matviewname,
    last_analyze,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public' 
  AND relname IN (
    'leaf_1', 'leaf_3', 'leaf_8', 'leaf_9', 'leaf_11', 'leaf_15', 'leaf_18',
    'non_leaf_10', 'non_leaf_20', 'non_leaf_23', 'non_leaf_31'
  )
ORDER BY matviewname;

-- MVの統計情報サマリー
SELECT 
    c.relname AS mv_name,
    c.reltuples::bigint AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    s.last_analyze
FROM pg_class c
LEFT JOIN pg_stat_user_tables s ON c.relname = s.relname
WHERE c.relkind = 'm'  -- Materialized Views
  AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
ORDER BY c.relname;

-- 完了メッセージ
SELECT '✅ All Materialized Views have been analyzed successfully!' AS status;
