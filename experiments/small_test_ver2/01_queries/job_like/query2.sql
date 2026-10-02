-- Query 2: 2テーブルJOIN (JOB-like simple join)
-- カンマJOIN形式で結合条件はWHERE句に記述

SELECT MIN(p.name) AS product_name,
       MIN(o.order_date) AS order_date
FROM orders AS o,
     products AS p
WHERE o.order_date >= CURRENT_DATE - INTERVAL '60 days'
  AND o.product_id = p.product_id;
