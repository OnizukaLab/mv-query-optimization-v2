#!/bin/bash
#set -e

run() {
CURDIR=$(cd `dirname $0`; pwd)
OUTDIR=$CURDIR/MV/$1

if [ ! -e $OUTDIR ]; then
    mkdir -p $OUTDIR
fi

cd $CURDIR
total_start=$(date +%s)
count_skipped=0
for file in `ls Output/query_rewrite/mv/*.sql`; do
    bname=`basename $file`
    name=${bname%.*}
    outputfile=$OUTDIR/$name.out
    errorfile=$OUTDIR/$name.err
    echo "run $file > $outputfile"
    start=$(date +%s)
    PGOPTIONS='--statement-timeout=10min' psql -U postgres -d imdbload -f $file >$outputfile 2> $errorfile
    error=$(grep "ERROR:  canceling statement due to statement timeout" $errorfile)
    if [ -n "$error" ]; then
        echo "$file has timed out"
        python remove_mv.py $file $1
        count_skipped=$((count_skipped+1))
    fi
    end=$(date +%s)
    elapsed=$(( $end - $start ))
    echo "elapsed time: $elapsed s" >> $errorfile
done
total_end=$(date +%s)
total_elapsed=$(( $total_end - $total_start ))
echo "Total elapsed time: $total_elapsed s"
echo "MVs skipped: $count_skipped"
}

if [ $# -eq 0 ]; then
    run postgres_r
else
    run $*
fi