import json
import os
import re
import random
import time
import pickle
import csv

from query_parse_beta import QueryParser

import ILP_proposed_u_b_beta as ILP_proposed_u_b_beta
import ILP_proposed_u_beta as ILP_proposed_u_beta
import ILP_bigsubs_beta as ILP_bigsubs_beta
import ILP_proposed_f_beta as ILP_proposed_f_beta


q_num = 113
insert_query = 2000
B_max =  0.1 * 1000 * 1000 * 1000

# Which ILP to use
# ILP_bigsubs = True
ILP_utility_capacity_based = True
ILP_utility_based = True
ILP_frequency_based = True



def count_row(result_y_ij):
	count = 0
	for yi_j in result_y_ij:
		for y in yi_j:
			if y == 1:
				count += 1
				break
	return count



query_path = "dataset/RED_JSON/job"
qp = QueryParser()
qp.query_parse(q_num, query_path, insert_query)

if ILP_utility_capacity_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_b_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()
	count = count_row(result_y_ij)

	print("ILP_utility_capacity_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)

	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_b_beta.no_neighbor_search(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()

	count = count_row(result_y_ij)
	print("\n\nILP_utility_capacity_based_no_neighbor_search")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)
	print("-------------------------------------")

if ILP_utility_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()
	count = count_row(result_y_ij)

	print("ILP_utility_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)

	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_u_beta.no_neighbor_search(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()
	count = count_row(result_y_ij)

	print("\n\nILP_utility_based_no_neighbor_search")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)
	print("-------------------------------------")

if ILP_frequency_based:
	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_f_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()
	count = count_row(result_y_ij)

	print("ILP_frequency_based")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)

	t1 = time.time()
	result_u, result_b, result_y_ij = ILP_proposed_f_beta.no_neighbor_search(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.u_ij, qp.X)
	t2 = time.time()
	count = count_row(result_y_ij)

	print("\n\nILP_frequency_based_no_neighbor_search")
	print("\n\nresult_Utility = ",result_u)
	print("result_b = ",result_b)
	print("count = ", count)
	print("Time: ", t2-t1)
	print("-------------------------------------")