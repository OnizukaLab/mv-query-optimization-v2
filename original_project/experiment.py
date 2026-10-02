import os
import time

ilp_types =  ["none", "normal", "bigsubs", "utility_capacity", "utility", "frequency"]

#ilp_types =  ["bigsubs"]

# initalize csv before each ilp
print("Initalize csv for each ILP")
os.system(f"python compare_bata.py > Output/compare_bata.out")

# Output dirs
if not os.path.exists("Output/experiment/run_mv"):
    os.makedirs("Output/experiment/run_mv")
if not os.path.exists("Output/experiment/mv_create"):
    os.makedirs("Output/experiment/mv_create")
if not os.path.exists("Output/redbench"):
    os.makedirs("Output/redbench")


for ilp in ilp_types:
    # clear up mv files
    os.system("rm -f Output/query_rewrite/mv/*") # to clean up extra mv

    os.system(f"bash delete_mv.sh > /dev/null") # deletes mv from database

    print("ILP : "+ilp)
    if ilp != "none":    
        # Materialized view sql scripts creation
        print("MV creation")
        os.system(f"python re_sql_exe.py {ilp} mv > Output/experiment/mv_create/mv_{ilp}.out")
        # Run Materialized view sql scripts
        print("Creating MVs on database")
        os.system(f"bash run_mv.sh {ilp} > Output/experiment/run_mv/{ilp}.out")
        # Rewrites queries with new mv
        print("Query rewrite")
        os.system(f"python re_sql_exe.py {ilp} > Output/experiment/mv_create/query_{ilp}.out")
 
    print("Running all rewritten queries")
    os.system(f"python execute_rewritten.py {ilp} > Output/query_rewrite/{ilp}.out")
    
    # sets up workloads with new rewritten queries
    print("Setting up Workloads")
    os.system(f"python setup_rewritten.py {ilp}")
    #setup redbench
    os.chdir("dataset/redbench")
    #run redbench
    print("REDBENCH")
    os.system(f"python run.py > ../../Output/redbench/{ilp}.out")
    # go back to original work directory for the next ilp
    os.chdir("../..")