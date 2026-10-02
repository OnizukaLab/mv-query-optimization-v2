"""
Session State Management

Utilities for managing Streamlit session state.
"""

import streamlit as st
from typing import Any, Dict, Optional


def initialize_session_state():
    """Initialize default session state values"""
    defaults = {
        'initialized': True,
        'experiment_running': False,
        'current_experiment': None,
        'experiment_history': [],
        'selected_algorithms': ['normal', 'bigsubs', 'frequency'],
        'storage_limit_mb': 50,
        'insert_queries': 1000,
        'enabled_phases': {
            'query_parsing': True,
            'optimization': True,
            'sql_generation': True,
            'mv_creation': True,
            'query_rewriting': True,
            'benchmark': True
        },
        'output_dir': 'Output',
        'verbose': False,
        'experiment_logs': [],
        'progress_tracker': None,
        # Workload configuration
        # Options: 'job', 'ceb', 'redbench', 'redbench-job', 'redbench-ceb'
        'workload_type': 'redbench-job',  # Default: RedBench JOB queries only
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_session_value(key: str, default: Any = None) -> Any:
    """Get value from session state
    
    Args:
        key: Session state key
        default: Default value if key doesn't exist
        
    Returns:
        Value from session state or default
    """
    return st.session_state.get(key, default)


def set_session_value(key: str, value: Any):
    """Set value in session state
    
    Args:
        key: Session state key
        value: Value to set
    """
    st.session_state[key] = value


def update_experiment_history(experiment_data: Dict):
    """Add experiment to history
    
    Args:
        experiment_data: Dictionary with experiment metadata
    """
    if 'experiment_history' not in st.session_state:
        st.session_state.experiment_history = []
    
    st.session_state.experiment_history.append(experiment_data)
    
    # Keep only last 100 experiments
    if len(st.session_state.experiment_history) > 100:
        st.session_state.experiment_history = st.session_state.experiment_history[-100:]


def get_experiment_history() -> list:
    """Get experiment history
    
    Returns:
        List of experiment dictionaries
    """
    return st.session_state.get('experiment_history', [])


def clear_experiment_logs():
    """Clear experiment logs from session"""
    st.session_state.experiment_logs = []


def append_experiment_log(log_line: str):
    """Append line to experiment logs
    
    Args:
        log_line: Log line to append
    """
    if 'experiment_logs' not in st.session_state:
        st.session_state.experiment_logs = []
    
    st.session_state.experiment_logs.append(log_line)
    
    # Keep only last 1000 lines
    if len(st.session_state.experiment_logs) > 1000:
        st.session_state.experiment_logs = st.session_state.experiment_logs[-1000:]


def get_experiment_logs(max_lines: Optional[int] = None) -> list:
    """Get experiment logs
    
    Args:
        max_lines: Maximum number of lines to return
        
    Returns:
        List of log lines
    """
    logs = st.session_state.get('experiment_logs', [])
    if max_lines:
        return logs[-max_lines:]
    return logs
