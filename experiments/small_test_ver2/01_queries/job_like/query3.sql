-- Query 3: 3テーブルJOIN (JOB-like multi-table join)
-- カンマJOIN形式、複数の結合条件

SELECT MIN(u.name) AS user_name,
       MIN(p.name) AS product_name,
       MIN(o.order_date) AS order_date
FROM users AS u,
     orders AS o,
     products AS p
WHERE u.age >= 30 
  AND p.price >= 500
  AND o.order_date >= CURRENT_DATE - INTERVAL '90 days'
  AND u.user_id = o.user_id
  AND o.product_id = p.product_id;
