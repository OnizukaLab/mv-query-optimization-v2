create or replace function update_mvs(table_name text)
  returns boolean as $$
declare
    r RECORD;
begin

    FOR r IN SELECT matviewname FROM pg_matviews where definition LIKE '%' || table_name || '%'
    LOOP
        RAISE NOTICE 'Refreshing %', r.matviewname;
        EXECUTE 'REFRESH MATERIALIZED VIEW ' || r.matviewname; 
    END LOOP;

    RETURN True;
end;
$$ language 'plpgsql';

create or replace function pact.insert_aka_name()
  returns trigger as $$
begin
    select update_mvs('aka_name');

    RETURN NEW;
end;
$$ language 'plpgsql';

create or replace trigger tg_insert_aka_name
after insert on aka_name
  for each statement execute procedure insert_aka_name();