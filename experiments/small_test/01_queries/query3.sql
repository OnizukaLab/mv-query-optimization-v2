-- クエリ3: 複雑なJOIN（3テーブル結合 + 集計 + フィルタ）

SELECT 
    u.city,
    p.category,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_spent,
    AVG(o.quantity) as avg_quantity
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE u.age >= 30 
  AND p.price >= 500
  AND o.order_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY u.city, p.category
HAVING COUNT(o.order_id) >= 2
ORDER BY total_spent DESC;
