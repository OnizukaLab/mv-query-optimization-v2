import os
import json
import time

json_path = "dataset/RED_JSON/job"
sql_path = "dataset/RED_SQL/job"

query = "1a"
delete_file = "dataset/alpha/title_delete.sql"
insert_file = "dataset/alpha/title_insert.sql"

t1 = time.time()
os.system(f"psql -U postgres -d imdbload -f {sql_path}/{query}.sql")
t2 = time.time()

query_execution_time = t2-t1


os.system(f"psql -U postgres -d imdbload -f {delete_file}")

t1 = time.time()
os.system(f"psql -U postgres -d imdbload -f {insert_file}")
t2 = time.time()


insert_execution_time = t2-t1

with open(f'{json_path}/{query}.json', 'r') as file:
    data = json.load(file)

#query_estimated_time = data[0]["Plan"]["Actual Total Time"]
query_estimated_time = data[0]["Plan"]["Total Cost"]

alpha = insert_execution_time * query_estimated_time

alpha = alpha/query_execution_time

print()
print("ALPHA MEASURE : ")
print()
print("Query execution time : ", query_execution_time)
print("Query estimated time : ", query_estimated_time)
print("Insert execution time : ", insert_execution_time)
print("Alpha : ", alpha)