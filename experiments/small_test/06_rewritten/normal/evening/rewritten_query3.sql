-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 1
-- Match Type: full
-- MV Used: mv_non_leaf_12
-- Matched Tables: o, p, u
-- Coverage Score: 100.0%
-- ================================================

SELECT non_leaf_12.city,
    non_leaf_12.category,
    COUNT(non_leaf_12.order_id) as order_count,
    SUM(non_leaf_12.total_amount) as total_spent,
    AVG(non_leaf_12.quantity) as avg_quantity
FROM non_leaf_12
WHERE non_leaf_12.age >= 30 
  AND non_leaf_12.price >= 500
  AND non_leaf_12.order_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY non_leaf_12.city, non_leaf_12.category
HAVING COUNT(non_leaf_12.order_id) >= 2
ORDER BY total_spent DESC;