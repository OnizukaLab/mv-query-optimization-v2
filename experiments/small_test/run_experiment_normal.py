#!/usr/bin/env python3
"""
小規模実験 - 通常モード実行スクリプト

単一の頻度設定でMV最適化を実行します。

使い方:
    python experiments/small_test/run_experiment_normal.py --phase all
    python experiments/small_test/run_experiment_normal.py --phase 2
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
from src.utils.legacy import get_all_job_queries, natural_sort_key


class NormalModeExperiment:
    """通常モード実験の段階的実行クラス"""
    
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
        self.parsed_dir = self.exp_dir / "03_parsed"
        self.optimized_dir = self.exp_dir / "04_optimized"
        self.mv_sql_dir = self.exp_dir / "05_mv_sql"
        self.rewritten_dir = self.exp_dir / "06_rewritten"
        
        self.pickle_path = self.exp_dir / "qp_class.pkl"
        self.qp: Optional[QueryParser] = None
        self.result = None
    
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
        
        try:
            result = subprocess.run(
                ["psql", "-U", "postgres", "-f", str(setup_file)],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',
                env={**subprocess.os.environ, 'PGPASSWORD': ''}
            )
            print(result.stdout)
            self.print_success("データベースセットアップ完了")
            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"エラー: {e}")
            if e.stderr:
                print(f"  stderr: {e.stderr}")
            return False
        except FileNotFoundError:
            self.print_error("psql コマンドが見つかりません")
            self.print_info("PostgreSQL のパスを確認してください")
            return False
    
    def phase1_generate_explain_json(self):
        """フェーズ1: EXPLAIN JSON 生成"""
        self.print_header("EXPLAIN JSON 生成", 1)
        
        query_files = sorted(self.queries_dir.glob("*.sql"))
        
        if not query_files:
            self.print_error(f"{self.queries_dir} にクエリファイルが見つかりません")
            return False
        
        self.print_info(f"{len(query_files)}個のクエリファイルを処理します")
        
        job_dir = self.json_dir / "job"
        job_dir.mkdir(parents=True, exist_ok=True)
        
        for query_file in query_files:
            output_file = job_dir / f"{query_file.stem}.json"
            
            self.print_info(f"処理中: {query_file.name}")
            
            # クエリを読み込み（コメント行を除去）
            with open(query_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
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
                
                json_data = json.loads(result.stdout.strip())
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                self.print_success(f"{output_file.name} を生成")
                
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                self.print_error(f"{query_file.name} の処理に失敗: {e}")
                return False
        
        return True
    
    def phase2_parse_queries(self):
        """フェーズ2: クエリパース（頻度重み付け）"""
        self.print_header("クエリパース", 2)
        
        from experiments.small_test.frequency_weighted_parser import FrequencyWeightedParser
        
        self.print_info("FrequencyWeightedParser を初期化")
        
        frequency_file = self.queries_dir / "frequency.json"
        
        if frequency_file.exists():
            self.print_info(f"頻度情報ファイル: {frequency_file}")
            self.qp = FrequencyWeightedParser(self.settings, str(frequency_file))
        else:
            self.print_info("頻度情報ファイルが見つかりません。通常のパーサーを使用")
            self.qp = QueryParser(self.settings)
        
        self.print_info("クエリをパース中...")
        try:
            query_dir = str(self.json_dir)
            files, _ = get_all_job_queries(query_dir)
            files = sorted(files, key=natural_sort_key)
            
            self.qp.query_parse(
                q_num=0,
                path=str(self.json_dir),
                insert_query=self.settings.optimization.insert_queries
            )
            
            insert_query = self.settings.optimization.insert_queries
            
            if isinstance(self.qp, FrequencyWeightedParser):
                self.qp.apply_frequency_weights(files)
                self.qp.calculate_maintenance_costs(insert_query)
            
            self.print_success(f"{len(self.qp.query)}個のクエリをパース完了")
            self.print_info(f"  リーフノード数: {len(self.qp.qm.leaf_nodes_map)}")
            self.print_info(f"  非リーフノード数: {len(self.qp.qm.non_leaf_nodes_map)}")
            self.print_info(f"  総ノード数: {self.qp.s_num}")
            
            self._save_parse_results()
            
            return True
            
        except Exception as e:
            self.print_error(f"クエリパースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_parse_results(self):
        """パース結果を保存"""
        with open(self.pickle_path, 'wb') as f:
            pickle.dump(self.qp, f)
        
        self.print_success(f"パース結果を {self.pickle_path} に保存")
        
        summary = {
            "num_queries": len(self.qp.query),
            "num_leaf_nodes": len(self.qp.qm.leaf_nodes_map),
            "num_non_leaf_nodes": len(self.qp.qm.non_leaf_nodes_map),
            "total_nodes": self.qp.s_num,
            "node_list": self.qp.node_list,
            "u_ij_shape": [len(self.qp.u_ij), len(self.qp.u_ij[0]) if self.qp.u_ij else 0],
            "b_j_length": len(self.qp.b_j),
            "m_cost_length": len(self.qp.m_cost),
        }
        summary_path = self.parsed_dir / "parse_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_success(f"サマリーを {summary_path} に保存")
    
    def phase3_optimize(self):
        """フェーズ3: ILP最適化（normalアルゴリズムのみ）"""
        self.print_header("ILP最適化", 3)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            self.print_info("先にフェーズ2を実行してください")
            return False
        
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        self.print_info("NORMAL アルゴリズムを実行")
        
        try:
            B_max = self.settings.optimization.storage_limit_bytes
            
            optimizer = OptimizerFactory.create(
                "normal",
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
            self.result = optimizer.optimize()
            
            storage_mb = self.result.total_storage / (1024 * 1024)
            self.print_success(f"{len(self.result.selected_views)}個のMVを選択")
            self.print_info(f"  総ユーティリティ: {self.result.total_utility:.2f}")
            self.print_info(f"  使用ストレージ: {storage_mb:.2f} MB")
            self.print_info(f"  実行時間: {self.result.execution_time:.2f} 秒")
            
            result_dir = self.optimized_dir / "normal"
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / "result.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(self.result.to_dict(), f, indent=2, ensure_ascii=False)
            self.print_success(f"結果を {result_file} に保存")
            
            return True

        except Exception as e:
            self.print_error(f"最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase4_generate_mv_sql(self):
        """フェーズ4: MV生成SQL作成"""
        self.print_header("MV生成SQL作成", 4)
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        if self.result is None:
            result_file = self.optimized_dir / "normal" / "result.json"
            if not result_file.exists():
                self.print_error("最適化結果が見つかりません")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                self.result = result_data
        
        try:
            from experiments.small_test.enhanced_mv_generator import EnhancedMVGenerator
            from experiments.small_test.small_test_schema_provider import SmallTestSchemaProvider
            
            selected_views = self.result.get('selected_views', []) if isinstance(self.result, dict) else self.result.selected_views
            
            selected_node_ids = set()
            for view in selected_views:
                node_id = view.get('node_id') if isinstance(view, dict) else view.node_id
                selected_node_ids.add(node_id)
            
            schema_provider = SmallTestSchemaProvider()
            
            mv_generator = EnhancedMVGenerator(
                query_manager=self.qp.qm,
                schema_provider=schema_provider,
                selected_mvs=selected_node_ids
            )
            
            output_dir = self.mv_sql_dir / "normal"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "create_mvs.sql"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("-- =====================================================\n")
                f.write("-- NORMAL アルゴリズムで選択されたMV作成SQL\n")
                f.write("-- =====================================================\n\n")
                f.write(f"\\c {self.settings.database.database}\n\n")
                
                mv_count = 0
                for view in selected_views:
                    node_id = view.get('node_id') if isinstance(view, dict) else view.node_id
                    
                    f.write(f"-- ノード: {node_id}\n")
                    
                    mv_sql = mv_generator.generate_mv_sql(node_id)
                    
                    if mv_sql:
                        f.write(f"{mv_sql}\n\n")
                        mv_count += 1
                    else:
                        self.print_info(f"⚠ {node_id} のSQL生成に失敗しました")
            
            self.print_success(f"{mv_count}個のMV作成SQLを生成 → {output_file}")
            return True
            
        except Exception as e:
            self.print_error(f"SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase5_create_mvs(self):
        """フェーズ5: MV作成（実際にDBに作成）"""
        self.print_header("MV作成（データベース）", 5)
        
        sql_file = self.mv_sql_dir / "normal" / "create_mvs.sql"
        
        if not sql_file.exists():
            self.print_error("MV作成SQLファイルが見つかりません")
            self.print_info("先にフェーズ4を実行してください")
            return False
        
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
            
            self.print_success("MV作成完了")
            self._list_created_mvs()
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.print_error(f"エラー: {e}")
            if e.stderr:
                print(f"  stderr: {e.stderr}")
            return False
    
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
            self.print_error("MV一覧の取得に失敗")
    
    def phase6_rewrite_queries(self):
        """フェーズ6: クエリ書き換え"""
        self.print_header("クエリ書き換え", 6)
        
        from experiments.small_test.query_rewriter import QueryRewriter
        
        if self.qp is None:
            self.print_info("QueryParserを読み込み中...")
            if not self.pickle_path.exists():
                self.print_error("パース結果が見つかりません")
                return False
            
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        result_file = self.optimized_dir / "normal" / "result.json"
        if not result_file.exists():
            self.print_error("最適化結果が見つかりません")
            return False
        
        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        # mv_selectionsを作成
        mv_selections = {}
        for i, query_views in enumerate(result_data.get('selected_views_per_query', [])):
            mv_selections[str(i)] = [v['node_id'] for v in query_views]
        
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        rewriter = QueryRewriter(self.qp.qm, mv_selections)
        
        output_dir = self.rewritten_dir / "normal"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        rewritten_count = rewriter.rewrite_all_queries(query_files, output_dir)
        
        self.print_success(f"{rewritten_count}個のクエリを書き換え完了")
        self.print_info(f"  出力先: {output_dir}")
        
        return True
    
    def run_all_phases(self):
        """全フェーズを順番に実行"""
        self.print_header("小規模実験（通常モード） - 全フェーズ実行")
        
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
    parser = argparse.ArgumentParser(description="小規模実験 - 通常モード")
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', '0', '1', '2', '3', '4', '5', '6'],
        help='実行するフェーズ (all: 全実行, 0-6: 個別実行)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test/config.yaml',
        help='設定ファイルのパス'
    )
    
    args = parser.parse_args()
    
    exp = NormalModeExperiment(args.config)
    
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
