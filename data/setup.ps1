#!/usr/bin/env pwsh
# Windows版 setup.sh
Invoke-WebRequest -Uri "https://event.cwi.nl/da/job/imdb.tgz" -OutFile "imdb.tgz"
tar -xzf imdb.tgz
