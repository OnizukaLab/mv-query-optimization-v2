"""pg_ivm を使った実測 m_j 推定.

IMMV (Incrementally Maintainable Materialized View) を 1% サンプル上に作成し、
更新オペレーションを実行して IVM トリガーの実行時間を計測する。

既存の theoretical コスト (calculate_maintenance_cost_v2) はそのまま保持し、
本クラスの結果は比較・上書きに使う。

使い方:
    from src.maintenance import IVMCostEstimator
    estimator = IVMCostEstimator(settings)
    actual_m_cost = estimator.estimate_for_qp(qp, top_k=200)
    # qp.m_cost は変更しない; 呼び出し元が判断して上書きする
"""
from __future__ import annotations

import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psycopg2

from .update_workload import UpdateWorkload, UpdateOperation, DEFAULT_UPDATE_FREQUENCY
from .mv_sql_expander import expand_mv_sql


SAMPLING_RATE = 0.01          # サンプルテーブルのサンプリング率 (1%)
SAMPLE_PREFIX = "_ivm_s_"     # サンプルテーブル / IMMV の名前プレフィックス
WARMUP_TRIALS = 2             # ウォームアップ (捨てる試行回数)


@dataclass
class IVMProfile:
    """1ノードの IVM 計測結果."""
    node_id: str
    table_name: str               # 更新対象のベーステーブル
    immv_name: str                # 作成した IMMV 名
    sample_size: int              # サンプル IMMV の行数
    full_size: int                # 本番テーブルの行数
    median_trigger_sec: float     # サンプルサイズでの中央値 IVM コスト
    scaled_m_j: float             # full_size にスケールアップした m_j (秒)
    n_trials: int
    error: Optional[str] = None


class IVMCostEstimator:
    """pg_ivm を使って実際の差分更新コストを計測するクラス.

    計測フロー (1ノード × 1テーブル):
      1. サンプルテーブル (1%) を作成
      2. pgivm.create_immv() でサンプル IMMV を作成
      3. BEGIN → UPDATE on sample table → 時間計測 → ROLLBACK を n_trials 回繰り返す
         (ROLLBACK するためサンプルデータも変更されない)
      4. 中央値 × (full_size / sample_size) × update_frequency でスケールアップ
      5. 使用後サンプルテーブルと IMMV を DROP

    注意:
      - 全既存メソッド (calculate_maintenance_cost_v2 等) はそのまま残る
      - このクラスは追加の計測手段として提供する
    """

    def __init__(self, settings, n_trials: int = 10):
        self.settings = settings
        self.n_trials = n_trials
        self._plans_cache: Optional[dict] = None

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    # IMDB の全既知テーブル (サンプル作成対象)
    IMDB_TABLES = list(DEFAULT_UPDATE_FREQUENCY.keys()) + [
        "movie_link", "link_type", "company_type", "info_type", "role_type",
        "kind_type", "aka_name", "aka_title", "complete_cast",
        "movie_info_idx", "comp_cast_type",
    ]

    def estimate_for_qp(
        self,
        qp,
        top_k: int = 200,
        update_frequency: dict[str, float] | None = None,
    ) -> list[float]:
        """qp (QueryParser) の上位 top_k ノードの実測 m_j を返す。

        サンプルテーブルは全テーブル分を一括作成し、各ノードで再利用する。

        Returns:
            actual_m_cost: len(qp.node_list) の float リスト。
                           計測できなかったノードは qp.m_cost[j] (理論値) をそのまま返す。
        """
        upd_freq = update_frequency or DEFAULT_UPDATE_FREQUENCY
        actual_m_cost = list(qp.m_cost)

        # u_ij 合計上位ノードを優先
        node_utility = []
        for j, node_id in enumerate(qp.node_list):
            total_u = sum(qp.u_ij[i][j] for i in range(len(qp.u_ij)))
            node_utility.append((j, node_id, total_u))
        node_utility.sort(key=lambda x: -x[2])
        target_nodes = [(j, nid) for j, nid, _ in node_utility[:top_k]]

        print(f"[IVMCostEstimator] {len(target_nodes)} ノードを計測対象に選択 (top_k={top_k})")

        plans = self._load_plans()

        conn = self._connect()
        try:
            # 全テーブルのサンプルを一括作成 (IMMV 作成前に必要)
            print("  [1/3] サンプルテーブルを一括作成中...")
            table_mapping = self._create_all_sample_tables(conn)
            print(f"        {len(table_mapping)} テーブルのサンプル作成完了")

            print(f"  [2/3] IMMV 作成 + 計測 ({len(target_nodes)} ノード)...")
            ok_count = 0
            for idx, (j, node_id) in enumerate(target_nodes):
                table_name = self._get_primary_table(node_id, qp)
                if table_name is None or table_name not in table_mapping:
                    continue

                # CTE 展開: non-leaf ノードの依存 MV を WITH 句でフラット化
                expanded_body = expand_mv_sql(node_id, plans)
                if expanded_body is None:
                    continue

                if (idx + 1) % 50 == 0:
                    print(f"    [{idx+1}/{len(target_nodes)}] {node_id} ({table_name}) ok={ok_count}")

                profile = self._measure_node_with_samples(
                    conn=conn,
                    node_id=node_id,
                    table_name=table_name,
                    expanded_body=expanded_body,
                    table_mapping=table_mapping,
                    full_size=self._get_full_size(conn, table_name),
                    update_frequency=upd_freq.get(table_name, 1.0),
                )
                if profile and profile.error is None:
                    actual_m_cost[j] = profile.scaled_m_j
                    ok_count += 1

            print(f"  [3/3] サンプルテーブルをクリーンアップ...")
            self._drop_all_sample_tables(conn, table_mapping)
        finally:
            conn.close()

        # ── スケール正規化 ──────────────────────────────────────────────
        # u_ij と m_j(理論値) は同じ EXPLAIN コスト単位。
        # IVM 実測値は「秒 × 100 × update_frequency」であり別スケール。
        # 計測済みノードの 理論値/IVM比率 を係数として IVM 値に乗じることで
        # 理論値と同じスケールに揃え、最適化の歪みを防ぐ。
        #
        # [重要] サイズ別キャリブレーション:
        # bigsubs の u_ij モデルは「MV がクエリ位置をカバーするか否か」の二値評価であり、
        # 大型 MV と小型 MV が同一クエリ位置をカバーする場合でも利得値 (u_ij) は同一になる。
        # しかし実際のクエリ実行速度は大型 MV の方が高い（事前計算済みの結合結果により高速）。
        # そこで:
        #   - 大型 MV (b_j >= LARGE_MV_THRESHOLD): min(calibrated, theoretical) を適用
        #     IVM が安価と測定した大型 MV を優先選択できるようにする
        #   - 小型 MV (b_j < LARGE_MV_THRESHOLD): 理論値 m_j を維持
        #     小型 MV の m_j を過度に下げると、大型 MV の選択機会を奪うため
        LARGE_MV_THRESHOLD_BYTES = 1 * 1024 * 1024  # 1 MB
        ivm_vals   = [(j, actual_m_cost[j]) for j in range(len(qp.node_list))
                      if actual_m_cost[j] != qp.m_cost[j]]
        if ivm_vals:
            theo_sum = sum(qp.m_cost[j] for j, _ in ivm_vals)
            ivm_sum  = sum(v for _, v in ivm_vals)
            scale_factor = (theo_sum / ivm_sum) if ivm_sum > 0 else 1.0
            clamped = restored = 0
            for j, _ in ivm_vals:
                b_j = qp.b_j[j] if j < len(qp.b_j) else 0
                if b_j >= LARGE_MV_THRESHOLD_BYTES:
                    # 大型 MV: IVM 安価な場合は lower m_j を採用
                    calibrated = actual_m_cost[j] * scale_factor
                    actual_m_cost[j] = min(calibrated, qp.m_cost[j])
                    if calibrated > qp.m_cost[j]:
                        clamped += 1
                else:
                    # 小型 MV: 理論値を維持（小型 MV が大型 MV の選択機会を奪わないように）
                    actual_m_cost[j] = qp.m_cost[j]
                    restored += 1
            print(f"  スケール正規化係数: {scale_factor:.4f} "
                  f"(理論平均={theo_sum/len(ivm_vals):.1f}, "
                  f"IVM平均={ivm_sum/len(ivm_vals):.4f}, "
                  f"大型MV_クランプ={clamped}, 小型MV_理論値復元={restored})")

        measured = sum(
            1 for j in range(len(qp.node_list))
            if actual_m_cost[j] != qp.m_cost[j]
        )
        print(f"[IVMCostEstimator] 完了: 実測={measured}, 理論値fallback={len(qp.node_list)-measured}")
        return actual_m_cost

    def measure_single(
        self,
        node_id: str,
        table_name: str,
        update_frequency: float = 1.0,
    ) -> IVMProfile:
        """単一ノードの IVM コストを計測する (デバッグ・単体テスト用)."""
        plans = self._load_plans()
        expanded_body = expand_mv_sql(node_id, plans)
        if expanded_body is None:
            return IVMProfile(node_id, table_name, "", 0, 0, 0.0, 0.0, 0,
                              error="CTE expansion failed")
        conn = self._connect()
        try:
            table_mapping = self._create_all_sample_tables(conn)
            full_size = self._get_full_size(conn, table_name)
            result = self._measure_node_with_samples(
                conn, node_id, table_name, expanded_body,
                table_mapping, full_size, update_frequency
            )
            self._drop_all_sample_tables(conn, table_mapping)
            return result
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────
    # Internal: サンプルテーブル一括管理 & IMMV 計測
    # ──────────────────────────────────────────────────────────────

    def _create_all_sample_tables(self, conn) -> dict[str, str]:
        """IMDB テーブル全体のサンプルを一括作成する。
        Returns: {orig_table_name: sample_table_name}
        """
        mapping = {}
        with conn.cursor() as cur:
            # 存在するテーブルのみ対象
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
            existing = {r[0] for r in cur.fetchall()}

        for tbl in self.IMDB_TABLES:
            if tbl not in existing:
                continue
            sample = SAMPLE_PREFIX + tbl
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {sample} CASCADE")
                    cur.execute(
                        f"CREATE UNLOGGED TABLE {sample} AS "
                        f"SELECT * FROM {tbl} TABLESAMPLE BERNOULLI({SAMPLING_RATE * 100})"
                    )
                conn.commit()
                mapping[tbl] = sample
            except Exception as e:
                conn.rollback()
        return mapping

    def _drop_all_sample_tables(self, conn, table_mapping: dict[str, str]):
        """一括作成したサンプルテーブルを削除する。"""
        for sample in table_mapping.values():
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {sample} CASCADE")
                conn.commit()
            except Exception:
                conn.rollback()

    def _measure_node_with_samples(
        self,
        conn,
        node_id: str,
        table_name: str,
        expanded_body: str,
        table_mapping: dict[str, str],
        full_size: int,
        update_frequency: float,
    ) -> Optional[IVMProfile]:
        """既存サンプルテーブルを使って IMMV を作成し計測する。

        expanded_body は expand_mv_sql() で CTE 展開済みの SELECT 本体。
        ベーステーブル名をサンプルテーブル名へ置換してから IMMV を作成する。
        """
        # IMMV 名: アルファベット + 数字のみ (pg_ivm の制約に対応)
        safe_name = re.sub(r'[^a-z0-9]', '', node_id.lower())
        immv_name = SAMPLE_PREFIX + safe_name

        try:
            # CTE 展開済み SQL のベーステーブル名をサンプルテーブル名に置換
            sample_body = UpdateWorkload.rename_sql_tables(expanded_body, table_mapping)
            sample_size = self._create_immv_from_body(conn, immv_name, sample_body)
            if sample_size is None:
                return IVMProfile(node_id, table_name, immv_name, 0, full_size, 0.0, 0.0, 0,
                                  error="IMMV creation failed")

            sample_table = table_mapping[table_name]
            times = self._run_timed_updates(conn, table_name, sample_table, immv_name)
            if not times:
                return IVMProfile(node_id, table_name, immv_name, sample_size, full_size,
                                  0.0, 0.0, 0, error="No successful trials")

            median_t = statistics.median(times)
            # スケール: サンプル IMMV (sample_size 行) → 本番 IMMV サイズ
            # 本番 IMMV の行数 ≈ full_size × (IMMV selectivity) ≈ sample_size / SAMPLING_RATE
            scale = 1.0 / SAMPLING_RATE if sample_size > 0 else 1.0
            scaled_m_j = median_t * scale * update_frequency

            return IVMProfile(
                node_id=node_id,
                table_name=table_name,
                immv_name=immv_name,
                sample_size=sample_size,
                full_size=full_size,
                median_trigger_sec=median_t,
                scaled_m_j=scaled_m_j,
                n_trials=len(times),
            )
        except Exception as e:
            return IVMProfile(node_id, table_name, immv_name, 0, full_size, 0.0, 0.0, 0,
                              error=str(e)[:200])
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
                conn.commit()
            except Exception:
                conn.rollback()

    def _create_immv_from_body(self, conn, immv_name: str, query_body: str) -> Optional[int]:
        """CTE 展開済みの SELECT 本体から IMMV を作成し、行数を返す。失敗時は None。"""
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
                cur.execute("SELECT pgivm.create_immv(%s, %s)", (immv_name, query_body))
                cur.fetchone()  # create_immv の戻り値を消費する
                cur.execute(f"SELECT COUNT(*) FROM {immv_name}")
                row_count = cur.fetchone()[0]
            conn.commit()
            return row_count
        except Exception:
            conn.rollback()
            return None

    def _run_timed_updates(
        self, conn, orig_table: str, sample_table: str, immv_name: str
    ) -> list[float]:
        """UPDATE × n_trials を計測し、ウォームアップを除いた時間リストを返す。"""
        from .update_workload import _SAFE_UPDATE_TEMPLATES
        tmpl = _SAFE_UPDATE_TEMPLATES.get(orig_table)
        if tmpl is None:
            return []

        times: list[float] = []
        for trial in range(self.n_trials + WARMUP_TRIALS):
            sql = tmpl.format(table=sample_table, offset=trial * 50)
            try:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    t0 = time.perf_counter()
                    cur.execute(sql)
                    elapsed = time.perf_counter() - t0
                    cur.execute("ROLLBACK")
                conn.rollback()

                if trial >= WARMUP_TRIALS:
                    times.append(elapsed)
            except Exception:
                conn.rollback()

        return times


    # ──────────────────────────────────────────────────────────────
    # Internal: ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _connect(self):
        s = self.settings.database
        conn = psycopg2.connect(
            host=s.host, port=s.port, dbname=s.database,
            user=s.user, password=s.password,
        )
        conn.autocommit = False
        return conn

    def _get_primary_table(self, node_id: str, qp) -> Optional[str]:
        """ノードの主テーブル名を返す。non_leaf は最初の leaf を使う。"""
        if node_id.startswith("leaf_"):
            return qp.qm.relation_tables.get(node_id)
        # non_leaf: subtree の leaf ノードから最初のテーブルを取得
        tables = qp.search_leaf_node(node_id) if hasattr(qp, "search_leaf_node") else []
        return tables[0] if tables else None

    def _load_plans(self) -> dict:
        """simple_migration_plans.json をキャッシュして返す。"""
        if self._plans_cache is not None:
            return self._plans_cache
        import json
        from pathlib import Path
        plans_path = (
            Path(__file__).parent.parent.parent
            / "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json"
        )
        try:
            with open(plans_path) as f:
                self._plans_cache = json.load(f)
        except Exception:
            self._plans_cache = {}
        return self._plans_cache

    def _get_full_size(self, conn, table_name: str) -> int:
        """本番テーブルの行数を取得する。"""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT reltuples::bigint FROM pg_class WHERE relname = %s",
                    (table_name,)
                )
                row = cur.fetchone()
                return max(1, int(row[0])) if row else 1
        except Exception:
            return 1

