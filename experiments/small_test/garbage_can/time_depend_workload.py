"""時系列ワークロードモデル"""

from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime


@dataclass
class TimeStep:
    """単一タイムステップの情報"""
    timestep_id: int
    start_time: datetime
    end_time: datetime
    duration_hours: float  # 期間（時間）
    
    @property
    def duration_seconds(self) -> float:
        return self.duration_hours * 3600


@dataclass
class QueryFrequency:
    """クエリの時系列頻度"""
    query_id: int
    frequencies: List[float]  # タイムステップごとの実行頻度（回数/時間）
    
    def get_frequency(self, timestep: int) -> float:
        """指定タイムステップの頻度取得"""
        if 0 <= timestep < len(self.frequencies):
            return self.frequencies[timestep]
        return 0.0
    
    def total_executions(self, timestep_durations: List[float]) -> float:
        """全期間の総実行回数"""
        total = 0.0
        for t, freq in enumerate(self.frequencies):
            if t < len(timestep_durations):
                total += freq * timestep_durations[t]
        return total


@dataclass
class TimeDependWorkload:
    """時系列ワークロード"""
    timesteps: List[TimeStep] = field(default_factory=list)
    query_frequencies: Dict[int, QueryFrequency] = field(default_factory=dict)
    
    def add_timestep(self, timestep: TimeStep):
        """タイムステップ追加"""
        self.timesteps.append(timestep)
    
    def add_query_frequency(self, query_id: int, frequencies: List[float]):
        """クエリ頻度追加"""
        if len(frequencies) != len(self.timesteps):
            raise ValueError(
                f"Frequency length {len(frequencies)} != timesteps {len(self.timesteps)}"
            )
        self.query_frequencies[query_id] = QueryFrequency(query_id, frequencies)
    
    def get_frequency_at(self, query_id: int, timestep: int) -> float:
        """指定クエリ・タイムステップの頻度"""
        if query_id not in self.query_frequencies:
            return 0.0
        return self.query_frequencies[query_id].get_frequency(timestep)
    
    @property
    def num_timesteps(self) -> int:
        """タイムステップ数"""
        return len(self.timesteps)
    
    @property
    def timestep_durations(self) -> List[float]:
        """各タイムステップの期間（秒）"""
        return [ts.duration_seconds for ts in self.timesteps]
    
    @classmethod
    def create_simple_2step_workload(cls) -> 'TimeDependWorkload':
        """2タイムステップのシンプルワークロード作成"""
        workload = cls()
        
        # タイムステップ1: 2024-01-01 00:00 - 12:00
        workload.add_timestep(TimeStep(
            timestep_id=0,
            start_time=datetime(2024, 1, 1, 0, 0),
            end_time=datetime(2024, 1, 1, 12, 0),
            duration_hours=12.0
        ))
        
        # タイムステップ2: 2024-01-01 12:00 - 24:00
        workload.add_timestep(TimeStep(
            timestep_id=1,
            start_time=datetime(2024, 1, 1, 12, 0),
            end_time=datetime(2024, 1, 1, 23, 59),
            duration_hours=12.0
        ))
        
        return workload


def create_small_test_workload() -> TimeDependWorkload:
    """small_test用ワークロード作成"""
    workload = TimeDependWorkload.create_simple_2step_workload()
    
    # small_testのクエリを想定（適当な頻度設定）
    # 時刻1: クエリ1が頻繁、クエリ2が少ない
    # 時刻2: クエリ2が頻繁、クエリ1が少ない
    
    workload.add_query_frequency(1, [10.0, 2.0])   # クエリ1: 高→低
    workload.add_query_frequency(2, [1.0, 15.0])   # クエリ2: 低→高
    workload.add_query_frequency(3, [5.0, 5.0])    # クエリ3: 一定
    
    return workload