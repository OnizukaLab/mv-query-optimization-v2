-- クエリ2: カテゴリ別の売上集計 (JOIN + 集計のテスト)

SELECT 
    p.category,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_sales,
    AVG(o.quantity) as avg_quantity
FROM products p
INNER JOIN orders o ON p.product_id = o.product_id
WHERE o.order_date >= CURRENT_DATE - INTERVAL '60 days'
GROUP BY p.category
ORDER BY total_sales DESC;
