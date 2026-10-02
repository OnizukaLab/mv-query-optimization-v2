"""
Main Streamlit Application for MV Query Optimization Dashboard
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="MV Optimization Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/Kaina3/mv-query-optimization',
        'Report a bug': 'https://github.com/Kaina3/mv-query-optimization/issues',
        'About': '# MV Query Optimization Dashboard\nVersion 1.0.0'
    }
)

# Load custom CSS
css_file = Path(__file__).parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.experiment_running = False
    st.session_state.current_experiment = None
    st.session_state.experiment_history = []

# Main content
st.title("🚀 MV Query Optimization Dashboard")
st.markdown("""
Welcome to the Materialized View Query Optimization Dashboard. 
This tool helps you visualize and analyze experiments for selecting optimal materialized views.
""")

# Quick stats
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="metric-card">
        <h3>📊 Total Experiments</h3>
        <p>{}</p>
    </div>
    """.format(len(st.session_state.experiment_history)), unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="metric-card">
        <h3>✅ Completed</h3>
        <p>{}</p>
    </div>
    """.format(sum(1 for e in st.session_state.experiment_history if e.get('status') == 'completed')), 
    unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="metric-card">
        <h3>🔄 Running</h3>
        <p>{}</p>
    </div>
    """.format(1 if st.session_state.experiment_running else 0), unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="metric-card">
        <h3>❌ Failed</h3>
        <p>{}</p>
    </div>
    """.format(sum(1 for e in st.session_state.experiment_history if e.get('status') == 'failed')), 
    unsafe_allow_html=True)

st.markdown("---")

# Navigation guide
st.subheader("📍 Getting Started")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    ### 🏠 Run Experiments
    Configure and execute optimization experiments with different algorithms and settings.
    
    **Go to:** `Pages → 🏠 Home`
    """)
    
    st.markdown("""
    ### 📊 Analyze Results
    Compare algorithm performance, view detailed metrics, and export results.
    
    **Go to:** `Pages → 📊 Results`
    """)

with col2:
    st.markdown("""
    ### 🔍 Query Analysis
    Deep dive into individual query performance and execution plans.
    
    **Go to:** `Pages → 🔍 Query Analysis`
    """)
    
    st.markdown("""
    ### 📦 MV Explorer
    Explore materialized views, their utilities, and selection process.
    
    **Go to:** `Pages → 📦 MV Explorer`
    """)

st.markdown("---")

# System status
st.subheader("⚡ System Status")

col1, col2 = st.columns([3, 1])

with col1:
    # Check database connection
    try:
        from config.settings import settings
        db_status = "🟢 Connected" if settings.db else "🔴 Not Configured"
    except Exception as e:
        db_status = f"🟡 Unknown ({str(e)[:50]}...)"
    
    st.markdown(f"""
    - **Database:** {db_status}
    - **Output Directory:** `{project_root / 'Output'}`
    - **Dataset Directory:** `{project_root / 'dataset'}`
    """)

with col2:
    if st.button("⚙️ Configure Settings"):
        st.switch_page("pages/3_⚙️_Settings.py")

# Recent activity
st.markdown("---")
st.subheader("📜 Recent Activity")

if st.session_state.experiment_history:
    # Show last 5 experiments
    recent = st.session_state.experiment_history[-5:]
    for exp in reversed(recent):
        status_icon = {
            'completed': '✅',
            'failed': '❌',
            'running': '🔄'
        }.get(exp.get('status', 'unknown'), '❓')
        
        st.markdown(f"""
        {status_icon} **{exp.get('timestamp', 'Unknown')}** - 
        Algorithms: {', '.join(exp.get('algorithms', []))} - 
        Storage: {exp.get('storage_limit', 'N/A')} MB
        """)
else:
    st.info("👋 No experiments yet. Start by running your first experiment!")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 0;'>
    <p>MV Query Optimization Dashboard v1.0.0</p>
    <p>Built with Streamlit | © 2025</p>
</div>
""", unsafe_allow_html=True)
