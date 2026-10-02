-- Query 6: 3テーブルJOIN、時間依存フィルタ (JOB-like)
-- 最近の注文データを対象

SELECT MIN(u.name) AS user_name,
       MIN(p.name) AS product_name,
       MIN(u.city) AS city
FROM users AS u,
     orders AS o,
     products AS p
WHERE o.order_date >= CURRENT_DATE - INTERVAL '90 days'
  AND u.age >= 25
  AND u.user_id = o.user_id
  AND o.product_id = p.product_id;
