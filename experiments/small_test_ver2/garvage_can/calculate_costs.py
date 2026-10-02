"""Cost calculator for converting utility-based u_ij to cost-based u_ij.

This script loads the parsed query data from qp_class.pkl and recalculates
the u_ij matrix to represent costs instead of utilities for minimization.
"""

import pickle
import json
import sys
from pathlib import Path

# Add project root to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def calculate_costs(pickle_path: str, output_path: str = None):
    """Calculate cost-based u_ij from utility-based data.

    Args:
        pickle_path: Path to the pickle file containing parsed query data
        output_path: Path to save the updated data (optional)
    """
    # Load pickle data (QueryParser object)
    with open(pickle_path, 'rb') as f:
        qp = pickle.load(f)

    qm = qp.qm
    u_ij = qp.u_ij
    position_node_id = qp.position_node_id
    node_list = qp.node_list

    # Calculate new cost-based u_ij
    new_u_ij = []
    for i in range(len(u_ij)):
        # Get total cost for query i (sum of costs of nodes used in query i)
        total_cost_i = 0
        for j in range(len(qp.q_s_list[i])):
            if qp.q_s_list[i][j] == 1:
                node_id = qp.node_list[j]
                total_cost_i += qm.subquery_costs.get(node_id, 0)

        new_u_ij_row = []
        for j in range(len(u_ij[i])):
            # Cost = total_cost - utility (current u_ij is utility)
            cost = total_cost_i - u_ij[i][j]
            new_u_ij_row.append(cost)
        new_u_ij.append(new_u_ij_row)

    # Update qp object
    qp.u_ij = new_u_ij
    # Add metadata if not exists
    if not hasattr(qp, '_metadata'):
        qp._metadata = {}
    qp._metadata['cost_based'] = True

    # Save updated data
    if output_path is None:
        output_path = pickle_path.replace('.pkl', '_cost.pkl')

    with open(output_path, 'wb') as f:
        pickle.dump(qp, f)

    # Also save as JSON for inspection (convert to dict)
    data_dict = {
        '_metadata': getattr(qp, '_metadata', {}),
        'qm': str(qp.qm),  # Convert to string to avoid serialization issues
        's_num': qp.s_num,
        'node_list': qp.node_list,
        'm_cost': qp.m_cost,
        'U_j_max': qp.U_j_max,
        'b_j': qp.b_j,
        'q_s_list': qp.q_s_list,
        'u_ij': qp.u_ij,
        'position_node_id': {str(k): v for k, v in qp.position_node_id.items()},  # Convert tuple keys to str
    }
    json_path = output_path.replace('.pkl', '.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data_dict, f, indent=2, default=str)

    print(f"Cost-based data saved to: {output_path}")
    print(f"JSON inspection saved to: {json_path}")


if __name__ == "__main__":
    # Default paths for small_test_ver2
    pickle_path = "experiments/small_test_ver2/time_dependent_output/qp_class.pkl"
    calculate_costs(pickle_path)