-- morning -> evening のマイグレーション SQL
-- =====================================================

-- CREATE MATERIALIZED VIEW
CREATE MATERIALIZED VIEW leaf_7 AS
SELECT p.product_id, p.name, p.category, p.price, p.stock
FROM products AS p
WHERE (price >= '500'::numeric);

CREATE MATERIALIZED VIEW non_leaf_16 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    leaf_11.product_id AS p_product_id,
    leaf_11.name,
    leaf_11.category,
    leaf_11.price,
    leaf_11.stock
FROM leaf_11, orders AS o
WHERE o.product_id = leaf_11.product_id AND (o.total_amount >= '1000'::numeric);

CREATE MATERIALIZED VIEW non_leaf_28 AS
SELECT o.order_id,
    o.user_id,
    o.product_id,
    o.quantity,
    o.order_date,
    o.total_amount,
    leaf_15.product_id AS p_product_id,
    leaf_15.name,
    leaf_15.category,
    leaf_15.price,
    leaf_15.stock,
    u.user_id AS u_user_id,
    u.name AS u_name,
    u.age,
    u.city,
    u.registered_date
FROM leaf_15, orders AS o, users AS u
WHERE o.product_id = leaf_15.product_id AND o.user_id = u.user_id AND (o.order_date >= '2024-01-01'::date);

CREATE MATERIALIZED VIEW non_leaf_5 AS
SELECT leaf_3.order_id,
    leaf_3.user_id,
    leaf_3.product_id,
    leaf_3.quantity,
    leaf_3.order_date,
    leaf_3.total_amount,
    p.product_id AS p_product_id,
    p.name,
    p.category,
    p.price,
    p.stock
FROM leaf_3, products AS p
WHERE leaf_3.product_id = p.product_id;

