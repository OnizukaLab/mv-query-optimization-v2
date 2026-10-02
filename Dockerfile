FROM postgres:latest

# PostgreSQLの環境変数設定
ENV POSTGRES_PASSWORD=pass
ENV POSTGRES_DB=imdbload

# 必要なツールとPostgreSQL拡張機能インストール
RUN apt-get update && apt-get install -y \
    postgresql-contrib \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ作成
RUN mkdir -p /tmp/imdb_data

# IMDBデータをダウンロードして展開
WORKDIR /tmp/imdb_data
RUN wget -q https://event.cwi.nl/da/job/imdb.tgz && \
    tar -xzf imdb.tgz && \
    rm imdb.tgz

# スキーマファイルとセットアップスクリプトをコピー
COPY ./data/schema.sql /tmp/imdb_data/
COPY ./data/setup.sql /tmp/imdb_data/

# 初期化スクリプトを作成（スキーマ作成→データロード→インデックス作成）
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL\n\
    \\i /tmp/imdb_data/schema.sql\n\
EOSQL\n\
\n\
cd /tmp/imdb_data\n\
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL\n\
    \\copy aka_name from '"'"'aka_name.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy aka_title from '"'"'aka_title.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy cast_info from '"'"'cast_info.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy char_name from '"'"'char_name.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy comp_cast_type from '"'"'comp_cast_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy company_name from '"'"'company_name.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy company_type from '"'"'company_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy complete_cast from '"'"'complete_cast.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy info_type from '"'"'info_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy keyword from '"'"'keyword.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy kind_type from '"'"'kind_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy link_type from '"'"'link_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy movie_companies from '"'"'movie_companies.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy movie_info from '"'"'movie_info.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy movie_info_idx from '"'"'movie_info_idx.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy movie_keyword from '"'"'movie_keyword.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy movie_link from '"'"'movie_link.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy name from '"'"'name.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy person_info from '"'"'person_info.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy role_type from '"'"'role_type.csv'"'"' csv escape '"'"'\\'"'"'\n\
    \\copy title from '"'"'title.csv'"'"' csv escape '"'"'\\'"'"'\n\
EOSQL\n\
\n\
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL\n\
    CREATE INDEX company_id_movie_companies ON movie_companies(company_id);\n\
    CREATE INDEX company_type_id_movie_companies ON movie_companies(company_type_id);\n\
    CREATE INDEX info_type_id_movie_info_idx ON movie_info_idx(info_type_id);\n\
    CREATE INDEX info_type_id_movie_info ON movie_info(info_type_id);\n\
    CREATE INDEX info_type_id_person_info ON person_info(info_type_id);\n\
    CREATE INDEX keyword_id_movie_keyword ON movie_keyword(keyword_id);\n\
    CREATE INDEX kind_id_aka_title ON aka_title(kind_id);\n\
    CREATE INDEX kind_id_title ON title(kind_id);\n\
    CREATE INDEX linked_movie_id_movie_link ON movie_link(linked_movie_id);\n\
    CREATE INDEX link_type_id_movie_link ON movie_link(link_type_id);\n\
    CREATE INDEX movie_id_aka_title ON aka_title(movie_id);\n\
    CREATE INDEX movie_id_cast_info ON cast_info(movie_id);\n\
    CREATE INDEX movie_id_complete_cast ON complete_cast(movie_id);\n\
    CREATE INDEX movie_id_movie_companies ON movie_companies(movie_id);\n\
    CREATE INDEX movie_id_movie_info_idx ON movie_info_idx(movie_id);\n\
    CREATE INDEX movie_id_movie_keyword ON movie_keyword(movie_id);\n\
    CREATE INDEX movie_id_movie_link ON movie_link(movie_id);\n\
    CREATE INDEX movie_id_movie_info ON movie_info(movie_id);\n\
    CREATE INDEX person_id_aka_name ON aka_name(person_id);\n\
    CREATE INDEX person_id_cast_info ON cast_info(person_id);\n\
    CREATE INDEX person_id_person_info ON person_info(person_id);\n\
    CREATE INDEX person_role_id_cast_info ON cast_info(person_role_id);\n\
    CREATE INDEX role_id_cast_info ON cast_info(role_id);\n\
EOSQL\n\
' > /docker-entrypoint-initdb.d/01_load_imdb.sh && \
    chmod +x /docker-entrypoint-initdb.d/01_load_imdb.sh

WORKDIR /

# PostgreSQL設定
# 【変更点】
#   effective_cache_size: 6GB → 8GB（メモリ16GB制限に対して適切な値に調整）
#   max_parallel_workers: 追加（実用環境を想定、方針B）
#   max_parallel_workers_per_gather: 追加（実用環境を想定、方針B）
#   max_parallel_maintenance_workers: 追加（MV作成時の並列度を明示）
#   jit: off 追加（初回実行ノイズの排除、再現性確保）
CMD ["postgres", \
     "-c", "shared_buffers=2GB", \
     "-c", "effective_cache_size=8GB", \
     "-c", "work_mem=128MB", \
     "-c", "maintenance_work_mem=1GB", \
     "-c", "random_page_cost=1.1", \
     "-c", "effective_io_concurrency=200", \
     "-c", "max_parallel_workers=8", \
     "-c", "max_parallel_workers_per_gather=2", \
     "-c", "max_parallel_maintenance_workers=2", \
     "-c", "jit=off", \
     "-c", "max_locks_per_transaction=256"]