#coding: utf-8

import gurobipy as gp
import copy

def ILP(u_ij,x,M,B_max,cand_j,cand_i,b_j,m_cost):
	#model make
	model = gp.Model("lo1")
	model.Params.OutputFlag=0
	y={}
	for i in range(len(u_ij)):
		for j in range(len(b_j)):
			y[i,j]=model.addVar(vtype=gp.GRB.BINARY,name="%d use %d"%(i,j))
	z={}
	for j in range(len(b_j)):
		z[j]=model.addVar(vtype=gp.GRB.BINARY,name="matelialize %d"%j)

	model.update()

	# model.setObjective(gp.quicksum(u_ij[i][j]*y[i,j] -z[j]*m_cost[j]/len(cand_j) for i in range(len(u_ij)) for j in cand_j), gp.GRB.MAXIMIZE)
	model.setObjective(
        gp.quicksum(u_ij[i][j] * y[i, j] for i in range(len(cand_i)) for j in range(len(cand_j)))
        - gp.quicksum(z[j] * m_cost[j] for j in range(len(cand_j))),
        gp.GRB.MAXIMIZE
    )

	con1={}#overlapping subexpression
	con2={}#storage
	t=0
	for i in range(len(u_ij)):
		for j in range(len(b_j)):
			con1[t]=model.addConstr(y[i,j]+(gp.quicksum(y[i,u]*x[j][u] for u in range(len(b_j))))/len(b_j)<=1)
			con2[t]=model.addConstr(y[i,j]<=z[j])
			t+=1

	model.addConstr(gp.quicksum(b_j[j]*z[j] for j in range(len(b_j)))<=B_max)
	model.optimize()


	ret_y=[[0]*len(b_j) for i in range(len(u_ij))]
	ret_z=[0]*len(b_j)
	for j in range(len(b_j)):
		ret_z[j]=z[(j)].X
		for i in range(len(u_ij)):
			ret_y[i][j]=y[(i,j)].X

	return ret_y,ret_z,model.objVal

def make_nodename_from_id(x_list, node_list):
	node_name_list = []
	for i in range(len(x_list)):
		node_name_list.append(node_list[x_list[i]])
	return node_name_list


def normal(qm,s_num,m_cost,node_list, B_max, b_j, u_ij, X, q_s_list):
	#initialize
	#s_num　はサブクエリの数
	U_pre=0
	U_j_max = copy.deepcopy(qm.subquery_costs)
	for item in U_j_max: #node_idを抜き出している
		U_j_max[item]=U_j_max[item]*len(qm.subquery_positions[item])

	# print("U_j_max= ",U_j_max)
	z_j=[1]*s_num

	# z_jはnode_listの順番で格納される
	# つまり、["leaf_1", "leaf_2", ..., "leaf_n", "non_leaf_1", "non_leaf_2", ..., "non_leaf_m"]の順番で格納される


	M=[]#クエリiに対して、利得のあるサブクエリのset
	for i in range(len(q_s_list)):
		M_i=[]
		M_i_=[]
		for j in range(len(z_j)):
			if(u_ij[i][j]>0):
				M_i.append(j)
			if(z_j[j]>0):
				M_i_.append(j)

		k=list(set(M_i)&set(M_i_))
		M.append(k)
	
	node_name_list_M = []
	for m_data in M:
		node_name_list_M_m = make_nodename_from_id(m_data, node_list)
		node_name_list_M.append(node_name_list_M_m)
	# print("M= ",node_name_list_M)


	cand_i=[]#mv候補となるサブクエリを利用しているクエリ
	for i in range(len(M)):
		if(len(M[i])!=0):
			cand_i.append(i)
	cand_j=[]#mv候補となるサブクエリ
	for j in range(len(z_j)):
		if(z_j[j]==1):
			cand_j.append(j)
	# print(len(cand_i),len(cand_j))
	# print(cand_i)
	# print(cand_j)

	node_name_list_b = make_nodename_from_id(cand_j, node_list)
	# print("Before = ",node_name_list_b)

	#NestedLoopの下位のサブクエリ(下位のindex scan?)は実体化候補から外す
	#bitmap index scan の下位のサブクエリも外す
	"""
	del_j=[]
	for j in cand_j:
		if('Nested Loop' in ope_num_list[j]):
			for i in range(len(X[j])):
				if(X[j][i]==1):
					if('rows=1' in ope_num_list[i]):
						del_j.append(i)
		if('Bitmap' in ope_num_list[j]):
			for i in range(len(X[j])):
				if(X[j][i]==1):
					del_j.append(i)
		if('Bitmap Index Scan on' in ope_num_list[j]):
			del_j.append(j)
	del_j=list(set(del_j))
	for j in del_j:
		if(j in cand_j):
			cand_j.remove(j)
	"""



	#print('ILP_start')
	y_z_obj=ILP(u_ij,X,M,B_max,cand_j,cand_i,b_j,m_cost)
	y_ij=y_z_obj[0]
	z_j=y_z_obj[1]
	U_cur=y_z_obj[2]

	#print('---------------------')
	mat_list=[]
	B_cur=0
	for j in range(len(z_j)):
		B_cur+=b_j[j]*z_j[j]
		if(z_j[j] ==1):
			mat_list.append(j)
	#print(mat_list)

	#print(U_cur,B_cur)

	if(U_pre>=U_cur):
		iter_flag=1
	U_pre=U_cur
	z_j_pre=z_j
	y_ij_pre=y_ij


	return U_cur,B_cur,y_ij

