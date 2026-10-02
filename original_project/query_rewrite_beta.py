import re
import regex
import os
import json
import pickle
import csv

import shutil
from query_parse_beta import QueryParser
from query_parse_beta import QueryManager

import sqlparse
from sqlparse.sql import Where, TokenList
from sqlparse.tokens import Keyword, Comparison

from utils import *

def find_child_leaf(node, qp, child_list=None):
	if child_list is None:
		child_list = []
	if node == "NONE":
		child_list = []
	elif node.startswith('leaf'):
		child_list.append(node)
	else:
		child_list.append(node)
		for child in qp.qm.non_leaf_nodes_map_r[node]:
			find_child_leaf(child, qp, child_list)
	return child_list

def find_child_leaf_alias(node, qp, child_alias_list=None):
	if child_alias_list is None:
		child_alias_list = []
	if node == "NONE":
		child_alias_list = []
		#child_alias_list.append(qp.qm.leaf_nodes_map_r[node][2])
	else:
		if node in qp.qm.non_leaf_nodes_map_r.keys():
			for child in qp.qm.non_leaf_nodes_map_r[node]:
				find_child_leaf_alias(child, qp, child_alias_list)
	return child_alias_list

def find_node(node, qp, query_id):
	query = qp.query[query_id]
	position = qp.qm.subquery_positions[node]
	for pos in position:
		if pos[0] == query_id:
			s_pos = pos[1]
			break

def condition_analaize(where_str, table, alias, used_alias, condition_type):
	aliases_in_condition = set(re.findall(r'(?:(?<=^)|(?<=[^:,.-]))([a-zA-Z_][a-zA-Z0-9_]*)(?=\.[a-zA-Z_])', where_str)) # fixes errors with words like m.i.t or w.i.p, etc

	if aliases_in_condition: # 明示的なエイリアスが条件に含まれる場合
		for cond_alias in aliases_in_condition:
			if cond_alias not in used_alias:
				# print(f"DEBUG: Invalid alias '{cond_alias}' in condition '{where_str}'. Valid aliases: {used_aliases}")
				return "" # 無効なエイリアスが含まれていれば、この条件は無視

	where_sql = ''
	if "::text" in where_str:
		where_str = where_str.replace("::text", "")
	if "::integer" in where_str:
		where_str = where_str.replace("::integer", "")
	if "::double precision" in where_str:
		where_str = where_str.replace("::double precision", "")
	if "[]" in where_str:
		where_str = where_str.replace("[]", "")
	# if ") = " in where_str or ") >" in where_str or ") <" in where_str:
	# 	where_str = where_str.replace(") = ", " = ")
	# 	where_str = where_str[1:]
	if ") " in where_str and ") (" not in where_str:
		where_str = where_str.replace(") ", " ")
		where_str = where_str[1:]
	if where_str[0] == "(" and where_str[-1] == ")":
		where_str = where_str[1:]
		where_str = where_str[:-1]
	where_str = extract_parentheses(where_str)

	
	# like句の場合
	if " ~~ " in where_str:
		where_str = where_str.split(" ~~ ")
		where_sql += alias + "." + where_str[0] + " LIKE " + where_str[1] + condition_type
	# not like句の場合
	elif " !~~ " in where_str:
		where_str = where_str.split(" !~~ ")
		where_sql += alias + "." + where_str[0] + " NOT LIKE " + where_str[1] + condition_type
	# IN句の場合_のちの解析処理のため、"IN"ではなく"=="に変更
	elif "= ANY " in where_str:
		where_str = where_str.split(" = ANY ")
		#不要なカッコ削除
		where_str[1] = where_str[1][3:]
		where_str[1] = where_str[1][:-3]
		where_str[1] = where_str[1].replace("\"", "")
		word = where_str[1].split(",")
		word_list = ''
		for w in word:
			word_list += "'" + w + "', "
		word_list = word_list[:-2]
		word_list = "(" + word_list + ")"
		where_sql += alias + "." + where_str[0] + " == " + word_list + condition_type  #本当は"IN"を使いたい
	elif " <> " in where_str:
		where_str = where_str.split(" <> ")
		where_sql += alias + "." + where_str[0] + " != " + where_str[1] + condition_type
	elif where_str[0] == "'" and " <= " in where_str: # for "'1000'::double precision <= (info)::double precision" cases where the order of comparison is different
		where_str = where_str.split(" <= ")
		if where_str[1][0] == "(":
			where_str[1] = where_str[1][1:]
			where_sql += where_str[0] + " <= " + "(" + alias + "." + where_str[1] + condition_type
		else:
			where_sql += where_str[0] + " <= " + alias + "." + where_str[1] + condition_type
	else:
		# print("where_str_cd: ", where_str)
		# print("alias: ", alias)
		check_cond = 0
		if where_str.startswith(alias + "."):
			# print("1, where_str: ", where_str)
			where_sql += where_str + condition_type
			check_cond = 1
		elif " " + alias + "." not in where_str and alias != "":
			# print("2, where_str: ", where_str)
			if where_str[0] == "(":
				where_str = where_str[1:]
				where_sql += "(" + alias + "." + where_str + condition_type
			else:
				where_sql += alias + "." + where_str + condition_type
		elif check_cond == 0:
			# print("3, where_str: ", where_str)
			where_sql += where_str + condition_type
	return where_sql

def extract_parentheses(where_str):
	# print("where_str: ", where_str)
	if where_str[0] == "(" and ")" not in where_str:
		where_str = where_str[1:]
	
	if where_str[-1] == ")" and "(" not in where_str:
		where_str = where_str[:-1]
	return where_str

def where_analaize(where_str, table, alias, used_alias):
	where_sql = ''

	check_cond = 0
	if where_str[0] == "(" and where_str[-1] == ")":
		where_str = where_str[1:-1]
	#print("where_str: ", where_str)
	if "AND" in where_str:
		where_list = where_str.split(" AND ")
		for where in where_list:
			if where[0] == "(" and where[-1] == ")":
				where = where[1:]
				where = where[:-1]
				check_cond = 1
			# print("   " , where)
			if "OR" in where:
				where = where.split(" OR ")
				for w in where:
					# print("where_b: ", w)
					# w = extract_parentheses(w)
					w = condition_analaize(w, table, alias, used_alias, " OR ")
					# print("where_a: ", w)

					if check_cond == 2:
						if w[0] == "(":
							check_cond = 0

					if check_cond == 1:
						w = "(" + w
						check_cond = 2
					
					where_sql += w
				where_sql = where_sql[:-4]
				if check_cond == 2:
					where_sql = where_sql + ")"
				# print("\nwhere_sql: ", where_sql)
				where_sql += " AND "
			else:
				# print("where_b: ", where)
				where = condition_analaize(where, table, alias, used_alias, " AND ")
				# print("where_a: ", where)
				where_sql += where
		where_sql = where_sql[:-5]
		
	else:
		# print("where_str_no&: ", where_str)
		if " OR " in where_str:
			where_str = where_str.split(" OR ")
			check_cond = 1
			for w in where_str:
				# print("where_b: ", w)
				# w = extract_parentheses(w)
				w = condition_analaize(w, table, alias, used_alias, " OR ")
				# print("where_a: ", w)
				if check_cond == 1:
					w = "(" + w
					check_cond = 2
				where_sql += w
			where_sql = where_sql[:-4]
			if check_cond == 2:
				where_sql = where_sql + ")"
		else:
			# print("where_b: ", where_str)
			where_sql += condition_analaize(where_str, table, alias, used_alias, "")
			# print("where_a: ", where_sql)

	return where_sql


def natural_sort_key(s):
	return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


# leaf nodes have a problem where the filters include a table
# get_table_name_filter should hopefully fix this problem
def get_table_name_filter(node, from_sql, leaf_nodes_map_r):
	res = []

	temp = from_sql.split(" ")
	#table with extracted aliases
	aliases = [i.split(".")[0] for i in temp if (len(i.split(".")) >1 and "'" not in i)]
	for alias in aliases:
		for key, value in leaf_nodes_map_r.items():
			if value[2] == alias:
				res.append((alias, value[1]))
				break
	return res

def remake_from_sql(from_sql, where_sql):
	tables = from_sql.replace("FROM ", "")
	tables = tables.split(",")
	tables = [i.strip() for i in tables if i != " "]
	aliases = [i.split("AS ")[1] for i in tables if len(i.split("AS "))>1]
	res = "FROM "
	for i in range(len(aliases)):
		if (" "+aliases[i]+".") in where_sql:
			res += tables[i] + ", "
	return res

def remake_from_sql_query(from_sql, where_sql, group_sql, select_sql):
	tables = from_sql.replace("FROM ", "")
	tables = tables.split(",")
	tables = [i.strip() for i in tables if i != " "]
	aliases = [i.split("AS ")[1] for i in tables if len(i.split("AS "))>1]
	res = "FROM "
	for i in range(len(aliases)):
		if (" "+aliases[i]+".") in where_sql or (" "+aliases[i]+".") in group_sql or (" "+aliases[i]+".") in select_sql:
			res += tables[i] + ", "
	for i in range(len(aliases),len(tables)):
		res += tables[i]+ ", "
	if len(aliases)!= len(tables):
		res = res[:-2]
	return res

# Creates Materialized views
def mv_make(mv_nodes):
	
	# path = "/Users/andersonkaina/Desktop/rs_system/compare_air/JOB_json"
	output_path = 'Output/'
	class_path = 'Output/qp_class.pkl'

	with open(class_path, 'rb') as file:
		qp = pickle.load(file)

	# with open(output_path + method + '/mv_y_list.csv', 'r') as file:
	# 	mv_data = csv.reader(file)
	# 	rows = list(mv_data)

	# mv_list = []
	# files = sorted([os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))], key=lambda f: natural_sort_key(os.path.basename(f)))


	# for query_num in rows:
	# 	for node_name in query_num:
	# 		if node_name not in mv_list:
	# 			mv_list.append(node_name)
	
	mv_list = mv_nodes

	# print(mv_list)

	print("len(mv_list): ", len(mv_list))
	print("\n\n")
	for i in range(len(mv_list)):
		# print("mv_id: ", mv_list[i])
		mv_id = mv_list[i]
		# if mv_id != "non_leaf_666":
		# 	continue
		if mv_id == "NONE":
			continue

		#mv_sql = "CREATE MATERIALIZED VIEW " + mv_id + " AS\nSELECT *\n"
		mv_sql = "SELECT pgivm.create_immv('" + mv_id + "','SELECT *\n"

		mv_node_list = find_child_leaf(mv_id, qp)
		used_alias = find_child_leaf_alias(mv_id, qp)
		# print("mv_node_list: ", mv_node_list)

		node_leaf_check = False
		if len(mv_node_list) <= 2: # "bitmap index scan" or "bitmap heap scan"
			node_leaf_check = True
		where_list = []
		where_str = ''

		from_sql = "FROM "
		where_sql = "WHERE "

		for node in mv_node_list:
			if node.startswith('leaf'):
				table = qp.qm.leaf_nodes_map_r[node][1] #1 is table name
				alias = qp.qm.leaf_nodes_map_r[node][2] #2 is alias name

				# print("alias: ", alias)
				from_sql += table + " AS " + alias + ", "


				if table == "":
					print("node: ", node)

				if qp.qm.leaf_nodes_map_r[node][3] != '':
					where_str = qp.qm.leaf_nodes_map_r[node][3]
					if node_leaf_check:
						if " AND " in where_str and qp.qm.leaf_nodes_map_r[node][0] != 'Bitmap Index Scan': #葉でbitmap index scan以外であり、結合条件が含まれる場合、それを抜く
							where_str = where_str.split(" AND ")
							if len(where_str) > 2 and "." in where_str[0]:
								where_str = " AND ".join(where_str[1:])
							elif "." not in where_str[0] or len(where_str) > 2: #結合条件が含まれない場合、その判定はこれでいいのか疑問
								where_str = " AND ".join(where_str)
							else:
								where_str = where_str[1]
						if qp.qm.leaf_nodes_map_r[node][0] == 'Bitmap Index Scan':
							where_str = ""
					
					# 不要なカッコなどを削除する

					# where_str = where_str[1:-1]
					# print("mv_make  where_str: ", where_str)
					count_parentheses = 0
					check_cond_and_filter = 0
					for w_id in range(len(where_str)):
						# print("w_id: ", w_id, "  ", where_str[w_id])
						if w_id == 0 and where_str[w_id] != "(":
							break
						if where_str[w_id] == "(":
							count_parentheses += 1
						elif where_str[w_id] == ")":
							count_parentheses -= 1
						if count_parentheses == 0 and w_id != len(where_str) - 1:
							where_str_1 = where_str[:w_id + 1]
							where_str_2 = where_str[w_id + 6:]
							# print("w_str_1: ", where_str_1)
							# print("w_str_2: ", where_str_2)
							check_cond_and_filter = 1
							break
					# print("w_str_b: ", where_str)
					# print(check_cond_and_filter)
					# print(node, "  ", alias)
					if where_str == '':
						continue
					elif check_cond_and_filter == 0:
						where_str = where_analaize(where_str, table, alias, used_alias)
						
					else:
						where_str_1 = where_analaize(where_str_1, table, alias, used_alias)
						where_str_2 = where_analaize(where_str_2, table, alias, used_alias)

						if where_str_1 == "" or where_str_2 =="":
							# fixes error where filter starts with an AND
							where_str = where_str_1 + where_str_2
						else:
							where_str = where_str_1 + " AND " + where_str_2
					# print("w_str: ", where_str)
					if where_str != '':
						where_sql += where_str + " AND "
					#where_sql += where_str + " AND "

			else:
				if qp.qm.non_leaf_nodes_filter[node] != '':
					where_str = qp.qm.non_leaf_nodes_filter[node]
					# print("mv_make nl where_str: ", where_str)
					if len(qp.qm.non_leaf_nodes_map_r[node]) == 1:
						child_leaf = qp.qm.non_leaf_nodes_map_r[node][0]
						table = qp.qm.leaf_nodes_map_r[child_leaf][1]
						alias = qp.qm.leaf_nodes_map_r[child_leaf][2]
					else:
						table = "t"
						alias = ""
					where_str = where_analaize(where_str, table, alias, used_alias)
					
					if where_str != '':
						where_sql += where_str + " AND "

		# removes uneccessary tables if not present in filter
		
		from_sql = remake_from_sql(from_sql, where_sql)
		if where_sql == "WHERE ": #条件がない場合
			#mv_sql += from_sql + ";"	
			#from_sql = from_sql[:-2]
			mv_sql += from_sql + "\n');"

			print("LEAF PROBLEM ",mv_id, qp.qm.leaf_nodes_map_r[node])
			print("NON WHERE ",mv_id, from_sql)
		else:
			where_sql = where_sql[:-5]
			# if "= '" in where_sql:  #4a.sqlに対応させるため、ここの空白を消す
			# 	where_sql = where_sql.replace("= '", "='")

			# creates extra tables in from_sql if they are called in filter
			filter_tables = get_table_name_filter(node, where_sql, qp.qm.leaf_nodes_map_r)
			for f_table in filter_tables:
				if f_table[1] + " AS " + f_table[0] not in from_sql:
					from_sql += f_table[1] + " AS " + f_table[0] + ", "
			from_sql = from_sql[:-2]
			
			#if "Scan" in qp.qm.leaf_nodes_map_r[node][0]:
			#	print(mv_id, qp.qm.leaf_nodes_map_r[node])
			
			mv_sql += from_sql + "\n" + where_sql.replace("'","''") + "\n');"
		

		#if "Seq Scan" in qp.qm.leaf_nodes_map_r[node][0]:
		#	print(mv_id, qp.qm.leaf_nodes_map_r[node][0], where_sql, qp.qm.leaf_nodes_map_r[node][3])

		# print(mv_sql, "\n")
		# print("---------------------------------")
		
		if mv_id != "NONE":
			with open(f"{output_path}query_rewrite/mv/{mv_id}.sql", "w+") as file:
				file.write(mv_sql)

def mv_node_analize(node):
	path = "Output/query_rewrite/mv/"

	with open(path + node + ".sql", "r") as file:
		content = file.read()
		# ここで解析処理を行う
	content = content.split("\n", 2)[1]
	content = content.replace(" as "," AS ")
	sql_mv = content
	if " IN " in sql_mv:
		sql_mv = sql_mv.replace(" IN ", " == ")
	content = content.replace("\n","")
	content = content.split("FROM ")
	if "WHERE " in content[1]:
		content = content[1].split("WHERE ")
		from_cond = content[0]
		where_cond = content[1]
	else:
		from_cond = content[1]
		where_cond = ""

	from_conds = from_cond.split(", ")
	if from_conds[-1][-1] == ";":
		from_conds[-1] = from_conds[-1][:-1]
	
	#print("mna_from_conds: ", from_conds)
	
	return sql_mv, from_conds

def query_rewrite(method, rows):
	#path = "dataset/JOB_sql"
	#json_path = "dataset/JOB_json"
	path = "dataset/RED_SQL"
	json_path = "dataset/RED_JSON"

	os.system(f"rm -f Output/query_rewrite/re_sql/{method}/*")

	mv_path = "Output/query_rewrite/mv/"
	output_path = 'Output/'
	result_path = output_path+'query_rewrite/re_sql/'
	class_path = 'Output/qp_class.pkl'

	#counter for unused MVs
	unused_count = 0

	# all queries
	files = []
	for folder, _ , file in os.walk(path):
		temp = [folder +'/'+ f for f in file if f.endswith(".sql")]
		files = files + temp
	
	files = sorted( files, key=natural_sort_key)

	#red queries
	workloads_dir = "Output/RED_WORKLOADS"
	files = sorted(get_red_queries_sql(path, workloads_dir, GET_CEB)[0], key=natural_sort_key)

	# all queries
	json_files = []
	for folder, _ , file in os.walk(json_path):
		temp = [folder +'/'+ f for f in file if f.endswith(".json")]
		json_files = json_files + temp

	json_files = sorted(json_files, key=natural_sort_key)

	#red queries
	workloads_dir = "Output/RED_WORKLOADS"
	json_files = sorted(get_red_queries(json_path, workloads_dir, GET_CEB)[0], key=natural_sort_key)

	i = 0
	# with open(output_path + method + '/mv_y_list.csv', 'r') as file:
	# 	mv_data = csv.reader(file)
	# 	rows = list(mv_data)

	print(result_path + method)
	# delete all previously rewritten queries
	os.system(f"rm {result_path + method}/*")

	print("len(files): ", len(files))
	# print("len(json_files): ", len(json_files)) #消して良き
	# print("len(rows): ", len(rows))
	for file_id in range(len(files)):
		#if i != 92:
		#	i += 1
		#	continue
		#if file_id == 112:
		#	break
		
		if file_id >= len(rows):
			break
		#file_path = os.path.join(path, files[file_id])
		file_path = files[file_id]
		#json_file_path = os.path.join(json_path, json_files[file_id])
		json_file_path = json_files[file_id]
		# if files[file_id] != "12b.sql":
		# 	continue

		mv_node = rows[file_id]
		if len(mv_node) == 0:
			# print("file: ", files[file_id])
			# print(file_path)
			with open(file_path, "r") as f:
				content = f.read()
			tmpFile = files[file_id].split('/')[-1]
			with open(result_path + method + '/' + tmpFile, "w") as file:  #ファイル保存
				file.write(content)

			# shutil.copy(file_path, f"{output_path}query_rewrite/{files[file_id]}")
		else:
			with open(file_path, "r") as f:
				#print("file: ", files[file_id])
				content = f.read()
				# ここで解析処理を行う

			with open(json_file_path, "r") as f:
				json_content = f.read()
				json_content = json.loads(json_content)
				# print("json_content: ", json_content)
			hint = generate_hints(json_content[0])
			#print("hint",file_id,": ", hint)

			sql_original = content
			
			sql_original = sql_original.replace("  "," ")
			sql_original = sql_original.replace(" ("," ( ")
			sql_original = sql_original.replace(") "," )")
			sql_original = sql_original.replace("          ","")
			sql_original = re.sub(r'\bbetween\b', 'BETWEEN', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'\band\b', 'AND', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'\bor\b', 'OR', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'\blike\b', 'LIKE', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'\bnot\b', 'NOT', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'\bis\b', 'IS', sql_original, flags=re.IGNORECASE)
			# sql_original = re.sub(r'\bIN\b', '==', sql_original, flags=re.IGNORECASE)
			sql_original = re.sub(r'(?<! )=(?! )', ' = ', sql_original) # Ensure there is a space before and after '='
			sql_original = sql_original.replace("! =", "!=")

			sql_original = sql_original.replace("IS NOT","!!=") #is notに対応するため, 7c.sqlにあり
			sql_original = sql_original.replace("IS NULL","=== NULL") #is notに対応するため, 7c.sqlにあり

			sql_original = sql_original.replace(" as "," AS ")

			# print("sql_original: ", sql_original)
			
			if " IN " in sql_original or " in " in sql_original:
				sql_original = sql_original.replace(" IN ", " == ")
				sql_original = sql_original.replace(" in ", " == ")
			# if "= '" in sql_original: #1a.sqlに対応させるため、ここの空白を消す
			# 	sql_original = sql_original.replace("= '", "='")
			if "='" in sql_original:
				sql_original = sql_original.replace("='", "= '")

			sql_original = sql_original.replace("\n"," ")

			sql_original = rewrite_between_conditions_2(sql_original)
			# print("sql_original: ", sql_original)

			content = content.replace("\n"," ") # changes "" to " " beause it was causing errors
			content = content.replace(" as "," AS ") # ceb uses as instead of AS
			content = content.replace("     "," ")
			content = content.split(" FROM ")
			select_str = content[0].replace("SELECT ", " ")
			content = content[1].split(" WHERE ")
			from_str = content[0]
			where_str = content[1]

			group_str = content[1].split("GROUP BY")
		
			if len(group_str) >= 2:
				group_str = "GROUP BY " + group_str[1]
			else:
				group_str=""
			from_sql = "\nFROM "
			where_sql = ""

			check_iteration = 0
			new_conditions = []

			# print("from_str: ", from_str)
			
			for node in mv_node:
			#for node in rows:
				if node =="NONE":
					continue
				sql_mv, from_conds_mv = mv_node_analize(node)
				sql_mv = sql_mv.replace("IS NOT","!!=")
				sql_mv = sql_mv.replace("IS NULL","=== NULL")
				# print(from_conds_mv)
				# print("sql_mv: ", sql_mv, "\n")
				if check_iteration == 0:
					unique1, unique2, common = remove_common_conditions_2(sql_original, sql_mv, "sql")
					check_iteration = 1
				else:
					mv_conditions = set(extract_where_conditions(sql_mv))
					unique1, unique2, common = remove_common_conditions_2(set(new_conditions), mv_conditions, "condition")
				# print("original_unique1: ", unique1)
				# print("mv_unique2: ", unique2)
				# print("common: ", common)
				# print("\n\n")

				mv_alias = []
				from_str = from_str + ","
				for from_cond_mv in from_conds_mv:
					if from_cond_mv in from_str:
						# print("from_cond_mv: ", from_cond_mv)
						
						from_str = from_str.replace(from_cond_mv + ",", "mv" + ",")
						# from_str = from_str.replace(from_cond_mv + " ", "mv" + " ")
					from_cond_mv = from_cond_mv.split(" AS ")
					mv_alias.append(from_cond_mv[1])
				# print("mv_alias: ", mv_alias)
				
				
				from_str = from_str[:-1]
				from_str_list = from_str.split(", ")
				from_str_list = [item for item in from_str_list if item != " mv" and item != "mv"]
				from_str_list.append(str(node))
				from_str = ", ".join(from_str_list)
				# print("from_str: ", from_str)

				# if unique1 == []:
				# 	where_sql = ""
				# else:
				# 	where_sql = ""
				# 	for u1 in unique1:
				# 		where_sql += u1 + " AND "	
				# 	where_sql = where_sql[:-5]
				# # print("where_sql: ", where_sql, "\n")
				for mv_a in mv_alias:
					# print("mv_a: ", mv_a)
					for u_cond_id in range(len(unique1)):
						# print("unique1_cond: ", unique1[u_cond_id])
						unique1[u_cond_id] = " " + unique1[u_cond_id]
						if " " + mv_a + "." in unique1[u_cond_id]:
							unique1[u_cond_id] = unique1[u_cond_id].replace(" " + mv_a + ".", " " + node + "." + mv_a + "_") #ここ変えたよ1/23
							# print("changed_u_cond: ", unique1[u_cond_id])
						unique1[u_cond_id] = unique1[u_cond_id][1:]
					select_str = select_str.replace("(" + mv_a + ".", "(" + node + "." + mv_a + "_")
					select_str = select_str.replace(" " + mv_a + ".", " " + node + "." + mv_a + "_")
					group_str = group_str.replace("(" + mv_a + ".", "(" + node + "." + mv_a + "_")
					group_str = group_str.replace(" " + mv_a + ".", " " + node + "." + mv_a + "_")

					where_sql = where_sql.replace(mv_a + ".", node + ".")
					
				new_conditions = unique1
				# print("new_conditions: ", new_conditions)

				

				if " == " in sql_mv: # INの" == "を" IN "に変更
					with open(mv_path + node + ".sql", "r") as file:
						content = file.read()
					with open(mv_path + node + ".sql", "w") as file:
						content = content.replace(" == ", " IN ")
						file.write(content)

			where_cond = new_conditions
			# print("where_cond: ", where_cond)
			# Remove duplicate conditions in where_cond

			# Remove duplicate conditions in where_cond
			where_cond = list(set(where_cond))
			
			# Normalize conditions to handle a=b and b=a as the same
			normalized_cond = set()
			for cond in where_cond:
				if " = " in cond and " LIKE " not in cond and " OR " not in cond:
					parts = cond.split(" = ")
					# print("parts: ", parts)
					if parts[0] != parts[1]:
						if "." in parts[0] and "." in parts[1]:
							table1, col1 = parts[0].split(".")
							table2, col2 = parts[1].split(".")
							if table1 == table2:
								continue
							else:
								normalized_cond.add(" = ".join(sorted(parts)))
						elif "." in parts[0]:
							normalized_cond.add(parts[0] + " = " + parts[1])
						else:
							normalized_cond.add(parts[1] + " = " + parts[0])
						# normalized_cond.add(" = ".join(sorted(parts)))
				else:
					normalized_cond.add(cond)
			
			where_cond = list(normalized_cond)
			
			# Reconstruct where_sql from unique where_cond
			where_sql = " AND ".join(where_cond)
			if where_sql != "":
				where_sql = "\nWHERE " + where_sql
				if " == " in where_sql:
					where_sql = where_sql.replace(" == ", " IN ")
				if "!!=" in where_sql:
					where_sql = where_sql.replace("!!=", "IS NOT")
				if "===" in where_sql:
					where_sql = where_sql.replace("===", "IS")
			
			
			from_sql += from_str
			# print("arranged_from: ",from_str)

			# Reconstruct Group by sql
			if group_str != "":
				group_str = "\n" + group_str

			from_sql = "\n" + remake_from_sql_query(from_sql, where_sql, group_str, select_str)
			new_sql = "SELECT" + select_str + from_sql + where_sql + group_str +";"
			#print(new_sql)

			mvs = set(re.findall(r'\w*leaf\w*', from_sql))
			
			for mv in mvs:
				if mv not in where_sql and mv not in group_str:
					unused_count+=1
					print("Unused MV :", mv, "FILE ID ", file_id, from_sql)
					print()
					print(new_sql)
					print()
					

			tmpFile = files[file_id].split('/')[-1]
			with open(result_path + method + '/' + tmpFile, "w+") as file:  #ファイル保存
				#print("file: ", files[file_id])
				file.write(new_sql)
			# print("---------------------------------")


		
		# select_str = select_str.split(", ")
		# for select_cond in select_str:
		# 	if "MIN" in select_cond or "MAX" in select_cond or "SUM" in select_cond or "COUNT" in select_cond:
		# 		select_cond = select_cond.split("(")
		# 		select_row = select_cond[1].split(")")
				
		
		i += 1
	print("UNUSED MVS : ",unused_count)
def extract_sql_str(content):
	# sql = sql.split("WHERE ")
	# content = sql[1]
	if "AND (" in content:
		content = content.split("AND (")
		content[1] = content[1].split(") ")
		# print("content: ", content)
	
		content_1, content_2 = extract_sql_str(content[1][1])
		# content[0] = content[0][:-3]
		if content[1][1] == content_1:
			new_content_1 = content[0] + content[1][1]
			new_content_2 = content[1][0]
		else:
			new_content_1 = content[0] + content[1][1] + content_1
			new_content_2 = content[1][0] + " AND " + content_2      #こちらでカッコの中身を取得

	else:
		return content, ""
	return new_content_1, new_content_2



# Helper function to extract WHERE conditions
def extract_where_conditions(sql):
	parsed = sqlparse.parse(sql)
	statement = parsed[0]
	# print("statement: ", statement)
	where_clause = None

	# Find the WHERE clause
	for token in statement.tokens:
		if isinstance(token, Where):
			where_clause = token
			break

	if not where_clause:
		return []

	# Extract conditions from the WHERE clause
	conditions = []
	for token in where_clause.tokens:
		if token.ttype is Comparison or (isinstance(token, TokenList) and token.is_group):
			# print("token: ", token)
			conditions.append(str(token).strip())
	# print("conditions: ", conditions)
	return conditions

# Helper function to extract WHERE conditions
def extract_where_conditions_2(sql):
    parsed = sqlparse.parse(sql)
    statement = parsed[0]
    where_clause = None

    # Find the WHERE clause
    for token in statement.tokens:
        if isinstance(token, Where):
            where_clause = token
            break

    if not where_clause:
        return []

    # Extract conditions from the WHERE clause
    conditions = []
    current_condition = []

    for token in where_clause.tokens:
        # Group tokens until we hit a logical operator or end of condition
        if token.ttype in (Keyword, Comparison) or str(token).upper() in ('AND', 'OR'):
            if current_condition:
                conditions.append(" ".join(current_condition).strip())
                current_condition = []
            if token.ttype not in (Keyword, Comparison):
                continue
        current_condition.append(str(token).strip())

    # Append the last condition
    if current_condition:
        conditions.append(" ".join(current_condition).strip())

    return conditions

# Helper function to remove common conditions
def remove_common_conditions(sql1, sql2):
	conditions1 = set(extract_where_conditions(sql1))
	conditions2 = set(extract_where_conditions(sql2))

	# Find common conditions
	common_conditions = conditions1.intersection(conditions2)

	# Remove common conditions from each set
	unique_conditions1 = conditions1 - common_conditions
	unique_conditions2 = conditions2 - common_conditions

	return list(unique_conditions1), list(unique_conditions2), list(common_conditions)

def remove_common_conditions_2(sql1, sql2, method):
	if method == "sql":
		conditions1 = set(extract_where_conditions(sql1))
		conditions2 = set(extract_where_conditions(sql2))
	elif method == "condition":
		conditions1 = sql1
		conditions2 = sql2
	# conditions1 = set(extract_sql_str(sql1))
	# conditions2 = set(extract_sql_str(sql2))
	# print("conditions1: ", conditions1)
	# print("conditions2: ", conditions2)
	# print("\n\n")

	for u_cond1 in conditions1:
		if " == " in u_cond1:
			new_u_cond1 = u_cond1.replace(" == ", " = ")  # INの" == "を" = "に変更
			new_u_cond1 = new_u_cond1.replace("(", "")
			new_u_cond1 = new_u_cond1.replace(")", "")
			# print("new_u_cond1: ", new_u_cond1)
			if new_u_cond1 in conditions2:
				conditions2.remove(new_u_cond1)
				conditions2.add(u_cond1)
		
		if u_cond1[0] == "(" and u_cond1[-1] == ")":
			new_u_cond1 = u_cond1[1:]
			new_u_cond1 = new_u_cond1[:-1]
			# print("new_u_cond1: ", new_u_cond1)
			if new_u_cond1 in conditions2:
				conditions2.remove(new_u_cond1)
				conditions2.add(u_cond1)
	# Find common conditions
	# print("conditions1: ", conditions1)
	# print("conditions2: ", conditions2)
	common_conditions = conditions1.intersection(conditions2)

	# Remove common conditions from each set
	unique_conditions1 = conditions1 - common_conditions
	unique_conditions2 = conditions2 - common_conditions

	new_conditions2 = []

	for u_cond2 in unique_conditions2:
		if " = " in u_cond2:
			u_cond2 = u_cond2.split(" = ")
			u_cond2 = u_cond2[1] + " = " + u_cond2[0]
			new_conditions2.append(u_cond2)
	
	new_common_conditions = []
	new_common_conditions = conditions1.intersection(new_conditions2)

	new_unique_conditions1 = unique_conditions1 - new_common_conditions

	common_conditions = common_conditions.union(new_common_conditions)

	return list(new_unique_conditions1), list(unique_conditions2), list(common_conditions)


# Helper function to rewrite BETWEEN conditions
def rewrite_between_conditions(sql):
	parsed = sqlparse.parse(sql)
	statement = parsed[0]

	# Rewrite WHERE clause
	for token in statement.tokens:
		if isinstance(token, Where):
			new_tokens = []
			skip_next = False

			for i, subtoken in enumerate(token.tokens):
				print("subtoken: ", subtoken)
				# Skip processing if the previous token already handled
				if skip_next:
					skip_next = False
					continue

				# Check if the current token is a BETWEEN clause
				if subtoken.ttype == Keyword and subtoken.value.upper() == 'BETWEEN':
					# Get the column name, lower bound, and upper bound
					column = token.tokens[i - 1].value.strip()
					lower_bound = token.tokens[i + 1].value.strip()
					upper_bound = token.tokens[i + 3].value.strip()
					# print(token.tokens[i - 2].value.strip())
					# print(column, lower_bound, upper_bound)

					# Rewrite the condition
					rewritten_condition = f"{column} >= {lower_bound} AND {column} <= {upper_bound}"
					print("rewritten_condition: ", rewritten_condition)
					new_tokens.append(sqlparse.sql.Token(None, rewritten_condition))

					# Skip the next tokens related to BETWEEN
					skip_next = True
				else:
					new_tokens.append(subtoken)

			# Replace tokens in the WHERE clause
			token.tokens = new_tokens

	return str(statement)

def rewrite_between_conditions_2(sql):
	sql = sql.split("WHERE ") # split does not work on newer sql
	where_str = sql[1]
	where_str = where_str.split(" ")
	new_where_str = "WHERE "
	j = 0
	while j < len(where_str):
		if where_str[j] == "BETWEEN":
			new_where_str += ">= " + where_str[j+1] + " AND " + where_str[j-1] + " <= " + where_str[j+3] + " "
			j += 4
		else:
			new_where_str += where_str[j] + " "
			j += 1
	new_sql = sql[0] + new_where_str
	return new_sql

def natural_sort_key(s):
		return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


def mv_remake(mv_nodes):
	table_columns = {
		"aka_name":["id", "person_id", "name", "imdb_index", "name_pcode_cf", "name_pcode_nf", "surname_pcode", "md5sum"],
		"aka_title":["id", "movie_id", "title", "imdb_index", "kind_id", "production_year", "phonetic_code", "episode_of_id", "season_nr", "episode_nr", "note", "md5sum"],
		"cast_info":["id", "person_id", "movie_id", "person_role_id", "note", "nr_order", "role_id"],
		"char_name":["id", "name", "imdb_index", "imdb_id", "name_pcode_nf", "surname_pcode", "md5sum"],
		"comp_cast_type":["id", "kind"],
		"company_name":["id", "name", "country_code", "imdb_id", "name_pcode_nf", "md5sum"],
		"company_type":["id", "kind"],
		"complete_cast":["id", "movie_id", "subject_id", "status_id"],
		"info_type":["id", "info"],
		"keyword":["id", "keyword", "phonetic_code"],
		"kind_type":["id", "kind"],
		"link_type":["id", "link"],
		"movie_companies":["id", "movie_id", "company_id", "company_type_id", "note"],
		"movie_info_idx":["id", "movie_id", "info_type_id", "info", "note"],
		"movie_keyword":["id", "movie_id", "keyword_id"],
		"movie_link":["id", "movie_id", "linked_movie_id", "link_type_id"],
		"name":["id", "name", "imdb_index", "imdb_id", "gender", "name_pcode_cf", "name_pcode_nf", "surname_pcode", "md5sum"],
		"role_type":["id", "role"],
		"title":["id", "title", "imdb_index", "kind_id", "production_year", "imdb_id", "phonetic_code", "episode_of_id", "season_nr", "episode_nr", "series_years", "md5sum"],
		"movie_info":["id", "movie_id", "info_type_id", "info", "note"],
		"person_info":["id", "person_id", "info_type_id", "info", "note"]
	}
	path = "Output/query_rewrite/mv/"
	output_path = 'Output/'

	
	# with open(output_path + method + '/mv_y_list.csv', 'r') as file:
	# 	mv_data = csv.reader(file)
	# 	rows = list(mv_data)

	# mv_nodes = []
	# for query_num in rows:
	# 	for node_name in query_num:
	# 		if node_name not in mv_nodes:
	# 			mv_nodes.append(node_name)


	for node in mv_nodes:
		if node == "NONE":
			continue
		select_str = ""
		columns_list = {}
		with open(path + node + ".sql", "r") as file:
			content = file.read()
		from_conds = content.split("FROM ")
		from_conds = from_conds[1].split("WHERE")
		from_str = from_conds[0]
		if from_str[-1] == ";":
			#from_str = from_str[:-1]
			from_str = from_str[:-4] # This will iclude the " ');"
		from_str = from_str.replace("\n", "")
		from_str = from_str.split(", ")
		for table in from_str:
			table = table.split(" AS ")
			table_name = table[0]
			alias = table[1]
			if table_name not in table_columns:
				print("table_name: ", table_name, table)
				print("node: ", node)
			columns = table_columns[table_name]
			for col in columns:
				select_str += alias + "." + col + " AS " + alias + "_" + col + ", "
		select_str = select_str[:-2]

		# print("node: ", node)
		# print(select_str)
		
		# content = "SET enable_nestloop = off;\n" + content
		content = content.replace("SELECT *", "SELECT " + select_str)
		content = content.replace(" == ", " IN ")
		# print(content)

		with open(path + node + ".sql", "w") as file:
			# print("file:", file)
			file.write(content)
		
		# print("----------------------------")
			
def extract_execution_order(plan, order=[]):
    """
    再帰的に JSON の実行計画を解析し、実行順序を抽出する。
    """
    if 'Relation Name' in plan:
        order.append(plan['Relation Name'])
    
    if 'Plans' in plan:
        for subplan in plan['Plans']:
            extract_execution_order(subplan, order)
    
    return order

def generate_hints(json_plan):
    """
    JSON 実行計画から PostgreSQL のヒント句を生成する。
    """
    execution_order = extract_execution_order(json_plan['Plan'], [])
    
    if execution_order:
        hint = f"/*+ Leading({', '.join(execution_order)}) */"
        return hint
    else:
        return ""



if __name__ == '__main__':
	q_num = 8
	sq_num = 8
	B_max = 1000
	insert_query = 0

	method = 'bigsubs'
	node = ["leaf_219"]
	# mv_make(node)
	# query_rewrite(method)
	# mv_remake(node)

	mv_nodes_bigsubs = []
	with open("Output/normal/mv_y_list.csv", "r") as f:
		reader = csv.reader(f)
		bigsubs_mv_rows = list(reader)
	
	query_rewrite(method, bigsubs_mv_rows)

	class_path = 'Output/qp_class.pkl'
	with open(class_path, 'rb') as file:
		qp = pickle.load(file)
	
	# print("qp.qm.leaf_nodes_map_r: ", qp.qm.leaf_nodes_map_r["leaf_43"])
	# print("qp.qm.non_leaf_nodes_map_r: ", qp.qm.non_leaf_nodes_map_r["non_leaf_162"])
	# print("qp.qm.subquery_positions: ", qp.qm.subquery_positions["leaf_43"])