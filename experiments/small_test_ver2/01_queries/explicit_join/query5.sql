SELECT
    p.category,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_sales,
    AVG(o.quantity) as avg_quantity
FROM products p
INNER JOIN orders o ON p.product_id = o.product_id
WHERE p.price >= 300
  AND o.total_amount >= 1000
GROUP BY p.category
ORDER BY total_sales DESC;