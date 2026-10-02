"""小規模実験用のスキーマプロバイダー

EnhancedMVGeneratorが必要とするスキーマ情報を提供します。
"""

from typing import Optional


class SmallTestSchemaProvider:
    """小規模実験用のスキーマプロバイダー"""
    
    # 小規模実験のテーブル定義
    SCHEMA = {
        "users": [
            "user_id",
            "name",
            "age",
            "city",
            "registered_date",
        ],
        "products": [
            "product_id",
            "name",
            "category",
            "price",
            "stock",
        ],
        "orders": [
            "order_id",
            "user_id",
            "product_id",
            "quantity",
            "order_date",
            "total_amount",
        ],
    }
    
    def get_table_columns(self, table_name: str) -> list[str]:
        """テーブルのカラム名を取得
        
        Args:
            table_name: テーブル名
            
        Returns:
            カラム名のリスト
            
        Raises:
            KeyError: テーブルが見つからない場合
        """
        if table_name not in self.SCHEMA:
            raise KeyError(f"Unknown table: {table_name}")
        return self.SCHEMA[table_name]
    
    def validate_table(self, table_name: str) -> bool:
        """テーブルがスキーマに存在するか確認
        
        Args:
            table_name: テーブル名
            
        Returns:
            存在する場合True
        """
        return table_name in self.SCHEMA
    
    def get_foreign_key_relations(self, left_tables: list[str], right_tables: list[str]) -> list:
        """外部キー関係を取得
        
        小規模実験の外部キー関係:
        - orders.user_id -> users.user_id
        - orders.product_id -> products.product_id
        
        Args:
            left_tables: 左側のテーブルリスト
            right_tables: 右側のテーブルリスト
            
        Returns:
            外部キー関係のリスト（簡易実装のため空リストを返す）
        """
        # EnhancedMVGeneratorの_infer_join_conditionメソッドで使用されるが、
        # 小規模実験ではJOIN条件が明示的に提供されているため、
        # この機能は使用されない想定
        return []
