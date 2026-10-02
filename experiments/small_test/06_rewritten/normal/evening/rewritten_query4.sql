-- No MVs selected for this query
-- Using original tables

-- クエリ4: 時間帯別の注文分析
-- (日付フィルタと集計のバリエーション)

SELECT 
    EXTRACT(MONTH FROM o.order_date) as order_month,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_sales,
    AVG(o.total_amount) as avg_order_value,
    MAX(o.total_amount) as max_order_value
FROM orders o
WHERE o.order_date >= CURRENT_DATE - INTERVAL '120 days'
  AND o.total_amount >= 100
GROUP BY order_month
ORDER BY order_month DESC;
