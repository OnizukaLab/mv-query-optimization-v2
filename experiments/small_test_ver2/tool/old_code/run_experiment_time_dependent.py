#!/usr/bin/env python3
"""
小規模実験 - 時刻依存型モード実行スクリプト

複数のタイムステップ（例: 朝、昼、夜）で異なる頻度設定を使用してMV最適化を実行します。

使い方:
    python experiments/small_test/run_experiment_time_dependent.py --phase 2
    python experiments/small_test/run_experiment_time_dependent.py --phase 3
    python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id morning
"""

import argparse
import json
import pickle
import subprocess
import sys
import yaml
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.optimization.factory import OptimizerFactory
from src.utils.legacy import get_all_job_queries, natural_sort_key


class TimeDependentExperiment:
    """時刻依存型モード実験の段階的実行クラス"""
    
    def __init__(self, config_path: str):
        """初期化"""
        self.config_path = Path(config_path)
        self.exp_dir = self.config_path.parent
        
        # UTF-8でYAMLを読み込む
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 一時ファイルに書き込んでからSettingsを読み込む
        temp_config = self.exp_dir / '.temp_config.yaml'
        with open(temp_config, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True)
        
        try:
            self.settings = Settings.from_yaml(str(temp_config))
        finally:
            if temp_config.exists():
                temp_config.unlink()
        
        # 各ディレクトリのパス
        self.queries_dir = self.exp_dir / "01_queries"
        self.json_dir = self.exp_dir / "02_json"
        self.mv_sql_dir = self.exp_dir / "05_mv_sql"
        self.rewritten_dir = self.exp_dir / "06_rewritten"
        
        # 時刻依存型用の出力ディレクトリ
        self.output_dir = self.exp_dir / "time_dependent_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.time_parser = None
    
    def print_header(self, title: str, phase: int = 0):
        """フェーズヘッダーを表示"""
        print("\n" + "=" * 70)
        if phase > 0:
            print(f"フェーズ {phase}: {title}")
        else:
            print(title)
        print("=" * 70)
    
    def print_success(self, message: str):
        """成功メッセージを表示"""
        print(f"  [OK] {message}")
    
    def print_info(self, message: str):
        """情報メッセージを表示"""
        print(f"  → {message}")
    
    def print_error(self, message: str):
        """エラーメッセージを表示"""
        print(f"  [ERROR] {message}")
    
    def phase2_parse_queries(self):
        """フェーズ2: クエリパース（時刻依存型）"""
        self.print_header("クエリパース（時刻依存型）", 2)
        
        from experiments.small_test_ver2.time_dependent_parser import TimeDependentFrequencyParser
        
        time_freq_file = self.queries_dir / "frequency_time_dependent.json"
        
        if not time_freq_file.exists():
            self.print_error(f"{time_freq_file} が見つかりません")
            self.print_info("時刻依存型モードには frequency_time_dependent.json が必要です")
            return False
        
        self.print_info("TimeDependentFrequencyParser を初期化")
        self.time_parser = TimeDependentFrequencyParser(
            self.settings,
            str(time_freq_file)
        )
        
        files, _ = get_all_job_queries(str(self.json_dir))
        files = sorted(files, key=natural_sort_key)
        
        self.print_info(f"タイムステップ数: {len(self.time_parser.timesteps)}")
        for ts in self.time_parser.timesteps:
            self.print_info(f"  - {ts['time_id']}: {ts['label']} ({ts['duration_hours']}時間)")
        
        self.print_info("全タイムステップでパース中...")
        try:
            self.time_parser.parse_for_all_timesteps(
                q_num=0,
                path=str(self.json_dir),
                insert_query=self.settings.optimization.insert_queries,
                files=files
            )
            
            self.time_parser.save_parsers(self.output_dir)
            
            self.print_success("全タイムステップのパース完了")
            return True
            
        except Exception as e:
            self.print_error(f"時刻依存型パースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase3_optimize(self):
        """フェーズ3: ILP最適化（normalアルゴリズムのみ）"""
        self.print_header("ILP最適化（時刻依存型）", 3)
        
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            self.print_error(f"{metadata_file} が見つかりません")
            self.print_info("先に --phase 2 を実行してください")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        timesteps_info = metadata['timesteps']
        
        self.print_info("使用アルゴリズム: normal")
        self.print_info(f"タイムステップ数: {len(time_ids)}")
        
        results_summary = []
        
        for i, (time_id, ts_info) in enumerate(zip(time_ids, timesteps_info)):
            label = ts_info['label']
            duration = ts_info['duration_hours']
            
            print(f"\n{'='*70}")
            print(f"タイムステップ {i+1}/{len(time_ids)}: {time_id}")
            print(f"  {label} ({duration}時間)")
            print(f"{'='*70}")
            
            parser_file = self.output_dir / f"qp_{time_id}.pkl"
            with open(parser_file, 'rb') as f:
                qp = pickle.load(f)
            
            self.print_info(f"パーサーを読み込み: {parser_file}")
            self.print_info(f"  ノード数: {qp.s_num}")
            self.print_info(f"  総利得: {qp.U_max:.2f}")
            
            self.print_info("最適化を実行中...")
            
            try:
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
                
                optimizer = OptimizerFactory.create("normal", **optimizer_params)
                result = optimizer.optimize()
                
                result_file = self.output_dir / f"normal_{time_id}_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
                
                self.print_success("最適化完了")
                self.print_info(f"  選択MV数: {len(result.selected_views)}")
                self.print_info(f"  総ユーティリティ: {result.total_utility:.2f}")
                self.print_info(f"  使用ストレージ: {result.total_storage / (1024*1024):.2f} MB")
                self.print_info(f"  実行時間: {result.execution_time:.2f} 秒")
                self.print_success(f"結果を {result_file} に保存")
                
                selected_node_ids = [mv.node_id for mv in result.selected_views]
                
                results_summary.append({
                    'time_id': time_id,
                    'label': label,
                    'duration_hours': duration,
                    'total_utility': result.total_utility,
                    'num_mvs': len(result.selected_views),
                    'storage_mb': result.total_storage / (1024*1024),
                    'execution_time': result.execution_time,
                    'selected_mvs': selected_node_ids
                })
                
            except Exception as e:
                self.print_error(f"{time_id} の最適化に失敗: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        summary_file = self.output_dir / "normal_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results_summary, f, indent=2, ensure_ascii=False)
        
        self.print_header("最適化サマリー")
        self._print_time_comparison(results_summary)
        
        self.print_success(f"サマリーを {summary_file} に保存")
        
        return True
    
    def _print_time_comparison(self, results_summary: list):
        """時刻別結果比較を出力"""
        print("\n時刻別最適化結果の比較:")
        print(f"{'時刻':<15} {'総利得':>12} {'MV数':>8} {'ストレージ(MB)':>15}")
        print("-" * 55)
        
        for result in results_summary:
            time_label = result['label'][:15]
            utility = result['total_utility']
            num_mvs = result['num_mvs']
            storage = result['storage_mb']
            
            print(f"{time_label:<15} {utility:>12.2f} {num_mvs:>8} {storage:>15.4f}")
        
        print("\n\nMV選択の違い:")
        
        all_mvs = set()
        for result in results_summary:
            all_mvs.update(result['selected_mvs'])
        
        for mv in sorted(all_mvs):
            selections = []
            for result in results_summary:
                if mv in result['selected_mvs']:
                    selections.append(result['time_id'])
            
            if len(selections) < len(results_summary):
                print(f"  {mv}: {', '.join(selections)}")
    
    def phase4_generate_mv_sql(self):
        """フェーズ4: MV生成SQL作成"""
        self.print_header("MV生成SQL作成（時刻依存型）", 4)
        
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            self.print_error(f"{metadata_file} が見つかりません")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        
        result_file = self.output_dir / "normal_summary.json"
        if not result_file.exists():
            self.print_error(f"最適化結果が見つかりません: {result_file}")
            return False
        
        with open(result_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        timesteps_data = summary if isinstance(summary, list) else summary.get('timesteps', [])
        
        for time_id in time_ids:
            parser_file = self.output_dir / f"qp_{time_id}.pkl"
            with open(parser_file, 'rb') as f:
                qp = pickle.load(f)
            
            ts_result = None
            for ts in timesteps_data:
                if ts.get('time_id') == time_id or ts.get('timestep') == time_id:
                    ts_result = ts
                    break
            
            if not ts_result:
                self.print_info(f"⚠ [{time_id}] 最適化結果が見つかりません")
                continue
            
            print(f"  [{time_id}] MV生成SQLを作成中...")
            
            from experiments.small_test_ver2.enhanced_mv_generator import EnhancedMVGenerator
            from experiments.small_test_ver2.small_test_schema_provider import SmallTestSchemaProvider
            
            selected_node_ids = set(ts_result.get('selected_mvs', []))
            
            schema_provider = SmallTestSchemaProvider()
            
            mv_generator = EnhancedMVGenerator(
                query_manager=qp.qm,
                schema_provider=schema_provider,
                selected_mvs=selected_node_ids
            )
            
            output_dir = self.mv_sql_dir / "normal" / time_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_file = output_dir / "create_mvs.sql"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("-- =====================================================\n")
                f.write(f"-- NORMAL アルゴリズム - {time_id}\n")
                f.write("-- =====================================================\n\n")
                f.write(f"\\c {self.settings.database.database}\n\n")
                
                mv_count = 0
                for node_id in ts_result.get('selected_mvs', []):
                    f.write(f"-- ノード: {node_id}\n")
                    
                    create_sql = mv_generator.generate_mv_sql(node_id)
                    
                    if create_sql:
                        f.write(f"{create_sql}\n\n")
                        mv_count += 1
                    else:
                        self.print_info(f"⚠ [{time_id}] {node_id}のSQL生成に失敗しました")
            
            self.print_success(f"  [{time_id}] {mv_count}個のMV作成SQL → {output_file}")
        
        return True
    
    def phase5_create_mvs(self, time_id: str = None):
        """フェーズ5: MV作成（単一タイムステップのみ）"""
        self.print_header("MV作成（時刻依存型）", 5)
        
        from experiments.small_test_ver2.mv_creator import MVCreator
        
        mv_creator = MVCreator(
            settings=self.settings,
            mv_sql_dir=self.mv_sql_dir,
            output_dir=self.output_dir
        )
        
        if time_id is None:
            available = mv_creator.get_available_timesteps("normal")
            if not available:
                self.print_error("利用可能なタイムステップが見つかりません")
                return False
            
            print(f"  利用可能なタイムステップ: {', '.join(available)}")
            print(f"  使用例: --phase 5 --time-id {available[0]}")
            return False
        
        metadata_file = self.output_dir / "time_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            time_ids = metadata['time_ids']
            if time_id not in time_ids:
                self.print_error(f"無効なタイムステップID: {time_id}")
                print(f"  利用可能: {', '.join(time_ids)}")
                return False
        
        success = mv_creator.create_mvs_for_single_timestep(
            algorithm="normal",
            time_id=time_id,
            drop_existing=True
        )
        
        if success:
            self.print_success(f"normal - {time_id} のMV作成完了")
        
        return success
    
    def phase6_rewrite_queries(self):
        """フェーズ6: クエリ書き換え"""
        self.print_header("クエリ書き換え（時刻依存型）", 6)
        
        from experiments.small_test_ver2.query_rewriter import TimeDependentQueryRewriter
        
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            self.print_error(f"{metadata_file} が見つかりません")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        
        self.print_info(f"タイムステップ数: {len(time_ids)}")
        
        parsers_dict = {}
        for time_id in time_ids:
            parser_file = self.output_dir / f"qp_{time_id}.pkl"
            if parser_file.exists():
                with open(parser_file, 'rb') as f:
                    parsers_dict[time_id] = pickle.load(f)
        
        if not parsers_dict:
            self.print_error("パース結果が見つかりません")
            return False
        
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        result_file = self.output_dir / "normal_summary.json"
        if not result_file.exists():
            self.print_error(f"最適化結果が見つかりません: {result_file}")
            return False
        
        with open(result_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        optimization_results = {}
        
        timesteps_data = summary if isinstance(summary, list) else summary.get('timesteps', [])
        
        for ts_result in timesteps_data:
            time_id = ts_result.get('time_id') or ts_result.get('timestep')
            if not time_id:
                self.print_info(f"⚠ タイムステップIDが見つかりません: {ts_result}")
                continue
            
            if 'selected_views_per_query' in ts_result:
                mv_selections = {}
                for i, query_views in enumerate(ts_result.get('selected_views_per_query', [])):
                    mv_selections[str(i)] = query_views
                optimization_results[time_id] = mv_selections
            else:
                detail_file = self.output_dir / f"normal_{time_id}_result.json"
                if not detail_file.exists():
                    self.print_info(f"⚠ [{time_id}] 詳細結果が見つかりません")
                    continue
                
                with open(detail_file, 'r', encoding='utf-8') as df:
                    detail = json.load(df)
                
                mv_selections = {}
                for view_info in detail.get('selected_views', []):
                    node_id = view_info['node_id']
                    for query_idx, _ in view_info.get('usage_positions', []):
                        if str(query_idx) not in mv_selections:
                            mv_selections[str(query_idx)] = []
                        mv_selections[str(query_idx)].append(node_id)
                
                optimization_results[time_id] = mv_selections
        
        if not optimization_results:
            self.print_error("選択されたMVが見つかりません")
            return False
        
        actual_timesteps = list(optimization_results.keys())
        
        td_rewriter = TimeDependentQueryRewriter(
            timesteps=actual_timesteps,
            parsers_dict=parsers_dict
        )
        
        output_base_dir = self.rewritten_dir / "normal"
        
        results = td_rewriter.rewrite_all_timesteps(
            optimization_results,
            query_files,
            output_base_dir
        )
        
        total_rewritten = sum(results.values())
        self.print_success(f"合計{total_rewritten}個のクエリを書き換え完了")
        self.print_info(f"  出力先: {output_base_dir}")
        
        for time_id, count in results.items():
            self.print_info(f"    [{time_id}]: {count}個")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="小規模実験 - 時刻依存型モード")
    parser.add_argument(
        '--phase',
        type=str,
        required=True,
        choices=['2', '3', '4', '5', '6'],
        help='実行するフェーズ (2: パース, 3: 最適化, 4: SQL生成, 5: MV作成, 6: 書き換え)'
    )
    parser.add_argument(
        '--time-id',
        type=str,
        default=None,
        help='タイムステップID (phase 5で必須、例: morning, evening)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test_ver2/config.yaml',
        help='設定ファイルのパス'
    )
    
    args = parser.parse_args()
    
    exp = TimeDependentExperiment(args.config)
    
    if args.phase == '2':
        success = exp.phase2_parse_queries()
    elif args.phase == '3':
        success = exp.phase3_optimize()
    elif args.phase == '4':
        success = exp.phase4_generate_mv_sql()
    elif args.phase == '5':
        success = exp.phase5_create_mvs(time_id=args.time_id)
    elif args.phase == '6':
        success = exp.phase6_rewrite_queries()
    else:
        parser.print_help()
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
