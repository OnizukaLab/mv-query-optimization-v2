"""
Settings Page - System Configuration

Page for configuring system settings and preferences.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.utils.session_state import initialize_session_state, set_session_value, get_session_value
from dashboard.utils.file_manager import FileManager

# Page config
st.set_page_config(page_title="Settings - MV Optimization", page_icon="⚙️", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("⚙️ System Settings")

# Create tabs
tab1, tab2, tab3 = st.tabs(["🗄️ Database", "📂 Paths", "🎨 Preferences"])

with tab1:
    st.subheader("🗄️ Database Configuration")
    
    # Load current config
    try:
        from config.settings import settings
        current_db = settings.db
    except:
        current_db = None
    
    with st.form("database_config"):
        col1, col2 = st.columns(2)
        
        with col1:
            db_host = st.text_input(
                "Host",
                value=current_db.host if current_db else "localhost",
                help="Database server hostname"
            )
            
            db_port = st.number_input(
                "Port",
                value=current_db.port if current_db else 5432,
                min_value=1,
                max_value=65535,
                help="Database server port"
            )
            
            db_name = st.text_input(
                "Database Name",
                value=current_db.name if current_db else "imdbload",
                help="Name of the database"
            )
        
        with col2:
            db_user = st.text_input(
                "Username",
                value=current_db.user if current_db else "postgres",
                help="Database username"
            )
            
            db_password = st.text_input(
                "Password",
                value="",
                type="password",
                help="Database password"
            )
            
            db_timeout = st.number_input(
                "Query Timeout (seconds)",
                value=current_db.timeout if current_db else 1800,
                min_value=60,
                max_value=7200,
                step=60,
                help="Maximum time for query execution"
            )
        
        submitted = st.form_submit_button("💾 Save Database Config", type="primary")
        
        if submitted:
            # Save configuration
            db_config = {
                'host': db_host,
                'port': db_port,
                'name': db_name,
                'user': db_user,
                'timeout': db_timeout
            }
            
            # Save to file
            config_path = project_root / "config" / "dashboard_db.json"
            FileManager.save_json(db_config, config_path)
            
            st.success("✅ Database configuration saved!")
    
    # Test connection
    if st.button("🔗 Test Database Connection"):
        try:
            from src.database.connection import DatabaseConnection
            
            with st.spinner("Testing connection..."):
                conn = DatabaseConnection.get_connection()
                if conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT version();")
                        version = cur.fetchone()[0]
                    st.success(f"✅ Connected successfully!\n\n**PostgreSQL Version:**\n{version[:100]}...")
                else:
                    st.error("❌ Failed to connect")
        except Exception as e:
            st.error(f"❌ Connection failed: {str(e)}")

with tab2:
    st.subheader("📂 Path Configuration")
    
    with st.form("path_config"):
        output_dir = st.text_input(
            "Output Directory",
            value=get_session_value('output_dir', 'Output'),
            help="Directory for experiment results"
        )
        
        queries_dir = st.text_input(
            "Queries Directory",
            value="dataset/RED_JSON",
            help="Directory containing query files"
        )
        
        sql_dir = st.text_input(
            "SQL Directory",
            value="dataset/RED_SQL",
            help="Directory containing SQL files"
        )
        
        workloads_dir = st.text_input(
            "Workloads Directory",
            value="Output/RED_WORKLOADS",
            help="Directory for workload files"
        )
        
        submitted = st.form_submit_button("💾 Save Paths", type="primary")
        
        if submitted:
            set_session_value('output_dir', output_dir)
            
            # Save to configuration file
            path_config = {
                'output_dir': output_dir,
                'queries_dir': queries_dir,
                'sql_dir': sql_dir,
                'workloads_dir': workloads_dir
            }
            
            config_path = project_root / "config" / "dashboard_paths.json"
            FileManager.save_json(path_config, config_path)
            
            st.success("✅ Path configuration saved!")
    
    st.markdown("---")
    
    # Directory status
    st.markdown("### 📁 Directory Status")
    
    dirs_to_check = [
        ("Output", output_dir if 'output_dir' in locals() else 'Output'),
        ("Queries", queries_dir if 'queries_dir' in locals() else 'dataset/RED_JSON'),
        ("SQL", sql_dir if 'sql_dir' in locals() else 'dataset/RED_SQL'),
        ("Workloads", workloads_dir if 'workloads_dir' in locals() else 'Output/RED_WORKLOADS')
    ]
    
    for name, path in dirs_to_check:
        full_path = project_root / path
        if full_path.exists():
            size = FileManager.get_directory_size(full_path)
            from dashboard.utils.data_processor import DataProcessor
            st.success(f"✅ **{name}**: `{path}` ({DataProcessor.format_bytes(size)})")
        else:
            st.warning(f"⚠️ **{name}**: `{path}` (Not found)")
    
    st.markdown("---")
    
    # Workload Configuration
    st.markdown("### 📂 Workload Configuration")
    
    with st.form("workload_config"):
        st.markdown("Configure the query workload for experiments")
        
        # Workload type selection
        workload_options = {
            'job': 'JOB - All 113 JOB queries',
            'ceb-1a': 'CEB 1a - CEB template 1a queries (3000 queries)',
            'redbench': 'RedBench - Full workload (JOB + CEB mixed)',
            'redbench-job': 'RedBench JOB - Only JOB queries from RedBench (83 queries)',
            'redbench-ceb': 'RedBench CEB - Only CEB queries from RedBench'
        }
        
        current_workload = get_session_value('workload_type', 'redbench-job')
        # Ensure current_workload is valid
        if current_workload not in workload_options:
            current_workload = 'redbench-job'
        
        workload_type = st.selectbox(
            "Workload Type",
            options=list(workload_options.keys()),
            format_func=lambda x: workload_options[x],
            index=list(workload_options.keys()).index(current_workload),
            help="Select the query workload to optimize for"
        )
        
        submitted = st.form_submit_button("💾 Save Workload Config", type="primary")
        
        if submitted:
            set_session_value('workload_type', workload_type)
            
            # Save to configuration file
            workload_config = {
                'workload_type': workload_type
            }
            
            config_path = project_root / "config" / "dashboard_workload.json"
            FileManager.save_json(workload_config, config_path)
            
            st.success("✅ Workload configuration saved!")
    
    # Workload info
    st.markdown("#### 📊 Workload Information")
    workload_info = {
        'job': """
        **JOB (Join Order Benchmark)**
        - All 113 queries from the JOB benchmark
        - Located in dataset/RED_JSON/job/
        - Standard benchmark for join order optimization
        """,
        'ceb': """
        **CEB (Cardinality Estimation Benchmark)**
        - All CEB queries from the benchmark
        - Located in dataset/RED_JSON/ (excluding job/)
        - Contains complex queries with varying cardinality estimation challenges
        """,
        'redbench': """
        **RedBench Full Workload**
        - Mimics real-world production query patterns from Redset
        - **JOB and CEB queries mixed** based on repetition patterns
        - 30 workloads across 10 variability buckets (0%-10% to 90%-100%)
        - Each bucket has high/mid/low variability workloads
        """,
        'redbench-job': """
        **RedBench JOB Only**
        - 83 unique JOB queries extracted from RedBench workloads
        - Queries selected based on real production patterns
        - **Recommended for most experiments**
        """,
        'redbench-ceb': """
        **RedBench CEB Only**
        - CEB queries extracted from RedBench workloads
        - Queries selected based on real production patterns
        - Useful for testing with more complex query patterns
        """
    }
    
    current_wl = get_session_value('workload_type', 'redbench-job')
    if current_wl not in workload_info:
        current_wl = 'redbench-job'
    st.info(workload_info.get(current_wl, "Select a workload type to see details"))

with tab3:
    st.subheader("🎨 UI Preferences")
    
    with st.form("ui_preferences"):
        # Theme selection
        theme = st.radio(
            "Theme",
            options=['Light', 'Dark', 'Auto'],
            index=0,
            help="Dashboard theme"
        )
        
        # Chart style
        chart_style = st.selectbox(
            "Chart Style",
            options=['plotly', 'seaborn', 'matplotlib'],
            index=0,
            help="Preferred chart library"
        )
        
        # Primary color
        primary_color = st.color_picker(
            "Primary Color",
            value='#667eea',
            help="Primary theme color"
        )
        
        st.markdown("---")
        
        # Advanced options
        st.markdown("### 🔧 Advanced Options")
        
        debug_logging = st.checkbox(
            "Enable Debug Logging",
            value=get_session_value('verbose', False),
            help="Show detailed debug information"
        )
        
        auto_save = st.checkbox(
            "Auto-save Experiment Results",
            value=True,
            help="Automatically save experiment results"
        )
        
        cache_parser = st.checkbox(
            "Cache Query Parser",
            value=True,
            help="Cache parsed queries for faster loading"
        )
        
        enable_profiling = st.checkbox(
            "Enable Performance Profiling",
            value=False,
            help="Track performance metrics (may slow down execution)"
        )
        
        # Refresh interval
        refresh_interval = st.slider(
            "Auto-refresh Interval (seconds)",
            min_value=1,
            max_value=30,
            value=5,
            help="How often to refresh during experiment execution"
        )
        
        submitted = st.form_submit_button("💾 Save Preferences", type="primary")
        
        if submitted:
            # Save preferences
            preferences = {
                'theme': theme,
                'chart_style': chart_style,
                'primary_color': primary_color,
                'debug_logging': debug_logging,
                'auto_save': auto_save,
                'cache_parser': cache_parser,
                'enable_profiling': enable_profiling,
                'refresh_interval': refresh_interval
            }
            
            set_session_value('verbose', debug_logging)
            
            config_path = project_root / "config" / "dashboard_preferences.json"
            FileManager.save_json(preferences, config_path)
            
            st.success("✅ Preferences saved!")

st.markdown("---")

# System information
st.subheader("ℹ️ System Information")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📦 Dashboard Info")
    st.markdown(f"""
    - **Version:** 1.0.0
    - **Python:** {sys.version.split()[0]}
    - **Project Root:** `{project_root}`
    """)

with col2:
    st.markdown("### 💾 Storage Info")
    output_path = project_root / get_session_value('output_dir', 'Output')
    if output_path.exists():
        total_size = FileManager.get_directory_size(output_path)
        from dashboard.utils.data_processor import DataProcessor
        st.markdown(f"""
        - **Output Directory:** {DataProcessor.format_bytes(total_size)}
        - **Location:** `{output_path}`
        """)
    else:
        st.markdown("*Output directory not found*")

st.markdown("---")

# Configuration management
st.subheader("📥 Configuration Management")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💾 Export All Settings"):
        # Gather all configurations
        all_config = {
            'database': {},
            'paths': {},
            'preferences': {},
            'session': {
                'output_dir': get_session_value('output_dir'),
                'verbose': get_session_value('verbose'),
                'storage_limit_mb': get_session_value('storage_limit_mb')
            }
        }
        
        # Load existing configs
        for config_type in ['dashboard_db', 'dashboard_paths', 'dashboard_preferences']:
            config_path = project_root / "config" / f"{config_type}.json"
            config_data = FileManager.load_json(config_path)
            if config_data:
                key = config_type.replace('dashboard_', '')
                all_config[key] = config_data
        
        # Save combined config
        export_path = project_root / "dashboard_config_export.json"
        FileManager.save_json(all_config, export_path)
        st.success(f"✅ Configuration exported to {export_path}")

with col2:
    if st.button("📂 Import Settings"):
        import_path = project_root / "dashboard_config_export.json"
        config = FileManager.load_json(import_path)
        
        if config:
            # Save individual configs
            for key in ['database', 'paths', 'preferences']:
                if key in config:
                    config_path = project_root / "config" / f"dashboard_{key}.json"
                    FileManager.save_json(config[key], config_path)
            
            st.success("✅ Configuration imported successfully!")
            st.rerun()
        else:
            st.error(f"❌ Import file not found: {import_path}")

with col3:
    if st.button("🔄 Reset to Defaults"):
        # Clear all dashboard configs
        for config_type in ['dashboard_db', 'dashboard_paths', 'dashboard_preferences']:
            config_path = project_root / "config" / f"{config_type}.json"
            if config_path.exists():
                config_path.unlink()
        
        st.success("✅ Settings reset to defaults!")
        st.rerun()

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem 0;'>
    <p>MV Query Optimization Dashboard v1.0.0</p>
    <p>💡 Changes to some settings may require restarting the dashboard</p>
</div>
""", unsafe_allow_html=True)
