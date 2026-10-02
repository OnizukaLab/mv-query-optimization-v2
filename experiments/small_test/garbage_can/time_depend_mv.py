"""時系列マテリアライズドビュー管理"""

from dataclasses import dataclass, field
from typing import Dict, List, Set
from enum import Enum


class MVStatus(Enum):
    """MV状態"""
    ACTIVE = "active"
    CREATING = "creating"
    DROPPING = "dropping"


@dataclass
class MVSnapshot:
    """特定タイムステップでのMV状態"""
    timestep: int
    active_mvs: Set[str] = field(default_factory=set)
    
    def total_storage_mb(self) -> float:
        """合計ストレージ（MB）"""
        # 簡易版: 各MVを1MBと仮定
        return len(self.active_mvs) * 1.0


@dataclass
class MVTransition:
    """MVの遷移"""
    from_timestep: int
    to_timestep: int
    mvs_to_create: Set[str] = field(default_factory=set)
    mvs_to_drop: Set[str] = field(default_factory=set)
    
    @property
    def has_changes(self) -> bool:
        """変更があるか"""
        return bool(self.mvs_to_create or self.mvs_to_drop)


@dataclass
class TimeDependMVPlan:
    """時系列MV計画"""
    workload_timesteps: int
    snapshots: List[MVSnapshot] = field(default_factory=list)
    transitions: List[MVTransition] = field(default_factory=list)
    
    def add_snapshot(self, snapshot: MVSnapshot):
        """スナップショット追加"""
        self.snapshots.append(snapshot)
    
    def add_transition(self, transition: MVTransition):
        """遷移追加"""
        if transition.has_changes:
            self.transitions.append(transition)
    
    def get_active_mvs(self, timestep: int) -> Set[str]:
        """指定タイムステップのアクティブMV取得"""
        if 0 <= timestep < len(self.snapshots):
            return self.snapshots[timestep].active_mvs
        return set()
    
    def total_transitions(self) -> int:
        """総遷移回数"""
        return len(self.transitions)