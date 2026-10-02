#!/bin/bash
set -e

run() {
CURDIR=$(cd `dirname $0`; pwd)
OUTDIR=$CURDIR/MV/$1

if [ ! -e $OUTDIR ]; then
	mkdir -p $OUTDIR
fi

cd $CURDIR
total_start=$(date +%s)

file=$CURDIR/Output/query_rewrite/mv/$2
if [ -z "$file" ]; then
	echo "No file specified."
	exit 1
fi

bname=`basename $file`
name=${bname%.*}
outputfile=$OUTDIR/$name.out
errorfile=$OUTDIR/$name.err
echo "run $file > $outputfile"
start=$(date +%s)
# if ! timeout 20s bash -c "PGPASSWORD='u039283a' psql -U postgres -h 127.0.0.1 -d imdbload -f $file" >$outputfile 2> $errorfile; then
#     echo "Error1: Execution of $file exceeded 20 seconds and was terminated." >> $errorfile
# fi
#PGPASSWORD='u039283a' psql -U postgres -h 127.0.0.1 -d imdbload -f $file >$outputfile 2> $errorfile
psql -U postgres -d imdbload -f $file >$outputfile 2> $errorfile
end=$(date +%s)
elapsed=$(( $end - $start ))
echo "elapsed time: $elapsed s" >> $errorfile

total_end=$(date +%s)
total_elapsed=$(( $total_end - $total_start ))
echo "Total elapsed time: $total_elapsed s"
}

if [ $# -lt 2 ]; then
	echo "Usage: $0 <output_directory> <sql_file>"
	exit 1
else
	run $1 $2
fi