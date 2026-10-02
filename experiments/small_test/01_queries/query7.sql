-- Query 7: 高額商品を購入したユーザーの分析
-- 商品価格が500以上の注文をしたユーザーの統計

SELECT 
    u.city,
    u.age,
    COUNT(DISTINCT o.order_id) as high_value_orders,
    SUM(p.price) as total_spent,
    AVG(p.price) as avg_product_price
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE p.price >= 500
  AND u.age >= 30
GROUP BY u.city, u.age
HAVING COUNT(DISTINCT o.order_id) >= 2
ORDER BY total_spent DESC;
