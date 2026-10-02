"""
Visualization Components

Creates various charts and visualizations for the dashboard.
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from typing import List, Dict, Optional


class Visualizations:
    """Collection of visualization methods for dashboard"""
    
    @staticmethod
    def create_algorithm_comparison_chart(comparison_data: Dict) -> go.Figure:
        """Create algorithm comparison bar chart
        
        Args:
            comparison_data: Dictionary with algorithm metrics
            
        Returns:
            Plotly figure
        """
        metrics = comparison_data.get('metrics', {})
        
        algorithms = list(metrics.keys())
        num_views = [metrics[algo]['num_views'] for algo in algorithms]
        total_utility = [metrics[algo]['total_utility'] for algo in algorithms]
        storage_mb = [metrics[algo]['storage_used_mb'] for algo in algorithms]
        
        fig = make_subplots(
            rows=1, cols=3,
            subplot_titles=('Number of MVs', 'Total Utility', 'Storage Used (MB)'),
            specs=[[{'type': 'bar'}, {'type': 'bar'}, {'type': 'bar'}]]
        )
        
        # Number of MVs
        fig.add_trace(
            go.Bar(x=algorithms, y=num_views, name='MVs', marker_color='#667eea'),
            row=1, col=1
        )
        
        # Total Utility
        fig.add_trace(
            go.Bar(x=algorithms, y=total_utility, name='Utility', marker_color='#764ba2'),
            row=1, col=2
        )
        
        # Storage Used
        fig.add_trace(
            go.Bar(x=algorithms, y=storage_mb, name='Storage', marker_color='#f093fb'),
            row=1, col=3
        )
        
        fig.update_layout(
            height=400,
            showlegend=False,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_utility_storage_scatter(comparison_data: Dict) -> go.Figure:
        """Create utility vs storage scatter plot
        
        Args:
            comparison_data: Dictionary with algorithm metrics
            
        Returns:
            Plotly figure
        """
        metrics = comparison_data.get('metrics', {})
        
        algorithms = list(metrics.keys())
        storage = [metrics[algo]['storage_used_mb'] for algo in algorithms]
        utility = [metrics[algo]['total_utility'] for algo in algorithms]
        
        fig = px.scatter(
            x=storage,
            y=utility,
            text=algorithms,
            labels={'x': 'Storage Used (MB)', 'y': 'Total Utility'},
            title='Utility vs Storage Trade-off'
        )
        
        fig.update_traces(
            marker=dict(size=15, line=dict(width=2, color='white')),
            textposition='top center',
            textfont=dict(size=12)
        )
        
        fig.update_layout(
            height=500,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_phase_time_breakdown(execution_times: Dict) -> go.Figure:
        """Create phase execution time breakdown chart
        
        Args:
            execution_times: Dictionary with phase execution times
            
        Returns:
            Plotly figure
        """
        phases = list(execution_times.keys())
        times = list(execution_times.values())
        
        fig = go.Figure(data=[
            go.Bar(
                x=phases,
                y=times,
                marker_color=['#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe', '#43e97b'],
                text=[f'{t:.2f}s' for t in times],
                textposition='auto'
            )
        ])
        
        fig.update_layout(
            title='Execution Time by Phase',
            xaxis_title='Phase',
            yaxis_title='Time (seconds)',
            height=400,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_query_performance_heatmap(query_data: Dict) -> go.Figure:
        """Create query performance heatmap
        
        Args:
            query_data: Dictionary with query performance across algorithms
            
        Returns:
            Plotly figure
        """
        # Prepare data for heatmap
        query_ids = list(query_data.keys())
        algorithms = []
        if query_ids:
            algorithms = list(query_data[query_ids[0]].keys())
        
        # Create matrix of speedup values
        speedup_matrix = []
        for algo in algorithms:
            row = []
            for qid in query_ids:
                if algo in query_data[qid]:
                    speedup = query_data[qid][algo].get('speedup', 1.0)
                    row.append(speedup)
                else:
                    row.append(None)
            speedup_matrix.append(row)
        
        fig = go.Figure(data=go.Heatmap(
            z=speedup_matrix,
            x=query_ids,
            y=algorithms,
            colorscale='RdYlGn',
            zmid=1.0,
            text=[[f'{v:.2f}x' if v else 'N/A' for v in row] for row in speedup_matrix],
            texttemplate='%{text}',
            textfont={"size": 10},
            colorbar=dict(title="Speedup")
        ))
        
        fig.update_layout(
            title='Query Performance Heatmap (Speedup)',
            xaxis_title='Query ID',
            yaxis_title='Algorithm',
            height=max(300, len(algorithms) * 50),
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_mv_utility_distribution(mv_data: List[Dict]) -> go.Figure:
        """Create MV utility distribution chart
        
        Args:
            mv_data: List of MV dictionaries with utility info
            
        Returns:
            Plotly figure
        """
        view_ids = [mv['view_id'] for mv in mv_data[:20]]  # Top 20
        utilities = [mv['utility'] for mv in mv_data[:20]]
        
        fig = go.Figure(data=[
            go.Bar(
                x=view_ids,
                y=utilities,
                marker_color='#667eea',
                text=[f'{u:.1f}' for u in utilities],
                textposition='auto'
            )
        ])
        
        fig.update_layout(
            title='Top 20 Materialized Views by Utility',
            xaxis_title='View ID',
            yaxis_title='Utility',
            height=500,
            template='plotly_white',
            xaxis={'tickangle': -45}
        )
        
        return fig
    
    @staticmethod
    def create_storage_pie_chart(mv_data: List[Dict]) -> go.Figure:
        """Create storage distribution pie chart
        
        Args:
            mv_data: List of MV dictionaries with storage info
            
        Returns:
            Plotly figure
        """
        # Group small MVs into "Others"
        threshold = 0.05  # 5% of total
        total_storage = sum(mv['storage_size'] for mv in mv_data)
        
        labels = []
        values = []
        others_storage = 0
        
        for mv in sorted(mv_data, key=lambda x: x['storage_size'], reverse=True):
            size_mb = mv['storage_size'] / (1024**2)
            if mv['storage_size'] / total_storage >= threshold:
                labels.append(mv['view_id'])
                values.append(size_mb)
            else:
                others_storage += size_mb
        
        if others_storage > 0:
            labels.append('Others')
            values.append(others_storage)
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker=dict(colors=px.colors.sequential.Purples_r)
        )])
        
        fig.update_layout(
            title='Storage Distribution by MV',
            height=500,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_query_improvement_histogram(query_perf: List[Dict]) -> go.Figure:
        """Create histogram of query improvements
        
        Args:
            query_perf: List of query performance dictionaries
            
        Returns:
            Plotly figure
        """
        speedups = [qp['speedup'] for qp in query_perf]
        
        fig = go.Figure(data=[go.Histogram(
            x=speedups,
            nbinsx=30,
            marker_color='#667eea'
        )])
        
        fig.update_layout(
            title='Query Speedup Distribution',
            xaxis_title='Speedup Factor',
            yaxis_title='Number of Queries',
            height=400,
            template='plotly_white'
        )
        
        # Add vertical line at 1.0 (no improvement)
        fig.add_vline(
            x=1.0,
            line_dash="dash",
            line_color="red",
            annotation_text="No Change"
        )
        
        return fig
    
    @staticmethod
    def create_progress_bar(progress: float, phase: str) -> str:
        """Create HTML progress bar
        
        Args:
            progress: Progress percentage (0-100)
            phase: Current phase name
            
        Returns:
            HTML string for progress bar
        """
        return f"""
        <div style="margin: 1rem 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-weight: 600;">{phase}</span>
                <span>{progress:.1f}%</span>
            </div>
            <div style="background: #e2e8f0; border-radius: 10px; overflow: hidden; height: 24px;">
                <div style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); 
                            width: {progress}%; height: 100%; transition: width 0.3s ease;">
                </div>
            </div>
        </div>
        """
