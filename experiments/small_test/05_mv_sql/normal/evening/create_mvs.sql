-- =====================================================
-- NORMAL アルゴリズム - evening
-- =====================================================

\c mv_small_test

-- ノード: leaf_15
CREATE MATERIALIZED VIEW leaf_15 AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age < 25)
;

-- ノード: non_leaf_5
CREATE MATERIALIZED VIEW non_leaf_5 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , products AS p
WHERE o.product_id = p.product_id AND (o.order_date >= (CURRENT_DATE - '60 days'::interval));

-- ノード: non_leaf_12
CREATE MATERIALIZED VIEW non_leaf_12 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    u.user_id AS u_user_id,
    u.name,
    u.age,
    u.city,
    u.registered_date,
    p.product_id AS p_product_id,
    p.name AS p_name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , users AS u , products AS p
WHERE o.user_id = u.user_id AND o.product_id = p.product_id AND (o.order_date >= (CURRENT_DATE - '90 days'::interval)) AND (u.age >= 30) AND (p.price >= '500'::numeric);

-- ノード: non_leaf_17
CREATE MATERIALIZED VIEW non_leaf_17 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , products AS p
WHERE o.product_id = p.product_id AND (o.total_amount >= '1000'::numeric) AND (p.price >= '300'::numeric);

-- ノード: non_leaf_20
CREATE MATERIALIZED VIEW non_leaf_20 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    u.user_id AS u_user_id,
    u.name,
    u.age,
    u.city,
    u.registered_date
FROM orders AS o , users AS u
WHERE o.user_id = u.user_id AND (o.order_date >= (CURRENT_DATE - '90 days'::interval)) AND (u.age >= 25);

-- ノード: non_leaf_33
CREATE MATERIALIZED VIEW non_leaf_33 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock,
    u.user_id AS u_user_id,
    u.name AS u_name,
    u.age,
    u.city,
    u.registered_date
FROM orders AS o , products AS p , users AS u
WHERE o.user_id = u.user_id AND o.product_id = p.product_id AND (o.order_date >= '2024-01-01'::date) AND ((p.category)::text = 'Electronics'::text);

-- ノード: non_leaf_38
CREATE MATERIALIZED VIEW non_leaf_38 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM orders AS o , products AS p
WHERE o.product_id = p.product_id AND (p.price < '300'::numeric);

