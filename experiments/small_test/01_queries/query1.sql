-- クエリ1: 都市別のユーザー集計とフィルタリング
-- (リーフMVと単純集計のテスト)

SELECT 
    u.city,
    COUNT(*) as user_count,
    AVG(u.age) as avg_age,
    COUNT(DISTINCT u.user_id) as distinct_users
FROM users u
WHERE u.age >= 25
GROUP BY u.city
ORDER BY user_count DESC;
