import json
import os
import re
import random
import time
import pickle
import csv

from query_parse_beta import QueryParser
import ILP_normal_beta as ILP_normal_beta
import ILP_proposed_u_b_beta as ILP_proposed_u_b_beta
import ILP_proposed_u_beta as ILP_proposed_u_beta
import ILP_bigsubs_beta as ILP_bigsubs_beta
import ILP_proposed_f_beta as ILP_proposed_f_beta

from utils import *

q_num = 113 # JOB
#q_num = 13759  # JOB + CEB
insert_query = 1000
B_max = 0.05 * 1000 * 1000 * 1000   # 50 MB
# Around 0.1G might be the best for all ILP

# Which ILP to use
ILP_normal = False
ILP_bigsubs = True
ILP_utility_capacity_based = True
ILP_utility_based = True
ILP_frequency_based = True

query_path = "dataset/RED_JSON"
workloads_dir = "Output/RED_WORKLOADS"

q_num = len(get_red_queries(query_path, workloads_dir, GET_CEB)[0])

qp = QueryParser()
#query_path = "dataset/RED_JSON"
#q_num = sum([len(files) for r, d, files in os.walk(query_path)])

qp.query_parse(q_num, query_path, insert_query)

output_path = "Output/"
with open(output_path + "qp_class.pkl", "wb+") as f:
	pickle.dump(qp, f)


print("B_max = ", B_max)
print("\n")

if ILP_normal:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_normal_beta.normal(qp.qm, qp.s_num, qp.m_cost, qp.node_list, B_max, qp.b_j, qp.u_ij, qp.X, qp.q_s_list)
	t2 = time.time()

	print("ILP_normal")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("\nTime: ", t2-t1)
	print("-------------------------------------")

	mv_y_list = []
	for i, y in enumerate(result_y_ij):
		mv_y_i_list = []
		for j in range(len(y)):
			if y[j] == 1:
				node_name = qp.node_list[j]
				mv_y_i_list.append(node_name)
		mv_y_list.append(mv_y_i_list)

	with open(output_path + "normal/mv_y_list.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerows(mv_y_list)

if ILP_bigsubs:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_bigsubs_beta.bigsubs(qp.s_num, qp.m_cost, qp.b_j, qp.U_j_max, qp.q_s_list, qp.u_ij, qp.y_ij, qp.X, qp.U_max, B_max)
	t2 = time.time()

	print("ILP_bigsubs")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("\nTime: ", t2-t1)
	print("-------------------------------------")

	mv_y_list = []
	for i, y in enumerate(result_y_ij):
		mv_y_i_list = []
		for j in range(len(y)):
			if y[j] == 1:
				node_name = qp.node_list[j]
				mv_y_i_list.append(node_name)
		mv_y_list.append(mv_y_i_list)

	with open(output_path + "bigsubs/mv_y_list.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerows(mv_y_list)

if ILP_utility_capacity_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_b_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()

	print("ILP_utility_capacity_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("\nTime: ", t2-t1)
	print("-------------------------------------")

	mv_y_list = []
	for i, y in enumerate(result_y_ij):
		mv_y_i_list = []
		for j in range(len(y)):
			if y[j] == 1:
				node_name = qp.node_list[j]
				mv_y_i_list.append(node_name)
		mv_y_list.append(mv_y_i_list)

	with open(output_path + "proposed_u_b/mv_y_list.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerows(mv_y_list)

if ILP_utility_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()

	print("ILP_utility_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("\nTime: ", t2-t1)
	print("-------------------------------------")

	mv_y_list = []
	for i, y in enumerate(result_y_ij):
		mv_y_i_list = []
		for j in range(len(y)):
			if y[j] == 1:
				node_name = qp.node_list[j]
				mv_y_i_list.append(node_name)
		mv_y_list.append(mv_y_i_list)

	with open(output_path + "proposed_u/mv_y_list.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerows(mv_y_list)

if ILP_frequency_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_f_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()

	print("ILP_frequency_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("\nTime: ", t2-t1)
	print("-------------------------------------")

	mv_y_list = []
	node_list = []
	node_list_counter = {}
	for i, y in enumerate(result_y_ij):
		mv_y_i_list = []
		for j in range(len(y)):
			if y[j] == 1:
				node_name = qp.node_list[j]
				if node_name not in node_list:
					node_list.append(node_name)
					node_list_counter[node_name] = 1
				else:
					node_list_counter[node_name] += 1
				mv_y_i_list.append(node_name)
		mv_y_list.append(mv_y_i_list)
	
	# for node in node_list:
	# 	c = node_list_counter[node]
	# 	m = qp.m_cost[qp.node_list.index(node)]
	# 	print(node, ": ", c, m, c*qp.qm.subquery_costs[node] - m)


	with open(output_path + "proposed_f/mv_y_list.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerows(mv_y_list)
