psql -U postgres -d imdbload -f get_del.sql > output
tail output -n 2 > delete_mv.sql
psql -U postgres -d imdbload -f delete_mv.sql
rm output delete_mv.sql