"""時刻依存型頻度重み付けQueryParserラッパー

複数の時刻で異なるクエリ頻度を設定し、
各時刻ごとに最適化を実行します。
"""

import json
from pathlib import Path
from typing import Dict, List, Any
import copy

from src.core.query_parser import QueryParser
from config.settings import Settings
from experiments.small_test.frequency_weighted_parser import FrequencyWeightedParser


class TimeDependentFrequencyParser:
    """時刻依存型頻度重み付けパーサー
    
    複数のタイムステップでクエリ頻度が変化する場合に対応。
    各時刻ごとに異なる頻度で重み付けされた利得を計算します。
    """
    
    def __init__(
        self,
        settings: Settings | None = None,
        time_frequency_file: str | None = None
    ):
        """初期化
        
        Args:
            settings: 設定オブジェクト
            time_frequency_file: 時刻依存型頻度情報JSONファイルのパス
        """
        self.settings = settings or Settings()
        self.time_frequency_file = time_frequency_file
        self.timesteps: List[Dict[str, Any]] = []
        self.parsers: Dict[str, FrequencyWeightedParser] = {}
        
        # 時刻依存型頻度情報を読み込み
        if time_frequency_file and Path(time_frequency_file).exists():
            self._load_time_frequencies(time_frequency_file)
    
    def _load_time_frequencies(self, time_frequency_file: str):
        """時刻依存型頻度情報をファイルから読み込み"""
        with open(time_frequency_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.timesteps = data.get('timesteps', [])
        
        print(f"\n[TimeDependentFrequency] 時刻依存型頻度情報を読み込み")
        print(f"  ファイル: {time_frequency_file}")
        print(f"  タイムステップ数: {len(self.timesteps)}")
        
        for i, timestep in enumerate(self.timesteps):
            time_id = timestep['time_id']
            label = timestep['label']
            duration = timestep['duration_hours']
            freqs = timestep['frequencies']
            
            print(f"\n  [{i+1}] {time_id} - {label} ({duration}時間)")
            total_freq = sum(freqs.values())
            print(f"      総実行回数: {total_freq}")
            for query, freq in freqs.items():
                print(f"      {query}: {freq}回")
    
    def parse_for_all_timesteps(
        self,
        q_num: int,
        path: str,
        insert_query: int,
        files: List[str]
    ):
        """全タイムステップでパースと頻度適用を実行
        
        Args:
            q_num: クエリ数
            path: クエリディレクトリパス
            insert_query: INSERT回数
            files: クエリファイルのリスト
        """
        print(f"\n[TimeDependentFrequency] 全タイムステップでパース開始")
        
        for i, timestep in enumerate(self.timesteps):
            time_id = timestep['time_id']
            label = timestep['label']
            frequencies = timestep['frequencies']
            
            print(f"\n{'='*70}")
            print(f"タイムステップ {i+1}/{len(self.timesteps)}: {time_id}")
            print(f"  {label}")
            print(f"{'='*70}")
            
            # このタイムステップ用のパーサーを作成
            parser = FrequencyWeightedParser(self.settings)
            parser.query_frequencies = frequencies
            
            # クエリをパース
            print(f"  → クエリをパース中...")
            parser.query_parse(q_num, path, insert_query)
            
            # 頻度の重みを適用
            print(f"  → 頻度の重みを適用中...")
            parser.apply_frequency_weights(files)

            #メンテナンスコストを再計算
            parser.calculate_maintenance_costs(insert_query)
            
            # パーサーを保存
            self.parsers[time_id] = parser
            
            print(f"  ✓ {time_id} のパース完了")
            print(f"    総利得: {parser.U_max:.2f}")
            print(f"    ノード数: {parser.s_num}")
    
    def get_parser(self, time_id: str) -> FrequencyWeightedParser | None:
        """特定の時刻のパーサーを取得
        
        Args:
            time_id: タイムステップID
            
        Returns:
            FrequencyWeightedParser インスタンス
        """
        return self.parsers.get(time_id)
    
    def get_all_time_ids(self) -> List[str]:
        """全タイムステップIDを取得
        
        Returns:
            タイムステップIDのリスト
        """
        return [ts['time_id'] for ts in self.timesteps]
    
    def get_timestep_info(self, time_id: str) -> Dict[str, Any] | None:
        """タイムステップ情報を取得
        
        Args:
            time_id: タイムステップID
            
        Returns:
            タイムステップ情報の辞書
        """
        for ts in self.timesteps:
            if ts['time_id'] == time_id:
                return ts
        return None
    
    def save_parsers(self, output_dir: Path):
        """全パーサーをファイルに保存
        
        Args:
            output_dir: 出力ディレクトリ
        """
        import pickle
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n[TimeDependentFrequency] パーサーを保存中...")
        
        for time_id, parser in self.parsers.items():
            output_file = output_dir / f"qp_{time_id}.pkl"
            with open(output_file, 'wb') as f:
                pickle.dump(parser, f)
            print(f"  ✓ {output_file}")
        
        # メタデータも保存
        metadata = {
            'timesteps': self.timesteps,
            'time_ids': list(self.parsers.keys())
        }
        metadata_file = output_dir / "time_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {metadata_file}")


def create_time_dependent_parser(
    settings: Settings,
    time_frequency_file: str | None = None
) -> TimeDependentFrequencyParser:
    """時刻依存型パーサーを作成
    
    Args:
        settings: 設定オブジェクト
        time_frequency_file: 時刻依存型頻度情報JSONファイルのパス
    
    Returns:
        TimeDependentFrequencyParser インスタンス
    """
    return TimeDependentFrequencyParser(settings, time_frequency_file)
