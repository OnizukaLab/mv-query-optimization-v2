-- Query 9: 若年層ユーザーの購買パターン分析
-- 25歳未満のユーザーによる低価格商品（300未満）の購入分析

SELECT 
    p.category,
    COUNT(DISTINCT u.user_id) as young_buyers,
    COUNT(o.order_id) as order_count,
    AVG(p.price) as avg_price,
    MIN(p.price) as min_price,
    MAX(p.price) as max_price
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE u.age < 25
  AND p.price < 300
GROUP BY p.category
ORDER BY order_count DESC;
