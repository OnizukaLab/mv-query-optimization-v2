"""頻度重み付けQueryParserラッパー もう使わなそう

src/core/query_parser.py を変更せずに、
experiments/small_test 専用の頻度重み付け機能を提供します。
"""

import json
from pathlib import Path
from typing import Dict

from src.core.query_parser import QueryParser
from config.settings import Settings


class FrequencyWeightedParser(QueryParser):
    """頻度で重み付けされた利得を計算するQueryParserの拡張版
    
    u_ij (utility matrix) に各クエリの実行頻度を乗算することで、
    頻度が高いクエリで使われるサブクエリの価値を高めます。
    """
    
    def __init__(self, settings: Settings | None = None, frequency_file: str | None = None):
        """初期化
        
        Args:
            settings: 設定オブジェクト
            frequency_file: 頻度情報JSONファイルのパス
        """
        super().__init__(settings)
        self.frequency_file = frequency_file
        self.query_frequencies: Dict[str, int] = {}
        
        # 頻度情報を読み込み
        if frequency_file and Path(frequency_file).exists():
            self._load_frequencies(frequency_file)
    
    def _load_frequencies(self, frequency_file: str):
        """頻度情報をファイルから読み込み"""
        with open(frequency_file, 'r', encoding='utf-8') as f:
            self.query_frequencies = json.load(f)
        
        print(f"\n[FrequencyWeighted] 頻度情報を読み込み: {frequency_file}")
        for query, freq in self.query_frequencies.items():
            print(f"  {query}: {freq}回")
    
    def apply_frequency_weights(self, files: list[str]):
        """u_ij に頻度の重みを適用
        
        この関数は query_parse() の後に呼び出されます。
        u_ij[query_id][node_id] *= query_frequency[query_id]
        
        Args:
            files: パースしたクエリファイルのリスト
        """
        if not self.query_frequencies:
            print("\n[FrequencyWeighted] 頻度情報なし。重み付けをスキップ")
            return
        
        print(f"\n[FrequencyWeighted] 利得に頻度の重みを適用中...")
        
        # 各クエリの頻度を取得
        query_freq_list = []
        for i, file_path in enumerate(files):
            file_name = Path(file_path).name
            freq = self.query_frequencies.get(file_name, 1)
            query_freq_list.append(freq)
            print(f"  Query {i} ({file_name}): 頻度 {freq}x")
        
        # u_ij に頻度を乗算
        original_u_ij = [row[:] for row in self.u_ij]  # コピーを保存
        
        for i in range(len(self.u_ij)):
            freq = query_freq_list[i]
            for j in range(len(self.u_ij[i])):
                if self.u_ij[i][j] > 0:
                    original_value = self.u_ij[i][j]
                    self.u_ij[i][j] = original_value * freq
        
        # us_ij にも適用
        if hasattr(self, 'us_ij'):
            for i in range(len(self.us_ij)):
                freq = query_freq_list[i]
                for j in range(len(self.us_ij[i])):
                    if self.us_ij[i][j] > 0:
                        self.us_ij[i][j] = self.us_ij[i][j] * freq
        
        # U_max を再計算
        self.U_max = sum(sum(u_row) for u_row in self.u_ij)
        
        # U_j_max を再計算
        self.U_j_max = [0.0] * len(self.U_j_max)
        for i in range(len(self.u_ij)):
            for j in range(len(self.u_ij[i])):
                self.U_j_max[j] += self.u_ij[i][j]
        
        print(f"\n[FrequencyWeighted] 重み付け完了")
        print(f"  総利得 (U_max): {self.U_max:.2f}")
        
        # 統計を表示
        total_freq = sum(query_freq_list)
        avg_freq = total_freq / len(query_freq_list) if query_freq_list else 0
        print(f"  総実行回数: {total_freq}")
        print(f"  平均実行回数: {avg_freq:.1f}")
        
        # トップ5の高利得ノードを表示
        node_utilities = []
        for j in range(len(self.U_j_max)):
            if self.U_j_max[j] > 0:
                node_utilities.append((self.node_list[j], self.U_j_max[j]))
        
        node_utilities.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  トップ5高利得ノード（頻度重み付け後）:")
        for node_id, utility in node_utilities[:5]:
            print(f"    {node_id}: {utility:.2f}")

    def calculate_maintenance_costs(self, insert_query: int = 1000):
        """小規模実験用のメンテナンスコストを計算
        
        元のquery_parser.pyのcheck_m_cost呼び出しロジックと同じ方式で、
        小規模実験用のテーブル情報を使ってメンテナンスコストを計算する。
        
        Args:
            insert_query: INSERT回数（デフォルト: 1000）
        """
        import random
        
        print("\n[MaintenanceCost] メンテナンスコスト計算開始")
        
        # 小規模実験用のテーブル情報を定義
        table_list = ["users", "products", "orders"]
        record_list = [50, 30, 200]  # 各テーブルの初期レコード数
        table_width = [42, 53, 28]  # 各テーブルの行幅（バイト）- 実際のカラムサイズに基づく
        search_cost = [8.4, 8.4, 8.4]  # 各テーブルの検索コスト（PostgreSQL互換）
        insert_cost_alpha = 0.01  # 挿入コスト係数
        
        print(f"  テーブル情報:")
        for i, table in enumerate(table_list):
            print(f"    {table}: レコード数={record_list[i]}, 行幅={table_width[i]}bytes")
        print(f"  INSERT回数: {insert_query}")
        print(f"  挿入コスト係数: {insert_cost_alpha}")
        
        # ノード数を取得
        len_leaf = len(self.qm.leaf_nodes_map)
        len_non_leaf = len(self.qm.non_leaf_nodes_map)
        
        # m_costを初期化（全ノード分）
        m_cost = [0.0] * (len_leaf + len_non_leaf)
        insert_times = insert_query / 1000
        
        # ランダムな更新テーブルを生成（元の実装と同じ）
        update_table = [[""] for _ in range(1000)]
        for i in range(len(update_table)):
            x = random.randint(0, len(table_list) - 1)  # テーブル数に合わせる
            update_table[i][0] = table_list[x]
        
        print(f"  ランダムな更新テーブルを生成: {len(update_table)}件")
        
        # check_m_cost関数を呼び出してメンテナンスコストを計算
        print(f"  メンテナンスコスト計算中...")
        
        self.m_cost = self.check_m_cost(
            m_cost=m_cost,
            table_list=table_list,
            update_table=update_table,
            record_list=record_list,
            search_cost=search_cost,
            insert_cost=insert_cost_alpha,
            table_width=table_width,
            insert_times=insert_times
        )
        
        print(f"  ✓ メンテナンスコスト計算完了")
        print(f"    平均コスト: {sum(self.m_cost) / len(self.m_cost):.4f}")
        print(f"    最大コスト: {max(self.m_cost):.4f}")
        print(f"    最小コスト: {min(self.m_cost):.4f}")
        
        # コストが高いノードトップ5を表示
        node_costs = [(self.node_list[j], self.m_cost[j]) for j in range(self.s_num)]
        node_costs.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\n  トップ5高コストノード:")
        for node_id, cost in node_costs[:5]:
            print(f"    {node_id}: {cost:.4f}")

            """頻度をコストにかける処理を入れる、実験ファイルにこの新しいコストを計算する処理を入れる"""


def create_frequency_weighted_parser(
    settings: Settings,
    frequency_file: str | None = None
) -> FrequencyWeightedParser:
    """頻度重み付けパーサーを作成
    
    Args:
        settings: 設定オブジェクト
        frequency_file: 頻度情報JSONファイルのパス
    
    Returns:
        FrequencyWeightedParser インスタンス
    """
    return FrequencyWeightedParser(settings, frequency_file)
