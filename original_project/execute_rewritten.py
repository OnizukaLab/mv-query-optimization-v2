import sys
import os
import time

ilp_types =  ["normal", "bigsubs", "utility_capacity", "utility", "frequency", "none"]

input_folder = "Output/query_rewrite/re_sql/"

from utils import *

## command line argument handler
if len(sys.argv) < 2:
	print(f"Usage: {sys.argv[0]} <ILP type>")
	print("ILP types :")
	for ilp in ilp_types:
		print(f"	{ilp}")
else:
	match sys.argv[1]:
		case "normal":
			input_folder += "normal"
		case "bigsubs":
			input_folder += "bigsubs"
		case "utility_capacity":
			input_folder += "proposed_u_b"
		case "utility":
			input_folder += "proposed_u"
		case "frequency":
			input_folder += "proposed_f"
		case "none":
			input_folder = "dataset/RED_SQL"
		case _:
			print("Non valid argument")
			exit(0)

"""
Returns list of all files in the given folder
"""	
def getAllFiles(path):
		res = []
		for folder, _ , files in os.walk(path):
			temp = [folder +'/'+ f for f in files]
			res = res + temp
		return res

os.listdir()

workloads_dir = "Output/RED_WORKLOADS"

files = getAllFiles(input_folder)
if sys.argv[1] == "none":
	files = get_red_queries_sql(input_folder, workloads_dir, GET_CEB)[0]

files = sorted(files, key= lambda f: natural_sort_key(os.path.basename(f)))

t1 = time.time()
for file in files:
	print(file)
	os.system(f"PGOPTIONS='--statement-timeout=30min' psql -U postgres -d imdbload -f {file}")
t2 = time.time()
print("Time: ", t2-t1)
    