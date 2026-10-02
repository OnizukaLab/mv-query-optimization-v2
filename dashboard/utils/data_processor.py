"""
Data Processor Utilities

Utilities for processing and transforming data.
"""

import pandas as pd
from typing import Dict, List, Optional


class DataProcessor:
    """Processes and transforms experiment data"""
    
    @staticmethod
    def format_bytes(bytes_value: int) -> str:
        """Format bytes to human-readable string
        
        Args:
            bytes_value: Size in bytes
            
        Returns:
            Formatted string (e.g., "1.5 MB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration to human-readable string
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted string (e.g., "1h 23m 45s")
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    @staticmethod
    def calculate_speedup(original_cost: float, rewritten_cost: float) -> float:
        """Calculate speedup factor
        
        This is the SINGLE SOURCE OF TRUTH for speedup calculation.
        Used by both the sidebar navigator and the query performance table.
        
        Args:
            original_cost: Original query cost (from 'none' algorithm baseline)
            rewritten_cost: Rewritten query cost (optimized)
            
        Returns:
            Speedup factor (>1 means improvement, 1.0 for edge cases)
        """
        # Both must be positive for meaningful speedup
        if rewritten_cost > 0 and original_cost > 0:
            return original_cost / rewritten_cost
        # Edge cases: return 1.0 (no change) to avoid inf or misleading values
        return 1.0
    
    @staticmethod
    def categorize_speedup(speedup: float) -> str:
        """Categorize speedup into improvement levels
        
        Args:
            speedup: Speedup factor
            
        Returns:
            Category string
        """
        if speedup > 2.0:
            return "Major Improvement"
        elif speedup > 1.1:
            return "Improvement"
        elif speedup > 0.9:
            return "Neutral"
        else:
            return "Degradation"
    
    @staticmethod
    def query_performance_to_dataframe(query_perf: List[Dict]) -> pd.DataFrame:
        """Convert query performance list to DataFrame
        
        Args:
            query_perf: List of query performance dictionaries
            
        Returns:
            Pandas DataFrame
        """
        if not query_perf:
            return pd.DataFrame()
        
        df = pd.DataFrame(query_perf)
        
        # Only calculate speedup if not already present
        # This ensures consistency with the source data from result_loader
        if 'speedup' not in df.columns:
            if 'original_cost' in df.columns and 'rewritten_cost' in df.columns:
                df['speedup'] = df.apply(
                    lambda row: DataProcessor.calculate_speedup(
                        row['original_cost'], 
                        row['rewritten_cost']
                    ),
                    axis=1
                )
        
        # Add category based on speedup
        if 'speedup' in df.columns:
            df['category'] = df['speedup'].apply(DataProcessor.categorize_speedup)
        
        return df
    
    @staticmethod
    def mv_details_to_dataframe(mv_details: List[Dict]) -> pd.DataFrame:
        """Convert MV details list to DataFrame
        
        Args:
            mv_details: List of MV detail dictionaries
            
        Returns:
            Pandas DataFrame
        """
        if not mv_details:
            return pd.DataFrame()
        
        df = pd.DataFrame(mv_details)
        
        # Format storage size
        if 'storage_size' in df.columns:
            df['storage_formatted'] = df['storage_size'].apply(DataProcessor.format_bytes)
        
        # Count queries
        if 'used_by_queries' in df.columns:
            df['query_count'] = df['used_by_queries'].apply(
                lambda x: len(x) if isinstance(x, list) else 0
            )
        
        return df
    
    @staticmethod
    def aggregate_query_statistics(query_perf: List[Dict]) -> Dict:
        """Aggregate statistics from query performance data
        
        Args:
            query_perf: List of query performance dictionaries
            
        Returns:
            Dictionary with aggregated statistics
        """
        if not query_perf:
            return {}
        
        df = DataProcessor.query_performance_to_dataframe(query_perf)
        
        return {
            'total_queries': len(df),
            'improved_queries': len(df[df['speedup'] > 1.1]),
            'degraded_queries': len(df[df['speedup'] < 0.9]),
            'neutral_queries': len(df[(df['speedup'] >= 0.9) & (df['speedup'] <= 1.1)]),
            'avg_speedup': df['speedup'].mean(),
            'median_speedup': df['speedup'].median(),
            'max_speedup': df['speedup'].max(),
            'min_speedup': df['speedup'].min(),
            'improvement_rate': len(df[df['speedup'] > 1.0]) / len(df) * 100 if len(df) > 0 else 0
        }
    
    @staticmethod
    def filter_queries(
        query_perf: List[Dict],
        min_speedup: Optional[float] = None,
        max_speedup: Optional[float] = None,
        categories: Optional[List[str]] = None
    ) -> List[Dict]:
        """Filter queries based on criteria
        
        Args:
            query_perf: List of query performance dictionaries
            min_speedup: Minimum speedup threshold
            max_speedup: Maximum speedup threshold
            categories: List of categories to include
            
        Returns:
            Filtered list of query dictionaries
        """
        df = DataProcessor.query_performance_to_dataframe(query_perf)
        
        if min_speedup is not None:
            df = df[df['speedup'] >= min_speedup]
        
        if max_speedup is not None:
            df = df[df['speedup'] <= max_speedup]
        
        if categories is not None:
            df = df[df['category'].isin(categories)]
        
        return df.to_dict('records')
    
    @staticmethod
    def sort_mvs(
        mv_details: List[Dict],
        sort_by: str = 'utility',
        ascending: bool = False
    ) -> List[Dict]:
        """Sort MVs by specified criterion
        
        Args:
            mv_details: List of MV detail dictionaries
            sort_by: Field to sort by
            ascending: Sort order
            
        Returns:
            Sorted list of MV dictionaries
        """
        df = DataProcessor.mv_details_to_dataframe(mv_details)
        
        if sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=ascending)
        
        return df.to_dict('records')
