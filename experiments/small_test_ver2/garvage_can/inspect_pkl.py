import pickle, sys, os

# Ensure repository root is on sys.path so modules referenced by the pickle
# (for example package 'experiments') can be imported during unpickling.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Check both locations: root and time_dependent_output
pkl_path_root = os.path.join(os.path.dirname(__file__), 'qp_class.pkl')
pkl_path_td = os.path.join(os.path.dirname(__file__), 'time_dependent_output', 'qp_class.pkl')

if os.path.exists(pkl_path_td):
    pkl_path = pkl_path_td
    print('loading from time_dependent_output:', pkl_path)
elif os.path.exists(pkl_path_root):
    pkl_path = pkl_path_root
    print('loading from root:', pkl_path)
else:
    pkl_path = 'qp_class.pkl'
    print('loading (fallback):', pkl_path)
with open(pkl_path, 'rb') as f:
    obj = pickle.load(f)
print('top type:', type(obj))
# If dict-like
if isinstance(obj, dict):
    print('dict keys sample:', list(obj.keys())[:50])
    for key in ['node_list','u_ij','b_j','X','q_s_list','m_cost','qm']:
        if key in obj:
            val = obj[key]
            print(f"{key}: type={type(val)} len={len(val) if hasattr(val,'__len__') else 'N/A'}")
else:
    attrs = [a for a in dir(obj) if not a.startswith('_')]
    print('attr sample:', attrs[:200])
    for key in ['node_list','u_ij','b_j','X','q_s_list','m_cost','qm']:
        if hasattr(obj, key):
            val = getattr(obj, key)
            try:
                l = len(val)
            except Exception:
                l = 'N/A'
            print(f"{key}: type={type(val)} len={l}")
    # Print some sample contents for inspection
    if hasattr(obj, 'node_list'):
        nl = getattr(obj, 'node_list')
        print('node_list sample (first 20):', nl[:20])
    if hasattr(obj, 'q_s_list'):
        qs = getattr(obj, 'q_s_list')
        try:
            print('q_s_list sample:', qs)
        except Exception:
            print('q_s_list present but could not print')
    if hasattr(obj, 'q_s_order_list'):
        qo = getattr(obj, 'q_s_order_list')
        print('q_s_order_list sample:', qo[:50])
    if hasattr(obj, 'u_ij'):
        u = getattr(obj, 'u_ij')
        # print basic shape
        try:
            print('u_ij shape: I=', len(u), 'J=', len(u[0]) if len(u)>0 else 0)
        except Exception:
            print('u_ij present but shape unknown')
print('done')
