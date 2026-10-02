import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.small_test_ver2.migration.simple_migration_cost_calculator import SimpleMigrationCostCalculator
from src.estimation.neurocard_wrapper import NeuroCardEstimator

class NeuroCardMigrationCostCalculator(SimpleMigrationCostCalculator):
    """
    Migration cost calculator that uses NeuroCard for size estimation.
    Inherits from SimpleMigrationCostCalculator and overrides size calculation.
    """
    
    def __init__(self, settings, query_set="job_like"):
        super().__init__(settings, query_set)
        print("Initializing NeuroCard Estimator...")
        self.estimator = NeuroCardEstimator()
        print("NeuroCard Estimator initialized.")

    def _parse_conditions(self, sql):
        """
        Parse SQL WHERE clause to extract conditions for NeuroCard.
        Returns list of (col, op, val).
        """
        conditions = []
        
        # Extract FROM clause to build alias map
        # Pattern: FROM table1 AS t1, table2 t2, ...
        alias_map = {}
        from_match = re.search(r'FROM\s+(.+?)\s+(?:WHERE|GROUP BY|ORDER BY|$)', sql, re.IGNORECASE | re.DOTALL)
        if from_match:
            from_clause = from_match.group(1)
            # Split by comma
            tables = from_clause.split(',')
            for t in tables:
                t = t.strip()
                # Parse "table AS alias" or "table alias"
                # e.g. "title AS t", "cast_info ci"
                parts = t.split()
                if len(parts) >= 2:
                    if parts[1].upper() == 'AS':
                        table_name = parts[0]
                        alias = parts[2]
                    else:
                        table_name = parts[0]
                        alias = parts[1]
                    alias_map[alias] = table_name
                elif len(parts) == 1:
                    # No alias
                    alias_map[parts[0]] = parts[0]

        # Extract WHERE clause
        match = re.search(r'WHERE\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return conditions
            
        where_clause = match.group(1)
        
        # Split by AND
        # This is a simple parser and might fail on complex nested conditions or ORs
        # But JOB-light queries usually have simple AND conditions
        parts = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            # Remove parentheses
            part = part.strip('()')
            
            # Parse condition: col op val
            # Supported ops: =, <, >, <=, >=, !=, <>
            # Regex to capture: (table.col) (op) (val)
            # Value might be string (quoted) or number
            
            # Pattern for: table.col op val
            cond_match = re.match(r'([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\s*(=|<=|>=|!=|<>|<|>)\s*(.+)', part)
            
            if cond_match:
                col_ref = cond_match.group(1)
                op = cond_match.group(2)
                val_str = cond_match.group(3).strip()
                
                # Check if value is a column reference (join condition)
                # If it looks like table.col or just col (and not a number/string), ignore it
                # Simple heuristic: if it contains a dot and no quotes, or if it's alphanumeric and not a number/keyword
                
                is_join = False
                # Check for table.col format
                if re.match(r'^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$', val_str):
                    is_join = True
                # Check for unquoted string that isn't a number (could be alias or col)
                elif not val_str.startswith("'") and not val_str.isdigit():
                    try:
                        float(val_str)
                    except ValueError:
                        # Not a number, likely a column
                        is_join = True
                
                if is_join:
                    # Skip join conditions
                    continue

                # Resolve alias
                if '.' in col_ref:
                    alias, col_name = col_ref.split('.')
                    if alias in alias_map:
                        table_name = alias_map[alias]
                        # NeuroCard expects table:column format
                        col = f"{table_name}:{col_name}"
                    else:
                        # Unknown alias, keep as is (might be full table name)
                        col = col_ref
                else:
                    col = col_ref
                
                # Handle value types
                if val_str.startswith("'") and val_str.endswith("'"):
                    val = val_str[1:-1]
                elif val_str.isdigit():
                    val = int(val_str)
                else:
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = val_str # Keep as string if not number
                
                # Normalize operator
                if op == '<>':
                    op = '!='
                    
                conditions.append((col, op, val))
                
        return conditions

    def _generate_csv_row(self, conditions):
        """
        Convert conditions list to NeuroCard CSV row format.
        Format: tables#joins#predicates#cardinality
        """
        # Group conditions by table
        # We need to map aliases back to table names for the CSV if we want to be consistent
        # But NeuroCard's JobToQuery handles aliases if we provide them.
        # However, our _parse_conditions returns "table:col" or "alias:col" (if alias map worked).
        # Actually _parse_conditions returns "table:col" because we resolve aliases there.
        
        tables = set()
        predicates = []
        
        for col, op, val in conditions:
            if ':' in col:
                table, column = col.split(':')
                tables.add(table)
                
                # NeuroCard predicate format: table.col,op,val
                # Value handling: strings need to be quoted? 
                # utils.py _try_parse_literal uses ast.literal_eval
                
                if isinstance(val, str):
                    val_str = f"'{val}'"
                else:
                    val_str = str(val)
                    
                predicates.append(f"{table}.{column},{op},{val_str}")
            else:
                # Fallback if no table prefix (shouldn't happen with our parser)
                pass
                
        # We don't have join info easily available from just the WHERE clause without parsing the FROM/JOINs fully.
        # But NeuroCard needs join info to know how tables connect.
        # If we only have single table queries (which might be the case for simple MVs?), joins are empty.
        # But for multi-table MVs, we need the joins.
        
        # CRITICAL: The current _parse_conditions DOES NOT extract join conditions (we explicitly ignore them).
        # But NeuroCard needs them in the CSV to build the join graph.
        # We need to update _parse_conditions or a new method to extract joins as well.
        
        # For now, let's assume we can get joins.
        # Wait, if we use the "JobToQuery" format, we need to provide the full query spec.
        
        # Alternative: We can construct the query object directly instead of going through CSV?
        # But the user asked for CSV.
        
        # Let's look at how we can get joins.
        # The SQL in simple_migration_plans.json is like "SELECT * FROM ... WHERE ..."
        # We need to parse the joins from WHERE (implicit joins) or JOIN clauses.
        
        return tables, predicates

    def calculate_all_costs(self):
        """
        Calculate costs for all migration plans, using NeuroCard for size estimation.
        Batch processing via CSV.
        """
        print("\n" + "="*70)
        print("Calculating migration costs with NeuroCard (Batch CSV)...")
        print("="*70)
        
        # 1. Collect all valid queries and generate CSV
        valid_plans = [] # List of (node, plan_key, sql, pg_rows, width, cost)
        
        # Get valid columns from NeuroCard model for filtering
        valid_columns = set(self.estimator.get_column_names())
        print(f"Loaded {len(valid_columns)} valid columns from NeuroCard model.")
        
        # We need a temporary file for the CSV
        csv_path = project_root / "neurocard_queries.csv"
        
        print("Generating CSV for batch estimation...")
        
        # We need to parse joins to generate valid NeuroCard CSVs.
        # Since _parse_conditions strips joins, we need a better parser or re-use existing one.
        # But implementing a full SQL parser here is risky.
        
        # WORKAROUND:
        # The user's request specifically asked to "take SQL from simple_migration_plans and convert to CSV".
        # If we can't easily parse joins, maybe we can't use CSV fully correctly?
        # However, NeuroCard's `JobToQuery` expects `tables#joins#predicates#cardinality`.
        
        # Let's try to extract joins in a simple way.
        # Most queries in JOB are implicit joins in WHERE clause: t.id = mc.movie_id
        
        csv_rows = []
        plan_map = [] # Map index in CSV to (node, plan_key)
        
        total_nodes = len(self.plans)
        processed = 0
        
        for node, plans in self.plans.items():
            processed += 1
            self.costs[node] = {}
            
            for plan_key in sorted(plans.keys()):
                if plan_key == "[]":
                    sql = plans[plan_key]
                    cost, pg_rows, width = self._explain_sql(sql)
                    
                    # Parse for CSV generation
                    # We need: tables, joins, predicates
                    
                    # 1. Tables (and aliases)
                    alias_map = {}
                    tables_list = []
                    from_match = re.search(r'FROM\s+(.+?)\s+(?:WHERE|GROUP BY|ORDER BY|$)', sql, re.IGNORECASE | re.DOTALL)
                    if from_match:
                        from_clause = from_match.group(1)
                        for t in from_clause.split(','):
                            parts = t.strip().split()
                            if len(parts) >= 2:
                                if parts[1].upper() == 'AS':
                                    t_name, alias = parts[0], parts[2]
                                else:
                                    t_name, alias = parts[0], parts[1]
                                alias_map[alias] = t_name
                                tables_list.append(f"{t_name} {alias}")
                            else:
                                t_name = parts[0]
                                alias_map[t_name] = t_name
                                tables_list.append(t_name)
                    
                    # 2. Joins and Predicates from WHERE
                    joins = []
                    predicates_flat = [] # Flat list for csv writer: col, op, val, col, op, val...
                    
                    where_match = re.search(r'WHERE\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
                    if where_match:
                        conditions = re.split(r'\s+AND\s+', where_match.group(1), flags=re.IGNORECASE)
                        for cond in conditions:
                            cond = cond.strip().strip('()')
                            # Check for join: col1 = col2
                            join_match = re.match(r'([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)$', cond)
                            if join_match:
                                # It's a join
                                joins.append(f"{join_match.group(1)}={join_match.group(2)}")
                            else:
                                # It's a predicate
                                # Need to format as table.col,op,val
                                pred_match = re.match(r'([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\s*(=|<=|>=|!=|<>|<|>)\s*(.+)', cond)
                                if pred_match:
                                    col = pred_match.group(1)
                                    
                                    # Filter out columns not in NeuroCard model
                                    # NeuroCard expects table:column format for internal lookup
                                    # We need to check if table:column exists in valid_columns
                                    
                                    # We need to resolve alias first to check validity
                                    # But we don't have alias map fully reliable here?
                                    # Wait, we constructed alias_map above.
                                    
                                    # Re-construct alias map logic inside the loop or use what we have?
                                    # We have alias_map populated above.
                                    
                                    if '.' in col:
                                        t_alias, c_name = col.split('.')
                                        if t_alias in alias_map:
                                            real_table = alias_map[t_alias]
                                            full_col_name = f"{real_table}:{c_name}"
                                            
                                            if full_col_name not in valid_columns:
                                                # print(f"Skipping invalid column: {full_col_name}")
                                                continue
                                        else:
                                            # Unknown alias, maybe it's a full table name
                                            full_col_name = f"{t_alias}:{c_name}"
                                            if full_col_name not in valid_columns:
                                                continue
                                    else:
                                        # No alias/table prefix? Unlikely for this dataset but possible
                                        continue
                                        
                                    op = pred_match.group(2)
                                    val = pred_match.group(3).strip()
                                    if op == '<>': op = '!='
                                    
                                    # Handle value quoting for NeuroCard
                                    # NeuroCard expects the value string to be parseable by ast.literal_eval
                                    # So strings should be quoted: 'val'
                                    # Numbers should be plain.
                                    
                                    if val.startswith("'") and val.endswith("'"):
                                        # Already quoted string
                                        pass
                                    elif val.isdigit():
                                        pass
                                    else:
                                        try:
                                            float(val)
                                        except ValueError:
                                            # Unquoted string? Quote it if it's not a number
                                            val = f"'{val}'"
                                    
                                    predicates_flat.extend([col, op, val])

                    # Construct CSV row using csv.writer to handle quoting of fields containing commas
                    import io
                    import csv
                    
                    def to_csv_str(items):
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(items)
                        return output.getvalue().strip()

                    tables_str = to_csv_str(tables_list)
                    joins_str = to_csv_str(joins)
                    predicates_str = to_csv_str(predicates_flat)
                    
                    # tables#joins#predicates#cardinality
                    # Note: The outer delimiter is #, so we don't need to escape # inside fields 
                    # unless csv.reader(delimiter='#') is used on the whole line.
                    # NeuroCard uses: csv.reader(f, delimiter='#')
                    # So we just need to ensure our fields don't contain # (unlikely for SQL)
                    
                    row_str = f"{tables_str}#{joins_str}#{predicates_str}#{pg_rows}"
                    csv_rows.append(row_str)
                    plan_map.append((node, plan_key, cost, pg_rows, width))
                else:
                    self.costs[node][plan_key] = {
                        "cost": 0.0, "rows": 0, "width": 0, "size": 0
                    }

        # Write CSV
        with open(csv_path, 'w') as f:
            for row in csv_rows:
                f.write(row + '\n')
                
        print(f"Generated CSV with {len(csv_rows)} queries at {csv_path}")
        
        # Run Batch Estimation
        print("Running NeuroCard batch estimation...")
        estimates = self.estimator.estimate_from_csv(str(csv_path))
        
        # Map results back
        for i, est in enumerate(estimates):
            node, plan_key, cost, pg_rows, width = plan_map[i]
            
            if est is not None:
                rows = est
            else:
                rows = pg_rows
                
            size = rows * width
            self.costs[node][plan_key] = {
                "cost": cost,
                "rows": rows,
                "width": width,
                "size": size,
                "pg_rows": pg_rows,
                "estimation_method": "neurocard" if est is not None else "postgres"
            }
            
        print(f"\n✓ Calculation complete: {len(self.costs)} nodes")
        print("="*70 + "\n")
        
        self.save_costs()
        return self.costs

if __name__ == "__main__":
    # Allow running this script directly for testing
    import argparse
    import yaml
    from config.settings import Settings

    parser = argparse.ArgumentParser(description="Migration cost calculation with NeuroCard")
    parser.add_argument("--query-set", type=str, default="job_like", help="Query set name")
    args = parser.parse_args()

    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    temp_config = config_path.parent / '.temp_config_nc.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
        calculator = NeuroCardMigrationCostCalculator(settings, query_set=args.query_set)
        calculator.calculate_all_costs()
    finally:
        if temp_config.exists():
            temp_config.unlink()
