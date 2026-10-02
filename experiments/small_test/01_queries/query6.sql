SELECT 
    u.city,
    p.category,
    u.age,
    COUNT(DISTINCT u.user_id) as unique_customers,
    COUNT(o.order_id) as total_orders,
    SUM(o.quantity) as total_quantity,
    SUM(o.total_amount) as total_revenue,
    AVG(o.total_amount) as avg_order_value
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
INNER JOIN products p ON o.product_id = p.product_id
WHERE o.order_date >= CURRENT_DATE - INTERVAL '90 days'
  AND u.age >= 25
GROUP BY u.city, p.category, u.age
HAVING COUNT(o.order_id) >= 1
ORDER BY total_revenue DESC, u.city, p.category;
