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
insert_query = 1000
B_maxs = [1 * 1000 * 1000 * (i+1) for i in range(3)]
B_maxs = [1 * 1000 * 1000, 10 * 1000 * 1000, 100 * 1000 * 1000, 500 * 1000 * 1000]
#100, 200, 300, 400, 500で試す

# Which ILP to use
ILP_normal = True
ILP_bigsubs = True
ILP_utility_capacity_based = True
ILP_utility_based = True
ILP_frequency_based = True

save_csv = True

query_path = "dataset/RED_JSON/job"
qp = QueryParser()
qp.query_parse(q_num, query_path, insert_query)

output_path = "Output/"
# with open(output_path + "qp_class.pkl", 'rb') as file:
# 		qp = pickle.load(file)

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

mv_nums = []
z_j = [0] * (qp.s_num)

t3 = time.time()
for B_max in B_maxs:
	print("B_max = ", B_max)
	if ILP_normal:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_normal_beta.normal(qp.qm, qp.s_num, qp.m_cost, qp.node_list, B_max, qp.b_j, qp.u_ij, qp.X, qp.q_s_list)
		t2 = time.time()

		for i in range(len(result_y_ij)):
			for j in range(len(result_y_ij[i])):
				if result_y_ij[i][j] == 1:
					z_j[j] = 1
		mv_num = sum(z_j)
		# print("ILP_normal")
		# print("\n\nresult_Utility = ",result_u)
		# print("result_b = ",result_b/B_max)
		# print("mv_num = ", mv_num)
		# print("\nTime: ", t2-t1)
		# print("-------------------------------------")

		result_normal_U.append(result_u)
		result_normal_B.append(result_b/B_max)
		result_normal_T.append(t2-t1)
		mv_nums.append(mv_num)

	
	if ILP_bigsubs:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_bigsubs_beta.bigsubs(qp.s_num, qp.m_cost, qp.b_j, qp.U_j_max, qp.q_s_list, qp.u_ij, qp.y_ij, qp.X, qp.U_max, B_max)
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

		with open(output_path + "experiment_2/bigsubs/mv_y_list_" + str(B_max/1000000) + "M.csv", "w+", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_utility_capacity_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_u_b_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
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

		with open(output_path + "experiment_2/proposed_u_b/mv_y_list_" + str(B_max/1000000) + "G.csv", "w+", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_utility_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_u_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
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

		with open(output_path + "experiment_2/proposed_u/mv_y_list_" + str(B_max/1000000) + "G.csv", "w+", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

	if ILP_frequency_based:
		t1 = time.time()
		result_u, result_b, result_y_ij = ILP_proposed_f_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
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

		with open(output_path + "experiment_2/proposed_f/mv_y_list_" + str(B_max/1000000) + "G.csv", "w+", newline="") as f:
			writer = csv.writer(f)
			writer.writerows(mv_y_list)

t4 = time.time()

print("Total time: ", t4-t3)
#横軸がB_max、縦軸がresult_Utility、result_b、Time
#それぞれのILPについて、B_maxごとにグラフを作成する

if save_csv:
	with open(output_path + "experiment_2/results/result_bmax.csv", "w+", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["B_max", "result_bigsubs_U", "result_proposed_u_b_U", "result_proposed_u_U", "result_proposed_f_U","result_normal_U","result_bigsubs_T","result_proposed_u_b_T","result_proposed_u_T","result_proposed_f_T","result_normal_T"])
		for i in range(len(B_maxs)):
			writer.writerow([B_maxs[i], result_bigsubs_U[i], result_proposed_u_b_U[i], result_proposed_u_U[i], result_proposed_f_U[i], result_normal_U[i], result_bigsubs_T[i], result_proposed_u_b_T[i], result_proposed_u_T[i], result_proposed_f_T[i], result_normal_T[i]])


#ここからグラフ作成
import matplotlib.pyplot as plt

plt.figure()

fig, axs = plt.subplots(2, 1, figsize=(9, 9))

#それぞれのデータセットをプロット
axs[0].plot(B_maxs, result_bigsubs_U, label="bigsubs")
axs[0].plot(B_maxs, result_proposed_u_b_U, label="proposed_u_b")
axs[0].plot(B_maxs, result_proposed_u_U, label="proposed_u")
axs[0].plot(B_maxs, result_proposed_f_U, label="proposed_f")
# ラベルの設定
axs[0].set_xlabel("B_max")
axs[0].set_ylabel("result_Utility")
axs[0].set_title("Comparison of result_Utility")
# 凡例の表示
axs[0].legend()

#それぞれのデータセットをプロット
axs[1].plot(B_maxs, result_bigsubs_T, label="bigsubs")
axs[1].plot(B_maxs, result_proposed_u_b_T, label="proposed_u_b")
axs[1].plot(B_maxs, result_proposed_u_T, label="proposed_u")
axs[1].plot(B_maxs, result_proposed_f_T, label="proposed_f")
# ラベルの設定
axs[1].set_xlabel("B_max")
axs[1].set_ylabel("execution time")
axs[1].set_title("Comparison of execution time")
# 凡例の表示
axs[1].legend()

plt.tight_layout()
plt.show()