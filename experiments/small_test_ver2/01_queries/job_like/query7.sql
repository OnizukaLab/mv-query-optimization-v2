-- Query 7: 高額商品購入ユーザー (JOB-like)
-- 商品価格フィルタ + ユーザー年齢フィルタ

SELECT MIN(u.name) AS user_name,
       MIN(p.name) AS product_name,
       MIN(u.city) AS city
FROM users AS u,
     orders AS o,
     products AS p
WHERE p.price >= 500
  AND u.age >= 30
  AND u.user_id = o.user_id
  AND o.product_id = p.product_id;
