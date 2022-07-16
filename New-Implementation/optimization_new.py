##### Initialization & Changeable Parameters ######
#%%
#region
from os import close, linesep
from Modules import data_import

from gurobipy import *
import itertools
import os.path
import pickle
import time
#endregion


def main_func(iter_lims, beta_fun, sub_mip_gap, import_data, export_data, export_model, import_model=False):

    ##### Read Data #####
    #region
    my_path = os.getcwd()
    input_data = data_import.read_data(os.path.join(my_path, import_data))

    # Quick Assess to Various Parameters
    TL = input_data.transition.wait_limit
    BM = 10000
    U = input_data.usage
    p_dat = input_data.ppe_data
    pea = input_data.arrival
    gam = input_data.model_param.gamma
    ptp_d = input_data.transition.transition_rate_comp
    ptp_k = input_data.transition.transition_rate_pri
    cw = input_data.model_param.cw
    cs = input_data.model_param.cs
    cc = input_data.model_param.cc
    cv = input_data.model_param.cv
    cuu = 1000

    ##### Generating Sets #####
    T = input_data.indices['t']
    M = input_data.indices['m']
    P = input_data.indices['p']
    D = input_data.indices['d']
    K = input_data.indices['k']
    C = input_data.indices['c']

    # Sub Sets
    PCO = []
    PNCO = []
    for k, v in input_data.ppe_data.items(): 
        if v.ppe_type == "non-carry-over": PNCO.append(k) 
        else: PCO.append(k)
        
    mTLdkc = [(m, d, k, c) for c in C for m in M[1:input_data.transition.wait_limit[c]] for d in D for k in K ]
    TLMdkc = [(m, d, k, c) for c in C for m in M[input_data.transition.wait_limit[c]:-1] for d in D for k in K ]
    tmTLdkc = [(t, m, d, k, c) for t in T[:-1] for c in C for m in M[1:input_data.transition.wait_limit[c]] for d in D for k in K ]
    tTLMdkc = [(t, m, d, k, c) for t in T[:-1] for c in C for m in M[input_data.transition.wait_limit[c]:-1] for d in D for k in K ]

    # Expected Data 
    E_UL = input_data.expected_state_values['ul']
    E_PW = input_data.expected_state_values['pw']
    E_PS = input_data.expected_state_values['ps']
    #endregion

    ##### Master Model #####
    #region
    master = Model("Master problem")
    master.params.LogToConsole = 0
    # master.params.Method = 1

    # Goal Variables
    mv_b0 = master.addVar(vtype = GRB.CONTINUOUS, lb=0, name='var_beta_0')

    mv_bul_co = master.addVars(PCO, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ul_co')
    mv_bul_nco = master.addVars(PNCO, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ul_nco')

    mv_bpw_0 = master.addVars(M[0:1], D, K, C, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_pw_0dkc')
    mv_bpw_1TL = master.addVars(mTLdkc, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_pw_1TLdkc')
    mv_bpw_TLM = master.addVars(TLMdkc, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_pw_TLMdkc')
    mv_bpw_M = master.addVars(M[-1:], D, K, C, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_pw_Mdkc')

    mv_bps_0 = master.addVars(T[:-1], M[0:1], D, K, C, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ps_t0dkc')
    mv_bps_1TL = master.addVars(tmTLdkc, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ps_t1TLdkc')
    mv_bps_TLM = master.addVars(tTLMdkc, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ps_tTLMdkc')
    mv_bps_M = master.addVars(T[:-1], M[-1:], D, K, C, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ps_tMdkc')
    mv_bps_T = master.addVars(T[-1:], M, D, K, C, vtype = GRB.CONTINUOUS, lb=0, name='var_beta_ps_Tmdkc')

    # Constraint Definition
    mc_b0 = master.addConstr(mv_b0 == 1, name='con_beta_0')

    mc_bul_co = master.addConstrs((mv_bul_co[p] >= E_UL[p] for p in PCO), name='con_beta_ul_co')
    mc_bul_nco = master.addConstrs((mv_bul_nco[p] >= E_UL[p] for p in PNCO), name='con_beta_ul_nco')

    mc_bpw_0 = master.addConstrs((mv_bpw_0[(m, d, k, c)] >= E_PW[(m, d, k, c)] for m in M[0:1] for d in D for k in K for c in C), name='con_beta_pw_0dkc')
    mc_bpw_1TL = master.addConstrs((mv_bpw_1TL[i] >= E_PW[i] for i in mTLdkc), name='con_beta_pw_1TLdkc')
    mc_bpw_TLM = master.addConstrs((mv_bpw_TLM[i] >= E_PW[i] for i in TLMdkc), name='con_beta_pw_TLMdkc')
    mc_bpw_M = master.addConstrs((mv_bpw_M[(m, d, k, c)] >= E_PW[(m, d, k, c)] for m in M[-1:] for d in D for k in K for c in C), name='con_beta_pw_Mdkc')

    mc_bps_0 = master.addConstrs((mv_bps_0[(t, m, d, k, c)] >= E_PS[(t, m, d, k, c)] for t in T[:-1] for m in M[0:1] for d in D for k in K for c in C), name='con_beta_ps_t0dkc')
    mc_bps_1TL = master.addConstrs((mv_bps_1TL[i] >= E_PS[i] for i in tmTLdkc), name='con_beta_ps_t1TLdkc')
    mc_bps_TLM = master.addConstrs((mv_bps_TLM[i] >= E_PS[i] for i in tTLMdkc), name='con_beta_ps_tTLMdkc')
    mc_bps_M = master.addConstrs((mv_bps_M[(t, m, d, k, c)] >= E_PS[(t, m, d, k, c)] for t in T[:-1] for m in M[-1:] for d in D for k in K for c in C ), name='con_beta_ps_tMdkc')
    mc_bps_T = master.addConstrs((mv_bps_T[(t, m, d, k, c)] >= E_PS[(t, m, d, k, c)] for t in T[-1:] for m in M for d in D for k in K for c in C), name='con_beta_ps_Tmdkc')

    # Objective Function Definition
    mo_bul_co = quicksum(mv_bul_co[p] for p in PCO)
    mo_bul_nco = quicksum(mv_bul_nco[p] for p in PNCO)

    mo_bpw_0 = quicksum(mv_bpw_0[(0, d, k, c)] for d in D for k in K for c in C)
    mo_bpw_1TL = quicksum(mv_bpw_1TL[i] for i in mTLdkc)
    mo_bpw_TLM = quicksum(mv_bpw_TLM[i] for i in TLMdkc)
    mo_bpw_M = quicksum(mv_bpw_M[(M[-1], d, k, c)] for d in D for k in K for c in C)

    mo_bps_0 = quicksum(mv_bps_0[(t, 0, d, k, c)] for t in T[:-1] for d in D for k in K for c in C)
    mo_bps_1TL = quicksum(mv_bps_1TL[i] for i in tmTLdkc)
    mo_bps_TLM = quicksum(mv_bps_TLM[i] for i in tTLMdkc)
    mo_bps_M = quicksum(mv_bps_M[t, M[-1], d, k, c] for t in T[:-1] for d in D for k in K for c in C)
    mo_bps_T = quicksum(mv_bps_T[T[-1], m, d, k, c] for m in M for d in D for k in K for c in C)

    master.setObjective( (mv_b0) + (mo_bul_co + mo_bul_nco) + (mo_bpw_0 + mo_bpw_1TL + mo_bpw_TLM + mo_bpw_M) + (mo_bps_0 + mo_bps_1TL + mo_bps_TLM + mo_bps_M + mo_bps_T), GRB.MINIMIZE)
    #endregion

    ##### Sub Problem #####
    #region
    sub_prob = Model('Sub problem')
    sub_prob.params.LogToConsole = 0
    # sub_prob.params.DegenMoves = 2
    sub_prob.params.MIPGap = sub_mip_gap

    # State Action & Auxiliary Variables
    sv_st_ul = sub_prob.addVars(P, vtype=GRB.CONTINUOUS, lb = 0, name='var_state_ul')
    sv_st_pw = sub_prob.addVars(M, D, K, C, vtype=GRB.INTEGER, lb=0, name='var_state_pw')
    sv_st_ps = sub_prob.addVars(T, M, D, K, C, vtype=GRB.INTEGER, lb=0, name='var_state_ps')

    sv_ac_sc = sub_prob.addVars(T, M, D, K, C, vtype=GRB.INTEGER, lb = 0, name='var_action_sc')
    sv_ac_rsc = sub_prob.addVars(T, T, M, D, K, C, vtype=GRB.INTEGER, lb = 0, name='var_action_rsc')

    sv_aux_uv = sub_prob.addVars(T, P, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_uv')
    sv_aux_uvb = sub_prob.addVars(T, P, vtype=GRB.BINARY, lb = 0, name='var_auxiliary_uvb')

    sv_aux_ulp = sub_prob.addVars(PCO, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_ul')
    sv_aux_ulb = sub_prob.addVars(PCO, vtype=GRB.BINARY, lb = 0, name='var_auxiliary_ulb')

    sv_aux_uup = sub_prob.addVars(T, P, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_uup')
    sv_aux_pwp = sub_prob.addVars(M, D, K, C, vtype=GRB.INTEGER, lb = 0, name='var_auxiliary_pwp')
    sv_aux_psp = sub_prob.addVars(T, M, D, K, C, vtype=GRB.INTEGER, lb = 0, name='var_auxiliary_psp')

    sv_aux_pwt_d = sub_prob.addVars(M,D,K,C, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_pwt_d')
    sv_aux_pwt_k = sub_prob.addVars(M,D,K,C, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_pwt_k')
    sv_aux_pst_d = sub_prob.addVars(T,M,D,K,C, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_pst_d')
    sv_aux_pst_k = sub_prob.addVars(T,M,D,K,C, vtype=GRB.CONTINUOUS, lb = 0, name='var_auxiliary_pst_k')

    sv_aux_uu = sub_prob.addVars(T, vtype=GRB.CONTINUOUS, lb=0, name='var_auxiliary_uu')
    sv_aux_uub = sub_prob.addVars(T, vtype=GRB.BINARY, lb=0, name='var_auxiliary_uub')

    # Definition of auxiliary variables
    sc_uup = sub_prob.addConstrs((sv_aux_uup[(t,p)] == quicksum( U[(p,d,c)] * sv_aux_psp[(t,m,d,k,c)] for m in M for d in D for k in K for c in C) for t in T for p in P), name='con_auxiliary_uup')
    sc_pwp = sub_prob.addConstrs((sv_aux_pwp[(m,d,k,c)] == sv_st_pw[(m,d,k,c)] - quicksum( sv_ac_sc[(t,m,d,k,c)] for t in T) for m in M for d in D for k in K for c in C), name='con_auxiliary_pwp')
    sc_psp = sub_prob.addConstrs((sv_aux_psp[(t,m,d,k,c)] == sv_st_ps[(t,m,d,k,c)] + sv_ac_sc[(t,m,d,k,c)] + quicksum( sv_ac_rsc[tp,t,m,d,k,c] for tp in T) - quicksum( sv_ac_rsc[t,tp,m,d,k,c] for tp in T) for t in T for m in M for d in D for k in K for c in C), name='con_auxiliary_pws')

    sc_aux_uv_0 = sub_prob.addConstrs((sv_aux_uv[(t,p)] >= 0 for t in T for p in P), name='con_auxiliary_uv_0')
    sc_aux_uv_0M = sub_prob.addConstrs((sv_aux_uv[(t,p)] <= BM * sv_aux_uvb[(t,p)] for t in T for p in P), name='con_auxiliary_uv_0M')
    sc_aux_uv_1 = sub_prob.addConstrs((sv_aux_uv[(1,p)] >= sv_aux_uup[(1, p)] - p_dat[p].expected_units - sv_st_ul[p] for p in P), name='con_auxiliary_uv_1')
    sc_aux_uv_1M = sub_prob.addConstrs((sv_aux_uv[(1,p)] <= (sv_aux_uup[(1, p)] - p_dat[p].expected_units - sv_st_ul[p]) + BM * (1 - sv_aux_uvb[(1, p)]) for p in P), name='con_auxiliary_uv_1M')
    sc_aux_uv_m = sub_prob.addConstrs((sv_aux_uv[(t, p)] >= (sv_aux_uup[(t, p)] - p_dat[p].expected_units) for t in T[1:] for p in P), name='con_auxiliary_uv_m')
    sc_aux_uv_mM = sub_prob.addConstrs((sv_aux_uv[(t, p)] <= (sv_aux_uup[(t,p)] - p_dat[p].expected_units) + BM * (1 - sv_aux_uvb[(t, p)]) for t in T[1:] for p in P), name='con_auxiliary_uv_mM')

    sc_aux_ulp_0 = sub_prob.addConstrs((sv_aux_ulp[p] >= 0 for p in PCO), name='con_auxiliary_ulp_0')
    sc_aux_ulp_0M = sub_prob.addConstrs((sv_aux_ulp[p] <= BM * sv_aux_ulb[p] for p in PCO), name='con_auxiliary_ulp_0M')
    sc_aux_ulp_p = sub_prob.addConstrs((sv_aux_ulp[p] >= (p_dat[p].expected_units + sv_st_ul[p] - sv_aux_uup[(1,p)]) for p in PCO), name='con_auxiliary_ulp_p')
    sc_aux_ulp_pM = sub_prob.addConstrs((sv_aux_ulp[p] <= (p_dat[p].expected_units + sv_st_ul[p] - sv_aux_uup[(1,p)]) + BM * (1-sv_aux_ulb[p]) for p in PCO), name='con_auxiliary_ulp_pM')

    sc_aux_pwt_d = sub_prob.addConstrs((sv_aux_pwt_d[(m,d,k,c)] == ptp_d[(d,c)] * sv_aux_pwp[(m,d,k,c)] for m in M for d in D for k in K for c in C), name='con_auxiliary_pwt_d')
    sc_aux_pwt_k_0 = sub_prob.addConstrs((sv_aux_pwt_k[(m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_pwp[(m,d,k,c)] - sv_aux_pwt_d[(m,d,k,c)]) for m in M for d in D for k in K for c in C if d == D[0]), name='con_auxiliary_pwt_k_0')
    sc_aux_pwt_k_i = sub_prob.addConstrs((sv_aux_pwt_k[(m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_pwp[(m,d,k,c)] + sv_aux_pwt_d[(m,D[D.index(d)-1],k,c)] - sv_aux_pwt_d[(m,d,k,c)]) for m in M for d in D for k in K for c in C if d != D[0] and d != D[-1]), name='con_auxiliary_pwt_k')
    sc_aux_pwt_k_D = sub_prob.addConstrs((sv_aux_pwt_k[(m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_pwp[(m,d,k,c)] + sv_aux_pwt_d[(m,D[D.index(d)-1],k,c)]) for m in M for d in D for k in K for c in C if d == D[-1]), name='con_auxiliary_pwt_k_D')
    sc_aux_pwt_k = {**sc_aux_pwt_k_0, **sc_aux_pwt_k_i, **sc_aux_pwt_k_D}

    sc_aux_pst_d = sub_prob.addConstrs((sv_aux_pst_d[(t,m,d,k,c)] == ptp_d[(d,c)] * sv_aux_psp[(t,m,d,k,c)] for t in T for m in M for d in D for k in K for c in C), name='con_auxiliary_pst_d')
    sc_aux_pst_k_0 = sub_prob.addConstrs((sv_aux_pst_k[(t,m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_psp[(t,m,d,k,c)] - sv_aux_pst_d[(t,m,d,k,c)]) for t in T for m in M for d in D for k in K for c in C if d == D[0]), name='con_auxiliary_pwt_k_0')
    sc_aux_pst_k_i = sub_prob.addConstrs((sv_aux_pst_k[(t,m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_psp[(t,m,d,k,c)] + sv_aux_pst_d[(t,m,D[D.index(d)-1],k,c)] - sv_aux_pst_d[(t,m,d,k,c)]) for t in T for m in M for d in D for k in K for c in C if d != D[0] and d != D[-1]), name='con_auxiliary_pwt_k')
    sc_aux_pst_k_D = sub_prob.addConstrs((sv_aux_pst_k[(t,m,d,k,c)] == ptp_k[(k,c)] * (sv_aux_psp[(t,m,d,k,c)] + sv_aux_pst_d[(t,m,D[D.index(d)-1],k,c)]) for t in T for m in M for d in D for k in K for c in C if d == D[-1]), name='con_auxiliary_pwt_k_D')
    sc_aux_pst_k = {**sc_aux_pst_k_0, **sc_aux_pst_k_i, **sc_aux_pst_k_D}

    sc_aux_uu_0 = sub_prob.addConstrs((sv_aux_uu[(t)] >= 0 for t in T), name='con_auxiliary_uu_0')
    sc_aux_uu_0M = sub_prob.addConstrs((sv_aux_uu[(t)] <= BM * sv_aux_uub[(t)] for t in T), name='con_auxiliary_uu_0M')
    sc_aux_uu_1 = sub_prob.addConstr((sv_aux_uu[(1)] >= p_dat[P[0]].expected_units + sv_st_ul[P[0]] - sv_aux_uup[1,P[0]]), name='con_auxiliary_uu_1')
    sc_aux_uu_1M = sub_prob.addConstr((sv_aux_uu[(1)] <= (p_dat[P[0]].expected_units + sv_st_ul[P[0]] - sv_aux_uup[1,P[0]]) + BM*(1 - sv_aux_uub[(1)])), name='con_auxiliary_uu_1M')
    sc_aux_uu_m = sub_prob.addConstrs((sv_aux_uu[(t)] >= (p_dat[P[0]].expected_units + sv_aux_uup[t,P[0]]) for t in T[1:]), name='con_auxiliary_uu_m')
    sc_aux_uu_mM = sub_prob.addConstrs((sv_aux_uu[(t)] <= (p_dat[P[0]].expected_units + sv_aux_uup[t,P[0]]) + BM * (1 - sv_aux_uub[(t)]) for t in T[1:]), name='con_auxiliary_uu_mM')

    # State Action Constraints
    sc_usage_1 = sub_prob.addConstrs((sv_aux_uup[(1,p)] <= p_dat[p].expected_units + sv_st_ul[p] + sv_aux_uv[(1,p)] for p in P), name='con_usage_1')
    sc_usage_tT = sub_prob.addConstrs((sv_aux_uup[(t,p)] <= p_dat[p].expected_units + sv_aux_uv[(t,p)] for t in T[1:] for p in P), name='con_usage_tT')

    sc_rescb = sub_prob.addConstrs((sv_ac_rsc[(t,tp,m,d,k,c)] == 0 for t in T[1:] for tp in T[1:] for m in M for d in D for k in K for c in C), name='con_reschedule_bounds')
    sc_rescb_ttp = sub_prob.addConstrs((sv_ac_rsc[(t,tp,m,d,k,c)] == 0 for t in T for tp in T for m in M for d in D for k in K for c in C if t == tp == 1), name='con_reschedule_bounds_ttp')

    sc_resch = sub_prob.addConstrs((quicksum(sv_ac_rsc[(t,tp,m,d,k,c)] for tp in T) <= sv_st_ps[(t,m,d,k,c)] for t in T for m in M for d in D for k in K for c in C), name='con_resch')
    sc_sched = sub_prob.addConstrs((quicksum(sv_ac_sc[(t,m,d,k,c)] for t in T) <= sv_st_pw[(m,d,k,c)] for m in M for d in D for k in K for c in C), name='con_sched')

    sc_ul_bd = sub_prob.addConstrs((sv_st_ul[p] <= max(10, 2 * p_dat[p].expected_units) for p in P), name='con_ul_bound')
    sc_pw_bd = sub_prob.addConstrs((sv_st_pw[(m,d,k,c)] <= max(10, 5*pea[(d,k,c)]) for m in M for d in D for k in K for c in C), name='con_pw_bound')
    sc_ps_bd = sub_prob.addConstrs((sv_st_ps[(t,m,d,k,c)] <= max(10, 5*pea[(d,k,c)]) for t in T for m in M for d in D for k in K for c in C), name='con_pw_bound')

    #endregion

    #%%
    ##### Phase 1 #####
    #region
    startP1 = time.time()

    mo_p2 = LinExpr()

    # Solve Phase 1
    iter = 0
    while True and import_model == False:

        # Solve Master
        master.optimize()
        print(f"PHASE 1 Master Iter {iter}:\t\t{master.ObjVal}")


        # Generate Value Equations
        val_b0 = LinExpr(1-gam)

        val_bul_co = {p: LinExpr(sv_st_ul[p] - gam*sv_aux_ulp[p])  for p in PCO }
        val_bul_nco = {p: LinExpr(sv_st_ul[p])  for p in PNCO }

        val_bpw_0 = {(0,d,k,c): LinExpr(sv_st_pw[(0,d,k,c)] - gam*pea[(d,k,c)])  for d in D for k in K for c in C}
        val_bpw_1TL = {(m,d,k,c): LinExpr(sv_st_pw[(m,d,k,c)] - gam*sv_aux_pwp[(m-1,d,k,c)])  for m,d,k,c in mTLdkc}
        val_bpw_TLM = {}
        for m,d,k,c in TLMdkc:
            val_bpw_TLM[(m,d,k,c)] = LinExpr( sv_st_pw[(m,d,k,c)] - gam*sv_aux_pwp[(m-1,d,k,c)] )
            if d != D[0]:  val_bpw_TLM[(m,d,k,c)] += -gam * sv_aux_pwt_d[(m-1, D[D.index(d)-1] ,k,c)]
            if k != K[0]:  val_bpw_TLM[(m,d,k,c)] += -gam * sv_aux_pwt_k[(m-1,d, K[K.index(k)-1] ,c)]
            if d != D[-1]: val_bpw_TLM[(m,d,k,c)] +=  gam * sv_aux_pwt_d[(m-1,d,k,c)]
            if k != K[-1]: val_bpw_TLM[(m,d,k,c)] +=  gam * sv_aux_pwt_k[(m-1,d,k,c)]
        val_bpw_M = {}
        for m,d,k,c in itertools.product( M[-1:], D, K, C):
            val_bpw_M[(m,d,k,c)] = LinExpr( sv_st_pw[(m,d,k,c)] - gam*quicksum( sv_aux_pwp[mm,d,k,c] for mm in M[-2:] ) )
            if d != D[0]:  val_bpw_M[(m,d,k,c)] += -gam * quicksum( sv_aux_pwt_d[(mm, D[D.index(d)-1] ,k,c)] for mm in M[-2:])
            if k != K[0]:  val_bpw_M[(m,d,k,c)] += -gam * quicksum( sv_aux_pwt_k[(mm,d, K[K.index(k)-1] ,c)] for mm in M[-2:])
            if d != D[-1]: val_bpw_M[(m,d,k,c)] +=  gam * quicksum( sv_aux_pwt_d[(mm,d,k,c)] for mm in M[-2:])
            if k != K[-1]: val_bpw_M[(m,d,k,c)] +=  gam * quicksum( sv_aux_pwt_k[(mm,d,k,c)] for mm in M[-2:])    

        val_bps_0 = {(t,0,d,k,c): LinExpr(sv_st_ps[(t,0,d,k,c)])  for t in T[:-1] for d in D for k in K for c in C }
        val_bps_1TL = {(t,m,d,k,c): LinExpr(sv_st_ps[(t,m,d,k,c)] - gam*sv_aux_psp[(t+1,m-1,d,k,c)]) for t,m,d,k,c in tmTLdkc}
        val_bps_TLM = {}
        for t,m,d,k,c in tTLMdkc:
            val_bps_TLM[(t,m,d,k,c)] = LinExpr( sv_st_ps[(t,m,d,k,c)] - gam*sv_aux_psp[(t+1,m-1,d,k,c)] )
            if d != D[0]:  val_bps_TLM[(t,m,d,k,c)] += -gam * sv_aux_pst_d[(t+1,m-1, D[D.index(d)-1] ,k,c)]
            if k != K[0]:  val_bps_TLM[(t,m,d,k,c)] += -gam * sv_aux_pst_k[(t+1,m-1,d, K[K.index(k)-1] ,c)]
            if d != D[-1]: val_bps_TLM[(t,m,d,k,c)] +=  gam * sv_aux_pst_d[(t+1,m-1,d,k,c)]
            if k != K[-1]: val_bps_TLM[(t,m,d,k,c)] +=  gam * sv_aux_pst_k[(t+1,m-1,d,k,c)]
        val_bps_M = {}
        for t,m,d,k,c in itertools.product(T[:-1], M[-1:], D, K, C):
            val_bps_M[(t,m,d,k,c)] = LinExpr( sv_st_ps[(t,m,d,k,c)] - gam*quicksum( sv_aux_psp[(t+1,mm,d,k,c)] for mm in M[-2:] ) )
            if d != D[0]:  val_bps_M[(t,m,d,k,c)] += -gam * quicksum( sv_aux_pst_d[(t+1,mm, D[D.index(d)-1] ,k,c)] for mm in M[-2:])
            if k != K[0]:  val_bps_M[(t,m,d,k,c)] += -gam * quicksum( sv_aux_pst_k[(t+1,mm,d, K[K.index(k)-1] ,c)] for mm in M[-2:])
            if d != D[-1]: val_bps_M[(t,m,d,k,c)] +=  gam * quicksum( sv_aux_pst_d[(t+1,mm,d,k,c)] for mm in M[-2:])
            if k != K[-1]: val_bps_M[(t,m,d,k,c)] +=  gam * quicksum( sv_aux_pst_k[(t+1,mm,d,k,c)] for mm in M[-2:])    
        val_bps_T = {(T[-1],m,d,k,c): LinExpr( sv_st_ps[(T[-1],m,d,k,c)] )  for m in M for d in D for k in K for c in C}


        # Update Subproblem
        so_val =   ((   mc_b0.Pi * val_b0                                                       ) +
                    (   quicksum(mc_bul_co[i].Pi*val_bul_co[i]      for i in mc_bul_co)     + 
                        quicksum(mc_bul_nco[i].Pi*val_bul_nco[i]    for i in mc_bul_nco)        ) + 
                    (   quicksum(mc_bpw_0[i].Pi*val_bpw_0[i]        for i in mc_bpw_0)      + 
                        quicksum(mc_bpw_1TL[i].Pi*val_bpw_1TL[i]    for i in mc_bpw_1TL)    + 
                        quicksum(mc_bpw_TLM[i].Pi*val_bpw_TLM[i]    for i in mc_bpw_TLM)    +  
                        quicksum(mc_bpw_M[i].Pi*val_bpw_M[i]        for i in mc_bpw_M)          ) +
                    (   quicksum(mc_bps_0[i].Pi*val_bps_0[i]        for i in mc_bps_0)      + 
                        quicksum(mc_bps_1TL[i].Pi*val_bps_1TL[i]    for i in mc_bps_1TL)    + 
                        quicksum(mc_bps_TLM[i].Pi*val_bps_TLM[i]    for i in mc_bps_TLM)    +  
                        quicksum(mc_bps_M[i].Pi*val_bps_M[i]        for i in mc_bps_M)      + 
                        quicksum(mc_bps_T[i].Pi*val_bps_T[i]        for i in mc_bps_T)          ))
        so_cw =     quicksum( cw[k] * sv_aux_pwp[(m,d,k,c)] for m in M for d in D for k in K for c in C )
        so_cs =     quicksum( cs[k][t] * sv_ac_sc[(t,m,d,k,c)] for t in T for m in M for d in D for k in K for c in C)
        so_brsc =   quicksum( (cs[k][tp-t]+cc[k]) * sv_ac_rsc[(t,tp,m,d,k,c)] for t in T for tp in T for m in M for d in D for k in K for c in C if tp > t)
        so_grsc =   quicksum( (cs[k][t-tp]-cc[k]) * sv_ac_rsc[(t,tp,m,d,k,c)] for t in T for tp in T for m in M for d in D for k in K for c in C if tp < t)
        so_cv =     quicksum( cv * sv_aux_uv[(t,p)] for  t in T for p in P)
        sc_cuu =    quicksum( cuu * sv_aux_uu[t] for t in T )
        so_cost = (so_cw + so_cs + so_brsc - so_grsc + so_cv + sc_cuu)
        # so_cost = (so_cw + so_cs + so_brsc - so_grsc + so_cv)

        sub_prob.setObjective( -so_val, GRB.MINIMIZE )


        # Solve Subproblem
        sub_prob.optimize()


        # Update Master
        sa = Column()
        sa.addTerms(val_b0.getValue(),              mc_b0)
        
        [sa.addTerms(val_bul_co[i].getValue(),      mc_bul_co[i])   for i in mc_bul_co     ]    
        [sa.addTerms(val_bul_nco[i].getValue(),     mc_bul_nco[i])  for i in mc_bul_nco    ]

        [sa.addTerms(val_bpw_0[i].getValue(),       mc_bpw_0[i])    for i in mc_bpw_0      ]    
        [sa.addTerms(val_bpw_1TL[i].getValue(),     mc_bpw_1TL[i])  for i in mc_bpw_1TL    ]
        [sa.addTerms(val_bpw_TLM[i].getValue(),     mc_bpw_TLM[i])  for i in mc_bpw_TLM    ]    
        [sa.addTerms(val_bpw_M[i].getValue(),       mc_bpw_M[i])    for i in mc_bpw_M      ]

        [sa.addTerms(val_bps_0[i].getValue(),       mc_bps_0[i])    for i in mc_bps_0      ]    
        [sa.addTerms(val_bps_1TL[i].getValue(),     mc_bps_1TL[i])  for i in mc_bps_1TL    ]
        [sa.addTerms(val_bps_TLM[i].getValue(),     mc_bps_TLM[i])  for i in mc_bps_TLM    ]    
        [sa.addTerms(val_bps_M[i].getValue(),       mc_bps_M[i])    for i in mc_bps_M      ]
        [sa.addTerms(val_bps_T[i].getValue(),       mc_bps_T[i])    for i in mc_bps_T      ]  

        sa_var = master.addVar(vtype = GRB.CONTINUOUS, name= f"sa_{iter}", column = sa)


        # Save objective for phase 2
        mo_p2.add(sa_var, so_cost.getValue())


        # End Condition
        if master.ObjVal <= 0: 
            master.optimize()
            break

        iter += 1
    endP1 = time.time()
    #endregion    

    ##### Phase 2 #####
    #region
    startP2 = time.time()

    # Update Master Model
    master.remove(mv_b0)
    master.remove(mv_bul_co)
    master.remove(mv_bul_nco)
    master.remove(mv_bpw_0)
    master.remove(mv_bpw_1TL)
    master.remove(mv_bpw_TLM)
    master.remove(mv_bpw_M)
    master.remove(mv_bps_0)
    master.remove(mv_bps_1TL)
    master.remove(mv_bps_TLM)
    master.remove(mv_bps_M)
    master.remove(mv_bps_T)
    master.setObjective(mo_p2, GRB.MINIMIZE)

    # Initiate Beta Approximation
    beta_approx = {'b0': 0, 'bul': {}, 'bpw': {}, 'bps': {}}
    for i in P: beta_approx['bul'][i] = 0
    for i in itertools.product(M,D,K,C): beta_approx['bpw'][i] = 0
    for i in itertools.product(T,M,D,K,C): beta_approx['bps'][i] = 0

    # Start up model
    to_import_betas = True
    if import_model:
        # print('imported')
        # time.sleep(1)
        model_to_import = read(import_model)
        model_to_import.optimize()
        vars_to_import = model_to_import.getVars()
        for var in vars_to_import:
            # if var.X != 0:
            col_to_import = model_to_import.getCol(var)
            sa_var = master.addVar(vtype = GRB.CONTINUOUS, name= f"sa_{iter}", column = col_to_import, obj=var.obj)
            iter += 1


    # Solve Phase 2

    iter += 1
    close_count = 0
    count_same = 0
    objs = []
    while True:

        # Update beta in the algoritm
        for point in range(len(beta_fun)):
            if iter >= beta_fun[point][0]: beta_alp = beta_fun[point][1]

        # If model is imported generates initial betas completely
        if import_model and to_import_betas:
            beta_alp = 0
            to_import_betas = False
        


        # Solve Master
        if iter%500 == 0: master.write(f'{export_model}')
        master.optimize()


        # Update beta approximation
        beta_approx['b0'] = (beta_alp)*beta_approx['b0'] + (1-beta_alp) * mc_b0.Pi

        for i in mc_bul_co: beta_approx['bul'][i] = (beta_alp)*beta_approx['bul'][i] + (1-beta_alp) * mc_bul_co[i].Pi
        for i in mc_bul_nco: beta_approx['bul'][i] = (beta_alp)*beta_approx['bul'][i] + (1-beta_alp) * mc_bul_nco[i].Pi

        for i in mc_bpw_0: beta_approx['bpw'][i] = (beta_alp)*beta_approx['bpw'][i] + (1-beta_alp) * mc_bpw_0[i].Pi
        for i in mc_bpw_1TL: beta_approx['bpw'][i] = (beta_alp)*beta_approx['bpw'][i] + (1-beta_alp) * mc_bpw_1TL[i].Pi
        for i in mc_bpw_TLM: beta_approx['bpw'][i] = (beta_alp)*beta_approx['bpw'][i] + (1-beta_alp) * mc_bpw_TLM[i].Pi
        for i in mc_bpw_M: beta_approx['bpw'][i] = (beta_alp)*beta_approx['bpw'][i] + (1-beta_alp) * mc_bpw_M[i].Pi
        
        for i in mc_bps_0: beta_approx['bps'][i] = (beta_alp)*beta_approx['bps'][i] + (1-beta_alp) * mc_bps_0[i].Pi
        for i in mc_bps_1TL: beta_approx['bps'][i] = (beta_alp)*beta_approx['bps'][i] + (1-beta_alp) * mc_bps_1TL[i].Pi
        for i in mc_bps_TLM: beta_approx['bps'][i] = (beta_alp)*beta_approx['bps'][i] + (1-beta_alp) * mc_bps_TLM[i].Pi
        for i in mc_bps_M: beta_approx['bps'][i] = (beta_alp)*beta_approx['bps'][i] + (1-beta_alp) * mc_bps_M[i].Pi
        for i in mc_bps_T: beta_approx['bps'][i] = (beta_alp)*beta_approx['bps'][i] + (1-beta_alp) * mc_bps_T[i].Pi
        

        # Generate Value Equations
        val_b0 = LinExpr(1-gam)

        val_bul_co = {p: LinExpr(sv_st_ul[p] - gam*sv_aux_ulp[p])  for p in PCO }
        val_bul_nco = {p: LinExpr(sv_st_ul[p])  for p in PNCO }

        val_bpw_0 = {(0,d,k,c): LinExpr(sv_st_pw[(0,d,k,c)] - gam*pea[(d,k,c)])  for d in D for k in K for c in C}
        val_bpw_1TL = {(m,d,k,c): LinExpr(sv_st_pw[(m,d,k,c)] - gam*sv_aux_pwp[(m-1,d,k,c)])  for m,d,k,c in mTLdkc}
        val_bpw_TLM = {}
        for m,d,k,c in TLMdkc:
            val_bpw_TLM[(m,d,k,c)] = LinExpr( sv_st_pw[(m,d,k,c)] - gam*sv_aux_pwp[(m-1,d,k,c)] )
            if d != D[0]:  val_bpw_TLM[(m,d,k,c)] += -gam * sv_aux_pwt_d[(m-1, D[D.index(d)-1] ,k,c)]
            if k != K[0]:  val_bpw_TLM[(m,d,k,c)] += -gam * sv_aux_pwt_k[(m-1,d, K[K.index(k)-1] ,c)]
            if d != D[-1]: val_bpw_TLM[(m,d,k,c)] +=  gam * sv_aux_pwt_d[(m-1,d,k,c)]
            if k != K[-1]: val_bpw_TLM[(m,d,k,c)] +=  gam * sv_aux_pwt_k[(m-1,d,k,c)]
        val_bpw_M = {}
        for m,d,k,c in itertools.product( M[-1:], D, K, C):
            val_bpw_M[(m,d,k,c)] = LinExpr( sv_st_pw[(m,d,k,c)] - gam*quicksum( sv_aux_pwp[mm,d,k,c] for mm in M[-2:] ) )
            if d != D[0]:  val_bpw_M[(m,d,k,c)] += -gam * quicksum( sv_aux_pwt_d[(mm, D[D.index(d)-1] ,k,c)] for mm in M[-2:])
            if k != K[0]:  val_bpw_M[(m,d,k,c)] += -gam * quicksum( sv_aux_pwt_k[(mm,d, K[K.index(k)-1] ,c)] for mm in M[-2:])
            if d != D[-1]: val_bpw_M[(m,d,k,c)] +=  gam * quicksum( sv_aux_pwt_d[(mm,d,k,c)] for mm in M[-2:])
            if k != K[-1]: val_bpw_M[(m,d,k,c)] +=  gam * quicksum( sv_aux_pwt_k[(mm,d,k,c)] for mm in M[-2:])    

        val_bps_0 = {(t,0,d,k,c): LinExpr(sv_st_ps[(t,0,d,k,c)])  for t in T[:-1] for d in D for k in K for c in C }
        val_bps_1TL = {(t,m,d,k,c): LinExpr(sv_st_ps[(t,m,d,k,c)] - gam*sv_aux_psp[(t+1,m-1,d,k,c)]) for t,m,d,k,c in tmTLdkc}
        val_bps_TLM = {}
        for t,m,d,k,c in tTLMdkc:
            val_bps_TLM[(t,m,d,k,c)] = LinExpr( sv_st_ps[(t,m,d,k,c)] - gam*sv_aux_psp[(t+1,m-1,d,k,c)] )
            if d != D[0]:  val_bps_TLM[(t,m,d,k,c)] += -gam * sv_aux_pst_d[(t+1,m-1, D[D.index(d)-1] ,k,c)]
            if k != K[0]:  val_bps_TLM[(t,m,d,k,c)] += -gam * sv_aux_pst_k[(t+1,m-1,d, K[K.index(k)-1] ,c)]
            if d != D[-1]: val_bps_TLM[(t,m,d,k,c)] +=  gam * sv_aux_pst_d[(t+1,m-1,d,k,c)]
            if k != K[-1]: val_bps_TLM[(t,m,d,k,c)] +=  gam * sv_aux_pst_k[(t+1,m-1,d,k,c)]
        val_bps_M = {}
        for t,m,d,k,c in itertools.product(T[:-1], M[-1:], D, K, C):
            val_bps_M[(t,m,d,k,c)] = LinExpr( sv_st_ps[(t,m,d,k,c)] - gam*quicksum( sv_aux_psp[(t+1,mm,d,k,c)] for mm in M[-2:] ) )
            if d != D[0]:  val_bps_M[(t,m,d,k,c)] += -gam * quicksum( sv_aux_pst_d[(t+1,mm, D[D.index(d)-1] ,k,c)] for mm in M[-2:])
            if k != K[0]:  val_bps_M[(t,m,d,k,c)] += -gam * quicksum( sv_aux_pst_k[(t+1,mm,d, K[K.index(k)-1] ,c)] for mm in M[-2:])
            if d != D[-1]: val_bps_M[(t,m,d,k,c)] +=  gam * quicksum( sv_aux_pst_d[(t+1,mm,d,k,c)] for mm in M[-2:])
            if k != K[-1]: val_bps_M[(t,m,d,k,c)] +=  gam * quicksum( sv_aux_pst_k[(t+1,mm,d,k,c)] for mm in M[-2:])    
        val_bps_T = {(T[-1],m,d,k,c): LinExpr( sv_st_ps[(T[-1],m,d,k,c)] )  for m in M for d in D for k in K for c in C}


        # Update Subproblem
        so_val =   ((   beta_approx['b0'] * val_b0                                                       ) +
                    (   quicksum(beta_approx['bul'][i]*val_bul_co[i]        for i in mc_bul_co)     + 
                        quicksum(beta_approx['bul'][i]*val_bul_nco[i]       for i in mc_bul_nco)        ) + 
                    (   quicksum(beta_approx['bpw'][i]*val_bpw_0[i]         for i in mc_bpw_0)      + 
                        quicksum(beta_approx['bpw'][i]*val_bpw_1TL[i]       for i in mc_bpw_1TL)    + 
                        quicksum(beta_approx['bpw'][i]*val_bpw_TLM[i]       for i in mc_bpw_TLM)    +  
                        quicksum(beta_approx['bpw'][i]*val_bpw_M[i]         for i in mc_bpw_M)          ) +
                    (   quicksum(beta_approx['bps'][i]*val_bps_0[i]         for i in mc_bps_0)      + 
                        quicksum(beta_approx['bps'][i]*val_bps_1TL[i]       for i in mc_bps_1TL)    + 
                        quicksum(beta_approx['bps'][i]*val_bps_TLM[i]       for i in mc_bps_TLM)    +  
                        quicksum(beta_approx['bps'][i]*val_bps_M[i]         for i in mc_bps_M)      + 
                        quicksum(beta_approx['bps'][i]*val_bps_T[i]         for i in mc_bps_T)          ))
        so_cw =     quicksum( cw[k] * sv_aux_pwp[(m,d,k,c)] for m in M for d in D for k in K for c in C )
        so_cs =     quicksum( cs[k][t] * sv_ac_sc[(t,m,d,k,c)] for t in T for m in M for d in D for k in K for c in C)
        so_brsc =   quicksum( (cs[k][tp-t]+cc[k]) * sv_ac_rsc[(t,tp,m,d,k,c)] for t in T for tp in T for m in M for d in D for k in K for c in C if tp > t)
        so_grsc =   quicksum( (cs[k][t-tp]-cc[k]) * sv_ac_rsc[(t,tp,m,d,k,c)] for t in T for tp in T for m in M for d in D for k in K for c in C if tp < t)
        so_cv =     quicksum( cv * sv_aux_uv[(t,p)] for  t in T for p in P)
        sc_cuu =    quicksum( cuu * sv_aux_uu[t] for t in T )
        so_cost = (so_cw + so_cs + so_brsc - so_grsc + so_cv + sc_cuu)
        # so_cost = (so_cw + so_cs + so_brsc - so_grsc + so_cv)

        sub_prob.setObjective( so_cost-so_val, GRB.MINIMIZE )


        # Solve Subproblem
        # if iter%500 == 0: sub_prob.write(f'p2s.lp')
        sub_prob.optimize()
        print(f"PHASE 2 Sub Iter {iter}:\t\t{sub_prob.ObjVal}")


        # Update Master
        sa = Column()
        sa.addTerms(val_b0.getValue(),              mc_b0)
        [sa.addTerms(val_bul_co[i].getValue(),      mc_bul_co[i])   for i in mc_bul_co     ]    
        [sa.addTerms(val_bul_nco[i].getValue(),     mc_bul_nco[i])  for i in mc_bul_nco    ]
        [sa.addTerms(val_bpw_0[i].getValue(),       mc_bpw_0[i])    for i in mc_bpw_0      ]    
        [sa.addTerms(val_bpw_1TL[i].getValue(),     mc_bpw_1TL[i])  for i in mc_bpw_1TL    ]
        [sa.addTerms(val_bpw_TLM[i].getValue(),     mc_bpw_TLM[i])  for i in mc_bpw_TLM    ]    
        [sa.addTerms(val_bpw_M[i].getValue(),       mc_bpw_M[i])    for i in mc_bpw_M      ]
        [sa.addTerms(val_bps_0[i].getValue(),       mc_bps_0[i])    for i in mc_bps_0      ]    
        [sa.addTerms(val_bps_1TL[i].getValue(),     mc_bps_1TL[i])  for i in mc_bps_1TL    ]
        [sa.addTerms(val_bps_TLM[i].getValue(),     mc_bps_TLM[i])  for i in mc_bps_TLM    ]    
        [sa.addTerms(val_bps_M[i].getValue(),       mc_bps_M[i])    for i in mc_bps_M      ]
        [sa.addTerms(val_bps_T[i].getValue(),       mc_bps_T[i])    for i in mc_bps_T      ]  
        sa_var = master.addVar(vtype = GRB.CONTINUOUS, name= f"sa_{iter}", column = sa, obj=so_cost.getValue())


        # End Conditions
        if sub_prob.ObjVal >= 0:
            close_count += 1
        else:
            close_count = 0
        if close_count >= 1000:
            master.optimize()
            master.write(f'{export_model}')
            break
        if iter >= iter_lims:
            master.optimize()
            master.write(f'{export_model}')
            break
        if count_same >= 100:
            master.optimize()
            master.write(f'{export_model}')
            break
        
        objs.append(sub_prob.ObjVal)
        objs = objs[-2:]
        if len(objs) >= 2 and objs[-1] == objs[-2]: count_same += 1
        else: count_same = 0

        #     for i in master.getVars(): 
        #         if i.X == 0: master.remove(i)
        # if iter%100 == 0:
        #     init_len = len(master.getVars())
        #     for i in master.getVars(): 
        #         if i.X == 0: master.remove(i)
        #     final_len = len(master.getVars())

        #     print(f'Trimmed \t{init_len - final_len}')


        iter += 1
    endP2 = time.time()
    #endregion

    ##### TIMING #####
    # print(f"AutoTune 5%\t\t Phase 1 {endP1 - startP1} \t Phase 2 {endP2 - startP2}")

    ##### Save Data #####
    #region

    betas = {'b0': mc_b0.Pi, 'bul': {}, 'bpw': {}, 'bps': {}}

    for p in PCO: betas['bul'][p] = mc_bul_co[p].Pi 
    for p in PNCO: betas['bul'][p] = mc_bul_nco[p].Pi 

    for i in itertools.product(M[0:1], D, K, C): betas['bpw'][i] = mc_bpw_0[i].Pi
    for i in mTLdkc: betas['bpw'][i] = mc_bpw_1TL[i].Pi
    for i in TLMdkc: betas['bpw'][i] = mc_bpw_TLM[i].Pi
    for i in itertools.product(M[-1:], D, K, C): betas['bpw'][i] = mc_bpw_M[i].Pi

    for i in itertools.product(T[:-1], M[0:1], D, K, C): betas['bps'][i] = mc_bps_0[i].Pi
    for i in tmTLdkc: betas['bps'][i] = mc_bps_1TL[i].Pi
    for i in tTLMdkc: betas['bps'][i] = mc_bps_TLM[i].Pi
    for i in itertools.product(T[:-1], M[-1:], D, K, C): betas['bps'][i] = mc_bps_M[i].Pi
    for i in itertools.product(T[-1:], M, D, K, C): betas['bps'][i] = mc_bps_T[i].Pi

    with open(os.path.join(my_path, export_data), 'wb') as outp:
        pickle.dump(betas, outp, pickle.HIGHEST_PROTOCOL)
    #endregion

# %%
