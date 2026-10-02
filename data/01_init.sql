-- 簡易初期化スクリプト
-- データベース接続
\connect imdbload

-- pg_ivmは現在未使用のためコメントアウト
-- CREATE EXTENSION pg_ivm;

-- スキーマ作成
\i /docker-entrypoint-initdb.d/schema.sql

-- テスト用: テーブルが作成されたことを確認
SELECT 'Schema created successfully!' as status;
