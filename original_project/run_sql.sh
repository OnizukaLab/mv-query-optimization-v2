#!/bin/bash
set -e

run() {
CURDIR=$(cd `dirname $0`; pwd)
OUTDIR=$CURDIR/Output/SQL/$1

if [ ! -e $OUTDIR ]; then
    mkdir -p $OUTDIR
fi

cd $CURDIR
total_start=$(date +%s.%N)
for file in `ls dataset/JOB_sql/*.sql`; do
    bname=`basename $file`
    name=${bname%.*}
    outputfile=$OUTDIR/$name.out
    errorfile=$OUTDIR/$name.err
    echo "run $file > $outputfile"
    start=$(date +%s.%N)
    #PGPASSWORD='u039283a' psql -U postgres -h 127.0.0.1 -d imdbload -f $file >$outputfile 2> $errorfile
    psql -U postgres -d imdbload -f $file >$outputfile 2> $errorfile
    end=$(date +%s.%N)
    elapsed=$(echo "$end - $start" | bc)
    echo "elapsed time: $elapsed s" >> $errorfile
done
total_end=$(date +%s.%N)
total_elapsed=$(echo "$total_end - $total_start" | bc)
echo "Total elapsed time: $total_elapsed s"
}

if [ $# -eq 0 ]; then
    run postgres_r
else
    run $*
fi