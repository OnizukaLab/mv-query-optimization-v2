#!/bin/bash
# Read-only file system エラーの修正スクリプト

set -e

echo "========================================="
echo "PostgreSQL Read-Only File System 修正"
echo "========================================="
echo ""

# Step 1: 現在のコンテナを停止
echo "Step 1: コンテナを停止..."
docker stop mv_postgres || true
echo "✓ コンテナを停止しました"
echo ""

# Step 2: コンテナを削除（ボリュームは保持）
echo "Step 2: コンテナを削除（データは保持）..."
docker rm mv_postgres || true
echo "✓ コンテナを削除しました"
echo ""

# Step 3: ボリュームの権限を確認
echo "Step 3: ボリュームの確認..."
docker volume inspect mv_postgres_data || echo "警告: ボリュームが見つかりません"
echo ""

# Step 4: 新しいコンテナを起動
echo "Step 4: 新しいコンテナを起動..."
docker run -d \
  --name mv_postgres \
  -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data \
  mv_postgres:1.0

echo "✓ コンテナを起動しました"
echo ""

# Step 5: PostgreSQLの起動を待つ
echo "Step 5: PostgreSQL起動を待機中..."
sleep 10

# Step 6: 接続確認
echo "Step 6: データベース接続確認..."
for i in {1..30}; do
  if docker exec mv_postgres psql -U postgres -d imdbload -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✓ データベースに接続できました"
    break
  fi
  echo "待機中... ($i/30)"
  sleep 2
done
echo ""

# Step 7: ANALYZE実行
echo "Step 7: ANALYZE実行..."
docker exec mv_postgres psql -U postgres -d imdbload -c "ANALYZE VERBOSE;" || {
  echo "エラー: ANALYZEに失敗しました"
  echo ""
  echo "以下を確認してください:"
  echo "1. ディスク容量: docker system df"
  echo "2. コンテナログ: docker logs mv_postgres"
  exit 1
}
echo "✓ ANALYZEが完了しました"
echo ""

echo "========================================="
echo "修正完了!"
echo "========================================="
echo ""
echo "次のコマンドで統計情報を確認できます:"
echo "docker exec -it mv_postgres psql -U postgres -d imdbload -c \"SELECT schemaname, tablename, last_analyze FROM pg_stat_user_tables;\""
