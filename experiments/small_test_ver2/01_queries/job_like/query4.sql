-- Query 4: 単純スキャン、複数フィルタ (JOB-like)
-- シンプルなフィルタ条件のテスト

SELECT MIN(o.order_id) AS order_id,
       MIN(o.order_date) AS order_date
FROM orders AS o
WHERE o.order_date >= CURRENT_DATE - INTERVAL '120 days'
  AND o.total_amount >= 100;
