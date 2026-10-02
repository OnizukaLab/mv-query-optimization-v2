"""Parse result exporter for annotating query plans with node IDs.

This module provides functionality to annotate original query plan JSON files
with the node_id assigned during parsing.
"""

import json
import shutil
from pathlib import Path
from typing import Any

from .query_manager import QueryManager


class ParseExporter:
    """Annotates query plan JSON files with assigned node IDs.
    
    This class takes the original query plan JSON files and adds node_id
    annotations to each operator node based on the parsing results.
    """
    
    def __init__(self, qm: QueryManager) -> None:
        """Initialize the ParseExporter.
        
        Args:
            qm: QueryManager instance containing parsed node information
        """
        self.qm = qm
    
    def annotate_query_files(
        self,
        query_files: list[str],
        output_dir: str | Path
    ) -> None:
        """Annotate query plan JSON files with node IDs.
        
        Args:
            query_files: List of query file paths to process
            output_dir: Directory where annotated files will be saved
        """
        output_path = Path(output_dir)

        # If there are no query files to process, do not modify the output
        # directory. This prevents accidental deletion of previously
        # annotated plans when the workload selection returns an empty list.
        if not query_files:
            print("No query files provided to annotate. Skipping export.")
            return

        # Refresh the output directory so previously annotated plans
        # from earlier runs do not linger with outdated node_id values.
        if output_path.exists():
            shutil.rmtree(output_path)

        output_path.mkdir(parents=True, exist_ok=True)
        
        for query_idx, query_file in enumerate(query_files):
            try:
                with open(query_file, 'r', encoding='utf-8') as f:
                    query_data = json.load(f)
                
                # Handle both array format [{...}] and single object format {...}
                if isinstance(query_data, list):
                    annotated_list = []
                    for item in query_data:
                        if isinstance(item, dict) and 'Plan' in item:
                            # Annotate the Plan inside the wrapper
                            item_copy = item.copy()
                            item_copy['Plan'] = self._annotate_plan_node(
                                item['Plan'],
                                query_idx
                            )
                            annotated_list.append(item_copy)
                        else:
                            annotated_list.append(item)
                    annotated_data = annotated_list
                else:
                    # Single object with 'Plan' key
                    if 'Plan' in query_data:
                        annotated_data = query_data.copy()
                        annotated_data['Plan'] = self._annotate_plan_node(
                            query_data['Plan'],
                            query_idx
                        )
                    else:
                        # Direct plan node
                        annotated_data = self._annotate_plan_node(
                            query_data,
                            query_idx
                        )
                
                # Save annotated plan
                output_file = output_path / Path(query_file).name
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(annotated_data, f, indent=2, ensure_ascii=False)
                    
            except Exception as e:
                print(f"Warning: Failed to annotate {query_file}: {e}")
        
        print(f"Annotated {len(query_files)} query files")
        print(f"Output directory: {output_path}")
    
    def _annotate_plan_node(
        self,
        node: Any,
        query_idx: int
    ) -> Any:
        """Recursively annotate a plan node with node_id by reconstructing the node structure.
        
        This method creates a temporary node structure identical to what query_parser.py creates,
        then calls QueryManager to get the actual node_id. This ensures consistency between
        the JSON output and the internal node_id assignment.
        
        Args:
            node: Plan node (dict or other type)
            query_idx: Query index
            
        Returns:
            Annotated node
        """
        if not isinstance(node, dict):
            return node
        
        # Get node_id by reconstructing the node structure and querying QueryManager
        node_id = self._get_node_id_from_plan(node, query_idx)
        
        # Create ordered dict with node_id first (if exists), then other fields, Plans last
        from collections import OrderedDict
        annotated = OrderedDict()
        
        # Add node_id first if it exists
        if node_id:
            annotated['node_id'] = node_id
        
        # Add all other fields except 'Plans'
        for k, v in node.items():
            if k != 'Plans':
                annotated[k] = v
        
        # Recursively process Plans (child nodes) and add them last
        if 'Plans' in node and isinstance(node['Plans'], list):
            annotated['Plans'] = [
                self._annotate_plan_node(child, query_idx)
                for child in node['Plans']
            ]
        
        return annotated
    
    def _get_node_id_from_plan(self, node: dict[str, Any], query_idx: int) -> str | None:
        """Get node_id by matching the node structure with QueryManager's records.
        
        Args:
            node: PostgreSQL EXPLAIN plan node
            query_idx: Query index
            
        Returns:
            Node ID if found, None otherwise
        """
        # Check if this is a leaf node (has Relation Name but no child Plans)
        # Note: Some nodes like Bitmap Heap Scan have both Relation Name and Plans
        has_relation = 'Relation Name' in node
        has_plans = 'Plans' in node and len(node['Plans']) > 0
        node_type = node.get('Node Type', '')
        
        # Leaf nodes: have Relation Name and either no Plans or are Bitmap Heap Scan
        if has_relation and (not has_plans or node_type == 'Bitmap Heap Scan'):
            # This is a leaf node
            operator = node_type
            table = node.get('Relation Name', '')
            alias = node.get('Alias', '')
            
            # Determine filter condition (same logic as in query_parser.py)
            # Note: Index Cond is NOT used for leaf node identification (it's a join condition)
            if 'Filter' in node:
                filter_condition = node['Filter']
            else:
                filter_condition = ""
            
            # Look up in leaf_nodes_map
            key = (operator, table, alias, filter_condition)
            node_id = self.qm.leaf_nodes_map.get(key)
            
            return node_id
        
        # This is a non-leaf node
        elif has_plans:
            # Recursively get child node IDs
            child_node_ids = []
            for child in node['Plans']:
                child_id = self._get_node_id_from_plan(child, query_idx)
                if child_id:
                    child_node_ids.append(child_id)
            
            if not child_node_ids:
                return None
            
            # Look up in non_leaf_nodes_map using sorted children
            key = tuple(sorted(child_node_ids))
            node_id = self.qm.non_leaf_nodes_map.get(key)
            
            return node_id
        
        # Special case: Bitmap Index Scan nodes don't have Relation Name
        # but are still leaf nodes - they should be handled by their parent Bitmap Heap Scan
        # So we return None here to skip annotation
        return None
