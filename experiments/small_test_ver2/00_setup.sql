-- =====================================================
-- 小規模実験用 テーブル・データ作成スクリプト
-- =====================================================
-- 使い方: psql -U postgres -f 00_setup.sql

-- データベース作成 (既存の場合は削除)
DROP DATABASE IF EXISTS mv_small_test;
CREATE DATABASE mv_small_test;

-- 新しいデータベースに接続
\c mv_small_test

-- =====================================================
-- テーブル作成
-- =====================================================

-- ユーザーテーブル
DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    age INTEGER,
    city VARCHAR(100),
    registered_date DATE
);

-- 商品テーブル
DROP TABLE IF EXISTS products CASCADE;
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10,2),
    stock INTEGER
);

-- 注文テーブル
DROP TABLE IF EXISTS orders CASCADE;
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER,
    order_date DATE,
    total_amount DECIMAL(10,2)
);

-- =====================================================
-- インデックス作成
-- =====================================================

CREATE INDEX idx_users_city ON users(city);
CREATE INDEX idx_users_age ON users(age);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_product_id ON orders(product_id);
CREATE INDEX idx_orders_date ON orders(order_date);

-- =====================================================
-- サンプルデータ挿入
-- =====================================================

-- ユーザーデータ (50件)
INSERT INTO users (user_id, name, age, city, registered_date)
SELECT 
    i,
    'User_' || i,
    20 + (i % 40),
    CASE (i % 5)
        WHEN 0 THEN 'Tokyo'
        WHEN 1 THEN 'Osaka'
        WHEN 2 THEN 'Kyoto'
        WHEN 3 THEN 'Fukuoka'
        ELSE 'Sapporo'
    END,
    CURRENT_DATE - (i * 10)
FROM generate_series(1, 50) AS i;

-- 商品データ (30件)
INSERT INTO products (product_id, name, category, price, stock)
SELECT 
    i,
    'Product_' || i,
    CASE (i % 3)
        WHEN 0 THEN 'Electronics'
        WHEN 1 THEN 'Books'
        ELSE 'Clothing'
    END,
    (i * 100.0)::DECIMAL(10,2),
    100 + (i * 5)
FROM generate_series(1, 30) AS i;

-- 注文データ (200件)
INSERT INTO orders (order_id, user_id, product_id, quantity, order_date, total_amount)
SELECT 
    i,
    1 + (i % 50),                                    -- user_id
    1 + (i % 30),                                    -- product_id
    1 + (i % 5),                                     -- quantity
    CURRENT_DATE - ((i % 180)),                      -- order_date
    ((1 + (i % 30)) * 100.0 * (1 + (i % 5)))::DECIMAL(10,2)  -- total_amount
FROM generate_series(1, 200) AS i;

-- =====================================================
-- 統計情報更新
-- =====================================================

ANALYZE users;
ANALYZE products;
ANALYZE orders;

-- =====================================================
-- 確認クエリ
-- =====================================================

\echo '===== テーブル作成完了 ====='
\echo ''
\echo '--- ユーザー数 ---'
SELECT COUNT(*) as user_count FROM users;

\echo ''
\echo '--- 商品数 ---'
SELECT COUNT(*) as product_count FROM products;

\echo ''
\echo '--- 注文数 ---'
SELECT COUNT(*) as order_count FROM orders;

\echo ''
\echo '--- 都市別ユーザー数 ---'
SELECT city, COUNT(*) as count FROM users GROUP BY city ORDER BY count DESC;

\echo ''
\echo '--- カテゴリ別商品数 ---'
SELECT category, COUNT(*) as count FROM products GROUP BY category ORDER BY count DESC;

\echo ''
\echo '===== セットアップ完了 ====='
