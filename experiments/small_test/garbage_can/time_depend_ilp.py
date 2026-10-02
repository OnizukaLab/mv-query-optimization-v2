"""時系列ILP最適化"""

import gurobipy as gp
from gurobipy import GRB
from typing import Dict, List, Set, Tuple
import numpy as np

from src.core.time_depend_workload import TimeDependWorkload
from src.core.time_depend_mv import TimeDependMVPlan, MVSnapshot, MVTransition
from src.core.query_manager import QueryManager


class TimeDependILP:
    """時系列MV選択ILP"""
    
    def __init__(
        self,
        workload: TimeDependWorkload,
        query_manager: QueryManager,
        storage_limit_per_timestep_mb: float = 50.0,
        creation_cost_coeff: float = 1e-6,
        migration_cost_coeff: float = 1e-10
    ):
        """
        Args:
            workload: 時系列ワークロード
            query_manager: クエリマネージャー
            storage_limit_per_timestep_mb: タイムステップごとのストレージ上限（MB）
            creation_cost_coeff: MV作成コスト係数
            migration_cost_coeff: マイグレーションコスト係数
        """
        self.workload = workload
        self.qm = query_manager
        self.storage_limit = storage_limit_per_timestep_mb
        self.creation_coeff = creation_cost_coeff
        self.migration_coeff = migration_cost_coeff
        
        self.model = gp.Model("TimeDependMV")
        self.model.setParam('OutputFlag', 0)  # ログ抑制
        
        # 決定変数
        self.y = {}  # y[mv, t]: タイムステップtでMVが存在するか
        self.x = {}  # x[query, mv, t]: タイムステップtでクエリがMVを使用するか
    
    def build_model(self):
        """ILPモデル構築"""
        T = self.workload.num_timesteps
        
        # 候補MV取得
        candidate_mvs = self._get_candidate_mvs()
        
        # 決定変数定義
        self._define_variables(candidate_mvs, T)
        
        # 制約条件
        self._add_constraints(candidate_mvs, T)
        
        # 目的関数
        self._set_objective(candidate_mvs, T)
    
    def _get_candidate_mvs(self) -> List[str]:
        """候補MV取得"""
        mvs = []
        
        # LeafノードMV
        for leaf_id in self.qm.leaf_nodes_map:
            mvs.append(leaf_id)
        
        # Non-leafノードMV
        for non_leaf_id in self.qm.non_leaf_nodes_map:
            mvs.append(non_leaf_id)
        
        return mvs
    
    def _define_variables(self, mvs: List[str], T: int):
        """決定変数定義"""
        # y[mv, t]: MVの存在
        for mv in mvs:
            for t in range(T):
                self.y[mv, t] = self.model.addVar(
                    vtype=GRB.BINARY,
                    name=f"y_{mv}_{t}"
                )
        
        # x[query, mv, t]: MVの使用
        for query_id in self.workload.query_frequencies:
            for mv in mvs:
                for t in range(T):
                    self.x[query_id, mv, t] = self.model.addVar(
                        vtype=GRB.BINARY,
                        name=f"x_{query_id}_{mv}_{t}"
                    )
        
        self.model.update()
    
    def _add_constraints(self, mvs: List[str], T: int):
        """制約条件追加"""
        
        # 1. MVが存在する時のみ使用可能
        for query_id in self.workload.query_frequencies:
            for mv in mvs:
                for t in range(T):
                    self.model.addConstr(
                        self.x[query_id, mv, t] <= self.y[mv, t],
                        name=f"use_if_exists_{query_id}_{mv}_{t}"
                    )
        
        # 2. 各クエリは最大1つのMVを使用（簡易版）
        for query_id in self.workload.query_frequencies:
            for t in range(T):
                self.model.addConstr(
                    gp.quicksum(self.x[query_id, mv, t] for mv in mvs) <= 1,
                    name=f"single_mv_{query_id}_{t}"
                )
        
        # 3. ストレージ制約
        for t in range(T):
            storage_expr = gp.quicksum(
                self.y[mv, t] * self._get_mv_size_mb(mv)
                for mv in mvs
            )
            self.model.addConstr(
                storage_expr <= self.storage_limit,
                name=f"storage_{t}"
            )
    
    def _set_objective(self, mvs: List[str], T: int):
        """目的関数設定"""
        timestep_durations = self.workload.timestep_durations
        
        # クエリ実行コスト最小化
        query_cost = gp.quicksum(
            self.workload.get_frequency_at(query_id, t) *
            timestep_durations[t] *
            self._get_query_cost(query_id, mv, t) *
            (1 - self.x[query_id, mv, t])  # MVを使わない場合のコスト
            for query_id in self.workload.query_frequencies
            for mv in mvs
            for t in range(T)
        )
        
        # マイグレーションコスト（MVの作成・削除）
        migration_cost = gp.quicksum(
            self.migration_coeff * self.y[mv, t]
            for mv in mvs
            for t in range(T)
        )
        
        # 総コスト最小化
        self.model.setObjective(
            query_cost + migration_cost,
            GRB.MINIMIZE
        )
    
    def optimize(self) -> TimeDependMVPlan:
        """最適化実行"""
        self.model.optimize()
        
        if self.model.status != GRB.OPTIMAL:
            raise RuntimeError(f"Optimization failed: status={self.model.status}")
        
        return self._extract_solution()
    
    def _extract_solution(self) -> TimeDependMVPlan:
        """解の抽出"""
        T = self.workload.num_timesteps
        plan = TimeDependMVPlan(workload_timesteps=T)
        
        # 各タイムステップのスナップショット
        for t in range(T):
            active_mvs = set()
            
            for mv in self.y.keys():
                if isinstance(mv, tuple) and mv[1] == t:
                    mv_id = mv[0]
                    if self.y[mv].X > 0.5:
                        active_mvs.add(mv_id)
            
            plan.add_snapshot(MVSnapshot(timestep=t, active_mvs=active_mvs))
        
        # 遷移情報（簡易版）
        for t in range(T - 1):
            prev_mvs = plan.snapshots[t].active_mvs
            next_mvs = plan.snapshots[t + 1].active_mvs
            
            mvs_to_create = next_mvs - prev_mvs
            mvs_to_drop = prev_mvs - next_mvs
            
            plan.add_transition(MVTransition(
                from_timestep=t,
                to_timestep=t + 1,
                mvs_to_create=mvs_to_create,
                mvs_to_drop=mvs_to_drop
            ))
        
        return plan
    
    def _get_mv_size_mb(self, mv_id: str) -> float:
        """MVサイズ取得（MB）（仮実装）"""
        return 1.0  # 1MB
    
    def _get_query_cost(self, query_id: int, mv_id: str, timestep: int) -> float:
        """クエリコスト取得（仮実装）"""
        # 実際にはEXPLAIN ANALYZEベース
        return 1.0