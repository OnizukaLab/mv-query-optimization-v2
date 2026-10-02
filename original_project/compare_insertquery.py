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


q_num = 113
insert_querys = [500 * (i) for i in range(11)]
B_max = 0.1 * 1000 * 1000 * 1000
#100, 200, 300, 400, 500で試す

# Which ILP to use
ILP_normal = True
ILP_bigsubs = True
ILP_utility_capacity_based = True
ILP_utility_based = True
ILP_frequency_based = True

save_csv = True
make_graph = True
check_m_cost = True
save_m_cost = True
save_normal_csv = True

result_normal_U = []
result_normal_B = []
result_normal_T = []

result_bigsubs_U = []
result_bigsubs_B = []
result_bigsubs_T = []

result_proposed_u_b_U = []
result_proposed_u_b_B = []
result_proposed_u_b_T = []

result_proposed_u_U = []
result_proposed_u_B = []
result_proposed_u_T = []

result_proposed_f_U = []
result_proposed_f_B = []
result_proposed_f_T = []

result_sum_utility = []
result_utility_positives = []

mv_nums = []

t3 = time.time()

# query_path = "/Users/andersonkaina/Desktop/rs_system/compare_air/JOB_json"
# qp = QueryParser()
# qp.query_parse(q_num, query_path, 0)

output_path = "Output/"
with open(output_path + "qp_class.pkl", 'rb') as file:
		qp = pickle.load(file)

z_j = [0] * (qp.s_num)

for insert_query in insert_querys:
	print("insert_query = ", insert_query)

	table_list = ['aka_name', 'aka_title', 'cast_info', 'char_name', 'comp_cast_type', 'company_name', 'company_type', 'complete_cast', 'info_type', 'keyword', 'kind_type', 'link_type', 'movie_companies', 'movie_info', 'movie_info_idx', 'movie_keyword', 'movie_link', 'name', 'person_info', 'role_type', 'title']
	record_list = [901343, 361472, 36244344, 3140339, 4, 234997, 4, 135086, 113, 134170, 7, 18, 2609129, 14835720, 1380035, 4523930, 29997, 4167491, 2963664, 12, 2528312]
	insert_cost = 0.01
	search_cost = [8.44, 8.44, 8.46, 8.45, 8.17, 8.44, 8.17, 8.31, 8.17, 8.44, 8.17, 8.17, 8.45, 8.45, 8.44, 8.45, 8.30, 8.45, 8.45, 8.17, 8.16]
	table_width = [324, 348, 56, 182, 86, 198, 86, 16, 86, 60, 52, 86, 48, 76, 52, 12, 16, 238, 76, 86, 306]
	m_cost = [0] * (qp.s_num)

	insert_times = insert_query / 1000
	update_table = [[''] for p in range(1000)]
	for i in range(len(update_table)):
		x = random.randint(0, 20)
		update_table[i][0] = table_list[x]
	m_cost = qp.check_m_cost(m_cost, table_list, update_table, record_list, search_cost, insert_cost, table_width, insert_times)

	if check_m_cost:
		sum_m_cost = sum(m_cost)
		print("Number of subqueries = ", qp.s_num)
		# print("Sum Utility includin m_cost = ", sum_Utility - sum_m_cost)

		num_s = 0
		for s_id in range(qp.s_num):
			check_u = qp.U_j_max[s_id] - m_cost[s_id]
			if check_u > 0:
				num_s += 1
			else:
				print("Negative Utility subquery = ", s_id, check_u)
		result_utility_positives.append(num_s)
		print("Number of subqueries with positive utility = ", num_s)
		print("-------------------------------------")
	
	if ILP_normal:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_normal_beta.normal(qp.qm, qp.s_num, m_cost, qp.node_list, B_max, qp.b_j, qp.u_ij, qp.X)
		t2 = time.time()

		for i in range(len(result_y_ij)):
			for j in range(len(result_y_ij[i])):
				if result_y_ij[i][j] == 1:
					z_j[j] = 1
		mv_num = sum(z_j)
		# print("ILP_normal")
		print("\n\nresult_Utility = ",result_u)
		print("result_b = ",result_b/B_max)
		print("mv_num = ", mv_num)
		print("\nTime: ", t2-t1)
		print("-------------------------------------")

		result_normal_U.append(result_u)
		result_normal_B.append(result_b/B_max)
		result_normal_T.append(t2-t1)
		mv_nums.append(mv_num)

		# mv_y_list = []
		# for i, y in enumerate(result_y_ij):
		# 	mv_y_i_list = []
		# 	for j in range(len(y)):
		# 		if y[j] == 1:
		# 			node_name = qp.node_list[j]
		# 			mv_y_i_list.append(node_name)
		# 	mv_y_list.append(mv_y_i_list)
	
	if ILP_bigsubs:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_bigsubs_beta.bigsubs(qp.s_num, m_cost, qp.b_j, qp.U_j_max, qp.q_s_list, qp.u_ij, qp.y_ij, qp.X, qp.U_max, B_max)
		t2 = time.time()

		result_bigsubs_U.append(result_u)
		result_bigsubs_B.append(result_b/B_max)
		result_bigsubs_T.append(t2-t1)

		mv_y_list = []
		for i, y in enumerate(result_y_ij):
			mv_y_i_list = []
			for j in range(len(y)):
				if y[j] == 1:
					node_name = qp.node_list[j]
					mv_y_i_list.append(node_name)
			mv_y_list.append(mv_y_i_list)

		with open(output_path + "experiment_1/bigsubs/mv_y_list_" + str(insert_query) + "is.csv", "w", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_utility_capacity_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_u_b_beta.proposed(qp.qm, qp.s_num, m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
		t2 = time.time()

		result_proposed_u_b_U.append(result_u)
		result_proposed_u_b_B.append(result_b/B_max)
		result_proposed_u_b_T.append(t2-t1)

		mv_y_list = []
		for i, y in enumerate(result_y_ij):
			mv_y_i_list = []
			for j in range(len(y)):
				if y[j] == 1:
					node_name = qp.node_list[j]
					mv_y_i_list.append(node_name)
			mv_y_list.append(mv_y_i_list)

		with open(output_path + "experiment_1/proposed_u_b/mv_y_list_" + str(insert_query) + "is.csv", "w", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_utility_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_u_beta.proposed(qp.qm, qp.s_num, m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
		t2 = time.time()

		result_proposed_u_U.append(result_u)
		result_proposed_u_B.append(result_b/B_max)
		result_proposed_u_T.append(t2-t1)

		mv_y_list = []
		for i, y in enumerate(result_y_ij):
			mv_y_i_list = []
			for j in range(len(y)):
				if y[j] == 1:
					node_name = qp.node_list[j]
					mv_y_i_list.append(node_name)
			mv_y_list.append(mv_y_i_list)

		with open(output_path + "experiment_1/proposed_u/mv_y_list_" + str(insert_query) + "is.csv", "w", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_frequency_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_f_beta.proposed(qp.qm, qp.s_num, m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
		t2 = time.time()

		result_proposed_f_U.append(result_u)
		result_proposed_f_B.append(result_b/B_max)
		result_proposed_f_T.append(t2-t1)

		mv_y_list = []
		for i, y in enumerate(result_y_ij):
			mv_y_i_list = []
			for j in range(len(y)):
				if y[j] == 1:
					node_name = qp.node_list[j]
					mv_y_i_list.append(node_name)
			mv_y_list.append(mv_y_i_list)

		with open(output_path + "experiment_1/proposed_f/mv_y_list_" + str(insert_query) + "is.csv", "w", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

t4 = time.time()

print("Total time: ", t4-t3)
#横軸がB_max、縦軸がresult_Utility、result_b、Time
#それぞれのILPについて、B_maxごとにグラフを作成する


# Save results to CSV
if save_csv:
	with open(output_path + "experiment_1/results/result_is.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["insert_querys", "result_normal_U", "result_bigsubs_U", "result_proposed_u_b_U", "result_proposed_u_U", "result_proposed_f_U"])
		for i in range(len(insert_querys)):
			writer.writerow([insert_querys[i], result_normal_U[i], result_bigsubs_U[i], result_proposed_u_b_U[i], result_proposed_u_U[i], result_proposed_f_U[i]])

if save_normal_csv:
	with open(output_path + "experiment_1/results/normal_is.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["insert_querys", "result_normal_U", "mv_num"])
		for i in range(len(insert_querys)):
			writer.writerow([insert_querys[i], result_normal_U[i], mv_nums[i]])

if save_m_cost:
	with open(output_path + "experiment_1/results/m_cost_is.csv", "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["insert_querys", "num_s"])
		for i in range(len(insert_querys)):
			writer.writerow([insert_querys[i], result_utility_positives[i]])