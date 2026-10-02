"""MV Generator Wrapper for Small Test

MVGeneratorを拡張し、時刻依存型のMV名に対応します。
experiments/small_test専用のラッパー。
"""

from src.rewrite.mv_generator import MVGenerator
from typing import Any


class MVGeneratorWrapper(MVGenerator):
    """時刻依存型MV名に対応したMVGenerator"""
    
    def generate_mv_sql_with_custom_name(
        self,
        node_id: str,
        qm: Any,
        mv_name: str
    ) -> str:
        """カスタムMV名でMV作成SQLを生成
        
        Args:
            node_id: ノードID
            qm: QueryManager
            mv_name: カスタムMV名
            
        Returns:
            CREATE MATERIALIZED VIEW 文
        """
        # 元のSQLを生成
        original_sql = self._generate_mv_sql(node_id, qm)
        
        if not original_sql:
            return ""
        
        # MV名を置き換え
        # 元のMV名: mv_{node_id} または {node_id}
        default_name = f"mv_{node_id}"
        
        # パターン1: "CREATE MATERIALIZED VIEW mv_{node_id} AS"
        if f"CREATE MATERIALIZED VIEW {default_name}" in original_sql:
            modified_sql = original_sql.replace(
                f"CREATE MATERIALIZED VIEW {default_name}",
                f"CREATE MATERIALIZED VIEW {mv_name}"
            )
        # パターン2: "CREATE MATERIALIZED VIEW {node_id} AS"
        elif f"CREATE MATERIALIZED VIEW {node_id}" in original_sql:
            modified_sql = original_sql.replace(
                f"CREATE MATERIALIZED VIEW {node_id}",
                f"CREATE MATERIALIZED VIEW {mv_name}"
            )
        else:
            # フォールバック: 最初の VIEW の後を置き換え
            import re
            pattern = r'(CREATE MATERIALIZED VIEW\s+)(\w+)(\s+AS)'
            modified_sql = re.sub(pattern, rf'\1{mv_name}\3', original_sql)
        
        return modified_sql
