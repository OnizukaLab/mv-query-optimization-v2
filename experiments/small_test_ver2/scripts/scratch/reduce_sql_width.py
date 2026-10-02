import re
import os

input_path = 'experiments/small_test_ver2/time_dependent_output/cluster_55_25_26_3_ex/static_initial_mvs.sql'
output_path = 'experiments/small_test_ver2/time_dependent_output/cluster_55_25_26_3_ex/static_initial_mvs_single_col.sql'

def transform_sql(input_file, output_file):
    with open(input_file, 'r') as f:
        content = f.read()

    # Regex: find SELECT ... FROM blocks
    # We use a non-greedy matching for the columns
    # We assume SELECT starts the column list and FROM ends it.
    
    def select_reducer(match):
        select_part = match.group(0)
        # Find the text between SELECT and FROM
        # Handling case-insensitivity manually for safety or using re.IGNORECASE
        sub_match = re.search(r'(SELECT)(\s+)(.*?)(\s+)(FROM)', select_part, re.DOTALL | re.IGNORECASE)
        if sub_match:
            prefix = sub_match.group(1) # "SELECT"
            space1 = sub_match.group(2)
            cols_text = sub_match.group(3)
            space2 = sub_match.group(4)
            suffix = sub_match.group(5) # "FROM"
            
            # Split columns by comma and take the first one
            # Note: complex SQL might have commas inside parentheses (functions), 
            # but in these generated MVs, usually it's just a comma-separated list of columns.
            # To be safer, we can just split by comma and strip.
            first_col = cols_text.split(',')[0].strip()
            
            return f"{prefix}{space1}{first_col}{space2}{suffix}"
        return select_part

    # Apply transformation to every SELECT ... FROM block
    # Note: Using DOTALL to handle multi-line SELECT clauses
    pattern = re.compile(r'SELECT\s+.*?\s+FROM', re.DOTALL | re.IGNORECASE)
    new_content = pattern.sub(select_reducer, content)

    with open(output_file, 'w') as f:
        f.write(new_content)
    
    print(f"Successfully created: {output_file}")

if __name__ == '__main__':
    transform_sql(input_path, output_path)
