#!/bin/bash
# PostgreSQLのステータス確認スクリプト

echo "========================================="
echo "1. アクティブなセッション"
echo "========================================="
docker exec -it mv_postgres psql -U postgres -d imdbload -c "
SELECT 
    pid, 
    usename, 
    state, 
    wait_event_type,
    wait_event,
    now() - query_start as duration,
    LEFT(query, 120) as query 
FROM pg_stat_activity 
WHERE state != 'idle' 
ORDER BY query_start;
"

echo ""
echo "========================================="
echo "2. ロック状況"
echo "========================================="
docker exec -it mv_postgres psql -U postgres -d imdbload -c "
SELECT 
    l.pid,
    c.relname,
    l.locktype,
    l.mode,
    l.granted,
    a.state,
    LEFT(a.query, 80) as query
FROM pg_locks l
LEFT JOIN pg_class c ON l.relation = c.oid
LEFT JOIN pg_stat_activity a ON l.pid = a.pid
WHERE l.locktype = 'relation' AND c.relname IS NOT NULL
ORDER BY l.granted, c.relname;
"

echo ""
echo "========================================="
echo "3. 存在するMV一覧"
echo "========================================="
docker exec -it mv_postgres psql -U postgres -d imdbload -c "
SELECT 
    matviewname,
    ispopulated,
    pg_size_pretty(pg_total_relation_size('public.' || matviewname)) as size
FROM pg_matviews 
WHERE schemaname = 'public'
ORDER BY matviewname;
"

echo ""
echo "========================================="
echo "4. ブロッキング状況（ロック待ち）"
echo "========================================="
docker exec -it mv_postgres psql -U postgres -d imdbload -c "
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS blocking_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
"

echo ""
echo "========================================="
echo "5. 長時間実行中のクエリ"
echo "========================================="
docker exec -it mv_postgres psql -U postgres -d imdbload -c "
SELECT 
    pid,
    now() - query_start AS duration,
    state,
    LEFT(query, 100) AS query
FROM pg_stat_activity
WHERE state != 'idle'
    AND now() - query_start > interval '10 seconds'
ORDER BY duration DESC;
"
