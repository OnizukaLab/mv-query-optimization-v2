-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 1
-- Match Type: full
-- MV Used: mv_leaf_1
-- Matched Tables: u
-- Coverage Score: 100.0%
-- ================================================

SELECT leaf_1.city,
    COUNT(*) as user_count,
    AVG(leaf_1.age) as avg_age,
    COUNT(DISTINCT leaf_1.user_id) as distinct_users
FROM leaf_1
WHERE leaf_1.age >= 25
GROUP BY leaf_1.city
ORDER BY user_count DESC;