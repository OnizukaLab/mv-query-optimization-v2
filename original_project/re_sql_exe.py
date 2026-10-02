import csv
import query_rewrite_beta as query_rewrite_beta
import test as test
import time
import sys

from query_parse_beta import QueryParser
from query_parse_beta import QueryManager


normal_ILP = False
bigsubs_ILP = False
utility_capacity_based_ILP = False
utility_based_ILP = False
frequency_based_ILP = False

query_mv = True
query_rewrite = False
count_mv_time = False
count_rewrite_time = False

query_result_path = "Output/"

ilp_types =  ["normal", "bigsubs", "utility_capacity", "utility", "frequency"]

## command line argument handler
if len(sys.argv) < 2:
	print(f"Usage: {sys.argv[0]} <ILP type>")
	print("ILP types :")
	for ilp in ilp_types:
		print(f"	{ilp}")
else:
	match sys.argv[1]:
		case "normal":
			normal_ILP = True
		case "bigsubs":
			bigsubs_ILP = True
		case "utility_capacity":
			utility_capacity_based_ILP = True
		case "utility":
			utility_based_ILP = True
		case "frequency":
			frequency_based_ILP = True
		case _:
			print("Non valid argument")
			exit(0)

# Get all subquery from files

mv_nodes = []
mv_nodes_count_list = []
mv_files_count_list = []

if normal_ILP:
	mv_nodes_normal = []
	with open(query_result_path + "normal/mv_y_list.csv", "r") as f:
		reader = csv.reader(f)
		normal_mv_rows = list(reader)
		# print("normal_mv_rows: ", normal_mv_rows)
		for row in normal_mv_rows:
			if len(row) > 1:
				for r in row:
					mv_nodes_normal.append(r)
			else:
				if len(row) == 0:
					continue
				mv_nodes_normal.append(row[0])
		
		for node in mv_nodes_normal:
			if node not in mv_nodes:
				mv_nodes.append(node)
	
	if query_rewrite:
		query_rewrite_beta.query_rewrite("normal",normal_mv_rows)
	# print("mv_nodes_normal: ", mv_nodes_normal)
	# print("Normal")
	if count_mv_time:
		mv_files_count_list.append("Normal")
		mv_nodes_count_list.append(mv_nodes_normal)
		#test.count_mv_exe_time(mv_nodes_normal)

if bigsubs_ILP:
	mv_nodes_bigsubs = []
	with open(query_result_path + "bigsubs/mv_y_list.csv", "r", newline='') as f:
		reader = csv.reader(f)
		bigsubs_mv_rows = list(reader)
		print("bg row len : ", len(bigsubs_mv_rows))
		for row in bigsubs_mv_rows:
			if len(row) > 1:
				for r in row:
					mv_nodes_bigsubs.append(r)
			else:
				if len(row) == 0:
					mv_nodes_bigsubs.append("NONE")
					continue
				mv_nodes_bigsubs.append(row[0])
		
		for node in mv_nodes_bigsubs:
			if node not in mv_nodes:
				mv_nodes.append(node)

	if query_rewrite:
		query_rewrite_beta.query_rewrite("bigsubs",bigsubs_mv_rows)
	# print("Bigsubs")
	if count_mv_time:
		mv_files_count_list.append("Bigsubs")
		mv_nodes_count_list.append(mv_nodes_bigsubs)
		# test.count_mv_exe_time(mv_nodes_bigsubs)

if utility_capacity_based_ILP:
	mv_nodes_utility_capacity_based = []
	with open(query_result_path + "proposed_u_b/mv_y_list.csv", "r") as f:
		reader = csv.reader(f)
		proposed_u_b_mv_rows = list(reader)
		for row in proposed_u_b_mv_rows:
			if len(row) > 1:
				for r in row:
					mv_nodes_utility_capacity_based.append(r)
			else:
				if len(row) == 0:
					continue
				mv_nodes_utility_capacity_based.append(row[0])
		
		for node in mv_nodes_utility_capacity_based:
			if node not in mv_nodes:
				mv_nodes.append(node)
	if query_rewrite:
		query_rewrite_beta.query_rewrite("proposed_u_b",proposed_u_b_mv_rows)
	# print("Utility Capacity Based")
	if count_mv_time:
		mv_files_count_list.append("Utility Capacity Based")
		mv_nodes_count_list.append(mv_nodes_utility_capacity_based)
		# test.count_mv_exe_time(mv_nodes_utility_capacity_based)

if utility_based_ILP:
	mv_nodes_utility_based = []
	with open(query_result_path + "proposed_u/mv_y_list.csv", "r") as f:
		reader = csv.reader(f)
		proposed_u_mv_rows = list(reader)
		for row in proposed_u_mv_rows:
			if len(row) > 1:
				for r in row:
					mv_nodes_utility_based.append(r)
			else:
				if len(row) == 0:
					continue
				mv_nodes_utility_based.append(row[0])
		
		for node in mv_nodes_utility_based:
			if node not in mv_nodes:
				mv_nodes.append(node)

	if query_rewrite:
		query_rewrite_beta.query_rewrite("proposed_u",proposed_u_mv_rows)
	# print("Utility Based")
	if count_mv_time:
		mv_files_count_list.append("Utility Based")
		mv_nodes_count_list.append(mv_nodes_utility_based)
		# test.count_mv_exe_time(mv_nodes_utility_based)

if frequency_based_ILP:
	mv_nodes_frequency_based = []
	with open(query_result_path + "proposed_f/mv_y_list.csv", "r") as f:
		reader = csv.reader(f)
		proposed_f_mv_rows = list(reader)
		for row in proposed_f_mv_rows:
			if len(row) > 1:
				for r in row:
					mv_nodes_frequency_based.append(r)
			else:
				if len(row) == 0:
					continue
				mv_nodes_frequency_based.append(row[0])
		
		for node in mv_nodes_frequency_based:
			if node not in mv_nodes:
				mv_nodes.append(node)

	if query_rewrite:
		query_rewrite_beta.query_rewrite("proposed_f",proposed_f_mv_rows)
	# print("Frequency Based")
	if count_mv_time:
		mv_files_count_list.append("Frequency Based")
		mv_nodes_count_list.append(mv_nodes_frequency_based)
		# test.count_mv_exe_time(mv_nodes_frequency_based)
		

# print("mv_nodes: ", mv_nodes)
# print("len(mv_nodes): ", len(mv_nodes))
# print("len(mv_nodes_normal): ", len(mv_nodes_normal))
# print("len(mv_nodes_bigsubs): ", len(mv_nodes_bigsubs))
# print("len(mv_nodes_utility_capacity_based): ", len(mv_nodes_utility_capacity_based))
# print("len(mv_nodes_utility_based): ", len(mv_nodes_utility_based))
# print("len(mv_nodes_frequency_based): ", len(mv_nodes_frequency_based))
# print("\n-------------------------------------\n")

if count_mv_time:
	print("-----MV analyze-----")
	for i in range(len(mv_nodes_count_list)):
		print("Folder:", mv_files_count_list[i])
		test.count_mv_exe_time(mv_nodes_count_list[i])
	print("\n\n")

if query_mv:
	if normal_ILP:
		print("Nomal ILP :")
		print("len(mv_nodes_normal): ", len(mv_nodes_normal))
		t1 = time.time()
		if len(sys.argv)>2 and sys.argv[2] == "mv":
			query_rewrite_beta.mv_make(mv_nodes_normal)
			query_rewrite_beta.mv_remake(mv_nodes_normal)
		else:
			query_rewrite_beta.query_rewrite('normal', normal_mv_rows)
		t2 = time.time()
		print("Time: ", t2-t1)
		print("-------------------------------------\n")

	if bigsubs_ILP:
		print("Bigsubs ILP :")
		print("len(mv_nodes_bigsubs): ", len(mv_nodes_bigsubs))
		t1 = time.time()
		if len(sys.argv)>2 and sys.argv[2] == "mv":
			query_rewrite_beta.mv_make(mv_nodes_bigsubs)
			query_rewrite_beta.mv_remake(mv_nodes_bigsubs)
		else:
			query_rewrite_beta.query_rewrite('bigsubs', bigsubs_mv_rows)
		t2 = time.time()
		print("Time: ", t2-t1)
		print("-------------------------------------\n")

	if utility_capacity_based_ILP:
		print("Utility capacity based ILP : ")
		print("len(mv_nodes_utility_capacity_based): ", len(mv_nodes_utility_capacity_based))
		t1 = time.time()
		if len(sys.argv)>2 and sys.argv[2] == "mv":
			query_rewrite_beta.mv_make(mv_nodes_utility_capacity_based)
			query_rewrite_beta.mv_remake(mv_nodes_utility_capacity_based)
		else:
			query_rewrite_beta.query_rewrite('proposed_u_b', proposed_u_b_mv_rows)
		t2 = time.time()
		print("Time: ", t2-t1)
		print("-------------------------------------\n")

	if utility_based_ILP:
		print("Utility base ILP :")
		print("len(mv_nodes_utility_based): ", len(mv_nodes_utility_based))
		t1 = time.time()
		if len(sys.argv)>2 and sys.argv[2] == "mv":
			query_rewrite_beta.mv_make(mv_nodes_utility_based)
			query_rewrite_beta.mv_remake(mv_nodes_utility_based)
		else:
			query_rewrite_beta.query_rewrite('proposed_u', proposed_u_mv_rows)
		t2 = time.time()
		print("Time: ", t2-t1)
		print("-------------------------------------\n")

	if frequency_based_ILP:
		print("Frequency based ILP : ")
		print("len(mv_nodes_frequency_based): ", len(mv_nodes_frequency_based))
		t1 = time.time()
		if len(sys.argv)>2 and sys.argv[2] == "mv":
			query_rewrite_beta.mv_make(mv_nodes_frequency_based)
			query_rewrite_beta.mv_remake(mv_nodes_frequency_based)
		else:
			query_rewrite_beta.query_rewrite('proposed_f', proposed_f_mv_rows)
		t2 = time.time()
		print("Time: ", t2-t1)
		print("-------------------------------------\n")

	#query_rewrite_beta.mv_make(mv_nodes)
	#query_rewrite_beta.mv_remake(mv_nodes)

if count_rewrite_time:
	test.count_exe_time()




