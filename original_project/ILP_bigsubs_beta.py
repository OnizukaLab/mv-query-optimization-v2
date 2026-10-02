#coding: utf-8

import gurobipy as gp
import random
import time

def initialize(mv_list):
    # creates random k list of randomly-labeled expressions
    k = random.randint(1,len(mv_list))
    k_list = random.sample(range(len(mv_list)), k)
    for i in k_list:
        mv_list[i] = 1
    return mv_list

def FlipP(iter,z_j,b_j,B_cur,U_cur,U_j_cur,U_j_max,U_max,B_max):
    p=10#kに合わせて変える
    #print(B_cur,B_max)
    if(B_cur<B_max):
        p_j_capacity=1-(float(B_cur)/B_max)
    else:
        p_j_capacity=1-(float(B_max)/B_cur)

    if(z_j==1):
        p_j_utility=1-(float(U_j_cur)/U_cur)

    elif(iter<=p or B_cur<=B_max-b_j):
        p_j_utility=(float(U_j_max)/b_j)/(float(U_max)/B_max)

        #print((float(U_j_max)/b_j),(float(U_max)/B_max))
    else:
        p_j_utility=0
    #print(p_j_capacity,p_j_utility)
    return p_j_capacity*p_j_utility

def DoFlip(p,z):
    t=random.random()
    if(p>t):
        if(z==0):
            return 1
        else:
            return 0
    else:
        return z


def LocalILP(u_ij,X,k,b_j,m_cost,i_len):
    #model make
    model = gp.Model("lo1")
    model.Params.OutputFlag=0

    y={}
    for j in range(len(b_j)):
        y[j]=model.addVar(vtype=gp.GRB.BINARY,name="use%d"%j)

    model.update()

    # model.setObjective(gp.quicksum(u_ij[j]*y[j] -m_cost[j]/i_len for j in k), gp.GRB.MAXIMIZE)
    model.setObjective(gp.quicksum(u_ij[j]*y[j] - m_cost[j]*y[j] for j in k), gp.GRB.MAXIMIZE)

    con={}#overlapping subexpression
    t=0
    for i in k:
        k_min=[]
        for s in k:
            if(s!=i):
                k_min.append(s)
        con[t]=model.addConstr((y[i]+(gp.quicksum(y[j]*X[i][j] for j in k_min)/len(b_j)))<=1) #包含制約
        t+=1


    model.optimize()

    y_opt=[]
    for v in model.getVars():
        y_opt.append(v.X)

    return y_opt


def bigsubs(s_num,m_cost,b_j,U_j_max,q_s_list,u_ij,y_ij,X,U_max,B_max):
    t=time.time()
    #initialize
    z_j=[0]*s_num
    z_j=initialize(z_j)

    B_cur=0
    for j in range(len(z_j)):
        B_cur+=z_j[j]*b_j[j]

    iter_max=3
    iter=0
    updated=1

    U_cur=1
    U_j_cur=[0]*len(z_j)
    best_u=0
    best_b=0

    del_j=[]
    # for j in range(len(z_j)):
    #     if('Nested Loop' in ope_num_list[j]):
    #         for t in range(len(X[j])):
    #             if(X[j][t]==1):
    #                 if('rows=1' in ope_num_list[t]):
    #                     del_j.append(t)
    #     if('Bitmap' in ope_num_list[j]):
    #         for t in range(len(X[j])):
    #             if(X[j][t]==1):
    #                 del_j.append(t)
    #     if('Bitmap Index Scan on' in ope_num_list[j]):
    #         del_j.append(j)
    # del_j=list(set(del_j))

    while(updated==1 and iter<iter_max):
        # print("iter=",iter)
        updated=0
        #subexpression vertex labeling
        for j in range(len(z_j)):

            if(j in del_j):
                z_j_new=0
            else:
                p_flip=FlipP(iter,z_j[j],b_j[j],B_cur,U_cur,U_j_cur[j],U_j_max[j],U_max,B_max)
                z_j_new=DoFlip(p_flip,z_j[j])

            if(z_j_new!=z_j[j]):
                updated=1
                if(z_j_new==0):
                    B_cur-=b_j[j]
                else:
                    B_cur+=b_j[j]
            z_j[j]=z_j_new

        #Edge labeling
        U_cur=0
        U_j_cur=[0]*len(z_j)
        z_j_new = [0]*len(z_j)

        for i in range(len(q_s_list)):
            M_i=[]
            M_i_=[]
            for j in range(len(z_j)):
                if(u_ij[i][j]>0):
                    M_i.append(j)
                if(z_j[j]>0):
                    M_i_.append(j)

            k=list(set(M_i)&set(M_i_))
            #NestedLoopの下位のサブクエリ(下位のindex scan?)は実体化候補から外す
            #bitmap index scan の下位のサブクエリも外す

            y_ij[i]=LocalILP(u_ij[i],X,k,b_j,m_cost,len(q_s_list))

            for j in k:
                if y_ij[i][j]==1 and z_j_new[j]==0:
                    
                    U_cur += u_ij[i][j]*y_ij[i][j] - m_cost[j]/len(q_s_list)
                    # for s_p in s_positions[node_list[j]]:
                    #     i_part = s_p[0]
                    #     if i_part == i:
                    #         print("i,j=",i,j, "\t", U_cur, u_ij[i][j], "\t", s_p[1])
                    z_j_new[j]=1
                # U_cur += u_ij[i][j]*y_ij[i][j] #To DO 重複しているのも計算しちゃってるよ
                U_j_cur[j] += u_ij[i][j]*y_ij[i][j]
        
        for j in range(len(z_j)):
            z_j[j]=z_j_new[j]
            U_cur -= m_cost[j]*z_j[j]
        iter+=1
        #print('---------------------')
        mat_list=[]
        for i in range(len(z_j)):
            if(z_j[i] ==1):
                mat_list.append(i)

        #print(U_cur,B_cur)
        # print("U_cur=",U_cur)

        if(U_cur>best_u):
            best_u=U_cur
            best_b=B_cur
            best_time=time.time()
        #print(mat_list)

    #print('best_u','best_b','best_time')
    #print('best',best_u,best_b,best_time-t)
    #print(U_cur,B_cur)

    #return best_u,best_b,best_time-t,y_ij,z_j

    return U_cur,B_cur, y_ij



