--CREATE DATABASE imdbload;

\connect imdbload

-- pg_ivm 1.14 インストール済み (2026-06-05, PG17 対応)
-- 初回セットアップ時は以下を実行: CREATE EXTENSION pg_ivm;
-- src/maintenance/ パッケージ経由で使用する (直接呼び出し不要)

\i schema.sql

\copy aka_name from 'aka_name.csv' csv escape '\'
\copy aka_title from 'aka_title.csv' csv escape '\'
\copy cast_info from 'cast_info.csv' csv escape '\'
\copy char_name from 'char_name.csv' csv escape '\'
\copy comp_cast_type from 'comp_cast_type.csv' csv escape '\'
\copy company_name from 'company_name.csv' csv escape '\'
\copy company_type from 'company_type.csv' csv escape '\'
\copy complete_cast from 'complete_cast.csv' csv escape '\'
\copy info_type from 'info_type.csv' csv escape '\'
\copy keyword from 'keyword.csv' csv escape '\'
\copy kind_type from 'kind_type.csv' csv escape '\'
\copy link_type from 'link_type.csv' csv escape '\'
\copy movie_companies from 'movie_companies.csv' csv escape '\'
\copy movie_info from 'movie_info.csv' csv escape '\'
\copy movie_info_idx from 'movie_info_idx.csv' csv escape '\'
\copy movie_keyword from 'movie_keyword.csv' csv escape '\'
\copy movie_link from 'movie_link.csv' csv escape '\'
\copy name from 'name.csv' csv escape '\'
\copy person_info from 'person_info.csv' csv escape '\'
\copy role_type from 'role_type.csv' csv escape '\'
\copy title from 'title.csv' csv escape '\'

create index company_id_movie_companies on movie_companies(company_id);
create index company_type_id_movie_companies on movie_companies(company_type_id);
create index info_type_id_movie_info_idx on movie_info_idx(info_type_id);
create index info_type_id_movie_info on movie_info(info_type_id);
create index info_type_id_person_info on person_info(info_type_id);
create index keyword_id_movie_keyword on movie_keyword(keyword_id);
create index kind_id_aka_title on aka_title(kind_id);
create index kind_id_title on title(kind_id);
create index linked_movie_id_movie_link on movie_link(linked_movie_id);
create index link_type_id_movie_link on movie_link(link_type_id);
create index movie_id_aka_title on aka_title(movie_id);
create index movie_id_cast_info on cast_info(movie_id);
create index movie_id_complete_cast on complete_cast(movie_id);
create index movie_id_movie_companies on movie_companies(movie_id);
create index movie_id_movie_info_idx on movie_info_idx(movie_id);
create index movie_id_movie_keyword on movie_keyword(movie_id);
create index movie_id_movie_link on movie_link(movie_id);
create index movie_id_movie_info on movie_info(movie_id);
create index person_id_aka_name on aka_name(person_id);
create index person_id_cast_info on cast_info(person_id);
create index person_id_person_info on person_info(person_id);
create index person_role_id_cast_info on cast_info(person_role_id);
create index role_id_cast_info on cast_info(role_id);