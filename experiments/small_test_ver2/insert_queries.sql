-- =====================================================
-- 小規模実験用 INSERTクエリ
-- MV保守コスト計算のためのワークロード
-- =====================================================

-- ユーザー追加 (10件)
INSERT INTO users (user_id, name, age, city, registered_date) VALUES
(51, 'Alice Johnson', 28, 'Tokyo', CURRENT_DATE - 10),
(52, 'Bob Smith', 35, 'Osaka', CURRENT_DATE - 15),
(53, 'Carol Davis', 42, 'Nagoya', CURRENT_DATE - 20),
(54, 'David Wilson', 29, 'Fukuoka', CURRENT_DATE - 5),
(55, 'Emma Brown', 31, 'Sapporo', CURRENT_DATE - 12),
(56, 'Frank Miller', 38, 'Tokyo', CURRENT_DATE - 8),
(57, 'Grace Lee', 26, 'Osaka', CURRENT_DATE - 18),
(58, 'Henry Taylor', 45, 'Nagoya', CURRENT_DATE - 25),
(59, 'Ivy Chen', 33, 'Fukuoka', CURRENT_DATE - 7),
(60, 'Jack Anderson', 27, 'Sapporo', CURRENT_DATE - 14);

-- 商品追加 (10件)
INSERT INTO products (product_id, name, category, price, stock) VALUES
(31, 'Wireless Headphones', 'Electronics', 299.99, 50),
(32, 'Coffee Maker', 'Appliances', 149.99, 30),
(33, 'Yoga Mat', 'Sports', 79.99, 100),
(34, 'Board Game', 'Entertainment', 39.99, 75),
(35, 'Desk Lamp', 'Furniture', 89.99, 40),
(36, 'Water Bottle', 'Sports', 24.99, 150),
(37, 'Notebook', 'Stationery', 12.99, 200),
(38, 'Bluetooth Speaker', 'Electronics', 199.99, 60),
(39, 'Cooking Pot', 'Appliances', 69.99, 45),
(40, 'Puzzle Set', 'Entertainment', 19.99, 80);

-- 注文追加 (30件)
INSERT INTO orders (order_id, user_id, product_id, quantity, order_date, total_amount) VALUES
(201, 1, 31, 1, CURRENT_DATE - 1, 299.99),
(202, 2, 32, 1, CURRENT_DATE - 1, 149.99),
(203, 3, 33, 2, CURRENT_DATE - 2, 159.98),
(204, 4, 34, 1, CURRENT_DATE - 2, 39.99),
(205, 5, 35, 1, CURRENT_DATE - 3, 89.99),
(206, 6, 36, 3, CURRENT_DATE - 3, 74.97),
(207, 7, 37, 5, CURRENT_DATE - 4, 64.95),
(208, 8, 38, 1, CURRENT_DATE - 4, 199.99),
(209, 9, 39, 2, CURRENT_DATE - 5, 139.98),
(210, 10, 40, 1, CURRENT_DATE - 5, 19.99),
(211, 11, 31, 1, CURRENT_DATE - 6, 299.99),
(212, 12, 32, 1, CURRENT_DATE - 6, 149.99),
(213, 13, 33, 1, CURRENT_DATE - 7, 79.99),
(214, 14, 34, 2, CURRENT_DATE - 7, 79.98),
(215, 15, 35, 1, CURRENT_DATE - 8, 89.99),
(216, 16, 36, 2, CURRENT_DATE - 8, 49.98),
(217, 17, 37, 3, CURRENT_DATE - 9, 38.97),
(218, 18, 38, 1, CURRENT_DATE - 9, 199.99),
(219, 19, 39, 1, CURRENT_DATE - 10, 69.99),
(220, 20, 40, 4, CURRENT_DATE - 10, 79.96),
(221, 21, 31, 1, CURRENT_DATE - 11, 299.99),
(222, 22, 32, 1, CURRENT_DATE - 11, 149.99),
(223, 23, 33, 1, CURRENT_DATE - 12, 79.99),
(224, 24, 34, 1, CURRENT_DATE - 12, 39.99),
(225, 25, 35, 1, CURRENT_DATE - 13, 89.99),
(226, 26, 36, 1, CURRENT_DATE - 13, 24.99),
(227, 27, 37, 2, CURRENT_DATE - 14, 25.98),
(228, 28, 38, 1, CURRENT_DATE - 14, 199.99),
(229, 29, 39, 1, CURRENT_DATE - 15, 69.99),
(230, 30, 40, 1, CURRENT_DATE - 15, 19.99);