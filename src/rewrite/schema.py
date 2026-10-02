"""IMDBデータベーススキーマ定義"""


# IMDBテーブルのカラム定義
IMDB_SCHEMA: dict[str, list[str]] = {
    "aka_name": [
        "id",
        "person_id",
        "name",
        "imdb_index",
        "name_pcode_cf",
        "name_pcode_nf",
        "surname_pcode",
        "md5sum",
    ],
    "aka_title": [
        "id",
        "movie_id",
        "title",
        "imdb_index",
        "kind_id",
        "production_year",
        "phonetic_code",
        "episode_of_id",
        "season_nr",
        "episode_nr",
        "note",
        "md5sum",
    ],
    "cast_info": ["id", "person_id", "movie_id", "person_role_id", "note", "nr_order", "role_id"],
    "char_name": [
        "id",
        "name",
        "imdb_index",
        "imdb_id",
        "name_pcode_nf",
        "surname_pcode",
        "md5sum",
    ],
    "comp_cast_type": ["id", "kind"],
    "company_name": ["id", "name", "country_code", "imdb_id", "name_pcode_nf", "md5sum"],
    "company_type": ["id", "kind"],
    "complete_cast": ["id", "movie_id", "subject_id", "status_id"],
    "info_type": ["id", "info"],
    "keyword": ["id", "keyword", "phonetic_code"],
    "kind_type": ["id", "kind"],
    "link_type": ["id", "link"],
    "movie_companies": ["id", "movie_id", "company_id", "company_type_id", "note"],
    "movie_info": ["id", "movie_id", "info_type_id", "info", "note"],
    "movie_info_idx": ["id", "movie_id", "info_type_id", "info", "note"],
    "movie_keyword": ["id", "movie_id", "keyword_id"],
    "movie_link": ["id", "movie_id", "linked_movie_id", "link_type_id"],
    "name": [
        "id",
        "name",
        "imdb_index",
        "imdb_id",
        "gender",
        "name_pcode_cf",
        "name_pcode_nf",
        "surname_pcode",
        "md5sum",
    ],
    "person_info": ["id", "person_id", "info_type_id", "info", "note"],
    "role_type": ["id", "role"],
    "title": [
        "id",
        "title",
        "imdb_index",
        "kind_id",
        "production_year",
        "imdb_id",
        "phonetic_code",
        "episode_of_id",
        "season_nr",
        "episode_nr",
        "series_years",
        "md5sum",
    ],
}


def get_table_columns(table_name: str) -> list[str]:
    """テーブルのカラム名を取得

    Args:
        table_name: テーブル名

    Returns:
        カラム名のリスト

    Raises:
        KeyError: テーブルが見つからない場合
    """
    if table_name not in IMDB_SCHEMA:
        raise KeyError(f"Unknown table: {table_name}")
    return IMDB_SCHEMA[table_name]


def validate_table(table_name: str) -> bool:
    """テーブルがスキーマに存在するか確認

    Args:
        table_name: テーブル名

    Returns:
        存在する場合True
    """
    return table_name in IMDB_SCHEMA
