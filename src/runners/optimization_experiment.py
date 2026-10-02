"""MV 選択最適化実験ランナー (bigsubs / topk-F).

使い方 (CLI):
    python -m src.runners.optimization_experiment \\
        --pkl Output/redbench_freq_v2/qp_class.pkl \\
        --b-max-mb 50

API:
    from src.runners.optimization_experiment import OptimizationExperiment
    exp = OptimizationExperiment(pkl_path="...", b_max_mb=50)
    results = exp.run(use_sampling=True)
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings


# ──────────────────────────────────────────────────────────────────────────────
# データクラス
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AlgorithmResult:
    algorithm: str
    total_utility: float
    num_selected_views: int
    total_storage_mb: float
    execution_time_sec: float
    iterations: Optional[int] = None


@dataclass
class ExperimentResult:
    b_max_mb: int
    sampling_used: bool
    sampling_coverage: Optional[str] = None   # e.g. "289/938"
    bigsubs: Optional[AlgorithmResult] = None
    topkf: Optional[AlgorithmResult] = None


# ──────────────────────────────────────────────────────────────────────────────
# メインクラス
# ──────────────────────────────────────────────────────────────────────────────

class OptimizationExperiment:
    """bigsubs と topk-F を比較する最適化実験クラス.

    Args:
        pkl_path: QueryParser pickle ファイルのパス
        migration_plans_dir: simple_migration_plans.json を保存するディレクトリ
        b_max_mb: ストレージ予算 (MB)
        sampling_query_set: SamplingMigrationCostCalculator に渡すクエリセット名
    """

    def __init__(
        self,
        pkl_path: str | Path,
        migration_plans_dir: str | Path | None = None,
        b_max_mb: int = 50,
        sampling_query_set: str = "job",
    ):
        self.pkl_path = Path(pkl_path)
        self.b_max_mb = b_max_mb
        self.b_max = float(b_max_mb * 1024 * 1024)
        self.sampling_query_set = sampling_query_set

        # migration plans のデフォルト保存先
        if migration_plans_dir is None:
            migration_plans_dir = (
                PROJECT_ROOT
                / "experiments/small_test_ver2/04_migration"
                / sampling_query_set
            )
        self.migration_plans_dir = Path(migration_plans_dir)
        self.migration_plans_file = self.migration_plans_dir / "simple_migration_plans.json"

        self.qp = None

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: pkl 読み込み
    # ──────────────────────────────────────────────────────────────────────────

    def load_qp(self):
        print(f"[1] pkl 読み込み: {self.pkl_path}")
        with open(self.pkl_path, "rb") as f:
            self.qp = pickle.load(f)
        print(f"    nodes={self.qp.s_num}, queries={len(self.qp.u_ij)}")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2: 全ノードの CREATE MV SQL → simple_migration_plans.json
    # ──────────────────────────────────────────────────────────────────────────

    def generate_migration_plans(self):
        if self.migration_plans_file.exists():
            print(f"[2] simple_migration_plans.json を再利用: {self.migration_plans_file}")
            return

        print("[2] simple_migration_plans.json を生成...")
        from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator

        self.migration_plans_dir.mkdir(parents=True, exist_ok=True)
        generator = EnhancedMVGenerator(self.qp.qm, selected_mvs=set(self.qp.node_list))

        plans = {}
        failed = 0
        for node_id in self.qp.node_list:
            try:
                sql = generator.generate_mv_sql(node_id)
                plans[node_id] = {"[]": sql}
            except Exception as e:
                plans[node_id] = {"[]": f"-- SQL generation failed: {e}"}
                failed += 1

        with open(self.migration_plans_file, "w", encoding="utf-8") as f:
            json.dump(plans, f, indent=2, ensure_ascii=False)
        print(f"    保存: {len(plans)} nodes, {failed} failures")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3: サンプリングで b_j を推定
    # ──────────────────────────────────────────────────────────────────────────

    def run_sampling(self) -> str:
        """サンプリングを実行し、qp.b_j と qm.subquery_sizes を更新する。

        Returns:
            カバレッジ文字列 e.g. "289/938"
        """
        print("[3] サンプリングで b_j を推定...")
        from experiments.small_test_ver2.migration.sampling_migration_cost_calculator_edbt import (
            SamplingMigrationCostCalculator,
        )

        t0 = time.time()
        settings = Settings()
        calculator = SamplingMigrationCostCalculator(
            settings, query_set=self.sampling_query_set
        )
        sampling_costs = calculator.calculate_all_costs(use_parallel=False)

        updated = 0
        for j, node_id in enumerate(self.qp.node_list):
            if node_id not in sampling_costs:
                continue
            full_build = sampling_costs[node_id].get("[]", {})
            if not isinstance(full_build, dict):
                continue
            size = full_build.get("size", 0)
            if size > 0:
                self.qp.b_j[j] = float(size)
                self.qp.qm.subquery_sizes[node_id] = float(size)
                updated += 1

        elapsed = time.time() - t0
        coverage = f"{updated}/{len(self.qp.node_list)}"
        print(f"    カバレッジ: {coverage}, 実行時間: {elapsed:.1f}s")
        return coverage

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4: 頻度重み付き u_ij
    # ──────────────────────────────────────────────────────────────────────────

    def _make_weighted_u_ij(self):
        q_num = len(self.qp.u_ij)
        freq = [float(self.qp.query_frequencies.get(i, 1)) for i in range(q_num)]
        weighted = [
            [self.qp.u_ij[i][j] * freq[i] for j in range(len(self.qp.node_list))]
            for i in range(q_num)
        ]
        total = sum(v for row in weighted for v in row if v > 0)
        print(f"[4] 頻度重み付き u_ij: nonzero={sum(1 for row in weighted for v in row if v>0)}, total={total:.2f}")
        return weighted

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5: bigsubs
    # ──────────────────────────────────────────────────────────────────────────

    def _run_bigsubs(self, weighted_u_ij, b_j, m_cost) -> AlgorithmResult:
        from src.optimization.bigsubs import BigSubsOptimizer

        s_num = len(self.qp.node_list)
        U_j_max = [
            sum(weighted_u_ij[i][j] for i in range(len(weighted_u_ij)))
            for j in range(s_num)
        ]
        optimizer = BigSubsOptimizer(
            qm=self.qp.qm,
            s_num=s_num,
            m_cost=m_cost,
            node_list=self.qp.node_list,
            B_max=self.b_max,
            b_j=b_j,
            u_ij=weighted_u_ij,
            X=self.qp.X,
            q_s_list=self.qp.q_s_list,
            settings=Settings(),
            U_j_max=U_j_max,
            U_max=sum(U_j_max),
            y_ij=getattr(self.qp, "y_ij", [[0] * s_num for _ in range(len(weighted_u_ij))]),
        )
        t0 = time.time()
        result = optimizer.optimize(iter_max=200)
        elapsed = time.time() - t0
        return AlgorithmResult(
            algorithm="bigsubs",
            total_utility=result.total_utility,
            num_selected_views=len(result.selected_views),
            total_storage_mb=result.total_storage / 1024 / 1024,
            execution_time_sec=elapsed,
            iterations=(result.metadata or {}).get("iterations"),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step 6: topk-F (FrequencyOptimizer)
    # ──────────────────────────────────────────────────────────────────────────

    def _run_topkf(self, weighted_u_ij, b_j, m_cost) -> AlgorithmResult:
        from src.optimization.frequency import FrequencyOptimizer

        optimizer = FrequencyOptimizer(
            qm=self.qp.qm,
            s_num=len(self.qp.node_list),
            m_cost=m_cost,
            node_list=self.qp.node_list,
            B_max=self.b_max,
            b_j=b_j,
            u_ij=weighted_u_ij,
            X=self.qp.X,
            q_s_list=self.qp.q_s_list,
            settings=Settings(),
            position_node_id=self.qp.position_node_id,
            deeplist=self.qp.deeplist,
            query_frequencies=self.qp.query_frequencies,
        )
        t0 = time.time()
        result = optimizer.optimize()
        elapsed = time.time() - t0
        return AlgorithmResult(
            algorithm="topkf",
            total_utility=result.total_utility,
            num_selected_views=len(result.selected_views),
            total_storage_mb=result.total_storage / 1024 / 1024,
            execution_time_sec=elapsed,
            iterations=(result.metadata or {}).get("iterations"),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # メイン実行
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, use_sampling: bool = True) -> ExperimentResult:
        """実験を実行して結果を返す。

        Args:
            use_sampling: True のとき sampling で b_j を改善する
        """
        self.load_qp()
        self.generate_migration_plans()

        sampling_coverage = None
        if use_sampling:
            try:
                sampling_coverage = self.run_sampling()
            except Exception as e:
                print(f"    sampling 失敗: {e} → 既存 b_j を使用")

        weighted_u_ij = self._make_weighted_u_ij()
        b_j = list(self.qp.b_j)
        m_cost = list(self.qp.m_cost)

        print(f"\n    B_max={self.b_max_mb}MB, nodes={len(self.qp.node_list)}, "
              f"queries={len(weighted_u_ij)}, m_cost_nonzero={sum(1 for v in m_cost if v > 0)}")

        print("\n[5] bigsubs 最適化...")
        bigsubs_result = None
        try:
            bigsubs_result = self._run_bigsubs(weighted_u_ij, b_j, m_cost)
        except Exception as e:
            print(f"    bigsubs 失敗: {e}")

        print("\n[6] topk-F (FrequencyOptimizer) 最適化...")
        topkf_result = None
        try:
            topkf_result = self._run_topkf(weighted_u_ij, b_j, m_cost)
        except Exception as e:
            print(f"    topk-F 失敗: {e}")

        return ExperimentResult(
            b_max_mb=self.b_max_mb,
            sampling_used=use_sampling and sampling_coverage is not None,
            sampling_coverage=sampling_coverage,
            bigsubs=bigsubs_result,
            topkf=topkf_result,
        )

    @staticmethod
    def print_results(r: ExperimentResult):
        print("\n" + "=" * 65)
        print(f"結果比較  (B_max={r.b_max_mb}MB, sampling={'あり' if r.sampling_used else 'なし'})")
        if r.sampling_coverage:
            print(f"  sampling カバレッジ: {r.sampling_coverage}")
        print("=" * 65)
        print(f"{'指標':<35} {'bigsubs':>13} {'topk-F':>13}")
        print("-" * 65)

        def _fmt(v, fmt=".2f"):
            return f"{v:{fmt}}" if v is not None else "  (失敗)"

        bs, fr = r.bigsubs, r.topkf
        print(f"{'総利得 (Σ u_ij − Σ m_j)':<35} {_fmt(bs.total_utility if bs else None):>13} {_fmt(fr.total_utility if fr else None):>13}")
        print(f"{'選択 MV 数':<35} {_fmt(bs.num_selected_views if bs else None, 'd'):>13} {_fmt(fr.num_selected_views if fr else None, 'd'):>13}")
        print(f"{'使用ストレージ (MB)':<35} {_fmt(bs.total_storage_mb if bs else None):>13} {_fmt(fr.total_storage_mb if fr else None):>13}")
        print(f"{'最適化時間 (秒)':<35} {_fmt(bs.execution_time_sec if bs else None):>13} {_fmt(fr.execution_time_sec if fr else None):>13}")
        if bs and bs.iterations is not None:
            print(f"{'収束反復回数 (bigsubs)':<35} {bs.iterations:>13}")
        if fr and fr.iterations is not None:
            print(f"{'収束反復回数 (topk-F)':<35} {fr.iterations:>13}")
        print("=" * 65)


# ──────────────────────────────────────────────────────────────────────────────
# CLI エントリポイント
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="bigsubs vs topk-F 最適化実験")
    parser.add_argument(
        "--pkl",
        default=str(PROJECT_ROOT / "Output/redbench_freq_v2/qp_class.pkl"),
        help="QueryParser pickle ファイルのパス",
    )
    parser.add_argument("--b-max-mb", type=int, default=50, help="ストレージ予算 (MB)")
    parser.add_argument("--query-set", default="job", help="サンプリング用クエリセット名")
    parser.add_argument("--skip-sampling", action="store_true", help="サンプリングをスキップ")
    parser.add_argument("--output", default=None, help="結果 JSON の保存先 (省略可)")
    args = parser.parse_args()

    exp = OptimizationExperiment(
        pkl_path=args.pkl,
        b_max_mb=args.b_max_mb,
        sampling_query_set=args.query_set,
    )
    results = exp.run(use_sampling=not args.skip_sampling)
    OptimizationExperiment.print_results(results)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)

        def _to_dict(r):
            d = asdict(r)
            return d

        with open(out, "w", encoding="utf-8") as f:
            json.dump(_to_dict(results), f, indent=2, ensure_ascii=False)
        print(f"\n結果を保存: {out}")


if __name__ == "__main__":
    main()
