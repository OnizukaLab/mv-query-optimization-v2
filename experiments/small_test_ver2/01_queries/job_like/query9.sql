-- Query 9: 若年層の低価格商品購入 (JOB-like)
-- 年齢フィルタ + 価格フィルタ

SELECT MIN(u.name) AS user_name,
       MIN(p.name) AS product_name,
       MIN(p.category) AS category
FROM users AS u,
     orders AS o,
     products AS p
WHERE u.age < 25
  AND p.price < 300
  AND u.user_id = o.user_id
  AND o.product_id = p.product_id;
