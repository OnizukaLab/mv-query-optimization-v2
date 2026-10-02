-- Query 8: 特定カテゴリ購入ユーザー (JOB-like)
-- カテゴリフィルタ + 日付フィルタ

SELECT MIN(u.name) AS user_name,
       MIN(p.name) AS product_name,
       MIN(u.city) AS city
FROM users AS u,
     orders AS o,
     products AS p
WHERE p.category = 'Electronics'
  AND o.order_date >= '2024-01-01'
  AND u.user_id = o.user_id
  AND o.product_id = p.product_id;
