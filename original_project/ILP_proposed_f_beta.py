#coding: utf-8

import gurobipy as gp
import copy

def ILP(u_ij,x,M,B_max,cand_j,cand_i,b_j,m_cost):

    #model make
    model = gp.Model("lo1")
    model.Params.OutputFlag=0
    y={}
    for i in range(len(cand_i)):
        for j in range(len(cand_j)):
            y[i,j]=model.addVar(vtype=gp.GRB.BINARY,name="%d use %d"%(i,j))
    z={}
    for j in range(len(cand_j)):
        z[j]=model.addVar(vtype=gp.GRB.BINARY,name="matelialize %d"%j)

    model.update()

    # model.setObjective(gp.quicksum(u_ij[i][j]*y[i,j] -z[j]*m_cost[j]/len(cand_i) for i in range(len(cand_i)) for j in range(len(cand_j))), gp.GRB.MAXIMIZE)
    model.setObjective(
        gp.quicksum(u_ij[i][j] * y[i, j] for i in range(len(cand_i)) for j in range(len(cand_j)))
        - gp.quicksum(z[j] * m_cost[j] for j in range(len(cand_j))),
        gp.GRB.MAXIMIZE
    )

    con1={}#overlapping subexpression
    con2={}#storage
    t=0
    for i in range(len(cand_i)):
        for j in M[i]:
            con1[t]=model.addConstr(y[i,j]+(gp.quicksum(y[i,u]*x[j][u] for u in M[i]))/len(cand_j)<=1)
            con2[t]=model.addConstr(y[i,j]<=z[j])
            t+=1

    model.addConstr(gp.quicksum(b_j[j]*z[j] for j in range(len(cand_j)))<=B_max)
    model.optimize()


    ret_y=[[0]*len(b_j) for i in range(len(u_ij))]
    ret_z=[0]*len(b_j)
    for j in range(len(b_j)):
        ret_z[j]=z[(j)].X
        for i in range(len(u_ij)):
            ret_y[i][j]=y[(i,j)].X

    return ret_y,ret_z,model.objVal


def initialize(mv_list,qm,b_max,U_j_max,m_cost,node_list): #ここで初期解を選択していて、u_bをとっている
    U_B_list={}
    for i in range(len(node_list)):
        U_B_list[node_list[i]] = len(qm.subquery_positions[node_list[i]])
    #U_B_listを降順にソート-----{'a': 3, 'b': 1, 'c': 2}  →  [('a', 3), ('c', 2), ('b', 1)]
    U_B_list_sorted=sorted(U_B_list.items(),key=lambda x:x[1],reverse=True) 
    # print("UBs= ", U_B_list_sorted)

    n=0
    b_now=0
    flag=0
    for n in range(len(U_B_list_sorted)):  #容量制約を満たすまで、利得/容量の高いものから選択
        if(b_now+qm.subquery_sizes[(U_B_list_sorted[n][0])] <= b_max):
            mv_list[node_list.index(U_B_list_sorted[n][0])]=1
            b_now+=qm.subquery_sizes[(U_B_list_sorted[n][0])]
    
    return mv_list

def neighbor_search_1(mv_list,opelist,ope_num,ope_num_list,deeplist):
    new_list_j=[]
    for i in range(len(mv_list)):
        if(mv_list[i]==1):
            uplist=[]
            for item in ope_num[ope_num_list[i]]: #itemには[[i,j]]が入っている
                uplist.append(up(item[0],item[1],deeplist))

            #downlist=down(ope_num[ope_num_list[i]][0][0],ope_num[ope_num_list[i]][0][1],deeplist,opelist)
            for item in uplist:
                if(item!=None):
                    j=ope_num_list.index(opelist[item[0]][item[1]])
                    if not(j in new_list_j):
                        new_list_j.append(j)
            '''for item in downlist:
                j=ope_num_list.index(opelist[item[0]][item[1]])
                if not(j in new_list_j):
                    new_list_j.append(j)
            '''
    for j in new_list_j:
        mv_list[j]=1
    return mv_list

def neighbor_search(mv_list, qm, node_list, ps_node_id, deeplist):
    new_list_j=[]
    # print("ps_node_id= ", ps_node_id)
    for i in range(len(mv_list)):
        if(mv_list[i]==1):
            #upword
            uplist=[]
            for item in qm.subquery_positions[node_list[i]]:
                uplist.append(up(item[0],item[1],deeplist))

            for item in uplist:
                if(item!=None):
                    position = (item[0], item[1])
                    j=node_list.index(ps_node_id[position])
                    if not(j in new_list_j):
                        new_list_j.append(j)

            #downword
            if node_list[i].startswith("non_leaf_"):
                for item in qm.non_leaf_nodes_map_r[node_list[i]]:
                    j = node_list.index(item)
                    if not(j in new_list_j):
                        new_list_j.append(j)

    for j in new_list_j:
        mv_list[j]=1
    return mv_list


def up(a,b,deeplist):
    i=1
    flag=0
    while(flag!=1):
        if (deeplist[a][b]==0):#根
            break
        if (deeplist[a][b-i]==deeplist[a][b]-1):
            return([a,b-i])
            flag=1
        i+=1
def down(a,b,deeplist,opelist):
    i=0
    down_return=[]
    flag=0
    if(deeplist[a][b]!=deeplist[a][-1]):
        while(flag!=1):#子方向は近傍が複数ある可能性あり
            if (deeplist[a][b+1]==deeplist[a][b]+1):
                down_return.append([a,b+i])
            if (opelist[a][b+i]==opelist[a][-1]):
                break
            i+=1
    return(down_return)

def make_nodename_from_id(x_list, node_list):
    node_name_list = []
    for i in range(len(x_list)):
        node_name_list.append(node_list[x_list[i]])
    return node_name_list


def proposed(qm,s_num,m_cost,node_list, position_node_id, deeplist, B_max, b_j, q_s_list, u_ij, X):
    #initialize
    #s_num　はサブクエリの数
    U_pre=0
    z_j=[0]*s_num
    U_j_max = copy.deepcopy(qm.subquery_costs)
    for item in U_j_max: #node_idを抜き出している
        U_j_max[item]=U_j_max[item]*len(qm.subquery_positions[item])

    # print("U_j_max= ",U_j_max)
    z_j=initialize(z_j,qm,B_max,U_j_max,m_cost,node_list)

    # z_jはnode_listの順番で格納される
    # つまり、["leaf_1", "leaf_2", ..., "leaf_n", "non_leaf_1", "non_leaf_2", ..., "non_leaf_m"]の順番で格納される
    # print("z_j= ",z_j)

    # if you want to set z_j manually, you can use the following code
    # z_j = [0]*s_num
    # X_test = [1, 2, 3, 4, 5,13]
    # for x in X_test:
    #     z_j[x-1] = 1

    iter_flag=0
    iter = 0
    while(iter_flag==0):
        # print("iter= ",iter)
        z_j=neighbor_search(z_j,qm,node_list, position_node_id, deeplist)  #近傍探索では親しか見ていない
        #Edge labeling
        # print("z_j= ",z_j)
        # for i in range(len(z_j)):
        #     if z_j[i] == 1:
                # print(node_list[i])

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

        cand_u=[[0 for j in range(len(cand_j))] for i in range(len(cand_i))]
        cand_m_cost=[0 for j in range(len(cand_j))]
        cand_x=[[0 for j in range(len(cand_j))] for i in range(len(cand_j))]
        cand_b=[0 for j in range(len(cand_j))]

        M=[]#クエリiに対して、利得のあるサブクエリのset
        for i in range(len(cand_i)):
            M_i=[]
            M_i_=[]
            for j in range(len(cand_j)):
                cand_u[i][j]=u_ij[cand_i[i]][cand_j[j]]
                if(u_ij[cand_i[i]][cand_j[j]]>0):
                    M_i.append(j)
                if(z_j[cand_j[j]]>0):
                    M_i_.append(j)
            k=list(set(M_i)&set(M_i_))
            M.append(k)

        for j in range(len(cand_j)):
            cand_b[j]=b_j[cand_j[j]]
            cand_m_cost[j]=m_cost[cand_j[j]]
            for j2 in range(len(cand_j)):
                cand_x[j][j2]=X[cand_j[j]][cand_j[j2]]


        # print(len(cand_i),len(cand_j))
        #print('ILP_start')
        y_z_obj=ILP(cand_u,cand_x,M,B_max,cand_j,cand_i,cand_b,cand_m_cost)
        y_ij=y_z_obj[0]
        z_j=[0]*len(b_j)
        for i in range(len(y_z_obj[1])):
            z_j[cand_j[i]]=y_z_obj[1][i]
        U_cur=y_z_obj[2]

        #print('---------------------')
        mat_list=[]
        B_cur=0
        for j in range(len(z_j)):
            B_cur+=b_j[j]*z_j[j]
            if(z_j[j] ==1):
                mat_list.append(j)
        node_name_list = make_nodename_from_id(mat_list, node_list)
        # print("After = ",node_name_list)

        # print("y_ij= ",y_ij)
        node_name_list_y=[]
        for i in range(len(y_ij)):
            node_y_seed=[]
            for j in range(len(y_ij[i])):
                if(y_ij[i][j]==1):
                    node_y_seed.append(j)
            node_y_seed = make_nodename_from_id(node_y_seed, node_name_list_b)
            node_name_list_y.append(node_y_seed)

        # print("y_ij= ",node_name_list_y)
        # print("---------------------------------------------------------------\n")

        if(U_pre>=U_cur): #convergence condition
            iter_flag=1
        U_pre=U_cur
        z_j_pre=z_j
        y_ij_pre=y_ij

        iter+=1
    #print(U_cur,B_cur)

    import numpy as np
    import pandas as pd
    top_cost=[0]*len(cand_j)
    count_j=[0]*len(cand_j)
    cost_j=[0]*len(cand_j)
    sum=0
    for i in range(len(y_ij_pre)):
        for j in range(len(y_ij_pre[i])):
            if(y_ij_pre[i][j]==1):
                count_j[j]+=1
    l_2d_t = np.array(u_ij).T.tolist()
    for j in range(len(cand_j)):
        cost_j[j]=max(l_2d_t[cand_j[j]])
        top_cost[j]=cost_j[j]*count_j[j]
    top_cost=np.array(top_cost)
    topten=[]
    # for i in range(10):

    top_num  = 10
    if len(cand_j) < 10:
        top_num = len(cand_j)
    for i in range(top_num):
        topten.append(cand_j[np.argsort(top_cost)[::-1][i]])

    y_ij=[[0 for i in range(len(z_j))] for j in range(len(u_ij))]
    for i in range(len(y_ij_pre)):
        for j in range(len(y_ij_pre[i])):
            y_ij[cand_i[i]][cand_j[j]]=y_ij_pre[i][j]

    #return topten,y_ij,z_j
    return U_cur,B_cur, y_ij


def no_neighbor_search(qm,s_num,m_cost,node_list, position_node_id, deeplist, B_max, b_j, q_s_list, u_ij, X):
    #initialize
    #s_num　はサブクエリの数
    U_pre=0
    z_j=[0]*s_num
    U_j_max = copy.deepcopy(qm.subquery_costs)
    for item in U_j_max: #node_idを抜き出している
        U_j_max[item]=U_j_max[item]*len(qm.subquery_positions[item])

    # print("U_j_max= ",U_j_max)
    z_j=initialize(z_j,qm,B_max,U_j_max,m_cost,node_list)

    count_z = 0
    for z in z_j:
        if z == 1:
            count_z += 1
    print("count_z= ",count_z)

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

    cand_i=[]#mv候補となるサブクエリを利用しているクエリ
    for i in range(len(M)):
        if(len(M[i])!=0):
            cand_i.append(i)
    cand_j=[]#mv候補となるサブクエリ
    for j in range(len(z_j)):
        if(z_j[j]==1):
            cand_j.append(j)
    
    cand_u=[[0 for j in range(len(cand_j))] for i in range(len(cand_i))]
    cand_m_cost=[0 for j in range(len(cand_j))]
    cand_x=[[0 for j in range(len(cand_j))] for i in range(len(cand_j))]
    cand_b=[0 for j in range(len(cand_j))]
    
    M=[]#クエリiに対して、利得のあるサブクエリのset
    for i in range(len(cand_i)):
        M_i=[]
        M_i_=[]
        for j in range(len(cand_j)):
            cand_u[i][j]=u_ij[cand_i[i]][cand_j[j]]
            if(u_ij[cand_i[i]][cand_j[j]]>0):
                M_i.append(j)
            if(z_j[cand_j[j]]>0):
                M_i_.append(j)
        k=list(set(M_i)&set(M_i_))
        M.append(k)

    for j in range(len(cand_j)):
        cand_b[j]=b_j[cand_j[j]]
        for j2 in range(len(cand_j)):
            cand_x[j][j2]=X[cand_j[j]][cand_j[j2]]


    #print('ILP_start')
    y_z_obj=ILP(cand_u,cand_x,M,B_max,cand_j,cand_i,cand_b,cand_m_cost)
    y_ij=y_z_obj[0]
    z_j=[0]*len(b_j)
    for i in range(len(y_z_obj[1])):
        z_j[cand_j[i]]=y_z_obj[1][i]
    U_cur=y_z_obj[2]

    B_cur=0
    for j in range(len(z_j)):
        B_cur+=b_j[j]*z_j[j]

    return U_cur,B_cur, y_ij
