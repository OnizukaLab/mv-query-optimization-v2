#!/usr/bin/env python3
"""
小規模実験 - 段階的実行スクリプト

各フェーズを段階的に実行し、結果を確認できます。

使い方:
    # 通常モード（単一頻度）
    python experiments/small_test/run_experiment.py --phase all
    python experiments/small_test/run_experiment.py --phase 2
    
    # 時刻依存型モード（複数タイムステップ）
    python experiments/small_test/run_experiment.py --mode time-dependent --phase 2
    python experiments/small_test/run_experiment.py --mode time-dependent --phase 3 --algorithm normal
"""

import argparse
import json
import pickle
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.rewrite.mv_generator import MVGenerator
from src.utils.legacy import get_all_job_queries, natural_sort_key


class SmallExperiment:
    """小規模実験の段階的実行クラス"""
    
    def __init__(self, config_path: str, mode: str = "normal"):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス
            mode: 実行モード ("normal" または "time-dependent")
        """
        self.config_path = Path(config_path)
        self.exp_dir = self.config_path.parent
        self.mode = mode
        
        # UTF-8でYAMLを読み込む（Windows環境でのエンコーディングエラー回避）
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 一時ファイルに書き込んでからSettingsを読み込む
        temp_config = self.exp_dir / '.temp_config.yaml'
        with open(temp_config, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True)
        
        try:
            self.settings = Settings.from_yaml(str(temp_config))
        finally:
            # 一時ファイルを削除
            if temp_config.exists():
                temp_config.unlink()
        
        # 各ディレクトリのパス
        self.queries_dir = self.exp_dir / "01_queries"
        self.json_dir = self.exp_dir / "02_json"
        self.parsed_dir = self.exp_dir / "03_parsed"
        self.optimized_dir = self.exp_dir / "04_optimized"
        self.mv_sql_dir = self.exp_dir / "05_mv_sql"
        self.rewritten_dir = self.exp_dir / "06_rewritten"
        self.logs_dir = self.exp_dir / "logs"
        
        # 出力ディレクトリを作成
        self.rewritten_dir.mkdir(parents=True, exist_ok=True)
        
        # モードに応じた出力設定
        if self.mode == "time-dependent":
            self.output_dir = self.exp_dir / "time_dependent_output"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.pickle_path = None  # 時刻依存型では複数のpickleファイルを使用
            self.time_parser = None
        else:
            self.output_dir = None
            self.pickle_path = self.exp_dir / "qp_class.pkl"
            self.time_parser = None
        
        self.qp: Optional[QueryParser] = None
        self.results = {}
    
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
    
    def phase0_setup(self):
        """フェーズ0: データベースセットアップ"""
        self.print_header("データベースセットアップ", 0)
        
        setup_file = self.exp_dir / "00_setup.sql"
        
        if not setup_file.exists():
            self.print_error(f"{setup_file} が見つかりません")
            return False
        
        print(f"  → {setup_file} を実行します")
        print(f"  → コマンド: psql -U postgres -f {setup_file}")
        print()
        
        try:
            # Windows環境でのエンコーディングエラーを回避
            result = subprocess.run(
                ["psql", "-U", "postgres", "-f", str(setup_file)],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',  # デコードエラーを無視
                env={**subprocess.os.environ, 'PGPASSWORD': ''}  # パスワード不要
            )
            print(result.stdout)
            self.print_success("データベースセットアップ完了")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ エラー: {e}")
            if e.stderr:
                print(f"  stderr: {e.stderr}")
            return False
        except FileNotFoundError:
            print("  ✗ エラー: psql コマンドが見つかりません")
            print("  → PostgreSQL のパスを確認してください")
            return False
    
    def phase1_generate_explain_json(self):
        """フェーズ1: EXPLAIN JSON 生成"""
        self.print_header("EXPLAIN JSON 生成", 1)
        
        query_files = sorted(self.queries_dir.glob("*.sql"))
        
        if not query_files:
            print(f"  ✗ エラー: {self.queries_dir} にクエリファイルが見つかりません")
            return False
        
        self.print_info(f"{len(query_files)}個のクエリファイルを処理します")
        
        # jobディレクトリを作成
        job_dir = self.json_dir / "job"
        job_dir.mkdir(parents=True, exist_ok=True)
        
        for query_file in query_files:
            output_file = job_dir / f"{query_file.stem}.json"
            
            self.print_info(f"処理中: {query_file.name}")
            
            # クエリを読み込み（コメント行を除去）
            with open(query_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # コメント行（--で始まる行）と空行を除去
            query_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('--'):
                    query_lines.append(line)
            
            query_sql = ''.join(query_lines).strip()
            
            # EXPLAIN JSON を実行
            explain_sql = f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {query_sql}"
            
            try:
                result = subprocess.run(
                    ["psql", "-U", "postgres", "-d", self.settings.database.database,
                     "-t", "-A", "-c", explain_sql],
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8',
                    errors='replace',
                    env={**subprocess.os.environ, 'PGPASSWORD': ''}
                )
                
                # JSON として保存
                json_data = json.loads(result.stdout.strip())
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                self.print_success(f"{output_file.name} を生成")
                
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                print(f"  ✗ エラー: {query_file.name} の処理に失敗: {e}")
                return False
        
        return True
    
    def phase2_parse_queries(self):
        """フェーズ2: クエリパース（頻度重み付け）"""
        self.print_header("クエリパース", 2)
        
        if self.mode == "time-dependent":
            return self._phase2_time_dependent_parse()
        else:
            return self._phase2_normal_parse()
    
    def _phase2_normal_parse(self):
        """通常モードのパース"""
        # 頻度重み付けパーサーを使用
        from experiments.small_test.frequency_weighted_parser import FrequencyWeightedParser
        
        self.print_info("FrequencyWeightedParser を初期化")
        
        # 頻度情報ファイルのパス
        frequency_file = Path(__file__).parent / "01_queries" / "frequency.json"
        
        if frequency_file.exists():
            self.print_info(f"頻度情報ファイル: {frequency_file}")
            self.qp = FrequencyWeightedParser(self.settings, str(frequency_file))
        else:
            self.print_info("頻度情報ファイルが見つかりません。通常のパーサーを使用")
            self.qp = QueryParser(self.settings)
        
        self.print_info("クエリをパース中...")
        try:
            # クエリファイルのリストを取得（頻度適用用）
            query_dir = str(self.json_dir)
            files, _ = get_all_job_queries(query_dir)
            files = sorted(files, key=natural_sort_key)
            
            # パース実行
            self.qp.query_parse(
                q_num=0,
                path=str(self.json_dir),
                insert_query=self.settings.optimization.insert_queries
            )
            
            insert_query=self.settings.optimization.insert_queries
            # 頻度重み付けパーサーの場合、頻度の重みを適用
            if isinstance(self.qp, FrequencyWeightedParser):
                self.qp.apply_frequency_weights(files)
                self.qp.calculate_maintenance_costs(insert_query) #メンテナンスコスト追加頻度はまだ考慮できていない
            
            self.print_success(f"{len(self.qp.query)}個のクエリをパース完了")
            self.print_info(f"  リーフノード数: {len(self.qp.qm.leaf_nodes_map)}")
            self.print_info(f"  非リーフノード数: {len(self.qp.qm.non_leaf_nodes_map)}")
            self.print_info(f"  総ノード数: {self.qp.s_num}")
            
            # パース結果を保存
            self._save_parse_results()
            
            return True
            
        except Exception as e:
            print(f"  ✗ エラー: クエリパースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _phase2_time_dependent_parse(self):
        """時刻依存型モードのパース"""
        from experiments.small_test.time_dependent_parser import TimeDependentFrequencyParser
        
        # 時刻依存型頻度ファイルのパス
        time_freq_file = self.queries_dir / "frequency_time_dependent.json"
        
        if not time_freq_file.exists():
            print(f"  ✗ エラー: {time_freq_file} が見つかりません")
            print("  → 時刻依存型モードには frequency_time_dependent.json が必要です")
            return False
        
        self.print_info("TimeDependentFrequencyParser を初期化")
        self.time_parser = TimeDependentFrequencyParser(
            self.settings,
            str(time_freq_file)
        )
        
        # クエリファイルのリストを取得
        files, _ = get_all_job_queries(str(self.json_dir))
        files = sorted(files, key=natural_sort_key)
        
        self.print_info(f"タイムステップ数: {len(self.time_parser.timesteps)}")
        for ts in self.time_parser.timesteps:
            self.print_info(f"  - {ts['time_id']}: {ts['label']} ({ts['duration_hours']}時間)")
        
        # 全タイムステップでパース実行
        self.print_info("全タイムステップでパース中...")
        try:
            self.time_parser.parse_for_all_timesteps(
                q_num=0,
                path=str(self.json_dir),
                insert_query=self.settings.optimization.insert_queries,
                files=files
            )
            
            # パーサーを保存
            self.time_parser.save_parsers(self.output_dir)
            
            self.print_success("全タイムステップのパース完了")
            return True
            
        except Exception as e:
            print(f"  ✗ エラー: 時刻依存型パースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_parse_results(self):
        """パース結果を保存"""
        import pickle
        
        # pickleファイルとして保存
        with open(self.pickle_path, 'wb') as f:
            pickle.dump(self.qp, f)
        
        self.print_success(f"パース結果を {self.pickle_path} に保存")
        
        # サマリーをJSONでも保存
        summary = {
            "num_queries": len(self.qp.query),
            "num_leaf_nodes": len(self.qp.qm.leaf_nodes_map),
            "num_non_leaf_nodes": len(self.qp.qm.non_leaf_nodes_map),
            "total_nodes": self.qp.s_num,
            # 追加情報
            "node_list": self.qp.node_list,
            "u_ij_shape": [len(self.qp.u_ij), len(self.qp.u_ij[0]) if self.qp.u_ij else 0],  # 行列サイズ
            "b_j_length": len(self.qp.b_j),
            "m_cost_length": len(self.qp.m_cost),
        }
        summary_path = self.parsed_dir / "parse_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_success(f"サマリーを {summary_path} に保存")
    
    def phase3_optimize(self, algorithm: str = None):
        """フェーズ3: ILP最適化
        
        Args:
            algorithm: 使用するアルゴリズム（時刻依存型モードで使用）
        """
        self.print_header("ILP最適化", 3)
        
        if self.mode == "time-dependent":
            if algorithm is None:
                print("  ✗ エラー: 時刻依存型モードでは --algorithm を指定してください")
                print("  → 例: --phase 3 --algorithm normal")
                return False
            return self._phase3_time_dependent_optimize(algorithm)
        else:
            return self._phase3_normal_optimize()
    
    def _phase3_normal_optimize(self):
        """通常モードの最適化"""
        # qp_class.pkl の存在確認
        if not self.pickle_path.exists():
            print(f"  ✗ エラー: {self.pickle_path} が見つかりません")
            print("  → 先にフェーズ2を実行してください:")
            print(f"     python {Path(__file__).name} --phase 2")
            return False
        
        # qpがメモリにない場合は読み込み
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                print(f"  ✗ エラー: パース結果の読み込みに失敗: {e}")
                return False
            
        algorithms = []
        # アルゴリズム設定を取得（辞書形式に対応）
        algo_config = self.settings.optimization.algorithms
        if isinstance(algo_config, dict):
            if algo_config.get('normal', False):
                algorithms.append('normal')
            if algo_config.get('bigsubs', False):
                algorithms.append('bigsubs')
        else:
            # オブジェクト形式の場合
            if getattr(algo_config, 'normal', False):
                algorithms.append('normal')
            if getattr(algo_config, 'bigsubs', False):
                algorithms.append('bigsubs')
        
        if not algorithms:
            print("  ✗ エラー: 実行するアルゴリズムが設定されていません")
            return False
        
        self.print_info(f"使用アルゴリズム: {', '.join(algorithms)}")
        
        for algo in algorithms:
            self.print_info(f"\n--- {algo.upper()} アルゴリズムを実行 ---")
            
            try:
                # ストレージ制限を設定から取得
                B_max = self.settings.optimization.storage_limit_bytes
                
                # OptimizerFactoryに必要な引数を渡す
                optimizer = OptimizerFactory.create(
                    algo,
                    qm=self.qp.qm,
                    s_num=self.qp.s_num,
                    m_cost=self.qp.m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=self.qp.b_j,
                    u_ij=self.qp.u_ij,
                    X=self.qp.X,
                    q_s_list=self.qp.q_s_list,
                    settings=self.settings
                )
                
                self.print_info("最適化を実行中...")
                result = optimizer.optimize()

                 # 結果を保存
                self.results[algo] = result
                
                # 統計表示
                storage_mb = result.total_storage / (1024 * 1024)
                self.print_success(f"{algo}: {len(result.selected_views)}個のMVを選択")
                self.print_info(f"  総ユーティリティ: {result.total_utility:.2f}")
                self.print_info(f"  使用ストレージ: {storage_mb:.2f} MB")
                self.print_info(f"  実行時間: {result.execution_time:.2f} 秒")
                
                # 結果をJSONで保存
                result_file = self.optimized_dir / f"{algo}_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
                self.print_success(f"結果を {result_file} に保存")

            except Exception as e:
                print(f"  ✗ エラー: {algo} の最適化に失敗: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        return True
    
    def _phase3_time_dependent_optimize(self, algorithm: str):
        """時刻依存型モードの最適化
        
        Args:
            algorithm: 使用するアルゴリズム
        """
        # メタデータを読み込み
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            print(f"  ✗ エラー: {metadata_file} が見つかりません")
            print("  → 先に --phase 2 を実行してください")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
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
                self.print_info(f"  選択MV数: {len(result.selected_views)}")
                self.print_info(f"  総ユーティリティ: {result.total_utility:.2f}")
                self.print_info(f"  使用ストレージ: {result.total_storage / (1024*1024):.2f} MB")
                self.print_info(f"  実行時間: {result.execution_time:.2f} 秒")
                self.print_success(f"結果を {result_file} に保存")
                
                # サマリーに追加
                # 選択されたMVのnode_idリストを作成
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
                print(f"  [ERROR] {time_id} の最適化に失敗: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # サマリーを保存
        summary_file = self.output_dir / f"{algorithm}_summary.json"
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
    
    def _save_optimization_results(self, algorithm: str, mv_selections: dict):
        """最適化結果を保存"""
        algo_dir = self.optimized_dir / algorithm
        algo_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = algo_dir / "mv_selections.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(mv_selections, f, indent=2, ensure_ascii=False)
        
        self.print_success(f"{algorithm} の結果を {output_file} に保存")
    
    def phase4_generate_mv_sql(self):
        """フェーズ4: MV生成SQL作成（通常モード・時刻依存型モード対応）"""
        self.print_header("MV生成SQL作成", 4)
        
        if self.mode == "time-dependent":
            return self._phase4_time_dependent_generate_sql()
        else:
            return self._phase4_normal_generate_sql()
    
    def _phase4_normal_generate_sql(self):
        """通常モードのMV生成SQL作成"""
        # qpが読み込まれていない場合は読み込む
        if self.qp is None:
            if not self.pickle_path.exists():
                print(f"  ✗ エラー: {self.pickle_path} が見つかりません")
                print("  → 先にフェーズ2を実行してください")
                return False
            
            import pickle
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                print(f"  ✗ エラー: パース結果の読み込みに失敗: {e}")
                return False
        
        # 最適化結果が読み込まれていない場合は読み込む
        if not self.results:
            self.print_info("最適化結果を読み込み中...")
            for algo in ['normal', 'bigsubs']:
                result_file = self.exp_dir / f"{algo}_result.json"
                if result_file.exists():
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                        self.results[algo] = result_data
                        self.print_info(f"  {algo}: 読み込み完了")
        
        if not self.results:
            print("  ✗ エラー: 最適化結果が見つかりません")
            print("  → 先にフェーズ3を実行してください")
            return False
        
        for algo, result_data in self.results.items():
            self.print_info(f"\n--- {algo.upper()} のMV生成SQL作成 ---")
            
            try:
                # EnhancedMVGeneratorを使用して列名重複を回避
                from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
                from experiments.small_test.small_test_schema_provider import SmallTestSchemaProvider
                
                # result_dataから選択されたビューのリストを取得
                if isinstance(result_data, dict):
                    selected_views = result_data.get('selected_views', [])
                else:
                    # OptimizationResultオブジェクトの場合
                    selected_views = result_data.selected_views
                
                # 選択されたノードIDのセットを作成
                selected_node_ids = set()
                for view in selected_views:
                    node_id = view.get('node_id') if isinstance(view, dict) else view.node_id
                    selected_node_ids.add(node_id)
                
                # 小規模実験用のスキーマプロバイダーを作成
                schema_provider = SmallTestSchemaProvider()
                
                # EnhancedMVGeneratorを初期化
                mv_generator = EnhancedMVGenerator(
                    query_manager=self.qp.qm,
                    schema_provider=schema_provider,
                    selected_mvs=selected_node_ids
                )
                
                # MV生成SQLを作成
                algo_dir = self.mv_sql_dir / algo
                algo_dir.mkdir(parents=True, exist_ok=True)
                
                output_file = algo_dir / "create_mvs.sql"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("-- =====================================================\n")
                    f.write(f"-- {algo.upper()} アルゴリズムで選択されたMV作成SQL\n")
                    f.write("-- =====================================================\n\n")
                    f.write(f"\\c {self.settings.database.database}\n\n")
                    
                    mv_count = 0
                    for view in selected_views:
                        node_id = view.get('node_id') if isinstance(view, dict) else view.node_id
                        
                        f.write(f"-- ノード: {node_id}\n")
                        
                        # EnhancedMVGeneratorでSQLを生成（列名重複を自動解決）
                        mv_sql = mv_generator.generate_mv_sql(node_id)
                        
                        if mv_sql:
                            f.write(f"{mv_sql}\n\n")
                            mv_count += 1
                        else:
                            print(f"  ⚠ {node_id} のSQL生成に失敗しました")
                
                self.print_success(f"{algo}: {mv_count}個のMV作成SQLを生成 → {output_file}")
                
            except Exception as e:
                print(f"  ✗ エラー: {algo} のSQL生成に失敗: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        return True
    
    def _phase4_time_dependent_generate_sql(self):
        """時刻依存型モードのMV生成SQL作成"""
        # メタデータを読み込み
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            print(f"  ✗ エラー: {metadata_file} が見つかりません")
            print("  → 先に --phase 2 を実行してください")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        
        # 使用するアルゴリズムを取得
        algorithms = []
        try:
            # 属性アクセスを試みる
            if hasattr(self.settings.optimization.algorithms, 'normal'):
                if self.settings.optimization.algorithms.normal:
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.bigsubs:
                    algorithms.append("bigsubs")
            else:
                # 辞書アクセスにフォールバック
                if self.settings.optimization.algorithms.get('normal', False):
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.get('bigsubs', False):
                    algorithms.append("bigsubs")
        except (AttributeError, TypeError):
            # デフォルトで両方使用
            algorithms = ["normal", "bigsubs"]
        
        if not algorithms:
            print("  ✗ エラー: 実行するアルゴリズムが設定されていません")
            return False
        
        for algo in algorithms:
            self.print_info(f"\n--- {algo.upper()} のMV生成SQL作成 ---")
            
            # 最適化結果を読み込み
            result_file = self.output_dir / f"{algo}_summary.json"
            if not result_file.exists():
                print(f"  ⚠ 最適化結果が見つかりません: {result_file}")
                continue
            
            with open(result_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            
            # summaryの構造を判定
            # リスト形式の場合: [{time_id: ..., selected_mvs: ...}, ...]
            # 辞書形式の場合: {timesteps: [{time_id: ..., selected_mvs: ...}, ...]}
            if isinstance(summary, list):
                timesteps_data = summary
            elif isinstance(summary, dict):
                timesteps_data = summary.get('timesteps', [])
            else:
                print(f"  ⚠ 予期しない形式の最適化結果: {type(summary)}")
                continue
            
            # 各タイムステップのMV作成SQL
            for time_id in time_ids:
                # パーサーを読み込み
                parser_file = self.output_dir / f"qp_{time_id}.pkl"
                with open(parser_file, 'rb') as f:
                    qp = pickle.load(f)
                
                # このタイムステップの結果を取得
                ts_result = None
                for ts in timesteps_data:
                    if ts.get('time_id') == time_id or ts.get('timestep') == time_id:
                        ts_result = ts
                        break
                
                if not ts_result:
                    print(f"  ⚠ [{time_id}] 最適化結果が見つかりません")
                    continue
                
                print(f"  [{time_id}] MV生成SQLを作成中...")
                
                # EnhancedMVGeneratorを使用して列名重複を回避
                from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
                from experiments.small_test.small_test_schema_provider import SmallTestSchemaProvider
                
                # 選択されたMVのセットを作成
                selected_node_ids = set(ts_result.get('selected_mvs', []))
                
                # 小規模実験用のスキーマプロバイダーを作成
                schema_provider = SmallTestSchemaProvider()
                
                # EnhancedMVGeneratorを初期化
                mv_generator = EnhancedMVGenerator(
                    query_manager=qp.qm,
                    schema_provider=schema_provider,
                    selected_mvs=selected_node_ids
                )
                
                # 出力ディレクトリ
                output_dir = self.mv_sql_dir / algo / time_id
                output_dir.mkdir(parents=True, exist_ok=True)
                
                output_file = output_dir / "create_mvs.sql"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("-- =====================================================\n")
                    f.write(f"-- {algo.upper()} アルゴリズム - {time_id}\n")
                    f.write("-- =====================================================\n\n")
                    f.write(f"\\c {self.settings.database.database}\n\n")
                    
                    mv_count = 0
                    for node_id in ts_result.get('selected_mvs', []):
                        f.write(f"-- ノード: {node_id} ({time_id})\n")
                        
                        # EnhancedMVGeneratorでSQLを生成（列名重複を自動解決）
                        create_sql = mv_generator.generate_mv_sql(node_id)
                        
                        if not create_sql:
                            print(f"  ⚠ [{time_id}] {node_id}のSQL生成に失敗しました")
                            continue
                        
                        # タイムステップ用のMV名に置き換え
                        mv_name = f"mv_{node_id}_{time_id}"
                        
                        # MV名を置き換え
                        import re
                        pattern = r'CREATE MATERIALIZED VIEW\s+(\w+)\s+AS'
                        modified_sql = re.sub(pattern, f'CREATE MATERIALIZED VIEW {mv_name} AS', create_sql)
                        
                        f.write(f"{modified_sql}\n\n")
                        mv_count += 1
                
                self.print_success(f"  [{time_id}] {mv_count}個のMV作成SQL → {output_file}")
        
        return True
    
    def phase5_create_mvs(self, time_id: str = None):
        """フェーズ5: MV作成（実際にDBに作成）（通常モード・時刻依存型モード対応）
        
        Args:
            time_id: 作成するタイムステップID（時刻依存型モードで必須）
        """
        self.print_header("MV作成（データベース）", 5)
        
        if self.mode == "time-dependent":
            return self._phase5_time_dependent_create_mvs(time_id)
        else:
            return self._phase5_normal_create_mvs()
    
    def _phase5_normal_create_mvs(self):
        """通常モードのMV作成"""
        # SQLファイルを検索
        sql_files = list(self.mv_sql_dir.glob("*/create_mvs.sql"))
        
        if not sql_files:
            print("  ✗ MV作成SQLファイルが見つかりません")
            print("  → 先にフェーズ4を実行してください")
            return False
        
        for sql_file in sql_files:
            algo = sql_file.parent.name
            
            self.print_info(f"\n--- {algo.upper()} のMVを作成 ---")
            self.print_info(f"実行: psql -U postgres -f {sql_file}")
            
            try:
                result = subprocess.run(
                    ["psql", "-U", "postgres", "-f", str(sql_file)],
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8',
                    errors='replace',
                    env={**subprocess.os.environ, 'PGPASSWORD': ''}
                )
                
                if result.stdout:
                    print(result.stdout)
                
                self.print_success(f"{algo}: MV作成完了")
                
            except subprocess.CalledProcessError as e:
                print(f"  ✗ エラー: {e}")
                if e.stderr:
                    print(f"  stderr: {e.stderr}")
                if e.stdout:
                    print(f"  stdout: {e.stdout}")
                # エラーでも続行
                continue
        
        # 作成されたMVを確認
        self._list_created_mvs()
        
        return True
    
    def _phase5_time_dependent_create_mvs(self, time_id: str = None):
        """時刻依存型モードのMV作成（単一タイムステップのみ）
        
        Args:
            time_id: 作成するタイムステップID
        """
        from experiments.small_test.mv_creator import MVCreator
        
        # MVCreatorを初期化
        mv_creator = MVCreator(
            settings=self.settings,
            mv_sql_dir=self.mv_sql_dir,
            output_dir=self.output_dir
        )
        
        # 使用するアルゴリズムを取得
        algorithms = []
        try:
            if hasattr(self.settings.optimization.algorithms, 'normal'):
                if self.settings.optimization.algorithms.normal:
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.bigsubs:
                    algorithms.append("bigsubs")
            else:
                if self.settings.optimization.algorithms.get('normal', False):
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.get('bigsubs', False):
                    algorithms.append("bigsubs")
        except (AttributeError, TypeError):
            algorithms = ["normal", "bigsubs"]
        
        if not algorithms:
            print("  ✗ エラー: 実行するアルゴリズムが設定されていません")
            return False
        
        # アルゴリズムを選択（最初のもの、または設定から）
        algo = algorithms[0]
        
        # タイムステップが指定されていない場合、利用可能なものを表示
        if time_id is None:
            available = mv_creator.get_available_timesteps(algo)
            if not available:
                print(f"  ✗ 利用可能なタイムステップが見つかりません")
                return False
            
            print(f"  利用可能なタイムステップ: {', '.join(available)}")
            print(f"  使用例: --phase 5 --time-id {available[0]}")
            return False
        
        # メタデータを確認
        metadata_file = self.output_dir / "time_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            time_ids = metadata['time_ids']
            if time_id not in time_ids:
                print(f"  ✗ 無効なタイムステップID: {time_id}")
                print(f"  利用可能: {', '.join(time_ids)}")
                return False
        
        # 単一タイムステップのMVを作成
        success = mv_creator.create_mvs_for_single_timestep(
            algorithm=algo,
            time_id=time_id,
            drop_existing=True  # 既存MVを削除
        )
        
        if success:
            self.print_success(f"{algo} - {time_id} のMV作成完了")
        
        return success
    
    def _list_created_mvs(self):
        """作成されたMVの一覧を表示"""
        self.print_info("\n--- 作成されたMV一覧 ---")
        
        query = """
        SELECT matviewname, 
               pg_size_pretty(pg_total_relation_size('public.'||matviewname)) as size
        FROM pg_matviews 
        WHERE schemaname = 'public'
        ORDER BY matviewname;
        """
        
        try:
            result = subprocess.run(
                ["psql", "-U", "postgres", "-d", self.settings.database.database,
                 "-c", query],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',
                env={**subprocess.os.environ, 'PGPASSWORD': ''}
            )
            
            print(result.stdout)
            
        except subprocess.CalledProcessError:
            print("  ✗ MV一覧の取得に失敗")
    
    def phase6_rewrite_queries(self):
        """フェーズ6: クエリ書き換え（通常モード・時刻依存型モード対応）"""
        self.print_header("クエリ書き換え", 6)
        
        if self.mode == "time-dependent":
            return self._phase6_time_dependent_rewrite()
        else:
            return self._phase6_normal_rewrite()
    
    def _phase6_normal_rewrite(self):
        """通常モードのクエリ書き換え"""
        from experiments.small_test.query_rewriter import QueryRewriter
        
        # QueryParserが読み込まれていない場合は読み込む
        if not hasattr(self, 'qp') or self.qp is None:
            self.print_info("QueryParserを読み込み中...")
            if not self.pickle_path or not self.pickle_path.exists():
                print("  ✗ エラー: パース結果が見つかりません")
                print("  → 先にフェーズ2を実行してください")
                return False
            
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
        
        # 最適化結果を読み込み
        algorithms = []
        try:
            # 属性アクセスを試みる
            if hasattr(self.settings.optimization.algorithms, 'normal'):
                if self.settings.optimization.algorithms.normal:
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.bigsubs:
                    algorithms.append("bigsubs")
            else:
                # 辞書アクセスにフォールバック
                if self.settings.optimization.algorithms.get('normal', False):
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.get('bigsubs', False):
                    algorithms.append("bigsubs")
        except (AttributeError, TypeError):
            # デフォルトで両方使用
            algorithms = ["normal", "bigsubs"]
        
        if not algorithms:
            print("  ✗ エラー: 実行するアルゴリズムが設定されていません")
            return False
        
        # クエリファイルを取得
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            print("  ✗ エラー: クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        for algo in algorithms:
            self.print_info(f"\n--- {algo.upper()} のクエリ書き換え ---")
            
            # MV選択結果を読み込み
            selection_file = self.optimized_dir / algo / "mv_selections.json"
            if not selection_file.exists():
                # 代替: result.json から取得
                result_file = self.optimized_dir / f"{algo}_result.json"
                if result_file.exists():
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                        # mv_selectionsを作成
                        mv_selections = {}
                        for i, query_views in enumerate(result_data.get('selected_views_per_query', [])):
                            mv_selections[str(i)] = [v['node_id'] for v in query_views]
                else:
                    print(f"  ⚠ 最適化結果が見つかりません: {selection_file}")
                    continue
            else:
                with open(selection_file, 'r', encoding='utf-8') as f:
                    mv_selections = json.load(f)
            
            # QueryRewriterを初期化
            rewriter = QueryRewriter(self.qp.qm, mv_selections)
            
            # 出力ディレクトリを作成
            output_dir = self.rewritten_dir / algo
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # すべてのクエリを書き換え
            rewritten_count = rewriter.rewrite_all_queries(query_files, output_dir)
            
            self.print_success(f"{algo}: {rewritten_count}個のクエリを書き換え完了")
            self.print_info(f"  出力先: {output_dir}")
        
        return True
    
    def _phase6_time_dependent_rewrite(self):
        """時刻依存型モードのクエリ書き換え"""
        from experiments.small_test.query_rewriter import TimeDependentQueryRewriter
        
        # メタデータを読み込み
        metadata_file = self.output_dir / "time_metadata.json"
        if not metadata_file.exists():
            print(f"  ✗ エラー: {metadata_file} が見つかりません")
            print("  → 先に --phase 2 を実行してください")
            return False
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        time_ids = metadata['time_ids']
        timesteps_info = metadata['timesteps']
        
        self.print_info(f"タイムステップ数: {len(time_ids)}")
        
        # パーサー辞書を読み込み
        parsers_dict = {}
        for time_id in time_ids:
            parser_file = self.output_dir / f"qp_{time_id}.pkl"
            if parser_file.exists():
                with open(parser_file, 'rb') as f:
                    parsers_dict[time_id] = pickle.load(f)
        
        if not parsers_dict:
            print("  ✗ エラー: パース結果が見つかりません")
            return False
        
        # クエリファイルを取得
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            print("  ✗ エラー: クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        # 使用するアルゴリズムを取得
        algorithms = []
        try:
            # 属性アクセスを試みる
            if hasattr(self.settings.optimization.algorithms, 'normal'):
                if self.settings.optimization.algorithms.normal:
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.bigsubs:
                    algorithms.append("bigsubs")
            else:
                # 辞書アクセスにフォールバック
                if self.settings.optimization.algorithms.get('normal', False):
                    algorithms.append("normal")
                if self.settings.optimization.algorithms.get('bigsubs', False):
                    algorithms.append("bigsubs")
        except (AttributeError, TypeError):
            # デフォルトで両方使用
            algorithms = ["normal", "bigsubs"]
        
        if not algorithms:
            print("  ✗ エラー: 実行するアルゴリズムが設定されていません")
            return False
        
        for algo in algorithms:
            self.print_info(f"\n--- {algo.upper()} のクエリ書き換え ---")
            
            # 最適化結果を読み込み
            result_file = self.output_dir / f"{algo}_summary.json"
            if not result_file.exists():
                print(f"  ⚠ 最適化結果が見つかりません: {result_file}")
                continue
            
            with open(result_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            
            # 各タイムステップの選択結果を収集
            optimization_results = {}
            
            # summaryが直接timestepsのリストか、timestepsキーを持つ辞書か判定
            if isinstance(summary, list):
                timesteps_data = summary
            elif isinstance(summary, dict):
                timesteps_data = summary.get('timesteps', [])
            else:
                print(f"  ⚠ 予期しないsummary形式: {type(summary)}")
                continue
            
            for ts_result in timesteps_data:
                # time_idまたはtimestepキーを探す
                time_id = ts_result.get('time_id') or ts_result.get('timestep')
                if not time_id:
                    print(f"  ⚠ タイムステップIDが見つかりません: {ts_result}")
                    continue
                
                # selected_views_per_queryがあればそれを使用、なければ詳細ファイルから構築
                if 'selected_views_per_query' in ts_result:
                    mv_selections = {}
                    for i, query_views in enumerate(ts_result.get('selected_views_per_query', [])):
                        mv_selections[str(i)] = query_views
                    optimization_results[time_id] = mv_selections
                else:
                    # 詳細ファイルから読み込み
                    detail_file = self.output_dir / f"{algo}_{time_id}_result.json"
                    if not detail_file.exists():
                        print(f"  ⚠ [{time_id}] 詳細結果が見つかりません: {detail_file}")
                        continue
                    
                    with open(detail_file, 'r', encoding='utf-8') as df:
                        detail = json.load(df)
                    
                    # usage_positionsからmv_selectionsを構築
                    mv_selections = {}
                    for view_info in detail.get('selected_views', []):
                        node_id = view_info['node_id']
                        for query_idx, _ in view_info.get('usage_positions', []):
                            if str(query_idx) not in mv_selections:
                                mv_selections[str(query_idx)] = []
                            mv_selections[str(query_idx)].append(node_id)
                    
                    optimization_results[time_id] = mv_selections
            
            if not optimization_results:
                print(f"  ⚠ 選択されたMVが見つかりません")
                continue
            
            # 実際のタイムステップIDを使用
            actual_timesteps = list(optimization_results.keys())
            
            # TimeDependentQueryRewriterを作成
            td_rewriter = TimeDependentQueryRewriter(
                timesteps=actual_timesteps,
                parsers_dict=parsers_dict
            )
            
            # 出力ディレクトリ
            output_base_dir = self.rewritten_dir / algo
            
            # すべてのタイムステップで書き換え
            results = td_rewriter.rewrite_all_timesteps(
                optimization_results,
                query_files,
                output_base_dir
            )
            
            # 結果サマリー
            total_rewritten = sum(results.values())
            self.print_success(f"{algo}: 合計{total_rewritten}個のクエリを書き換え完了")
            self.print_info(f"  出力先: {output_base_dir}")
            
            for time_id, count in results.items():
                self.print_info(f"    [{time_id}]: {count}個")
        
        return True
    
    def run_all_phases(self):
        """全フェーズを順番に実行"""
        self.print_header("小規模実験 - 全フェーズ実行")
        
        phases = [
            (0, "データベースセットアップ", self.phase0_setup),
            (1, "EXPLAIN JSON生成", self.phase1_generate_explain_json),
            (2, "クエリパース", self.phase2_parse_queries),
            (3, "ILP最適化", self.phase3_optimize),
            (4, "MV生成SQL作成", self.phase4_generate_mv_sql),
            (5, "MV作成", self.phase5_create_mvs),
            (6, "クエリ書き換え", self.phase6_rewrite_queries),
        ]
        
        for phase_num, phase_name, phase_func in phases:
            if not phase_func():
                print(f"\n✗ フェーズ{phase_num}で失敗しました")
                return False
        
        self.print_header("実験完了！")
        self.print_success("全フェーズが正常に完了しました")
        self.print_info(f"結果は {self.exp_dir} に保存されています")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="小規模実験 - 段階的実行")
    parser.add_argument(
        '--mode',
        type=str,
        default='normal',
        choices=['normal', 'time-dependent'],
        help='実行モード (normal: 単一頻度, time-dependent: 時刻依存型)'
    )
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', '0', '1', '2', '3', '4', '5', '6'],
        help='実行するフェーズ (all: 全実行, 0-6: 個別実行)'
    )
    parser.add_argument(
        '--algorithm',
        type=str,
        default=None,
        choices=['normal', 'bigsubs', 'frequency'],
        help='使用するアルゴリズム (時刻依存型モードのphase 3で必須)'
    )
    parser.add_argument(
        '--time-id',
        type=str,
        default=None,
        help='タイムステップID (時刻依存型モードのphase 5で必須、例: morning, evening)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test/config.yaml',
        help='設定ファイルのパス'
    )
    
    args = parser.parse_args()
    
    # 実験インスタンス作成
    exp = SmallExperiment(args.config, mode=args.mode)
    
    # モードに応じたフェーズ実行
    if args.mode == "time-dependent":
        # 時刻依存型モードで実行可能なフェーズ: 2, 3, 4, 5, 6
        if args.phase in ['all', '0', '1']:
            print("時刻依存型モードではフェーズ2（パース）、フェーズ3（最適化）、")
            print("フェーズ4（SQL生成）、フェーズ5（MV作成）、フェーズ6（書き換え）のみ実行可能です")
            print("使用例:")
            print("  python experiments/small_test/run_experiment.py --mode time-dependent --phase 2")
            print("  python experiments/small_test/run_experiment.py --mode time-dependent --phase 3 --algorithm normal")
            print("  python experiments/small_test/run_experiment.py --mode time-dependent --phase 4")
            print("  python experiments/small_test/run_experiment.py --mode time-dependent --phase 5 --time-id morning")
            print("  python experiments/small_test/run_experiment.py --mode time-dependent --phase 6")
            sys.exit(1)
        
        if args.phase == '2':
            success = exp.phase2_parse_queries()
        elif args.phase == '3':
            success = exp.phase3_optimize(algorithm=args.algorithm)
        elif args.phase == '4':
            success = exp.phase4_generate_mv_sql()
        elif args.phase == '5':
            success = exp.phase5_create_mvs(time_id=args.time_id)
        elif args.phase == '6':
            success = exp.phase6_rewrite_queries()
        else:
            parser.print_help()
            success = False
    else:
        # 通常モード
        if args.phase == 'all':
            success = exp.run_all_phases()
        elif args.phase == '0':
            success = exp.phase0_setup()
        elif args.phase == '1':
            success = exp.phase1_generate_explain_json()
        elif args.phase == '2':
            success = exp.phase2_parse_queries()
        elif args.phase == '3':
            success = exp.phase3_optimize()
        elif args.phase == '4':
            success = exp.phase4_generate_mv_sql()
        elif args.phase == '5':
            success = exp.phase5_create_mvs()
        elif args.phase == '6':
            success = exp.phase6_rewrite_queries()
        else:
            print(f"不明なフェーズ: {args.phase}")
            success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
