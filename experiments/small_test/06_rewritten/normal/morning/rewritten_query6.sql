-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 2
-- Match Type: full
-- MV Used: mv_non_leaf_23
-- Matched Tables: o, p, u
-- Coverage Score: 100.0%
-- ================================================

SELECT non_leaf_23.city,
    non_leaf_23.category,
    non_leaf_23.age,
    COUNT(DISTINCT non_leaf_23.user_id) as unique_customers,
    COUNT(non_leaf_23.order_id) as total_orders,
    SUM(non_leaf_23.quantity) as total_quantity,
    SUM(non_leaf_23.total_amount) as total_revenue,
    AVG(non_leaf_23.total_amount) as avg_order_value
FROM non_leaf_23
WHERE non_leaf_23.order_date >= CURRENT_DATE - INTERVAL '90 days'
  AND non_leaf_23.age >= 25
GROUP BY non_leaf_23.city, non_leaf_23.category, non_leaf_23.age
HAVING COUNT(non_leaf_23.order_id) >= 1
ORDER BY total_revenue DESC, non_leaf_23.city, non_leaf_23.category;