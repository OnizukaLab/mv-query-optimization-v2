-- クエリ1: 都市別のユーザー集計とフィルタリング
-- (リーフMVと単純集計のテスト)

SELECT 
    MIN(u.city) as city,
    MIN(u.age) as age
FROM users u
WHERE u.age >= 25;
