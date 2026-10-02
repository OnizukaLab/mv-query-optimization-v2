-- ================================================
-- Query rewritten using Advanced Rewrite Engine
-- ================================================
-- Selected MVs: 1
-- Match Type: partial
-- MV Used: mv_leaf_7
-- Matched Tables: o
-- Coverage Score: 20.0%
-- ================================================

SELECT EXTRACT(MONTH
FROM leaf_7 COUNT COUNT SUM SUM AVG AVG MAX MAX
WHERE leaf_7.order_date >= CURRENT_DATE - INTERVAL '120 days'
  AND leaf_7.total_amount >= 100;