# サイズをサンプリングにより推定するコード
import subprocess
import json
import sys
import os
import time
import re
from pathlib import Path
import psycopg2

# Add project root to path
sys.path.insert(0, '/Users/masudakanji/lab/mv-query-optimization')

from config.settings import Settings

# Settings
settings = Settings()
db_name = settings.database.database
db_user = settings.database.user

# Paths
base_dir = Path('/Users/masudakanji/lab/mv-query-optimization/experiments/small_test_ver2')
plans_path = base_dir / '04_migration/job/simple_migration_plans.json'
costs_path = base_dir / '04_migration/job/simple_migration_costs.json'

# Tables to sample (Name -> Alias in queries)
# We will create samples for these. Order matters: check for largest tables first.
TARGET_TABLES = [
    ("cast_info", "ci"),
    ("movie_info", "mi"),
    ("movie_companies", "mc"),
    ("person_info", "pi"),
    ("movie_keyword", "mk"),
    ("title", "t"),
    ("name", "n")
]

SAMPLING_RATE = 0.005
SCALE_FACTOR = 1.0 / SAMPLING_RATE
OVERHEAD_MULTIPLIER = 1.2  # Account for PostgreSQL storage overhead (indexes, TOAST, metadata)

def run_sql(conn, sql_text):
    """Execute SQL using psycopg2 connection."""
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql_text)
        conn.commit()
        return True
    except Exception as e:
        print(f"Error running SQL: {sql_text}")
        print(str(e))
        conn.rollback()
        return False

def create_sample_tables(conn):
    """Create sample tables using psycopg2 connection."""
    print("Creating sample tables...")
    for table, _ in TARGET_TABLES:
        sample_table = f"sample_{table}"
        print(f"  Creating {sample_table} ({SAMPLING_RATE * 100}% of {table})...")
        sql_text = f"""
        DROP TABLE IF EXISTS {sample_table};
        CREATE TABLE {sample_table} AS SELECT * FROM {table} TABLESAMPLE BERNOULLI ({SAMPLING_RATE * 100});
        ANALYZE {sample_table};
        """
        if not run_sql(conn, sql_text):
            print(f"  Failed to create {sample_table}")
            return False
    return True

def drop_sample_tables(conn):
    """Drop sample tables using psycopg2 connection."""
    print("Dropping sample tables...")
    for table, _ in TARGET_TABLES:
        sample_table = f"sample_{table}"
        run_sql(conn, f"DROP TABLE IF EXISTS {sample_table};")

def get_sample_estimate(conn, query):
    """Execute query and get row count and size using psycopg2."""
    # Remove trailing semicolon
    query = query.strip().rstrip(';')
    
    # Wrap in count/size query
    wrapped_query = f"""
    SELECT count(*), sum(pg_column_size(sub)) 
    FROM ({query}) as sub;
    """
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(wrapped_query)
            result = cursor.fetchone()
            if result and len(result) >= 2:
                rows = int(result[0]) if result[0] else 0
                size = int(result[1]) if result[1] else 0
                return rows, size
        return 0, 0
    except Exception as e:
        # print(f"Error executing sample query: {e}")
        return 0, 0

def rewrite_query(query):
    """Find which table to replace. We prioritize larger tables."""
    best_table = None
    
    for table, alias in TARGET_TABLES:
        # Regex to find table usage with alias
        pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
        if pattern.search(query):
            best_table = (table, alias)
            break  # Stop at the first (largest) table found
            
    if best_table:
        table, alias = best_table
        sample_table = f"sample_{table}"
        pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
        new_query = pattern.sub(f"{sample_table} AS {alias}", query)
        return new_query, table
    
    return None, None

def main():
    print("=" * 80)
    print("Estimating MV Sizes using Sampling")
    print("=" * 80)
    
    # 1. Load Data
    print(f"Loading plans from {plans_path}")
    with open(plans_path, 'r') as f:
        plans = json.load(f)
        
    print(f"Loading costs from {costs_path}")
    with open(costs_path, 'r') as f:
        costs = json.load(f)
    
    # 2. Connect to database
    print(f"Connecting to database {db_name}...")
    try:
        conn = psycopg2.connect(
            database=db_name,
            user=db_user,
            password='',
            host='localhost'
        )
        print("Connected successfully.")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    try:
        # 3. Create Samples
        if not create_sample_tables(conn):
            print("Failed to create sample tables. Exiting.")
            sys.exit(1)
            
        # 4. Process MVs
        print("\\nProcessing MVs...")
        updated_count = 0
        skipped_count = 0
        
        start_time = time.time()
    
        for mv_name, mv_data in plans.items():
            # Only process the "[]" key (zero-dependency migration)
            if "[]" not in mv_data:
                continue
                
            create_sql = mv_data["[]"]
            # Extract SELECT part
            match = re.search(r"AS\s+(SELECT.*);", create_sql, re.IGNORECASE | re.DOTALL)
            if not match:
                # print(f"Could not extract SELECT from {mv_name}")
                skipped_count += 1
                continue
                
            select_query = match.group(1)
            
            # Rewrite query
            rewritten_query, used_table = rewrite_query(select_query)
            
            if rewritten_query:
                # Execute
                rows, size = get_sample_estimate(conn, rewritten_query)
                
                if rows > 0:
                    est_rows = int(rows * SCALE_FACTOR)
                    est_size = int(size * SCALE_FACTOR * OVERHEAD_MULTIPLIER)  # Apply overhead multiplier
                    
                    # Update costs
                    if mv_name in costs and "[]" in costs[mv_name]:
                        old_size = costs[mv_name]["[]"].get("size", 0)
                        costs[mv_name]["[]"]["rows"] = est_rows
                        costs[mv_name]["[]"]["size"] = est_size
                        
                        # print(f"  {mv_name} ({used_table}): {old_size/1024/1024:.2f} MB -> {est_size/1024/1024:.2f} MB")
                        updated_count += 1
                else:
                    # print(f"  {mv_name}: Sample query returned 0 rows.")
                    skipped_count += 1
            else:
                # print(f"  {mv_name}: No target table found for sampling.")
                skipped_count += 1
                
            if (updated_count + skipped_count) % 10 == 0:
                print(f"  Processed {updated_count + skipped_count}/{len(plans)} MVs...")

        print(f"\\nProcessed {updated_count} MVs, Skipped {skipped_count} MVs.")
        print(f"Total time: {time.time() - start_time:.2f}s")
        
        # 5. Save Updated Costs
        print(f"Saving updated costs to {costs_path}")
        with open(costs_path, 'w') as f:
            json.dump(costs, f, indent=2)
            
        # 6. Cleanup
        drop_sample_tables(conn)
        print("Done.")
        
    finally:
        # Close database connection
        conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    main()
