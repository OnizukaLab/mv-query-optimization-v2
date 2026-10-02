-- =====================================================
-- NORMAL アルゴリズム - morning
-- =====================================================

\c mv_small_test

-- ノード: leaf_1
CREATE MATERIALIZED VIEW leaf_1 AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age >= 25)
;

-- ノード: leaf_4
CREATE MATERIALIZED VIEW leaf_4 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE (order_date >= (CURRENT_DATE - '90 days'::interval))
;

-- ノード: leaf_7
CREATE MATERIALIZED VIEW leaf_7 AS
SELECT o.order_id, o.user_id, o.product_id, o.quantity, o.order_date, o.total_amount
FROM orders AS o
WHERE ((total_amount >= '100'::numeric) AND (order_date >= (CURRENT_DATE - '120 days'::interval)))
;

-- ノード: leaf_12
CREATE MATERIALIZED VIEW leaf_12 AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE ((category)::text = 'Electronics'::text)
;

-- ノード: leaf_15
CREATE MATERIALIZED VIEW leaf_15 AS
SELECT u.user_id, u.name, u.age, u.city, u.registered_date
FROM users AS u
WHERE (age < 25)
;

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

-- ノード: non_leaf_28
CREATE MATERIALIZED VIEW non_leaf_28 AS
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
WHERE o.user_id = u.user_id AND o.product_id = p.product_id AND (u.age >= 30) AND (p.price >= '500'::numeric);

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

