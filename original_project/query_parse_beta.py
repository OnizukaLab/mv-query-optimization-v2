import json
import os
import re
import random
import time
import pickle
import csv

import ILP_proposed_u_b_beta
import ILP_proposed_u_beta
import ILP_bigsubs_beta

from utils import *

class QueryManager:
	def __init__(self):
		# 初期化：leafノードとnon-leafノード用のhashmap
		self.leaf_nodes_map = {}  # {(operator_name, table_name, alias, filter_condition): leaf_node_id}
		self.leaf_nodes_map_r = {}  # {leaf_node_id: (operator_name, table_name, alias, filter_condition)}
		self.non_leaf_nodes_map = {}  # {tuple(sorted(child_node_ids)): non_leaf_node_id}
		self.non_leaf_nodes_map_r = {} # {non_leaf_node_id: tuple(sorted(child_node_ids))}
		self.non_leaf_nodes_filter = {} # {non_leaf_node_id: operator_name}
		self.leaf_id_counter = 0  # leaf_node_id生成用
		self.non_leaf_id_counter = 0  # non_leaf_node_id生成用
		self.subquery_positions = {}  # {node_id: [[i, j], ...]}
		self.subquery_costs = {}  # {node_id: total_cost}
		self.subquery_sizes = {}  # {node_id: size}
		self.relation_tables = {}  # relation tables for leaf nodes
		self.subquery_widths = {}  # {node_id: width}

	def _generate_unique_id(self, prefix):
		"""
		サブクエリ用のユニークなIDを生成するための簡易メソッド
		"""
		if prefix == "leaf":
			self.leaf_id_counter += 1
			return f"leaf_{self.leaf_id_counter}"
		elif prefix == "non_leaf":
			self.non_leaf_id_counter += 1
			return f"non_leaf_{self.non_leaf_id_counter}"

	def process_leaf_node(self, operator_name, table_name, alias, filter_condition, position, total_cost, size, width):
		"""
		葉ノードの処理
		"""
		key = (operator_name, table_name, alias, filter_condition)
		if key in self.leaf_nodes_map:
			node_id = self.leaf_nodes_map[key]
		else:
			# 新しいleaf_node_idを生成して登録
			node_id = self._generate_unique_id("leaf")
			self.leaf_nodes_map[key] = node_id
			self.leaf_nodes_map_r[node_id] = key
		if position[0] != -1:
			if node_id in self.subquery_positions:
				self.subquery_positions[node_id].append(position)
			else:
				self.subquery_positions[node_id] = [position]
		if node_id in self.subquery_costs:
			if self.subquery_costs[node_id] >= total_cost:
				self.subquery_costs[node_id] = total_cost
		else:
			self.subquery_costs[node_id] = total_cost
		self.subquery_sizes[node_id] = size
		self.relation_tables[node_id] = table_name
		self.subquery_widths[node_id] = width
		return node_id

	def process_non_leaf_node(self, child_node_ids, position, total_cost, size, width, filter):
		"""
		非葉ノードの処理
		"""
		# 子ノードIDリストをソートしてキーを作成
		key = tuple(sorted(child_node_ids))
		if key in self.non_leaf_nodes_map:
			node_id = self.non_leaf_nodes_map[key]
		else:
			# 新しいnon_leaf_node_idを生成して登録
			node_id = self._generate_unique_id("non_leaf")
			self.non_leaf_nodes_map[key] = node_id
			self.non_leaf_nodes_map_r[node_id] = key
		if position[0] != -1:
			if node_id in self.subquery_positions:
				self.subquery_positions[node_id].append(position)
			else:
				self.subquery_positions[node_id] = [position]
		self.non_leaf_nodes_filter[node_id] = filter
		self.subquery_costs[node_id] = total_cost
		self.subquery_sizes[node_id] = size
		self.subquery_widths[node_id] = width
		return node_id

	def depth_first_search(self, node, position):
		"""
		深さ優先探索を実行する。
		各ノードが`node`として渡される。
		ノードは以下の形式を仮定:
		- 葉ノード: {"type": "leaf", "operator": str, "table": str, "filter": str}
		- 非葉ノード: {"type": "non_leaf", "children": [child_nodes]}
		"""

		if node["type"] == "leaf":
			return self.process_leaf_node(node["operator"], node["table"], node["alias"], node["filter"], position, node["cost"], node["size"], node["width"])

		elif node["type"] == "non_leaf":
			# 子ノードの再帰的処理
			child_ids = [self.depth_first_search(child, [-1, -1]) for child in node["children"]]
			return self.process_non_leaf_node(child_ids, position, node["cost"], node["size"], node["width"], node["filter"])
		
	def depth_child_to_parent_search(self, node, child_to_parent, parent_id):
		"""
		深さ優先探索を実行する。
		各ノードが`node`として渡される。
		ノードは以下の形式を仮定:
		- 葉ノード: {"type": "leaf", "operator": str, "table": str, "filter": str}
		- 非葉ノード: {"type": "non_leaf", "children": [child_nodes]}
		"""

		# if node["type"] == "leaf":
		# 	current_node = self.process_leaf_node(node["operator"], node["table"], node["filter"], [-1, -1], node["cost"], node["size"], node["width"])
			# print("current_node= ",current_node)
		if node["type"] == "non_leaf":
			# 子ノードの再帰的処理
			child_ids = [self.depth_child_to_parent_search(child, child_to_parent, parent_id) for child in node["children"]]
			current_node = self.process_non_leaf_node(child_ids, [-1, -1], node["cost"], node["size"], node["width"])
			child_to_parent[current_node] = [parent_id]
		print("child_ids= ",child_ids)
		print("current_node= ",current_node)
		print("parent_id= ",parent_id)
		return child_to_parent

class QueryParser:
	def __init__(self):
		self.qm = QueryManager()
		self.s_num = 0

		self.m_cost = []
		self.node_list = []
		self.position_node_id = {}
		self.deeplist = []
		self.U_j_max = []
		self.b_j = []
		self.q_s_list = []
		self.q_s_order_list = []
		self.u_ij = []
		self.us_ij = []
		self.y_ij = []
		self.X = []
		self.U_max = 0
		self.query = []
		self.subqlist = []

	def natural_sort_key(self, s):
		return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
	
	def convert_node(self, node, subquery_list, deep_list, order_list, order, depth=0, table_info = [], frequency = 1): # default should be changed
		deep_list.append(depth)

		if "Plans" in node: # Non-leaf node
			children = []
			new_order = order
			if node["Node Type"] == "Bitmap Heap Scan":
				table_info = [node["Relation Name"], node["Alias"]]
			for child in node["Plans"]:
				converted_child, order_1 = self.convert_node(child, subquery_list, deep_list, order_list, new_order + 1, depth + 1, table_info, frequency)
				children.append(converted_child)
				new_order = order_1

			if node["Node Type"] == "Hash Join":
				filter_name = "Hash Cond"
			elif node["Node Type"] == "Merge Join":
				filter_name = "Merge Cond"
			elif node["Node Type"] == "Nested Loop":
				filter_name = "Join Filter"
			else:
				filter_name = "Filter"

			## Prevent mvs with no where str
			if "Seq Scan" in node["Node Type"] and filter == "":
				cost = 0

			#if "Seq Scan" in node["Node Type"]:
			#	cost = 0
			#edge case
			elif "Hash" == node["Node Type"] and "Plans" in node and "Filter" not in node["Plans"][0]:
				cost = 0
			else:
				cost = node.get("Total Cost", 0)
			filter = node.get(filter_name, "")
			if filter == "":
				cost = 0
			if node["Plan Width"] == 0:
				width = 1
			else:
				width = node["Plan Width"]

			subquery_list.append({
				"type": "non_leaf",
				"operator": node["Node Type"],
				"filter": filter,
				"cost": cost * frequency,
				"size": node.get("Plan Rows", 0) * width,
				"width": node.get("Plan Width", 0),
				"children": children
			})
			order_list.append(order)
			return subquery_list[-1], new_order
		
		else: # Leaf node
			if "Index Cond" in node and "Filter" in node:
				filter = f"{node['Index Cond']} AND {node['Filter']}" #query_rewriteで複数のfilterを結合しているのかどうか区別するため、全体を括弧では括らない
				cost = node["Total Cost"]
			elif "Index Cond" in node:
				filter = node["Index Cond"]
				cost = node["Total Cost"]
			elif "Filter" in node:
				filter = node["Filter"]
				cost = node["Total Cost"]
			else:
				filter = ""
				cost = 0

			# "Index Cond" not in node
			if "Scan" in node["Node Type"] and "Filter" not in node:
				cost = 0

			if node["Plan Width"] == 0:
				Width = 1
			else:
				Width = node["Plan Width"]

			if node["Node Type"] == "Bitmap Index Scan":
				table = table_info[0]
				alias = table_info[1]
			else:
				table = node.get("Relation Name", "")
				alias = node.get("Alias", "")
			subquery_list.append({
				"type": "leaf",
				"operator": node["Node Type"],
				"table": table,
				"alias": alias,
				"filter": filter,
				"cost": cost* frequency,
				"size": node.get("Plan Rows", 0) * Width,
				"width": node.get("Plan Width", 0)
			})
			order_list.append(order)
			return subquery_list[-1], order

	def convert_json(self, json_data, freq):
		subquery_list = []
		deep_list = []
		order_list = []
		order = 0
		for plan in json_data:
			self.convert_node(plan["Plan"], subquery_list, deep_list, order_list, order, frequency= freq)
		return subquery_list, deep_list, order_list

	def make_reverse_dict(self, d):
		reverse_dict = {}
		for key, value in d.items():
			if len(value) == 1:
				value = tuple(value[0])
				reverse_dict[value] = key
			else:
				for v in value:
					v = tuple(v)
					reverse_dict[v] = key
		return reverse_dict

	def make_reverse_dict2(self, d):
		reverse_dict = {}
		for key, value in d.items():
			reverse_dict[value] = key
		return reverse_dict

	def search_leaf_node(self, node_id):
		"""
		指定されたnode_idをルートとするサブツリー内のすべての葉ノードに関連するテーブル名をリストとして返します。
		"""
		leaf_tables = set()

		def _find_leaf_tables_recursive(current_node_id):
			if current_node_id.startswith("leaf_"):
				table_name = self.qm.relation_tables.get(current_node_id)
				if table_name:
					leaf_tables.add(table_name)
			elif current_node_id.startswith("non_leaf_"):
				# self.qm.non_leaf_nodes_map_r は {non_leaf_node_id: tuple(sorted(child_node_ids))}
				child_node_ids = self.qm.non_leaf_nodes_map_r.get(current_node_id, [])
				for child_id in child_node_ids:
					_find_leaf_tables_recursive(child_id)
		
		_find_leaf_tables_recursive(node_id)
		return list(leaf_tables)

	def check_m_cost(self, m_cost, table_list, update_table, record_list, search_cost, insert_cost, table_width, insert_times):
		len_leaf = len(self.qm.leaf_nodes_map)
		for i in range(len(self.qm.leaf_nodes_map)):
			node_id = "leaf_" + str(i + 1)
			for item in update_table:
				item2 = self.qm.relation_tables[node_id]
				if item[0] == item2:
					m_cost[i] += self.qm.subquery_costs[node_id] / record_list[table_list.index(item2)]
					# m_cost[i] += search_cost[table_list.index(item2)]
					m_cost[i] += insert_cost * self.qm.subquery_widths[node_id] / table_width[table_list.index(item2)]
			m_cost[i] *= insert_times

		for i in range(len(self.qm.non_leaf_nodes_map)): #ここが違うと思う
			node_id = "non_leaf_" + str(i + 1)
			node_id_table_list = self.search_leaf_node(node_id)
			for item in update_table:
				if item[0] in node_id_table_list:
					m_cost[i + len_leaf] += self.qm.subquery_costs[node_id] / record_list[table_list.index(item[0])]
					# m_cost[i + len_leaf] += search_cost[table_list.index(item[0])]
					# m_cost[i + len_leaf] += insert_cost * self.qm.subquery_sizes[node_id] * self.qm.subquery_widths[node_id] / table_width[table_list.index(item[0])]
					m_cost[i + len_leaf] += insert_cost * self.qm.subquery_widths[node_id] / table_width[table_list.index(item[0])]
			m_cost[i + len_leaf] *= insert_times
		return m_cost
	
	def query_parse(self, q_num, path, insert_query):
		opelist = []
		subqlist = []
		query = []
		Node_q_list = []
		u_list = []
		stolist = []
		widthlist = []
		costlist = []
		filterlist = []
		table_subq_list = []
		deeplist = []
		orderlist = []
		ope_wherelist = []
		child_to_parent = {}

		workloads_dir = "Output/RED_WORKLOADS"

		#files = sorted([os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))], key=lambda f: self.natural_sort_key(os.path.basename(f)))
		files, file_freq = get_red_queries(path, workloads_dir, GET_CEB)
		files = sorted(files, key=natural_sort_key)
		
		s_num = 0
		q_num_len = len(files)
		print("q_num_len= ", q_num_len)
		try:
			for i in range(q_num_len):
				depth_list = [0]
				Node_list = []
				cost = []
				sto_list = []
				width_list = []
				table_sub = []
				filter = []
				ope = []
				with open(files[i], 'r') as f:
					data = json.load(f)
					frequency = file_freq[files[i]]
					converted_data, deep_list, order_list = self.convert_json(data, frequency)
					deeplist.append(deep_list)
					orderlist.append(order_list)
					for j, subquery in zip(order_list, converted_data):
						result = self.qm.depth_first_search(subquery, [i, j])
						# query.append(data[0]["Plan"])
					query.append(converted_data)

			for key, value in self.qm.non_leaf_nodes_map.items():
				for item in key:
					if item not in child_to_parent:
						child_to_parent[item] = []
					child_to_parent[item].append(value)

			ope_num = {}
			ope_time_name_seed = []
			ope_time_seed = {}
			print(f"Root node ID: {result}")

			node_list = list(self.qm.leaf_nodes_map.values()) + list(self.qm.non_leaf_nodes_map.values())
			position_node_id = self.make_reverse_dict(self.qm.subquery_positions)

			len_leaf = len(self.qm.leaf_nodes_map)
			len_non_leaf = len(self.qm.non_leaf_nodes_map)
			s_num = len_leaf + len_non_leaf

			s_counter = [0] * s_num
			s_counter2 = [0] * s_num

			for j in range(s_num):
				s_counter2[j] = len(self.qm.subquery_positions[node_list[j]])
				if len(self.qm.subquery_positions[node_list[j]]) > 1:
					s_counter[j] = 1

			# print("s_counter2= ",s_counter2)
			q_s_list = []
			q_s_order_list = []
			u_ij = []
			us_ij = []
			y_ij = []
			for i in range(q_num):
				q_by_s = [0] * s_num
				q_s_order = []
				u_ij_seed = [0] * s_num
				y_ij_seed = [0] * s_num
				us_ij_seed = [0] * s_num
				for j in range(s_num):
					for item in self.qm.subquery_positions[node_list[j]]:
						if item[0] == i:
							q_s_order.append(item[1])
							q_by_s[j] = 1
							u_ij_seed[j] = self.qm.subquery_costs[node_list[j]]
							us_ij_seed[j] = self.qm.subquery_costs[node_list[j]] * s_counter[j]

				q_s_list.append(q_by_s)
				q_s_order_list.append(q_s_order)
				u_ij.append(u_ij_seed)
				us_ij.append(us_ij_seed)
				y_ij.append(y_ij_seed)

			b_j = [0] * s_num
			j = 0
			maxb = 0
			maxu = 0

			for i in range(len(u_ij)):
				p_0 = (i, 0)
				p_1 = (i, 1)
				node_0 = position_node_id[p_0]
				node_1 = position_node_id[p_1]
				maxb += self.qm.subquery_sizes[node_0]
				if len(orderlist[i]) > 1:
					if self.qm.subquery_costs[node_0] < self.qm.subquery_costs[node_1]:
						maxu += self.qm.subquery_costs[node_1]
					else:
						maxu += self.qm.subquery_costs[node_0]
						# print("i=",i,"\tmaxu= ",maxu,"\t",self.qm.subquery_costs[node_0])
				else:
					maxu += self.qm.subquery_costs[node_0]
			print('total_cost', 'total_budget')
			print(maxu, maxb)

			j = 0
			for item in node_list:
				b_j[j] = self.qm.subquery_sizes[item]
				j += 1

			for j in range(len(b_j)):
				if b_j[j] == 0:
					b_j[j] = 1

			U_max = 0
			for i in range(len(u_ij)):
				for j in range(len(u_ij[i])):
					U_max += u_ij[i][j]

			U_j_max = [0] * s_num
			for i in range(len(u_ij)):
				for j in range(len(u_ij[i])):
					U_j_max[j] += u_ij[i][j]

			# Xの作成　うまくいってない12/13
			# X = [[0] * len(b_j) for i in range(len(b_j))]
			self.subqlist = self.make_reverse_dict2(self.qm.non_leaf_nodes_map)
			self.node_list = node_list
			# print("subqlist= ",self.subqlist)
			# for j in range(s_num):
			#     item = node_list[j]
			#     if item in subqlist.keys():
			#         for item2 in subqlist[item]:
			#             X[j][node_list.index(item2)] = 1
			X = self.set_inclusive_dependency(None,0)
			# print("X= ",X)
			# for i in range(len(X)):
			#     for j in range(len(X[i])):
			#         if X[i][j] == 1:
			#             print(node_list[i], " -> ", node_list[j])

			table_list = ['aka_name', 'aka_title', 'cast_info', 'char_name', 'comp_cast_type', 'company_name', 'company_type', 'complete_cast', 'info_type', 'keyword', 'kind_type', 'link_type', 'movie_companies', 'movie_info', 'movie_info_idx', 'movie_keyword', 'movie_link', 'name', 'person_info', 'role_type', 'title']
			record_list = [901343, 361472, 36244344, 3140339, 4, 234997, 4, 135086, 113, 134170, 7, 18, 2609129, 14835720, 1380035, 4523930, 29997, 4167491, 2963664, 12, 2528312]
			insert_cost = 0.01 # alpha
			search_cost = [8.44, 8.44, 8.46, 8.45, 8.17, 8.44, 8.17, 8.31, 8.17, 8.44, 8.17, 8.17, 8.45, 8.45, 8.44, 8.45, 8.30, 8.45, 8.45, 8.17, 8.16]
			table_width = [324, 348, 56, 182, 86, 198, 86, 16, 86, 60, 52, 86, 48, 76, 52, 12, 16, 238, 76, 86, 306]
			m_cost = [0] * (len_leaf + len_non_leaf)

			insert_times = insert_query / 1000
			update_table = [[''] for p in range(1000)]
			for i in range(len(update_table)):
				x = random.randint(0, 20)
				update_table[i][0] = table_list[x]

			m_cost = self.check_m_cost(m_cost, table_list, update_table, record_list, search_cost, insert_cost, table_width, insert_times)
			# print("m_cost= ",m_cost)

			self.qm = self.qm
			self.s_num = s_num
			self.m_cost = m_cost
			self.node_list = node_list
			self.position_node_id = position_node_id
			self.deeplist = deeplist
			self.U_j_max = U_j_max
			self.b_j = b_j
			self.q_s_list = q_s_list
			self.q_s_order_list = q_s_order_list
			self.u_ij = u_ij
			self.us_ij = us_ij
			self.y_ij = y_ij
			self.X = X
			self.U_max = U_max
			self.query = query

		except json.JSONDecodeError as e:
			print(f"Error reading {files[i]}: {e}")
			return 1
	
	def set_inclusive_dependency(self, X, j, parent= None):
		# # print("subqlist= ",self.subqlist.keys())
		# print("parent= ",parent)
		# print("node_list= ",self.node_list)
		if parent is None:
			X = [[0] * len(self.node_list) for i in range(len(self.node_list))]
			for j in range(len(self.node_list)):
				parent = self.node_list[j]
				if parent in self.subqlist.keys():
					for child in self.subqlist[parent]:
						X[j][self.node_list.index(child)] = 1
						X = self.set_inclusive_dependency(X, j, child)
		else:
			if parent not in self.subqlist.keys():
				return X
			for child in self.subqlist[parent]:
				X[j][self.node_list.index(child)] = 1
				X = self.set_inclusive_dependency(X, j, child)
		return X

# Example usage:
# qp = QueryParser()
# qp.query_parse(q_num, path, insert_query)
# Now you can access the variables as attributes of the QueryParser instance, e.g., qp.qm, qp.s_num, etc.
if __name__ == '__main__':
	q_num = 113
	ilp = "u_b"
	# path = "/Users/andersonkaina/Desktop/rs_system/compare_air/dataset/redbench/RED_JSON"
	path = "/Users/andersonkaina/Desktop/rs_system/compare_air/dataset/JOB_json"
	insert_query = 2000
	B_max = 0.1 * 1000 * 1000 * 1000
	# parsed = query_parse(q_num, path, insert_query)
	# for key in parsed[1]:
	# 	if len(parsed[1][key]) >= 2:
	# 		print(key, parsed[1][key])


	qp = QueryParser()
	t1 = time.time()
	qp.query_parse(q_num, path, insert_query)
	t2 = time.time()
	print("Time: ", t2-t1)

	leaf_num = len(qp.qm.leaf_nodes_map)
	non_leaf_num = qp.s_num - leaf_num

	count_ave = 0
	for leaf_id in range(leaf_num):
		count_ave += qp.m_cost[leaf_id]
	count_ave /= leaf_num
	print("count_ave_for_leaf= ",count_ave)

	count_ave = 0
	for non_leaf_id in range(leaf_num, qp.s_num):
		count_ave += qp.m_cost[non_leaf_id]
	count_ave /= non_leaf_num
	print("count_ave_for_non_leaf= ",count_ave)

	negative_count = 0
	total_count = 0
	for i in range(len(qp.node_list)):
			current_node = qp.node_list[i]
			current_node_cost = qp.qm.subquery_costs[current_node]
			if current_node_cost != 0:
				if current_node_cost - qp.m_cost[i] < 0:
					negative_count += 1
			total_count += 1
	negative_ratio = negative_count / total_count if total_count > 0 else 0
	print(f"Leaf nodes length: {leaf_num}")
	print(f"Non-leaf nodes length: {non_leaf_num}")
	print(f"Negative ratio in qp.u_ij - qp.m_cost: {negative_ratio:.4f} ({negative_count}/{total_count})")



	# print("qp.qm.leaf_nodes_map_r= ",qp.qm.leaf_nodes_map_r["leaf_67"])
	# u_ij_order = []

	# for i,x in enumerate(qp.q_s_list[0]):
	# 	if x == 1:
	# 		u_ij_order.append(qp.u_ij[0][i])
	
	# new_order = [0] * len(u_ij_order)
	# j = 0
	# for i in qp.q_s_order_list[0]:
	# 	new_order[i] = u_ij_order[j]
	# 	j += 1
	# for n in new_order:
		# print("u_ij= ",n)

	# output_path = "/Users/andersonkaina/Desktop/rs_system/compare_air/Output/"
	# with open(output_path + "qp_class.pkl", "wb") as f:
	# 	pickle.dump(qp, f)
	
	# print("qp.query= ",qp.query[0][0])
	# print("qp.qm.leaf_nodes_map= ",qp.qm.leaf_nodes_map)


	# if ilp == "u":
	# 	result_u, result_b, result_y_ij = ILP_proposed_u_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.us_ij, qp.X)
	# elif ilp == "u_b":
	# 	result_u, result_b, result_y_ij = ILP_proposed_beta.proposed(qp.qm, qp.s_num, qp.m_cost, qp.node_list, qp.position_node_id, qp.deeplist, B_max, qp.b_j, qp.q_s_list, qp.us_ij, qp.X)
	# elif ilp == "bigsubs":
	# 	result_u, result_b, result_y_ij = ILP_bigsubs_beta.bigsubs(qp.s_num, qp.m_cost, qp.b_j, qp.U_j_max, qp.q_s_list, qp.us_ij, qp.y_ij, qp.X, qp.U_max, B_max)

	# print("ilp= ",ilp)
	# print("\n\nresult_Utility = ",result_u)
	# print("result_b = ",result_b)
	# # print("result[2]= ",result[2])

	# mv_y_list = []
	# for i, y in enumerate(result_y_ij):
	# 	# print(y)
	# 	print("Query ", i)
	# 	mv_y_i_list = []
	# 	for j in range(len(y)):
	# 		if y[j] == 1:
	# 			node_name = qp.node_list[j]
	# 			mv_y_i_list.append(node_name)
	# 			print(node_name)
	# 	print("-------------")
	# 	mv_y_list.append(mv_y_i_list)

	# with open("/Users/andersonkaina/Desktop/rs_system/compare_air/graph/mv_y_list.csv", "w", newline="") as f:
	# 	writer = csv.writer(f)
	# 	writer.writerows(mv_y_list)

	
	# graph_path = "/Users/andersonkaina/Desktop/rs_system/compare_air/graph/qp_class.pkl"
	# with open(graph_path, "wb") as f:
	# 	pickle.dump(qp, f)