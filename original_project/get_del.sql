\t
--SELECT 'DROP MATERIALIZED VIEW ' || string_agg(oid::regclass::text, ', ')
--FROM   pg_class
--WHERE  relkind = 'm';
SELECT 'DROP TABLE ' || string_agg(immvrelid::regclass::text, ', ')
FROM pgivm.pg_ivm_immv;
