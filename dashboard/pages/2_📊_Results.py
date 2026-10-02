"""
Results Page - Unified Results Analysis Dashboard

統合された結果分析ページ：
- Overview: アルゴリズム比較
- Query Analysis: クエリパフォーマンス分析
- MV Explorer: 実体化ビュー詳細
- Parse Statistics: パース統計
"""

import streamlit as st
import sys
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.components.result_loader import ResultLoader
from dashboard.components.visualizations import Visualizations
from dashboard.utils.session_state import initialize_session_state, get_session_value
from dashboard.utils.data_processor import DataProcessor

# Page config
st.set_page_config(page_title="Results - MV Optimization", page_icon="📊", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("📊 Results Analysis")

# Initialize result loader
output_dir = st.session_state.get('output_dir', 'Output')
loader = ResultLoader(output_dir)

# List available experiments
experiments = loader.list_experiments()

# Create main navigation tabs
main_tabs = st.tabs([
    "📊 Overview",
    "🔍 Query Analysis", 
    "📦 MV Explorer",
    "📈 Parse Statistics"
])

# ============================================================
# TAB 1: Overview - Algorithm Comparison
# ============================================================
with main_tabs[0]:
    if not experiments:
        st.warning("⚠️ No experiment results found. Run an experiment first!")
    else:
        # Algorithm selection for comparison
        st.subheader("🔍 Select Algorithms to Compare")
        available_algorithms = [exp['algorithm'] for exp in experiments]
        selected_algorithms = st.multiselect(
            "Choose algorithms",
            options=available_algorithms,
            default=available_algorithms[:3] if len(available_algorithms) >= 3 else available_algorithms,
            key="overview_algo_select"
        )

        if not selected_algorithms:
            st.info("ℹ️ Select at least one algorithm to view results")
        else:
            st.markdown("---")

            # Load comparison data
            comparison_data = loader.compare_algorithms(selected_algorithms)

            # Key Metrics Cards
            st.subheader("📈 Key Metrics")
            cols = st.columns(len(selected_algorithms))

            for idx, algo in enumerate(selected_algorithms):
                metrics = comparison_data['metrics'].get(algo, {})
                
                with cols[idx]:
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>{algo}</h3>
                        <p style="font-size: 1.5rem;">{metrics.get('num_views', 0)} MVs</p>
                        <hr style="border-color: rgba(255,255,255,0.3);">
                        <p style="font-size: 1rem;">Utility: {metrics.get('total_utility', 0):.2f}</p>
                        <p style="font-size: 1rem;">Storage: {DataProcessor.format_bytes(metrics.get('storage_used_bytes', 0))}</p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")

            # ============================================================
            # Execution Results Section - Total Time Breakdown
            # ============================================================
            st.subheader("🚀 Execution Results")
            
            # ============================================================
            # Comparison Table - All algorithms side by side
            # ============================================================
            st.markdown("### 📋 アルゴリズム比較表")
            
            # Collect execution summaries for all algorithms
            all_summaries = {}
            for algo in selected_algorithms:
                exec_summary = loader.load_execution_summary(algo)
                if exec_summary:
                    all_summaries[algo] = exec_summary
            
            if all_summaries:
                # Phase names for display (benchmarkは分離表示するため除外)
                phase_display_names = {
                    'optimization': '🧮 最適化時間',
                    'sql_generation': '📝 SQL生成時間',
                    'mv_creation': '🏗️ MV作成時間',
                    'query_rewriting': '✏️ クエリ書き換え時間',
                }
                
                # Build comparison data
                comparison_rows = []
                
                # Total execution time
                row = {'項目': '⏱️ 総実行時間'}
                for algo, summary in all_summaries.items():
                    row[algo] = f"{summary.get('total_execution_time', 0):.2f}秒"
                comparison_rows.append(row)
                
                # Phase times (benchmark以外)
                for phase_key, phase_name in phase_display_names.items():
                    row = {'項目': phase_name}
                    for algo, summary in all_summaries.items():
                        phases = summary.get('phases', {})
                        row[algo] = f"{phases.get(phase_key, 0):.2f}秒"
                    comparison_rows.append(row)
                
                # Benchmark phase breakdown (ANALYZE + Query Execution)
                # summary.jsonのbenchmark = ANALYZE時間 + クエリ実行時間
                # benchmark_results.jsonのtotal_time = 純粋なクエリ実行時間
                row = {'項目': '📊 ベンチマーク合計時間'}
                for algo, summary in all_summaries.items():
                    phases = summary.get('phases', {})
                    row[algo] = f"{phases.get('benchmark', 0):.2f}秒"
                comparison_rows.append(row)
                
                row = {'項目': '  └ 🔍 ANALYZE時間'}
                for algo, summary in all_summaries.items():
                    phases = summary.get('phases', {})
                    bm = summary.get('benchmark', {})
                    benchmark_total = phases.get('benchmark', 0)
                    query_exec_time = bm.get('total_time', 0)
                    analyze_time = benchmark_total - query_exec_time
                    row[algo] = f"{analyze_time:.2f}秒"
                comparison_rows.append(row)
                
                row = {'項目': '  └ ⚡ クエリ実行時間'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    row[algo] = f"{bm.get('total_time', 0):.2f}秒"
                comparison_rows.append(row)
                
                # Separator row (empty)
                comparison_rows.append({'項目': '─' * 20, **{algo: '─' * 10 for algo in all_summaries.keys()}})
                
                # MV Creation stats
                row = {'項目': '📦 作成MV数'}
                for algo, summary in all_summaries.items():
                    mv = summary.get('mv_creation', {})
                    row[algo] = f"{mv.get('created', 0)}/{mv.get('total_mvs', 0)}"
                comparison_rows.append(row)
                
                row = {'項目': '✅ MV作成成功率'}
                for algo, summary in all_summaries.items():
                    mv = summary.get('mv_creation', {})
                    total = mv.get('total_mvs', 0)
                    created = mv.get('created', 0)
                    rate = (created / total * 100) if total > 0 else 0
                    row[algo] = f"{rate:.1f}%"
                comparison_rows.append(row)
                
                row = {'項目': '💾 MV総サイズ'}
                for algo, summary in all_summaries.items():
                    mv = summary.get('mv_creation', {})
                    row[algo] = f"{mv.get('total_size_mb', 0):.2f} MB"
                comparison_rows.append(row)
                
                # Separator row
                comparison_rows.append({'項目': '─' * 20, **{algo: '─' * 10 for algo in all_summaries.keys()}})
                
                # Benchmark stats
                row = {'項目': '📝 総クエリ数'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    row[algo] = str(bm.get('total_queries', 0))
                comparison_rows.append(row)
                
                row = {'項目': '✅ クエリ成功数'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    row[algo] = str(bm.get('successful', 0))
                comparison_rows.append(row)
                
                row = {'項目': '❌ クエリ失敗数'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    row[algo] = str(bm.get('failed', 0))
                comparison_rows.append(row)
                
                row = {'項目': '✅ クエリ成功率'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    total = bm.get('total_queries', 0)
                    success = bm.get('successful', 0)
                    rate = (success / total * 100) if total > 0 else 0
                    row[algo] = f"{rate:.1f}%"
                comparison_rows.append(row)
                
                row = {'項目': '⏱️ 平均クエリ実行時間'}
                for algo, summary in all_summaries.items():
                    bm = summary.get('benchmark', {})
                    row[algo] = f"{bm.get('avg_time_per_query', 0):.3f}秒"
                comparison_rows.append(row)
                
                # Create DataFrame and display
                comparison_df = pd.DataFrame(comparison_rows)
                
                # Style the dataframe
                st.dataframe(
                    comparison_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        '項目': st.column_config.TextColumn('項目', width='medium')
                    }
                )
                
                # Time comparison bar chart
                st.markdown("### 📊 フェーズ別時間比較")
                
                # Phase names for chart (benchmarkを分離)
                chart_phase_names = {
                    'optimization': '🧮 最適化時間',
                    'sql_generation': '📝 SQL生成時間',
                    'mv_creation': '🏗️ MV作成時間',
                    'query_rewriting': '✏️ クエリ書き換え時間',
                }
                
                # Build data for grouped bar chart
                chart_data = []
                for algo, summary in all_summaries.items():
                    phases = summary.get('phases', {})
                    bm = summary.get('benchmark', {})
                    
                    # Regular phases
                    for phase_key, phase_name in chart_phase_names.items():
                        chart_data.append({
                            'アルゴリズム': algo,
                            'フェーズ': phase_name,
                            '時間 (秒)': phases.get(phase_key, 0)
                        })
                    
                    # Benchmark phase breakdown
                    benchmark_total = phases.get('benchmark', 0)
                    query_exec_time = bm.get('total_time', 0)
                    analyze_time = benchmark_total - query_exec_time
                    
                    chart_data.append({
                        'アルゴリズム': algo,
                        'フェーズ': '🔍 MV ANALYZE',
                        '時間 (秒)': analyze_time
                    })
                    chart_data.append({
                        'アルゴリズム': algo,
                        'フェーズ': '⚡ クエリ実行',
                        '時間 (秒)': query_exec_time
                    })
                
                if chart_data:
                    chart_df = pd.DataFrame(chart_data)
                    fig = px.bar(
                        chart_df,
                        x='フェーズ',
                        y='時間 (秒)',
                        color='アルゴリズム',
                        barmode='group',
                        title='フェーズ別実行時間の比較'
                    )
                    fig.update_layout(
                        xaxis_tickangle=-45,
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True, key="phase_comparison_bar")
            
            st.markdown("---")
            
            # ============================================================
            # Detailed Results per Algorithm (Expandable)
            # ============================================================
            st.markdown("### 📂 アルゴリズム別詳細")
            
            for algo in selected_algorithms:
                exec_summary = loader.load_execution_summary(algo)
                if exec_summary:
                    with st.expander(f"📊 {algo} - 実行結果の詳細", expanded=False):
                        # Total execution time
                        total_time = exec_summary.get('total_execution_time', 0)
                        timestamp = exec_summary.get('timestamp', 'N/A')
                        
                        st.markdown(f"**実行日時:** {timestamp}")
                        st.markdown(f"**総実行時間:** {DataProcessor.format_duration(total_time)}")
                        
                        st.markdown("---")
                        
                        # Phase breakdown
                        phases = exec_summary.get('phases', {})
                        bm_data = exec_summary.get('benchmark', {})
                        if phases:
                            st.markdown("#### ⏱️ フェーズ別実行時間")
                            
                            # Benchmark分離: benchmark = ANALYZE時間 + クエリ実行時間
                            benchmark_total = phases.get('benchmark', 0)
                            query_exec_time = bm_data.get('total_time', 0)
                            analyze_time = benchmark_total - query_exec_time
                            
                            phase_names = {
                                'optimization': '🧮 最適化 (MV選択)',
                                'sql_generation': '📝 SQL生成',
                                'mv_creation': '🏗️ MV作成',
                                'query_rewriting': '✏️ クエリ書き換え',
                            }
                            
                            # Create phase data for chart and table (benchmarkは分離表示)
                            phase_data = []
                            for phase_key, phase_time in phases.items():
                                if phase_key == 'benchmark':
                                    continue  # benchmarkは後で分離追加
                                phase_label = phase_names.get(phase_key, phase_key)
                                phase_data.append({
                                    'フェーズ': phase_label,
                                    '時間 (秒)': phase_time,
                                    '割合 (%)': (phase_time / total_time * 100) if total_time > 0 else 0
                                })
                            
                            # Benchmark分離追加
                            phase_data.append({
                                'フェーズ': '🔍 MV ANALYZE',
                                '時間 (秒)': analyze_time,
                                '割合 (%)': (analyze_time / total_time * 100) if total_time > 0 else 0
                            })
                            phase_data.append({
                                'フェーズ': '⚡ クエリ実行',
                                '時間 (秒)': query_exec_time,
                                '割合 (%)': (query_exec_time / total_time * 100) if total_time > 0 else 0
                            })
                            
                            col1, col2 = st.columns([1, 1])
                            
                            with col1:
                                # Phase pie chart
                                if phase_data:
                                    fig = px.pie(
                                        phase_data,
                                        values='時間 (秒)',
                                        names='フェーズ',
                                        title='フェーズ別時間配分',
                                        hole=0.4
                                    )
                                    fig.update_traces(textposition='inside', textinfo='percent+label')
                                    fig.update_layout(height=300, showlegend=False)
                                    st.plotly_chart(fig, use_container_width=True, key=f"phase_pie_{algo}")
                            
                            with col2:
                                # Phase metrics
                                for pd_item in phase_data:
                                    pct = pd_item['割合 (%)']
                                    time_val = pd_item['時間 (秒)']
                                    st.markdown(f"**{pd_item['フェーズ']}**: {time_val:.2f}秒 ({pct:.1f}%)")
                        
                        st.markdown("---")
                        
                        # Benchmark results
                        benchmark = exec_summary.get('benchmark', {})
                        if benchmark:
                            st.markdown("#### 📊 書き換えクエリ実行結果")
                            
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric(
                                    "📝 総クエリ数",
                                    benchmark.get('total_queries', 0)
                                )
                            
                            with col2:
                                success_count = benchmark.get('successful', 0)
                                total_queries = benchmark.get('total_queries', 0)
                                success_rate = (success_count / total_queries * 100) if total_queries > 0 else 0
                                st.metric(
                                    "✅ 成功",
                                    success_count,
                                    f"{success_rate:.1f}%"
                                )
                            
                            with col3:
                                failed_count = benchmark.get('failed', 0)
                                st.metric(
                                    "❌ 失敗",
                                    failed_count,
                                    delta_color="inverse" if failed_count > 0 else "off"
                                )
                            
                            with col4:
                                st.metric(
                                    "⏱️ 平均実行時間",
                                    f"{benchmark.get('avg_time_per_query', 0):.3f}秒"
                                )
                            
                            st.markdown(f"**ベンチマーク総実行時間:** {benchmark.get('total_time', 0):.2f}秒")
                            
                            # Show failed queries if any
                            failed_queries = benchmark.get('failed_queries', [])
                            if failed_queries:
                                with st.expander(f"⚠️ 失敗したクエリ ({len(failed_queries)}件)", expanded=False):
                                    for fq in failed_queries:
                                        st.markdown(f"**{fq.get('query_id', 'N/A')}**")
                                        st.code(fq.get('error', 'No error message'), language='text')
                        
                        st.markdown("---")
                        
                        # MV creation results
                        mv_creation = exec_summary.get('mv_creation', {})
                        if mv_creation:
                            st.markdown("#### 🏗️ MV作成結果")
                            
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric(
                                    "📦 計画MV数",
                                    mv_creation.get('total_mvs', 0)
                                )
                            
                            with col2:
                                created_count = mv_creation.get('created', 0)
                                total_mvs = mv_creation.get('total_mvs', 0)
                                create_rate = (created_count / total_mvs * 100) if total_mvs > 0 else 0
                                st.metric(
                                    "✅ 作成成功",
                                    created_count,
                                    f"{create_rate:.1f}%"
                                )
                            
                            with col3:
                                failed_mvs_count = mv_creation.get('failed', 0)
                                st.metric(
                                    "❌ 作成失敗",
                                    failed_mvs_count,
                                    delta_color="inverse" if failed_mvs_count > 0 else "off"
                                )
                            
                            with col4:
                                total_size_mb = mv_creation.get('total_size_mb', 0)
                                st.metric(
                                    "💾 総サイズ",
                                    f"{total_size_mb:.2f} MB"
                                )
                            
                            st.markdown(f"**MV作成総時間:** {mv_creation.get('total_time', 0):.2f}秒")
                            
                            # Show failed MVs if any
                            failed_mvs = mv_creation.get('failed_mvs', [])
                            if failed_mvs:
                                with st.expander(f"⚠️ 作成失敗したMV ({len(failed_mvs)}件)", expanded=False):
                                    for fmv in failed_mvs:
                                        st.markdown(f"**{fmv.get('view_id', 'N/A')}** (Node: {fmv.get('node_id', 'N/A')})")
                                        st.code(fmv.get('error', 'No error message'), language='text')
                        
                        st.markdown("---")
                        
                        # Total Time Summary Table
                        st.markdown("#### 📋 実行結果サマリー")
                        
                        summary_data = {
                            '項目': [
                                '総実行時間',
                                'MV選択（最適化）時間',
                                'MV作成時間',
                                'クエリ書き換え時間',
                                'ベンチマーク実行時間',
                                '作成MV数',
                                'MV作成成功率',
                                'クエリ実行成功率'
                            ],
                            '値': [
                                f"{total_time:.2f}秒",
                                f"{phases.get('optimization', 0):.2f}秒",
                                f"{phases.get('mv_creation', 0):.2f}秒",
                                f"{phases.get('query_rewriting', 0):.2f}秒",
                                f"{phases.get('benchmark', 0):.2f}秒",
                                f"{mv_creation.get('created', 0)}/{mv_creation.get('total_mvs', 0)}",
                                f"{(mv_creation.get('created', 0) / mv_creation.get('total_mvs', 1) * 100):.1f}%" if mv_creation.get('total_mvs', 0) > 0 else "N/A",
                                f"{(benchmark.get('successful', 0) / benchmark.get('total_queries', 1) * 100):.1f}%" if benchmark.get('total_queries', 0) > 0 else "N/A"
                            ]
                        }
                        
                        summary_df = pd.DataFrame(summary_data)
                        st.dataframe(summary_df, use_container_width=True, hide_index=True)

            st.markdown("---")

            # Comparison visualizations
            st.subheader("📊 Algorithm Comparison")

            # Create sub-tabs for different views
            overview_tabs = st.tabs(["📊 Overview", "⏱️ Performance", "💾 Storage"])

            with overview_tabs[0]:
                # Algorithm comparison chart
                if comparison_data['metrics']:
                    fig = Visualizations.create_algorithm_comparison_chart(comparison_data)
                    st.plotly_chart(fig, use_container_width=True, key="overview_algo_comparison")
                
                # Comparison table
                st.markdown("### 📋 Detailed Metrics")
                
                metrics_df = pd.DataFrame(comparison_data['metrics']).T
                metrics_df.index.name = 'Algorithm'
                
                # Format columns
                if 'storage_used_bytes' in metrics_df.columns:
                    metrics_df['storage_used'] = metrics_df['storage_used_bytes'].apply(
                        lambda x: DataProcessor.format_bytes(x)
                    )
                    metrics_df.drop('storage_used_bytes', axis=1, inplace=True)
                if 'storage_used_mb' in metrics_df.columns:
                    metrics_df.drop('storage_used_mb', axis=1, inplace=True)
                if 'optimization_time' in metrics_df.columns:
                    metrics_df['optimization_time'] = metrics_df['optimization_time'].apply(
                        lambda x: DataProcessor.format_duration(x)
                    )
                
                st.dataframe(metrics_df, use_container_width=True)

            with overview_tabs[1]:
                # Utility vs Storage scatter
                if len(comparison_data['metrics']) > 1:
                    st.markdown("### 💡 Utility vs Storage Trade-off")
                    fig = Visualizations.create_utility_storage_scatter(comparison_data)
                    st.plotly_chart(fig, use_container_width=True, key="overview_utility_storage")
                
                # Query performance comparison
                if comparison_data['queries']:
                    st.markdown("### 🔍 Query Performance Heatmap")
                    fig = Visualizations.create_query_performance_heatmap(comparison_data['queries'])
                    st.plotly_chart(fig, use_container_width=True, key="overview_query_heatmap")
                    
                    # Performance statistics
                    st.markdown("### 📈 Performance Statistics")
                    
                    for algo in selected_algorithms:
                        query_perf = loader.load_query_performance(algo)
                        if query_perf:
                            stats = DataProcessor.aggregate_query_statistics(query_perf)
                            
                            with st.expander(f"📊 {algo} Statistics"):
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    st.metric("Total Queries", stats['total_queries'])
                                    st.metric("Improved", stats['improved_queries'])
                                
                                with col2:
                                    st.metric("Degraded", stats['degraded_queries'])
                                    st.metric("Neutral", stats['neutral_queries'])
                                
                                with col3:
                                    st.metric("Avg Speedup", f"{stats['avg_speedup']:.2f}x")
                                    st.metric("Improvement Rate", f"{stats['improvement_rate']:.1f}%")

            with overview_tabs[2]:
                # Storage analysis for each algorithm
                st.markdown("### 💾 Storage Analysis")
                
                for algo in selected_algorithms:
                    mv_details = loader.load_mv_details(algo)
                    if mv_details:
                        with st.expander(f"📦 {algo} - Storage Distribution"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                fig = Visualizations.create_storage_pie_chart(mv_details)
                                st.plotly_chart(fig, use_container_width=True, key=f"overview_storage_pie_{algo}")
                            
                            with col2:
                                # Storage summary
                                total_storage = sum(mv['storage_size'] for mv in mv_details)
                                avg_storage = total_storage / len(mv_details) if mv_details else 0
                                
                                st.markdown(f"""
                                **Storage Summary**
                                - Total Storage: {DataProcessor.format_bytes(total_storage)}
                                - Number of MVs: {len(mv_details)}
                                - Average per MV: {DataProcessor.format_bytes(avg_storage)}
                                """)
                                
                                # Top storage consumers
                                st.markdown("**Top Storage Consumers**")
                                sorted_mvs = sorted(mv_details, key=lambda x: x['storage_size'], reverse=True)[:5]
                                for mv in sorted_mvs:
                                    st.markdown(f"- `{mv['view_id']}`: {DataProcessor.format_bytes(mv['storage_size'])}")

            st.markdown("---")

            # Export options
            st.subheader("📥 Export Results")

            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("📄 Export to CSV", key="overview_export_csv"):
                    from dashboard.utils.file_manager import FileManager
                    
                    # Export comparison metrics
                    export_path = Path(output_dir) / "comparison_results.csv"
                    metrics_data = []
                    
                    for algo, metrics in comparison_data['metrics'].items():
                        metrics_data.append({
                            'algorithm': algo,
                            **metrics
                        })
                    
                    FileManager.export_to_csv(metrics_data, export_path)
                    st.success(f"✅ Exported to {export_path}")

            with col2:
                if st.button("📊 Export Charts", key="overview_export_charts"):
                    st.info("💡 Right-click on any chart and select 'Download plot as PNG'")

            with col3:
                if st.button("📦 Archive Results", key="overview_archive"):
                    from dashboard.utils.file_manager import FileManager
                    from datetime import datetime
                    
                    archive_name = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    archive_path = FileManager.archive_experiment(
                        Path(output_dir),
                        Path(output_dir) / "archives",
                        archive_name
                    )
                    st.success(f"✅ Archived to {archive_path}")

# ============================================================
# TAB 2: Query Analysis
# ============================================================
with main_tabs[1]:
    if not experiments:
        st.warning("⚠️ No experiment results found. Run an experiment first!")
    else:
        available_algorithms = [exp['algorithm'] for exp in experiments]
        selected_algorithm = st.selectbox(
            "Select Algorithm", 
            options=available_algorithms,
            key="query_analysis_algo_select"
        )

        if selected_algorithm:
            # Load query performance data
            query_perf = loader.load_query_performance(selected_algorithm)

            if not query_perf:
                st.warning(f"⚠️ No query performance data found for {selected_algorithm}")
            else:
                st.markdown("---")

                # Performance overview
                st.subheader("📊 Query Performance Overview")

                stats = DataProcessor.aggregate_query_statistics(query_perf)

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>Total Queries</h3>
                        <p>{stats['total_queries']}</p>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);">
                        <h3>Improved</h3>
                        <p>{stats['improved_queries']}</p>
                        <small>{stats['improvement_rate']:.1f}%</small>
                    </div>
                    """, unsafe_allow_html=True)

                with col3:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #f56565 0%, #e53e3e 100%);">
                        <h3>Degraded</h3>
                        <p>{stats['degraded_queries']}</p>
                    </div>
                    """, unsafe_allow_html=True)

                with col4:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%);">
                        <h3>Avg Speedup</h3>
                        <p>{stats['avg_speedup']:.2f}x</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("---")

                # Sub-tabs for Query Analysis
                query_tabs = st.tabs(["📊 Distribution", "📋 Query List", "🔍 Query Details"])

                with query_tabs[0]:
                    st.markdown("### 📈 Speedup Distribution")
                    fig = Visualizations.create_query_improvement_histogram(query_perf)
                    st.plotly_chart(fig, use_container_width=True, key="query_speedup_histogram")
                    
                    # Performance categories
                    st.markdown("### 🎯 Performance Categories")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        major_improvement = len([q for q in query_perf if q['speedup'] > 2.0])
                        st.metric(
                            "Major Improvement (>2x)",
                            major_improvement,
                            f"{major_improvement/len(query_perf)*100:.1f}%"
                        )
                    
                    with col2:
                        minor_improvement = len([q for q in query_perf if 1.1 < q['speedup'] <= 2.0])
                        st.metric(
                            "Minor Improvement (1.1-2x)",
                            minor_improvement,
                            f"{minor_improvement/len(query_perf)*100:.1f}%"
                        )
                    
                    with col3:
                        degradation = len([q for q in query_perf if q['speedup'] < 0.9])
                        st.metric(
                            "Degradation (<0.9x)",
                            degradation,
                            f"{degradation/len(query_perf)*100:.1f}%",
                            delta_color="inverse"
                        )

                with query_tabs[1]:
                    st.markdown("### 📋 Query Performance List")
                    
                    # Filters
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        sort_by = st.selectbox(
                            "Sort by",
                            options=['speedup', 'original_cost', 'rewritten_cost'],
                            index=0,
                            key="query_list_sort"
                        )
                    
                    with col2:
                        sort_order = st.radio("Order", options=['Descending', 'Ascending'], index=0, key="query_list_order")
                    
                    with col3:
                        filter_category = st.multiselect(
                            "Filter by category",
                            options=['Major Improvement', 'Improvement', 'Neutral', 'Degradation'],
                            default=[],
                            key="query_list_filter"
                        )
                    
                    # Convert to DataFrame
                    df = DataProcessor.query_performance_to_dataframe(query_perf)
                    
                    # Apply filters
                    if filter_category:
                        df = df[df['category'].isin(filter_category)]
                    
                    # Sort
                    ascending = sort_order == 'Ascending'
                    df = df.sort_values(by=sort_by, ascending=ascending)
                    
                    # Format for display
                    display_df = df[['query_id', 'original_cost', 'rewritten_cost', 'speedup', 'category']].copy()
                    display_df['original_cost'] = display_df['original_cost'].round(2)
                    display_df['rewritten_cost'] = display_df['rewritten_cost'].round(2)
                    display_df['speedup'] = display_df['speedup'].round(2)
                    
                    # Style function for row coloring based on category (matching sidebar colors)
                    def style_row_by_category(row):
                        category = row['category']
                        if category in ['Major Improvement', 'Improvement']:
                            # Green for improved queries (matching 🟢 in sidebar)
                            return ['background-color: rgba(0, 200, 83, 0.3)'] * len(row)
                        elif category == 'Degradation':
                            # Red for degraded queries (matching 🔴 in sidebar)
                            return ['background-color: rgba(255, 82, 82, 0.3)'] * len(row)
                        else:
                            # White/transparent for neutral (matching 🟡 which shows as white)
                            return ['background-color: transparent'] * len(row)
                    
                    # Apply styling
                    styled_df = display_df.style.apply(style_row_by_category, axis=1)
                    
                    # Calculate dynamic height based on number of rows (35px per row + header)
                    row_height = 35
                    header_height = 40
                    dynamic_height = min(max(len(display_df) * row_height + header_height, 200), 800)
                    
                    st.dataframe(styled_df, use_container_width=True, height=dynamic_height, hide_index=False)
                    
                    # Summary stats for filtered data
                    if len(df) > 0:
                        st.markdown(f"""
                        **Filtered Results:** {len(df)} queries  
                        **Avg Speedup:** {df['speedup'].mean():.2f}x  
                        **Median Speedup:** {df['speedup'].median():.2f}x
                        """)

                with query_tabs[2]:
                    st.markdown("### 🔍 Query Details")
                    
                    query_ids = [q['query_id'] for q in query_perf]
                    
                    # サイドバーにクエリナビゲーターを配置
                    with st.sidebar:
                        st.markdown("---")
                        st.markdown("### 📋 Query Navigator")
                        
                        # Search/filter queries
                        search_query = st.text_input("🔍 Search Query ID", "", key="query_search_input")
                        
                        # Filter query list
                        filtered_ids = [qid for qid in query_ids if search_query.lower() in qid.lower()] if search_query else query_ids
                        
                        # Show performance category filter (matching categorize_speedup logic)
                        st.markdown("**Filter by Performance:**")
                        show_improved = st.checkbox("🟢 Improved (>1.1x)", value=True, key="filter_improved")
                        show_neutral = st.checkbox("⚪ Neutral (0.9<x≤1.1)", value=True, key="filter_neutral")
                        show_degraded = st.checkbox("🔴 Degraded (≤0.9x)", value=True, key="filter_degraded")
                        
                        # Apply performance filters (matching categorize_speedup exactly)
                        # categorize_speedup: >2.0=Major, >1.1=Improvement, >0.9=Neutral, <=0.9=Degradation
                        final_filtered_ids = []
                        for qid in filtered_ids:
                            q_data = next((q for q in query_perf if q['query_id'] == qid), None)
                            if q_data:
                                spd = q_data['speedup']
                                if show_improved and spd > 1.1:
                                    final_filtered_ids.append(qid)
                                elif show_neutral and 0.9 < spd <= 1.1:
                                    final_filtered_ids.append(qid)
                                elif show_degraded and spd <= 0.9:
                                    final_filtered_ids.append(qid)
                        
                        st.markdown(f"**{len(final_filtered_ids)}** queries")
                        st.markdown("---")
                        
                        # Query selection with radio buttons
                        if final_filtered_ids:
                            # Create options with speedup info
                            def format_query_option(qid):
                                q_data = next((q for q in query_perf if q['query_id'] == qid), None)
                                if q_data:
                                    spd = q_data['speedup']
                                    # Match categorize_speedup exactly: >1.1=green, >0.9=white, <=0.9=red
                                    if spd > 1.1:
                                        icon = "🟢"
                                    elif spd <= 0.9:
                                        icon = "🔴"
                                    else:
                                        icon = "⚪"
                                    return f"{icon} {qid} ({spd:.2f}x)"
                                return qid
                            
                            selected_query = st.radio(
                                "Select Query:",
                                options=final_filtered_ids,
                                format_func=format_query_option,
                                key="query_navigator_radio",
                                label_visibility="collapsed"
                            )
                        else:
                            selected_query = None
                            st.warning("No queries match the filter")
                    
                    # Main content area - show selected query details
                    if selected_query:
                        # Find query data
                        query_data = next((q for q in query_perf if q['query_id'] == selected_query), None)
                        
                        if query_data:
                            # Display metrics at the top
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("Original Cost", f"{query_data['original_cost']:.2f}")
                            
                            with col2:
                                st.metric("Rewritten Cost", f"{query_data['rewritten_cost']:.2f}")
                            
                            with col3:
                                speedup = query_data['speedup']
                                delta = f"{(speedup - 1) * 100:+.1f}%"
                                st.metric(
                                    "Speedup",
                                    f"{speedup:.2f}x",
                                    delta,
                                    delta_color="normal" if speedup >= 1.0 else "inverse"
                                )
                            
                            # Performance assessment
                            st.markdown("---")
                            st.markdown("### 🎯 Performance Assessment")
                            
                            category = DataProcessor.categorize_speedup(speedup)
                            
                            if category == "Major Improvement":
                                st.success(f"✅ **{category}**: This query shows significant performance improvement!")
                            elif category == "Improvement":
                                st.info(f"ℹ️ **{category}**: This query has moderate performance improvement.")
                            elif category == "Neutral":
                                st.warning(f"⚠️ **{category}**: This query shows minimal performance change.")
                            else:
                                st.error(f"❌ **{category}**: This query performance has degraded. Consider investigating.")
                            
                            # Additional details - MVs used
                            st.markdown("---")
                            st.markdown("### 📝 Query Information")
                            
                            # Load optimization results to get selected views
                            opt_results = loader.load_optimization_results(selected_algorithm)
                            selected_views = opt_results.get('selected_views', []) if opt_results else []
                            
                            # Get y_ij, node_list, and query_files from metadata to determine actual MV usage
                            metadata = {}
                            if opt_results:
                                metadata = opt_results.get('metadata')
                                if not metadata and 'solution' in opt_results:
                                    metadata = opt_results['solution'].get('metadata', {})
                                if metadata is None:
                                    metadata = {}
                            
                            y_ij = metadata.get('y_ij')
                            node_list = metadata.get('node_list')
                            query_files = metadata.get('query_files')
                            
                            # Find MVs used in this query
                            used_mvs = []
                            mv_node_positions = {}  # node_id -> mv info
                            
                            # Determine query index for y_ij lookup
                            query_idx_for_y = -1
                            if query_files and selected_query in query_files:
                                query_idx_for_y = query_files.index(selected_query)
                            
                            if y_ij is not None and node_list is not None and query_idx_for_y != -1:
                                # Use y_ij to find MVs actually used by this query
                                for view in selected_views:
                                    node_id = view.get('node_id', '')
                                    try:
                                        node_idx = node_list.index(node_id)
                                        if y_ij[query_idx_for_y][node_idx] == 1:
                                            used_mvs.append(view)
                                            mv_node_positions[node_id] = view
                                    except (ValueError, IndexError):
                                        pass
                            else:
                                # Fallback to using usage_positions
                                for view in selected_views:
                                    for pos in view.get('usage_positions', []):
                                        if pos[0] == query_ids.index(selected_query):
                                            used_mvs.append(view)
                                            node_id = view.get('node_id', '')
                                            mv_node_positions[node_id] = view
                                            break
                            
                            if used_mvs:
                                st.markdown(f"**Materialized Views Used:** {len(used_mvs)}")
                                for mv in used_mvs:
                                    node_id = mv.get('node_id', 'N/A')
                                    view_id = mv.get('view_id', 'N/A')
                                    size_mb = mv.get('size_mb', 0)
                                    st.markdown(f"- `{view_id}` (Node: `{node_id}`, Size: {size_mb:.2f} MB)")
                            else:
                                st.markdown("*No materialized views used for this query*")
                            
                            # Display execution plan tree
                            st.markdown("---")
                            st.markdown("### 🌳 Execution Plan Tree")
                            
                            # Load parsed query plan
                            parsed_dir = Path(output_dir) / "parsed"
                            query_file = parsed_dir / f"{selected_query}.json"
                            
                            if query_file.exists():
                                try:
                                    with open(query_file, 'r') as f:
                                        plan_data = json.load(f)
                                    
                                    # Create tabs for different views
                                    plan_tab1, plan_tab2 = st.tabs(["🌲 Tree View", "📄 JSON View"])
                                    
                                    with plan_tab1:
                                        st.info(f"💡 Green nodes indicate materialized views selected by the {selected_algorithm} algorithm")
                                        
                                        # Build graph structure for visualization
                                        import networkx as nx
                                        
                                        def build_graph_from_plan(node, graph=None, parent_id=None, mv_positions=None):
                                            """Build networkx graph from execution plan"""
                                            if graph is None:
                                                graph = nx.DiGraph()
                                            if mv_positions is None:
                                                mv_positions = mv_node_positions
                                            
                                            node_id = node.get('node_id', 'N/A')
                                            node_type = node.get('Node Type', 'Unknown')
                                            cost = node.get('Total Cost', 0)
                                            rows = node.get('Plan Rows', 0)
                                            
                                            # Check if this node is a selected MV
                                            is_mv = node_id in mv_positions
                                            mv_info = mv_positions.get(node_id, None)
                                            
                                            # Create node label
                                            if is_mv:
                                                label = f"{node_type}\n(MV: {mv_info['view_id']})\nID: {node_id}\nCost: {cost:.2f}"
                                                color = '#48bb78'
                                            else:
                                                label = f"{node_type}\nID: {node_id}\nCost: {cost:.2f}\nRows: {rows}"
                                                color = '#4299e1'
                                            
                                            # Add node to graph
                                            graph.add_node(node_id, 
                                                         label=label, 
                                                         node_type=node_type,
                                                         cost=cost,
                                                         is_mv=is_mv,
                                                         color=color)
                                            
                                            # Add edge from parent
                                            if parent_id is not None:
                                                graph.add_edge(parent_id, node_id)
                                            
                                            # Process children
                                            children = node.get('Plans', [])
                                            for child in children:
                                                build_graph_from_plan(child, graph, node_id, mv_positions)
                                            
                                            return graph
                                        
                                        # Render the plan tree
                                        if isinstance(plan_data, list) and len(plan_data) > 0:
                                            # Build graph
                                            G = build_graph_from_plan(plan_data[0].get('Plan', {}))
                                            
                                            # Use hierarchical layout
                                            pos = nx.spring_layout(G, k=2, iterations=50)
                                            
                                            # Try to use hierarchical layout
                                            try:
                                                for layer, nodes in enumerate(nx.topological_generations(G)):
                                                    for i, node in enumerate(nodes):
                                                        pos[node] = (i - len(nodes)/2, -layer)
                                            except:
                                                pass
                                            
                                            # Extract positions and edges
                                            edge_x = []
                                            edge_y = []
                                            for edge in G.edges():
                                                x0, y0 = pos[edge[0]]
                                                x1, y1 = pos[edge[1]]
                                                edge_x.extend([x0, x1, None])
                                                edge_y.extend([y0, y1, None])
                                            
                                            edge_trace = go.Scatter(
                                                x=edge_x, y=edge_y,
                                                line=dict(width=2, color='#718096'),
                                                hoverinfo='none',
                                                mode='lines')
                                            
                                            # Create node trace
                                            node_x = []
                                            node_y = []
                                            node_text = []
                                            node_color = []
                                            node_size = []
                                            
                                            for node in G.nodes():
                                                x, y = pos[node]
                                                node_x.append(x)
                                                node_y.append(y)
                                                
                                                node_data = G.nodes[node]
                                                node_text.append(node_data['label'])
                                                node_color.append(node_data['color'])
                                                
                                                # Size based on cost
                                                size = min(50, max(20, node_data['cost'] / 10 + 20))
                                                node_size.append(size)
                                            
                                            node_trace = go.Scatter(
                                                x=node_x, y=node_y,
                                                mode='markers+text',
                                                hoverinfo='text',
                                                text=[G.nodes[node]['node_type'] for node in G.nodes()],
                                                hovertext=node_text,
                                                textposition="top center",
                                                marker=dict(
                                                    showscale=False,
                                                    color=node_color,
                                                    size=node_size,
                                                    line=dict(width=2, color='white')))
                                            
                                            # Create figure
                                            fig = go.Figure(data=[edge_trace, node_trace],
                                                          layout=go.Layout(
                                                              title=dict(text=f'Execution Plan for Query {selected_query}', font=dict(size=16)),
                                                              showlegend=False,
                                                              hovermode='closest',
                                                              margin=dict(b=20, l=5, r=5, t=40),
                                                              xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                                              yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                                              plot_bgcolor='rgba(0,0,0,0)',
                                                              paper_bgcolor='rgba(0,0,0,0)',
                                                              height=600))
                                            
                                            st.plotly_chart(fig, use_container_width=True, key="query_execution_plan_tree")
                                        else:
                                            st.warning("Unable to parse plan data")
                                    
                                    with plan_tab2:
                                        st.json(plan_data)
                                
                                except Exception as e:
                                    st.error(f"Error loading execution plan: {str(e)}")
                            else:
                                st.warning(f"Execution plan file not found: {query_file}")
                    else:
                        st.info("👈 サイドバーからクエリを選択してください")

                st.markdown("---")

                # Export options
                col1, col2 = st.columns(2)

                with col1:
                    if st.button("📥 Export Query Performance", key="query_export"):
                        from dashboard.utils.file_manager import FileManager
                        export_path = Path(output_dir) / f"{selected_algorithm}_query_performance.csv"
                        FileManager.export_to_csv(query_perf, export_path)
                        st.success(f"✅ Exported to {export_path}")

# ============================================================
# TAB 3: MV Explorer
# ============================================================
with main_tabs[2]:
    if not experiments:
        st.warning("⚠️ No experiment results found. Run an experiment first!")
    else:
        available_algorithms = [exp['algorithm'] for exp in experiments]
        selected_algorithm_mv = st.selectbox(
            "Select Algorithm", 
            options=available_algorithms,
            key="mv_explorer_algo_select"
        )

        if selected_algorithm_mv:
            # Load MV details
            mv_details = loader.load_mv_details(selected_algorithm_mv)

            if not mv_details:
                st.warning(f"⚠️ No materialized view data found for {selected_algorithm_mv}")
            else:
                st.markdown("---")

                # Overview metrics
                st.subheader("📊 MV Selection Overview")

                total_storage = sum(mv['storage_size'] for mv in mv_details)
                total_utility = sum(mv['utility'] for mv in mv_details)
                avg_utility = total_utility / len(mv_details) if mv_details else 0

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>Total MVs</h3>
                        <p>{len(mv_details)}</p>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <h3>Total Utility</h3>
                        <p>{total_utility:.2f}</p>
                    </div>
                    """, unsafe_allow_html=True)

                with col3:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                        <h3>Total Storage</h3>
                        <p>{DataProcessor.format_bytes(total_storage)}</p>
                    </div>
                    """, unsafe_allow_html=True)

                with col4:
                    st.markdown(f"""
                    <div class="metric-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                        <h3>Avg Utility</h3>
                        <p>{avg_utility:.2f}</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("---")

                # Sub-tabs for MV Explorer
                mv_tabs = st.tabs(["📊 Overview", "📋 MV List", "🔍 MV Details"])

                with mv_tabs[0]:
                    st.markdown("### 💡 Utility Distribution")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig = Visualizations.create_mv_utility_distribution(mv_details)
                        st.plotly_chart(fig, use_container_width=True, key="mv_utility_distribution")
                    
                    with col2:
                        st.markdown("### 💾 Storage Distribution")
                        fig = Visualizations.create_storage_pie_chart(mv_details)
                        st.plotly_chart(fig, use_container_width=True, key="mv_storage_pie")
                    
                    # Summary statistics
                    st.markdown("---")
                    st.markdown("### 📈 Statistics")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("**Utility Statistics**")
                        utilities = [mv['utility'] for mv in mv_details]
                        st.markdown(f"""
                        - Max: {max(utilities):.2f}
                        - Min: {min(utilities):.2f}
                        - Median: {sorted(utilities)[len(utilities)//2]:.2f}
                        """)
                    
                    with col2:
                        st.markdown("**Storage Statistics**")
                        sizes = [mv['storage_size'] for mv in mv_details]
                        st.markdown(f"""
                        - Max: {DataProcessor.format_bytes(max(sizes))}
                        - Min: {DataProcessor.format_bytes(min(sizes))}
                        - Median: {DataProcessor.format_bytes(sorted(sizes)[len(sizes)//2])}
                        """)
                    
                    with col3:
                        st.markdown("**Usage Statistics**")
                        
                        # Load optimization results to get actual usage counts
                        opt_results = loader.load_optimization_results(selected_algorithm_mv)
                        selected_views = opt_results.get('selected_views', []) if opt_results else []
                        
                        if selected_views:
                            total_usage = sum(len(view.get('usage_positions', [])) for view in selected_views)
                            avg_usage = total_usage / len(selected_views) if selected_views else 0
                            max_usage = max((len(view.get('usage_positions', [])) for view in selected_views), default=0)
                        else:
                            total_usage = sum(len(mv.get('used_by_queries', [])) for mv in mv_details)
                            avg_usage = total_usage / len(mv_details) if mv_details else 0
                            max_usage = max((len(mv.get('used_by_queries', [])) for mv in mv_details), default=0)
                        
                        st.markdown(f"""
                        - Total Usage Positions: {total_usage}
                        - Avg per MV: {avg_usage:.1f}
                        - Most Used: {max_usage}
                        """)

                with mv_tabs[1]:
                    st.markdown("### 📋 Materialized Views List")
                    
                    # Sorting and filtering options
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        sort_by_mv = st.selectbox(
                            "Sort by",
                            options=['utility', 'storage_size', 'query_count'],
                            format_func=lambda x: x.replace('_', ' ').title(),
                            key="mv_list_sort"
                        )
                    
                    with col2:
                        sort_order_mv = st.radio("Order", options=['Descending', 'Ascending'], index=0, key="mv_list_order")
                    
                    with col3:
                        min_utility = st.number_input("Min Utility", min_value=0.0, value=0.0, step=10.0, key="mv_min_utility")
                    
                    # Process data
                    df_mv = DataProcessor.mv_details_to_dataframe(mv_details)
                    
                    # Filter
                    if min_utility > 0:
                        df_mv = df_mv[df_mv['utility'] >= min_utility]
                    
                    # Sort
                    ascending_mv = sort_order_mv == 'Ascending'
                    if sort_by_mv in df_mv.columns:
                        df_mv = df_mv.sort_values(by=sort_by_mv, ascending=ascending_mv)
                    
                    # Display columns
                    display_cols = ['view_id', 'utility', 'storage_formatted', 'query_count', 'node_type']
                    available_cols = [col for col in display_cols if col in df_mv.columns]
                    
                    if available_cols:
                        display_df_mv = df_mv[available_cols].copy()
                        display_df_mv.columns = [col.replace('_', ' ').title() for col in available_cols]
                        
                        st.dataframe(display_df_mv, use_container_width=True, height=500)
                        
                        st.markdown(f"**Showing {len(df_mv)} of {len(mv_details)} MVs**")

                with mv_tabs[2]:
                    st.markdown("### 🔍 Materialized View Details")
                    
                    # MV selection
                    mv_ids = [mv['view_id'] for mv in mv_details]
                    selected_mv = st.selectbox("Select Materialized View", options=mv_ids, key="mv_detail_select")
                    
                    if selected_mv:
                        # Find MV data
                        mv_data = next((mv for mv in mv_details if mv['view_id'] == selected_mv), None)
                        
                        if mv_data:
                            # Display metrics
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("Utility", f"{mv_data['utility']:.2f}")
                            
                            with col2:
                                st.metric("Storage Size", DataProcessor.format_bytes(mv_data['storage_size']))
                            
                            with col3:
                                query_count = len(mv_data.get('used_by_queries', []))
                                st.metric("Used by Queries", query_count)
                            
                            # Additional info
                            st.markdown("---")
                            st.markdown("### ℹ️ Additional Information")
                            
                            st.markdown(f"""
                            **Node Type:** `{mv_data.get('node_type', 'unknown')}`  
                            **Maintenance Cost:** {mv_data.get('maintenance_cost', 0):.2f}
                            """)
                            
                            # SQL definition
                            if mv_data.get('sql'):
                                st.markdown("---")
                                st.markdown("### 📝 SQL Definition")
                                st.code(mv_data['sql'], language='sql')

                st.markdown("---")

                # Export options
                col1, col2 = st.columns(2)

                with col1:
                    if st.button("📥 Export MV List", key="mv_export"):
                        from dashboard.utils.file_manager import FileManager
                        export_path = Path(output_dir) / f"{selected_algorithm_mv}_mv_list.csv"
                        FileManager.export_to_csv(mv_details, export_path)
                        st.success(f"✅ Exported to {export_path}")

# ============================================================
# TAB 4: Parse Statistics
# ============================================================
with main_tabs[3]:
    st.markdown("クエリパース時の統計情報を表示します。利得（Utility）、更新コスト（Maintenance Cost）、純利益（Net Benefit）の分布を確認できます。")

    # Get output directory
    output_dir_path = Path(get_session_value('output_dir', 'Output'))

    # Check for parse statistics file
    stats_file = output_dir_path / "parse_statistics.json"

    if not stats_file.exists():
        st.warning(f"⚠️ パース統計ファイルが見つかりません: `{stats_file}`")
        st.info("ℹ️ 実験を実行し、Query Parsingフェーズを完了してください。")
        
        # Try to load from pickle if available
        pickle_path = output_dir_path / "qp_class.pkl"
        if pickle_path.exists():
            st.markdown("---")
            st.markdown("### 🔄 キャッシュからの統計生成")
            st.markdown("保存済みのQuery Parserキャッシュから統計を生成できます。")
            
            if st.button("📊 統計を生成", type="primary", key="generate_stats"):
                try:
                    import pickle
                    with open(pickle_path, 'rb') as f:
                        qp = pickle.load(f)
                    
                    # Check if statistics method exists
                    if hasattr(qp, '_compute_parse_statistics'):
                        stats = qp._compute_parse_statistics()
                        
                        # Save statistics
                        with open(stats_file, 'w') as f:
                            json.dump(stats, f, indent=2)
                        
                        st.success(f"✅ 統計を生成しました: `{stats_file}`")
                        st.rerun()
                    else:
                        st.info("キャッシュが古い形式です。実験を再実行してください。")
                except Exception as e:
                    st.error(f"❌ エラー: {str(e)}")
    else:
        # Load statistics
        with open(stats_file, 'r') as f:
            stats = json.load(f)

        # Sub-tabs for Parse Statistics
        parse_tabs = st.tabs(["📊 概要", "💹 利得分析", "🔧 コスト分析", "📋 詳細データ"])

        with parse_tabs[0]:
            st.subheader("📊 パース概要")
            
            # Key metrics in columns
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "📝 クエリ数",
                    stats.get('num_queries', 0),
                    help="パースされたクエリの総数"
                )
            
            with col2:
                st.metric(
                    "🌲 ノード数",
                    stats.get('num_nodes', 0),
                    help="MV候補となるノードの総数"
                )
            
            with col3:
                st.metric(
                    "🍃 リーフノード",
                    stats.get('num_leaf_nodes', 0),
                    help="単一テーブルノード"
                )
            
            with col4:
                st.metric(
                    "🔗 非リーフノード",
                    stats.get('num_non_leaf_nodes', 0),
                    help="結合ノード"
                )
            
            st.markdown("---")
            
            # Utility summary with gauge charts
            st.subheader("💡 利得（Utility）サマリー")
            
            col1, col2 = st.columns(2)
            
            nodes_positive_pct = stats.get('nodes_with_positive_utility_percentage', 0)
            net_benefit_pct = stats.get('nodes_with_positive_net_benefit_percentage', 0)
            
            with col1:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=nodes_positive_pct,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "正の利得ノード"},
                    number={'suffix': '%', 'font': {'size': 30}},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "#3498db"},
                        'steps': [
                            {'range': [0, 30], 'color': "#ffebee"},
                            {'range': [30, 70], 'color': "#fff3e0"},
                            {'range': [70, 100], 'color': "#e3f2fd"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 2},
                            'thickness': 0.75,
                            'value': 50
                        }
                    }
                ))
                fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig, use_container_width=True, key="parse_gauge_positive_utility")
                st.caption(f"{stats.get('nodes_with_positive_utility', 0):,} / {stats.get('num_nodes', 0):,} ノード")
            
            with col2:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=net_benefit_pct,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "正の純利益ノード"},
                    number={'suffix': '%', 'font': {'size': 30}},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "#9b59b6"},
                        'steps': [
                            {'range': [0, 30], 'color': "#ffebee"},
                            {'range': [30, 70], 'color': "#fff3e0"},
                            {'range': [70, 100], 'color': "#f3e5f5"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 2},
                            'thickness': 0.75,
                            'value': 50
                        }
                    }
                ))
                fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig, use_container_width=True, key="parse_gauge_net_benefit")
                st.caption(f"{stats.get('nodes_with_positive_net_benefit', 0):,} / {stats.get('num_nodes', 0):,} ノード")

        with parse_tabs[1]:
            st.subheader("💹 利得（Utility）詳細分析")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("最小値", f"{stats.get('utility_min', 0):.2f}")
            
            with col2:
                st.metric("最大値", f"{stats.get('utility_max', 0):.2f}")
            
            with col3:
                st.metric("平均値", f"{stats.get('utility_mean', 0):.2f}")
            
            with col4:
                st.metric("中央値", f"{stats.get('utility_median', 0):.2f}")
            
            st.markdown("---")
            
            st.markdown("### 🌟 正の利得のみの統計")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("正の利得 - 平均", f"{stats.get('positive_utility_mean', 0):.2f}")
            
            with col2:
                st.metric("正の利得 - 最大", f"{stats.get('positive_utility_max', 0):.2f}")
            
            with col3:
                st.metric(
                    "正の利得を持つクエリ",
                    f"{stats.get('queries_with_positive_utility', 0)} / {stats.get('num_queries', 0)}",
                    f"({stats.get('queries_with_positive_utility_percentage', 0):.1f}%)"
                )

        with parse_tabs[2]:
            st.subheader("🔧 コスト分析")
            
            st.markdown("### 🔄 更新コスト（Maintenance Cost）")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("最小値", f"{stats.get('maintenance_cost_min', 0):.4f}")
            
            with col2:
                st.metric("最大値", f"{stats.get('maintenance_cost_max', 0):.4f}")
            
            with col3:
                st.metric("平均値", f"{stats.get('maintenance_cost_mean', 0):.4f}")
            
            with col4:
                st.metric("合計", f"{stats.get('maintenance_cost_total', 0):.2f}")
            
            st.markdown("---")
            
            st.markdown("### 💾 ストレージサイズ")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("最小", f"{stats.get('storage_size_min', 0):,} bytes")
            
            with col2:
                st.metric("最大", f"{stats.get('storage_size_max', 0):,} bytes")
            
            with col3:
                st.metric("平均", f"{stats.get('storage_size_mean', 0):,.0f} bytes")
            
            with col4:
                total_mb = stats.get('storage_size_total', 0) / (1024 * 1024)
                st.metric("合計", f"{total_mb:.2f} MB")
            
            st.markdown("---")
            
            st.markdown("### 📊 純利益（Net Benefit = Max Utility - Maintenance Cost）")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("最小", f"{stats.get('net_benefit_min', 0):.2f}")
            
            with col2:
                st.metric("最大", f"{stats.get('net_benefit_max', 0):.2f}")
            
            with col3:
                st.metric("平均", f"{stats.get('net_benefit_mean', 0):.2f}")
            
            with col4:
                st.metric(
                    "正の純利益ノード",
                    f"{stats.get('nodes_with_positive_net_benefit', 0)} / {stats.get('num_nodes', 0)}"
                )

        with parse_tabs[3]:
            st.subheader("📋 詳細データ")
            
            # Convert to DataFrame for better display
            stats_df = pd.DataFrame([
                {"カテゴリ": "基本情報", "項目": "クエリ数", "値": stats.get('num_queries', 0)},
                {"カテゴリ": "基本情報", "項目": "ノード数", "値": stats.get('num_nodes', 0)},
                {"カテゴリ": "基本情報", "項目": "リーフノード数", "値": stats.get('num_leaf_nodes', 0)},
                {"カテゴリ": "基本情報", "項目": "非リーフノード数", "値": stats.get('num_non_leaf_nodes', 0)},
                {"カテゴリ": "利得値", "項目": "最小値", "値": f"{stats.get('utility_min', 0):.4f}"},
                {"カテゴリ": "利得値", "項目": "最大値", "値": f"{stats.get('utility_max', 0):.4f}"},
                {"カテゴリ": "利得値", "項目": "平均値", "値": f"{stats.get('utility_mean', 0):.4f}"},
                {"カテゴリ": "利得値", "項目": "中央値", "値": f"{stats.get('utility_median', 0):.4f}"},
                {"カテゴリ": "正の利得", "項目": "平均値", "値": f"{stats.get('positive_utility_mean', 0):.4f}"},
                {"カテゴリ": "正の利得", "項目": "最大値", "値": f"{stats.get('positive_utility_max', 0):.4f}"},
                {"カテゴリ": "ノード分析", "項目": "正の利得ノード数", "値": stats.get('nodes_with_positive_utility', 0)},
                {"カテゴリ": "ノード分析", "項目": "正の利得ノード率 (%)", "値": f"{stats.get('nodes_with_positive_utility_percentage', 0):.2f}"},
                {"カテゴリ": "ノード分析", "項目": "正の純利益ノード数", "値": stats.get('nodes_with_positive_net_benefit', 0)},
                {"カテゴリ": "ノード分析", "項目": "正の純利益ノード率 (%)", "値": f"{stats.get('nodes_with_positive_net_benefit_percentage', 0):.2f}"},
            ])
            
            st.dataframe(stats_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Export options
            st.markdown("### 📥 エクスポート")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📄 JSONでダウンロード",
                    data=json.dumps(stats, indent=2, ensure_ascii=False),
                    file_name="parse_statistics.json",
                    mime="application/json",
                    key="parse_download_json"
                )
            
            with col2:
                csv_data = stats_df.to_csv(index=False)
                st.download_button(
                    label="📊 CSVでダウンロード",
                    data=csv_data,
                    file_name="parse_statistics.csv",
                    mime="text/csv",
                    key="parse_download_csv"
                )

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem 0;'>
    <p>💡 各タブで詳細な結果分析が可能です</p>
</div>
""", unsafe_allow_html=True)
