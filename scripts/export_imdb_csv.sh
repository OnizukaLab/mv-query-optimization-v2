#!/bin/bash
# PostgreSQLコンテナからIMDBテーブルをCSVエクスポート
# 使用方法: bash scripts/export_imdb_csv.sh

set -e

CONTAINER="mv_postgres"
DB="imdbload"
OUTPUT_DIR="deepdb/deepdb-public/imdb_csv"

echo "=========================================="
echo "IMDB CSV Export Script"
echo "=========================================="

# 出力ディレクトリ作成
mkdir -p "$OUTPUT_DIR"
echo "Output directory: $OUTPUT_DIR"

# エクスポート対象テーブル（DeepDB gen_imdb_schema に合わせる）
# Full JOB対応のため movie_link, link_type を追加
TABLES=(
    "title"
    "movie_info"
    "movie_info_idx"
    "cast_info"
    "movie_keyword"
    "movie_companies"
    "movie_link"
    "link_type"
    "name"
    "char_name"
    "keyword"
    "company_name"
    "info_type"
    "kind_type"
    "role_type"
    "company_type"
    "comp_cast_type"
    "complete_cast"
    "aka_name"
    "aka_title"
    "person_info"
)

echo ""
echo "Exporting ${#TABLES[@]} tables..."
echo ""

for TABLE in "${TABLES[@]}"; do
    echo -n "  $TABLE... "
    docker exec "$CONTAINER" psql -U postgres -d "$DB" \
        -c "\COPY $TABLE TO STDOUT WITH CSV HEADER" \
        > "$OUTPUT_DIR/$TABLE.csv" 2>/dev/null
    
    # ファイルサイズを表示
    SIZE=$(du -h "$OUTPUT_DIR/$TABLE.csv" | cut -f1)
    ROWS=$(wc -l < "$OUTPUT_DIR/$TABLE.csv")
    echo "done ($ROWS rows, $SIZE)"
done

echo ""
echo "=========================================="
echo "Export complete!"
echo "Total files: $(ls -1 "$OUTPUT_DIR"/*.csv | wc -l)"
echo "Total size: $(du -sh "$OUTPUT_DIR" | cut -f1)"
echo "=========================================="
