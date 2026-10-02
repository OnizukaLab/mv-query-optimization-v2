-- Query 8: 特定カテゴリの商品を購入したユーザー数
-- Electronics カテゴリの商品を購入したユーザーの都市別集計

SELECT 
    u.city,
    COUNT(DISTINCT u.user_id) as electronics_buyers,
    COUNT(o.order_id) as total_electronics_orders,
    SUM(p.price) as total_electronics_revenue
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE p.category = 'Electronics'
  AND o.order_date >= '2024-01-01'
GROUP BY u.city
ORDER BY total_electronics_revenue DESC;
