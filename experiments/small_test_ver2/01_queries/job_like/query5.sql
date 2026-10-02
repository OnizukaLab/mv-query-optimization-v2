-- Query 5: 2テーブルJOIN、両テーブルにフィルタ (JOB-like)
-- 選択的フィルタを持つJOIN

SELECT MIN(p.name) AS product_name,
       MIN(o.order_id) AS order_id
FROM products AS p,
     orders AS o
WHERE p.price >= 300
  AND o.total_amount >= 1000
  AND p.product_id = o.product_id;