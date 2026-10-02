#!/usr/bin/env python3
"""時刻依存型頻度重み付け最適化の実行スクリプト

複数の時刻で異なるクエリ頻度を設定し、
各時刻ごとに最適化を実行します。
"""

import sys
import json
import pickle
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.utils.legacy import get_all_job_queries, natural_sort_key
from src.optimization.factory import OptimizerFactory
from experiments.small_test.time_dependent_parser import TimeDependentFrequencyParser


class TimeDependentExperiment:
    """時刻依存型実験クラス"""
    
    def __init__(self, config_path: str):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス
        """
        # UTF-8でconfig.yamlを直接読み込んでSettingsを作成
        # Settings.from_yaml()はエンコーディング指定がないため使用しない
        import yaml
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        # Settingsオブジェクトを直接構築
        from config.settings import (
            Settings, DatabaseConfig, OptimizationConfig, 
            BenchmarkConfig, PathsConfig, QueryConfig, 
            ExecutionPhasesConfig, LoggingConfig
        )
        
        # 各設定セクションを構築
        db_config = DatabaseConfig(**config_dict.get('database', {}))
        
        # OptimizationConfig (algorithms は辞書型)
        opt_config = OptimizationConfig(**config_dict.get('optimization', {}))
        
        benchmark_config = BenchmarkConfig(**config_dict.get('benchmark', {}))
        paths_config = PathsConfig(**config_dict.get('paths', {}))
        query_config = QueryConfig(**config_dict.get('query', {}))
        exec_config = ExecutionPhasesConfig(**config_dict.get('execution', {}))
        log_config = LoggingConfig(**config_dict.get('logging', {}))
        
        self.settings = Settings(
            database=db_config,
            optimization=opt_config,
            benchmark=benchmark_config,
            paths=paths_config,
            query=query_config,
            execution=exec_config,
            logging=log_config
        )
        
        self.exp_dir = Path(__file__).parent
        self.output_dir = self.exp_dir / "time_dependent_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.time_parser: TimeDependentFrequencyParser | None = None
    
    def print_header(self, title: str, phase: int = 0):
        """ヘッダー出力"""
        print(f"\n{'='*70}")
        if phase > 0:
            print(f"フェーズ {phase}: {title}")
        else:
            print(f"{title}")
        print(f"{'='*70}")
    
    def print_info(self, message: str):
        """情報メッセージ出力"""
        print(f"  → {message}")
    
    def print_success(self, message: str):
        """成功メッセージ出力"""
        print(f"  ✓ {message}")
    
    def phase1_parse_time_dependent(self):
        """フェーズ1: 時刻依存型パース"""
        self.print_header("時刻依存型クエリパース", 1)
        
        # 時刻依存型頻度ファイルのパス
        time_freq_file = self.exp_dir / "01_queries" / "frequency_time_dependent.json"
        
        if not time_freq_file.exists():
            print(f"  ✗ エラー: {time_freq_file} が見つかりません")
            return False
        
        # 時刻依存型パーサーを作成
        self.print_info("TimeDependentFrequencyParser を初期化")
        self.time_parser = TimeDependentFrequencyParser(
            self.settings,
            str(time_freq_file)
        )
        
        # クエリファイルのリストを取得
        json_dir = self.exp_dir / "02_json"
        files, _ = get_all_job_queries(str(json_dir))
        files = sorted(files, key=natural_sort_key)
        
        # 全タイムステップでパース実行
        self.time_parser.parse_for_all_timesteps(
            q_num=0,
            path=str(json_dir),
            insert_query=self.settings.optimization.insert_queries,
            files=files
        )
        
        # パーサーを保存
        self.time_parser.save_parsers(self.output_dir)
        
        self.print_success("全タイムステップのパース完了")
        return True
    
    def phase2_optimize_all_timesteps(self, algorithm: str = "normal"):
        """フェーズ2: 全タイムステップで最適化
        
        Args:
            algorithm: 使用するアルゴリズム
        """
        self.print_header("時刻依存型最適化", 2)
        
        # メタデータを読み込み
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            print(f"  ✗ エラー: {metadata_file} が見つかりません")
            print("  → 先に phase1 を実行してください")
            return False
        
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        timesteps_info = metadata['timesteps']
        
        self.print_info(f"使用アルゴリズム: {algorithm}")
        self.print_info(f"タイムステップ数: {len(time_ids)}")
        
        results_summary = []
        
        # 各タイムステップで最適化を実行
        for i, (time_id, ts_info) in enumerate(zip(time_ids, timesteps_info)):
            label = ts_info['label']
            duration = ts_info['duration_hours']
            
            print(f"\n{'='*70}")
            print(f"タイムステップ {i+1}/{len(time_ids)}: {time_id}")
            print(f"  {label} ({duration}時間)")
            print(f"{'='*70}")
            
            # パーサーを読み込み
            parser_file = self.output_dir / f"qp_{time_id}.pkl"
            with open(parser_file, 'rb') as f:
                qp = pickle.load(f)
            
            self.print_info(f"パーサーを読み込み: {parser_file}")
            self.print_info(f"  ノード数: {qp.s_num}")
            self.print_info(f"  総利得: {qp.U_max:.2f}")
            
            # 最適化実行
            self.print_info("最適化を実行中...")
            
            try:
                # オプティマイザーパラメータ準備
                optimizer_params = {
                    "qm": qp.qm,
                    "s_num": qp.s_num,
                    "m_cost": qp.m_cost,
                    "node_list": qp.node_list,
                    "B_max": self.settings.optimization.storage_limit_bytes,
                    "b_j": qp.b_j,
                    "u_ij": qp.u_ij,
                    "X": qp.X,
                    "q_s_list": qp.q_s_list,
                    "settings": self.settings,
                }
                
                optimizer = OptimizerFactory.create(algorithm, **optimizer_params)
                result = optimizer.optimize()
                
                # 結果を保存
                result_file = self.output_dir / f"{algorithm}_{time_id}_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
                
                self.print_success(f"最適化完了")
                self.print_info(f"  選択MV数: {result.materialized_count}")
                self.print_info(f"  総ユーティリティ: {result.objective_value:.2f}")
                self.print_info(f"  使用ストレージ: {result.storage_used / (1024*1024):.2f} MB")
                self.print_info(f"  実行時間: {result.execution_time:.2f} 秒")
                self.print_success(f"結果を {result_file} に保存")
                
                # サマリーに追加
                results_summary.append({
                    'time_id': time_id,
                    'label': label,
                    'duration_hours': duration,
                    'total_utility': result.objective_value,
                    'num_mvs': result.materialized_count,
                    'storage_mb': result.storage_used / (1024*1024),
                    'execution_time': result.execution_time,
                    'selected_mvs': result.materialized_nodes
                })
                
            except Exception as e:
                print(f"  ✗ エラー: {time_id} の最適化に失敗: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # サマリーを保存
        summary_file = self.output_dir / f"{algorithm}_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results_summary, f, indent=2, ensure_ascii=False)
        
        self.print_header("最適化サマリー")
        self._print_comparison(results_summary)
        
        self.print_success(f"サマリーを {summary_file} に保存")
        
        return True
    
    def _print_comparison(self, results_summary: list):
        """結果比較を出力"""
        print("\n時刻別最適化結果の比較:")
        print(f"{'時刻':<15} {'総利得':>12} {'MV数':>8} {'ストレージ(MB)':>15}")
        print("-" * 55)
        
        for result in results_summary:
            time_label = result['label'][:15]
            utility = result['total_utility']
            num_mvs = result['num_mvs']
            storage = result['storage_mb']
            
            print(f"{time_label:<15} {utility:>12.2f} {num_mvs:>8} {storage:>15.4f}")
        
        # MV選択の違いを分析
        print("\n\nMV選択の違い:")
        
        all_mvs = set()
        for result in results_summary:
            all_mvs.update(result['selected_mvs'])
        
        # 各時刻でのMV選択状況
        for mv in sorted(all_mvs):
            selections = []
            for result in results_summary:
                if mv in result['selected_mvs']:
                    selections.append(result['time_id'])
            
            if len(selections) < len(results_summary):
                print(f"  {mv}: {', '.join(selections)}")


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="時刻依存型頻度重み付け最適化実験"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        help="実行するフェーズ (1: パース, 2: 最適化, 3: 全実行)"
    )
    parser.add_argument(
        "--algorithm",
        type=str,
        default="normal",
        choices=["normal", "bigsubs", "frequency"],
        help="使用する最適化アルゴリズム"
    )
    
    args = parser.parse_args()
    
    # 設定ファイルのパス
    config_path = Path(__file__).parent / "config.yaml"
    
    exp = TimeDependentExperiment(str(config_path))
    
    if args.phase == 1:
        exp.phase1_parse_time_dependent()
    elif args.phase == 2:
        exp.phase2_optimize_all_timesteps(args.algorithm)
    elif args.phase == 3:
        exp.phase1_parse_time_dependent()
        exp.phase2_optimize_all_timesteps(args.algorithm)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
