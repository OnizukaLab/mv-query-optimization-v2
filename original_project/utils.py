import os
import re

GET_CEB = True


"""
Function returns all query jsons for redbench

source_path: path to the json files
workloads_dir: path to the redbench workloads
get_ceb: If False then the function returns the JOB queries or else it returns the JOB queries

return: List of all the jsons that are used in redbench and a dictionary with number of occurences of each file
"""
def get_red_queries(source_path, workloads_dir, get_ceb = False):
    query_paths = []
    query_count = {}
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path+'/job/'+line.split(",")[0].split('/')[-1]
                    query_path = query_path.split(".")[0] + ".json"
                else:
                    query_path = source_path+'/'+"/".join(line.split(",")[0].split('/')[2:])
                    query_path = query_path.split(".")[0] + ".json"
                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


"""
Function returns all query sql for redbench

source_path: path to the sql files
workloads_dir: path to the redbench workloads
get_ceb: If False then the function returns the JOB queries or else it returns the JOB queries

return: List of all the sql that are used in redbench and a dictionary with number of occurences of each file
"""
def get_red_queries_sql(source_path, workloads_dir, get_ceb = False):
    query_paths = []
    query_count = {}
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path+'/job/'+line.split(",")[0].split('/')[-1]
                else:
                    query_path = source_path+'/'+"/".join(line.split(",")[0].split('/')[2:])
                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count

def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


"""
Function returns all query jsons for redbench 
and writes in a csv file all the queries used with how many times thay are used in redbench 

source_path: path to the json files
workloads_dir: path to the redbench workloads
get_ceb: If False then the function returns the JOB queries or else it returns the JOB queries

return: List of all the jsons that are used in redbench and a dictionary with number of occurences of each file
"""
def get_red_queries_to_file(source_path, workloads_dir, get_ceb = False):
    query_paths = []
    query_count = {}
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path+'/job/'+line.split(",")[0].split('/')[-1]
                    query_path = query_path.split(".")[0] + ".json" # file name
                else:
                    query_path = source_path+'/'+"/".join(line.split(",")[0].split('/')[2:])
                    query_path = query_path.split(".")[0] + ".json"
                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    query_paths = sorted(query_paths, key=natural_sort_key)

    with open("red_queries.csv", "w+", newline="") as f:
        for line in query_paths:
            f.write(line + "," + str(query_count[line]) + "\n")

    return query_paths, query_count

if __name__ == "__main__":
    workloads_dir = "Output/RED_WORKLOADS"
    json_path = "dataset/RED_JSON"
    get_red_queries_to_file(json_path, workloads_dir, GET_CEB)