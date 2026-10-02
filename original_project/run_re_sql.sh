#!/bin/bash
set -e

run() {
CURDIR=$(cd `dirname $0`; pwd)
OUTDIR=$CURDIR/Output/RE_SQL/$1

if [ ! -e $OUTDIR ]; then
	mkdir -p $OUTDIR
fi

cd $CURDIR
total_start=$(date +%s)
for folder in bigsubs normal proposed_u_b proposed_u proposed_f; do
	for file in `ls Output/query_rewrite/re_sql/$folder/*.sql`; do
		bname=`basename $file`
		name=${bname%.*}
		outputfile=$OUTDIR/$folder/$name.out
		errorfile=$OUTDIR/$folder/$name.err
		mkdir -p $OUTDIR/$folder
		echo "run $file > $outputfile"
		start=$(date +%s)
		#PGPASSWORD='u039283a' psql -U postgres -h 127.0.0.1 -d imdbload -f $file >$outputfile 2> $errorfile
		psql -U postgres -d imdbload -f $file >$outputfile 2> $errorfile
		end=$(date +%s)
		elapsed=$(( $end - $start ))
		echo "elapsed time: $elapsed s" >> $errorfile
	done
done
total_end=$(date +%s)
total_elapsed=$(( $total_end - $total_start ))
echo "Total elapsed time: $total_elapsed s"
}

if [ $# -eq 0 ]; then
	run postgres_r
else
	run $*
fi