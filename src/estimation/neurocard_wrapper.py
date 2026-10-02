import sys
import os
import torch
import numpy as np
import collections

# Add neurocard to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
NEUROCARD_DIR = os.path.join(PROJECT_ROOT, 'neurocard')
sys.path.append(NEUROCARD_DIR)

# Disable W&B login
os.environ['WANDB_MODE'] = 'offline'

import argparse

# Import NeuroCard modules
# Handle import conflict: 'experiments' exists in both project root and neurocard
# We need to force run.py to import neurocard/experiments.py

# 1. Save existing 'experiments' module if loaded
original_experiments = sys.modules.pop('experiments', None)

# 2. Prepend neurocard/neurocard to sys.path
neurocard_inner_dir = os.path.join(NEUROCARD_DIR, 'neurocard')
sys.path.insert(0, neurocard_inner_dir)

# 3. Patch argparse to prevent run.py from parsing args on import
original_parse_args = argparse.ArgumentParser.parse_args

def dummy_parse_args(self, args=None, namespace=None):
    # Return a dummy namespace with expected attributes if needed
    # run.py expects 'run', 'cpus', 'gpus' but only uses them in __main__
    return argparse.Namespace(run=[], cpus=1, gpus=0)

argparse.ArgumentParser.parse_args = dummy_parse_args

try:
    # 4. Import NeuroCard (this will import 'experiments' from neurocard_inner_dir)
    from run import NeuroCard
    import experiments as neurocard_experiments
    import utils as neurocard_utils
except ImportError as e:
    print(f"Failed to import NeuroCard: {e}")
    raise
finally:
    # 5. Cleanup
    sys.path.pop(0)
    argparse.ArgumentParser.parse_args = original_parse_args
    
    # 6. Restore original experiments module
    # Note: run.py will retain reference to neurocard_experiments
    if original_experiments:
        sys.modules['experiments'] = original_experiments
    elif 'experiments' in sys.modules:
        # If it wasn't there before but is now (neurocard one), remove it to avoid confusion
        del sys.modules['experiments']


class NeuroCardEstimator:
    def __init__(self, config_name='job-light-reload', base_dir=None):
        """
        Initialize NeuroCard estimator.
        
        Args:
            config_name: Name of the experiment config to use (default: 'job-light-reload')
            base_dir: Project root directory. If None, inferred from file location.
        """
        if base_dir is None:
            self.base_dir = PROJECT_ROOT
        else:
            self.base_dir = base_dir
            
        self.neurocard_dir = os.path.join(self.base_dir, 'neurocard', 'neurocard')
        
        # Ensure we are in the correct directory for relative paths in config (datasets, queries)
        # NeuroCard expects to run from neurocard/neurocard
        self.original_cwd = os.getcwd()
        os.chdir(self.neurocard_dir)
        
        try:
            if config_name not in neurocard_experiments.EXPERIMENT_CONFIGS:
                raise ValueError(f"Config {config_name} not found in experiments.py")
            
            self.config = neurocard_experiments.EXPERIMENT_CONFIGS[config_name]
            
            # Override cwd in config to ensure it matches current dir
            self.config['cwd'] = self.neurocard_dir
            
            # Inject keys normally added by run.py
            self.config['__gpu'] = 0
            self.config['__cpu'] = 1
            self.config['__run'] = config_name
            
            # Flatten grid search parameters
            for k, v in self.config.items():
                if isinstance(v, dict) and 'grid_search' in v:
                    self.config[k] = v['grid_search'][0]


            
            # Instantiate NeuroCard
            # We use a mocked logger creator or just pass None as it might not be strictly needed for inference
            # Actually NeuroCard inherits from tune.Trainable, which takes config as init arg
            self.neurocard = NeuroCard(self.config)
            
            # Setup model (loads data, builds model structure)
            self.neurocard.setup(self.config)
            
            # Load checkpoint
            self.neurocard.LoadCheckpoint()
            
            self.model = self.neurocard.model
            self.table = self.neurocard.table
            
            # Filter base table columns to match train_data columns
            # This prevents FillInUnqueriedColumns from adding columns that were skipped (e.g. join keys)
            # Must be done BEFORE creating estimators so they see the consistent table structure
            if self.neurocard.factorize:
                valid_columns = set(self.neurocard.train_data.columns)
                if hasattr(self.table, 'tables'):
                    for t in self.table.tables:
                        t.columns = [c for c in t.columns if c in valid_columns]
                    # Rebuild self.table.columns list
                    self.table.columns = []
                    for t in self.table.tables:
                        self.table.columns.extend(t.columns)
                else:
                    self.table.columns = [c for c in self.table.columns if c in valid_columns]
                
                # Identify virtual columns (e.g. __in_table) that are in train_data but not in base tables
                # These must be added to base_table so FillInUnqueriedColumns includes them
                # and ProjectQuery doesn't crash with IndexError
                current_cols_set = set(self.table.columns)
                virtual_cols = [c for c in self.neurocard.train_data.columns if c not in current_cols_set]
                
                if virtual_cols:
                    if hasattr(self.table, 'tables'):
                        # Create a dummy table for virtual columns
                        from neurocard.common import Table
                        virtual_table = Table("virtual_columns", virtual_cols, validate_cardinality=False)
                        self.table.tables.append(virtual_table)
                        self.table.columns.extend(virtual_cols)
                    else:
                        # Single table case: just extend columns
                        self.table.columns.extend(virtual_cols)

                # Rebuild name_to_index because columns list has changed
                self.table.name_to_index = {c.Name(): i for i, c in enumerate(self.table.columns)}

            # Create estimators (ProgressiveSampling)
            self.estimators = self.neurocard.MakeProgressiveSamplers(
                self.model,
                self.neurocard.train_data if self.neurocard.factorize else self.table,
                # Disable fanout scaling for now because it requires join keys in base_table,
                # but including them causes ProjectQuery to crash due to mismatch with train_data.
                do_fanout_scaling=False # (self.neurocard.dataset == 'imdb')
            )
            
            # Map column names to Column objects for easy lookup
            self.col_map = {}
            
            # Use table-qualified names to avoid ambiguity
            if hasattr(self.table, 'tables'):
                for t in self.table.tables:
                    for c in t.columns:
                        # Support both dot and colon notation
                        self.col_map[f"{t.name}.{c.name}"] = c
                        self.col_map[f"{t.name}:{c.name}"] = c
                        # Also support simple name (last one wins if duplicate, but usually qualified is used)
                        self.col_map[c.name] = c
                        if hasattr(c, 'pg_name'):
                            self.col_map[c.pg_name] = c
            else:
                for c in self.table.columns:
                    self.col_map[c.name] = c
                    if hasattr(c, 'pg_name'):
                        self.col_map[c.pg_name] = c
                    
        finally:
            # Restore CWD
            os.chdir(self.original_cwd)

    def estimate_cardinality(self, conditions):
        """
        Estimate cardinality for a given set of conditions.
        
        Args:
            conditions: list of (col_name, op, val) tuples.
                        e.g. [('production_year', '>', 2010), ('info_type_id', '=', 3)]
                        
        Returns:
            Estimated cardinality (int)
        """
        # Switch to neurocard dir for execution (just in case model needs relative paths during query)
        # Though usually Query only needs model and table which are in memory.
        # But let's be safe if it logs or something.
        # os.chdir(self.neurocard_dir) 
        # -> Avoiding chdir in hot path if possible. Let's assume it's fine.
        
        columns = []
        operators = []
        vals = []
        
        involved_tables = set()
        
        for col_name, op, val in conditions:
            col_obj = self._get_column(col_name)
            if col_obj:
                columns.append(col_obj)
                operators.append(op)
                
                # Cast value to correct type
                # __in_table カラムはインジケータなのでキャストしない (GetTablesInQueryで [1] と比較されるため)
                if col_name.startswith('__in_'):
                    vals.append(val)
                else:
                    try:
                        # Ensure we have a valid dtype
                        if col_obj.all_distinct_values is not None:
                            cast_fn = col_obj.all_distinct_values.dtype.type
                            if isinstance(val, (list, set, tuple)):
                                qv = type(val)(map(cast_fn, val))
                            else:
                                qv = cast_fn(val)
                            vals.append(qv)
                        else:
                            vals.append(val)
                    except Exception as e:
                        # print(f"Warning: Failed to cast value {val} for column {col_name}: {e}")
                        # Casting failed, so we must skip this condition to avoid ufunc errors in OPS
                        columns.pop()
                        operators.pop()
                        continue
                
                # Infer table name from column name (expected format: table:column)
                if ':' in col_obj.name:
                    table_name = col_obj.name.split(':')[0]
                    involved_tables.add(table_name)
            else:
                # print(f"Warning: Column {col_name} not found in NeuroCard model. Ignoring condition.")
                pass
        
        # Add __in_table indicators
        for table in involved_tables:
            in_col_name = f"__in_{table}"
            in_col_obj = self._get_column(in_col_name)
            if in_col_obj:
                columns.append(in_col_obj)
                operators.append('=')
                vals.append(1) # Indicator value 1 means table is present
        
        if not columns:
            # No valid conditions, return total cardinality?
            # Or return None?
            # NeuroCard Query with empty lists might return total count.
            pass
            
        try:
            # Use the last estimator (usually the one with most samples, e.g. 8000)
            # or configurable.
            estimator = self.estimators[-1]
            cardinality = estimator.Query(columns, operators, vals)
            return int(cardinality)
        except Exception as e:
            print(f"Error during NeuroCard estimation: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_column(self, col_name):
        """Resolve column name to Column object."""
        if col_name in self.col_map:
            return self.col_map[col_name]
        
        # Try stripping table name if present
        if '.' in col_name:
            _, c = col_name.split('.', 1)
            if c in self.col_map:
                return self.col_map[c]
                
        return None

    def estimate_from_csv(self, csv_path):
        """
        Estimate cardinality for queries in a CSV file.
        
        Args:
            csv_path: Path to the CSV file containing queries in NeuroCard format.
            
        Returns:
            List of estimated cardinalities (floats).
        """
        # Ensure absolute path
        csv_path = os.path.abspath(csv_path)
        
        # Switch to neurocard dir for execution
        os.chdir(self.neurocard_dir)
        
        try:
            # Parse CSV using NeuroCard's utility
            # use_alias_keys=True matches our SQL parsing logic (we map aliases to tables, 
            # but NeuroCard's JobToQuery expects aliases in join_dict if use_alias_keys=True)
            # Actually, let's check utils.JobToQuery.
            # It returns (tables, join_dict, predicate_dict, true_cardinality)
            # UnpackQueries then converts this to (cols, ops, vals)
            
            queries_job_format = neurocard_utils.JobToQuery(csv_path)
            loaded_queries, oracle_cards = neurocard_utils.UnpackQueries(
                self.table, queries_job_format)
            
            estimates = []
            estimator = self.estimators[-1] # Use the most accurate estimator
            
            for i, query in enumerate(loaded_queries):
                # query is (cols, ops, vals)
                cols, ops, vals = query
                try:
                    card = estimator.Query(cols, ops, vals)
                    estimates.append(float(card))
                except Exception as e:
                    print(f"Error estimating query {i}: {e}")
                    estimates.append(None)
                    
            return estimates
            
        finally:
            os.chdir(self.original_cwd)

    def get_column_names(self):
        """Return list of available column names."""
        return list(self.col_map.keys())

if __name__ == '__main__':
    # Simple test
    try:
        estimator = NeuroCardEstimator()
        print("Model loaded successfully.")
        print(f"Available columns (first 10): {estimator.get_column_names()[:10]}")
        
        # Test query: title.production_year > 2010
        conds = [('production_year', '>', 2010)]
        est = estimator.estimate_cardinality(conds)
        print(f"Estimate for production_year > 2010: {est}")
        
    except Exception as e:
        print(f"Failed to initialize or run estimator: {e}")
        import traceback
        traceback.print_exc()
