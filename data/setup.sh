#!/bin/bash
wget https://event.cwi.nl/da/job/imdb.tgz
tar -xvzf imdb.tgz
echo "shared_preload_libraries = 'pg_ivm'" >> /var/lib/postgresql/data/postgresql.conf

# echo "shared_preload_libraries = 'pg_ivm'" >> "/mnt/c/Program Files/PostgreSQL/18/data/postgresql.conf"