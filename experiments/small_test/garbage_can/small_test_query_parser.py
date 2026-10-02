"""小規模実験専用QueryParser

小規模実験のテーブル情報（users, products, orders）を使って
メンテナンスコストを計算するQueryParser拡張版
"""

from src.core.query_parser import QueryParser
from config.settings import Settings


class SmallTestQueryParser(QueryParser):
    """小規模実験専用のQueryParser

    check_m_costメソッドで使用するテーブル情報を
    小規模実験用（users, products, orders）に設定
    """

    def __init__(self, settings: Settings | None = None):
        """初期化"""
        super().__init__(settings)

    def query_parse(self, q_num: int, path: str, insert_query: int) -> None:
        """小規模実験用のテーブル情報でquery_parseを実行"""

        # まず親クラスのquery_parseを呼び出し
        super().query_parse(q_num, path, insert_query)

        # 小規模実験用のテーブル情報を設定してメンテナンスコストを再計算
        self._recalculate_maintenance_costs(insert_query)

    def _recalculate_maintenance_costs(self, insert_query: int):
        """小規模実験用のテーブル情報でメンテナンスコストを再計算"""

        # 小規模実験のテーブル情報
        table_list = ["users", "products", "orders"]
        record_list = [50, 30, 200]  # 各テーブルのレコード数
        insert_cost_alpha = 0.01  # 挿入コスト係数

        # 簡易的な検索コスト（全テーブル同じ値）
        search_cost = [8.4, 8.4, 8.4]

        # テーブル幅（バイト単位）の推定値
        table_width = [100, 150, 80]  # users, products, orders

        # メンテナンスコストの初期化
        len_leaf = len(self.qm.leaf_nodes_map)
        len_non_leaf = len(self.qm.non_leaf_nodes_map)
        m_cost = [0.0] * (len_leaf + len_non_leaf)

        # 挿入回数（正規化）
        insert_times = insert_query / 1000

        # 更新対象テーブル（ランダムに選択）
        import random
        update_table = [[""] for _ in range(1000)]
        for i in range(len(update_table)):
            x = random.randint(0, 2)  # 0: users, 1: products, 2: orders
            update_table[i][0] = table_list[x]

        # メンテナンスコスト再計算
        m_cost = self.check_m_cost(
            m_cost,
            table_list,
            update_table,
            record_list,
            search_cost,
            insert_cost_alpha,
            table_width,
            insert_times,
        )

        # 再計算したコストを保存
        self.m_cost = m_cost

        print("\n[SmallTestQueryParser] メンテナンスコストを再計算しました:")
        print(f"  テーブル情報: {table_list}")
        print(f"  レコード数: {record_list}")
        print(f"  挿入クエリ数: {insert_query}")
        print(f"  メンテナンスコスト数: {len(m_cost)}")
        if m_cost:
            print(f"  最大メンテナンスコスト: {max(m_cost):.2f}")
            print(f"  最小メンテナンスコスト: {min(m_cost):.2f}")