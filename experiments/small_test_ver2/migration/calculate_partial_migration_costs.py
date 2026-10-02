#!/usr/bin/env python3
"""
partial_migration_plans.jsonのコストを実測

使い方:
    python experiments/small_test_ver2/migration/calculate_partial_migration_costs.py --query-set job --input partial_migration_non_leaf_100_non_leaf_200.json
"""

import argparse
import json
import psycopg2
import re
import sys
import yaml
from pathlib import Path
from typing import Dict, Set, Any

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class PartialMigrationCostCalculator:
    """partial_migration_plans.jsonのマイグレーションコストを実測するクラス"""
    
    def __init__(self, settings: Settings, query_set: str = "job_like", input_file: str = "partial_migration_plans.json"):
        """
        Args:
            settings: config.yamlから読み込んだSettings
            query_set: クエリセット名
            input_file: 入力ファイル名（partial_migration_plans.json など）
        """
        self.settings = settings
        self.query_set = query_set
        self.input_file = input_file
        
        # パス設定
        migration_dir = Path(__file__).parent.parent / "04_migration" / query_set
        self.partial_plans_path = migration_dir / input_file
        self.full_plans_path = migration_dir / "migration_plans.json"
        self.output_dir = migration_dir
        
        # データロード
        self.partial_plans = self._load_json(self.partial_plans_path)
        self.full_plans = self._load_json(self.full_plans_path)
        
        # 結果保存用
        self.costs = {}
        self.explain_results = {}
        self.required_mvs: Set[str] = set()
    
    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """JSONファイルを読み込み"""
        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_connection(self):
        """データベース接続を取得"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    
    def collect_required_mvs(self) -> Set[str]:
        """partial_plans内で必要なMVをすべて収集"""
        print("\n" + "="*70)
        print("必要なMVを収集中...")
        print("="*70)
        
        required_mvs = set()
        
        for node_id, plans in self.partial_plans.items():
            print(f"  ノード: {node_id}")
            
            for plan_key, sql in plans.items():
                # "NON_MIGRATE"や生成失敗はスキップ
                if sql in ["NON_MIGRATE", "CREATE MATERIALIZED VIEW (generation failed)"]:
                    continue
                
                # plan_keyから依存MVを抽出
                # 例: "['leaf_39', 'non_leaf_99']" -> ['leaf_39', 'non_leaf_99']
                try:
                    if plan_key != "[]":
                        # Pythonリテラルとしてパース
                        dependencies = eval(plan_key)
                        if isinstance(dependencies, list):
                            for dep in dependencies:
                                # 自分自身は除外（NON_MIGRATEケース）
                                if dep != node_id:
                                    required_mvs.add(dep)
                except Exception as e:
                    print(f"    警告: plan_key '{plan_key}' のパースに失敗: {e}")
        
        self.required_mvs = required_mvs
        
        print(f"\n  必要なMV数: {len(required_mvs)}個")
        if required_mvs:
            print(f"  MV一覧: {sorted(required_mvs)[:10]}{'...' if len(required_mvs) > 10 else ''}")
        print("="*70 + "\n")
        
        return required_mvs
    
    def create_required_mvs(self):
        """必要なMVを作成（migration_plans.jsonの"[]"プランを使用）"""
        if not self.required_mvs:
            print("作成すべきMVがありません")
            return True
        
        print("\n" + "="*70)
        print(f"必要なMVを作成中（{len(self.required_mvs)}個）...")
        print("="*70)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        try:
            for mv_id in sorted(self.required_mvs):
                print(f"  {mv_id}", end=" ... ")
                
                # full_plans から "[]" プランのSQLを取得
                if mv_id not in self.full_plans:
                    print(f"✗ migration_plans.json に存在しません")
                    error_count += 1
                    continue
                
                if "[]" not in self.full_plans[mv_id]:
                    print(f"✗ \"[]\"プランが存在しません")
                    error_count += 1
                    continue
                
                mv_sql = self.full_plans[mv_id]["[]"]
                
                if not mv_sql or not isinstance(mv_sql, str) or not mv_sql.startswith("CREATE MATERIALIZED VIEW"):
                    print("✗ 無効なSQL")
                    error_count += 1
                    continue
                
                try:
                    # 既存MVを削除
                    drop_sql = f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;"
                    cursor.execute(drop_sql)
                    
                    # MV作成
                    cursor.execute(mv_sql)
                    conn.commit()
                    
                    print("✓ 作成完了")
                    created_count += 1
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    error_msg = str(e).split('\n')[0]
                    print(f"✗ エラー: {error_msg}")
                    error_count += 1
        
        finally:
            cursor.close()
            conn.close()
        
        print("\n" + "="*70)
        print(f"MV作成完了: 成功={created_count}, スキップ={skipped_count}, エラー={error_count}")
        print("="*70 + "\n")
        
        return error_count == 0
    
    def analyze_required_mvs(self):
        """作成したMVに対してANALYZEを実行"""
        if not self.required_mvs:
            print("ANALYZEすべきMVがありません")
            return
        
        print("\n" + "="*70)
        print(f"MVの統計情報を更新中（ANALYZE）...")
        print("="*70)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for mv_id in sorted(self.required_mvs):
                print(f"  ANALYZE {mv_id}", end=" ... ")
                
                try:
                    cursor.execute(f"ANALYZE {mv_id};")
                    conn.commit()
                    print("✓ 完了")
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    error_msg = str(e).split('\n')[0]
                    print(f"✗ エラー: {error_msg}")
        
        finally:
            cursor.close()
            conn.close()
        
        print("\n" + "="*70)
        print(f"統計情報更新完了")
        print("="*70 + "\n")
    
    def _extract_select_from_create_mv(self, sql: str) -> str:
        """CREATE MATERIALIZED VIEW文からSELECT文を抽出"""
        if not sql or not isinstance(sql, str):
            return ""
        
        # "NON_MIGRATE"や生成失敗はスキップ
        if sql in ["NON_MIGRATE", "CREATE MATERIALIZED VIEW (generation failed)"]:
            return ""
        
        # CREATE MATERIALIZED VIEW ... AS 以降を抽出
        match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        else:
            return ""
    
    def _explain_sql(self, sql: str) -> tuple[float, dict]:
        """SQLをEXPLAINし、totalcostとJSON結果を取得"""
        select_sql = self._extract_select_from_create_mv(sql)
        
        if not select_sql:
            return 0.0, {}
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # EXPLAIN を実行（Bitmap Scanを無効化）
                    cursor.execute("SET enable_bitmapscan = off")
                    explain_query = f"EXPLAIN (FORMAT JSON) {select_sql}"
                    cursor.execute(explain_query)
                    result = cursor.fetchone()
                    
                    if result and result[0]:
                        json_result = result[0][0]
                        cost = float(json_result.get('Plan', {}).get('Total Cost', 0.0))
                        return cost, json_result
                    else:
                        return 0.0, {}
        
        except Exception as e:
            print(f"    エラー: EXPLAIN失敗 - {str(e).split(chr(10))[0]}")
            return 0.0, {}
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのマイグレーションプランのコストを計算"""
        print("\n" + "="*70)
        print("マイグレーションコストを計算中...")
        print("="*70)
        
        total_plans = sum(len(plans) for plans in self.partial_plans.values())
        processed = 0
        
        for node_id, plans in self.partial_plans.items():
            print(f"\n  ノード: {node_id} ({len(plans)}個のプラン)")
            self.costs[node_id] = {}
            self.explain_results[node_id] = {}
            
            for plan_key, sql in plans.items():
                processed += 1
                print(f"    [{processed}/{total_plans}] {plan_key[:50]}...", end=" ")
                
                cost, json_result = self._explain_sql(sql)
                self.costs[node_id][plan_key] = cost
                self.explain_results[node_id][plan_key] = json_result
                
                print(f"→ {cost:.2f}")
        
        print("\n" + "="*70)
        print(f"計算完了: {len(self.costs)}ノード, {total_plans}プラン")
        print("="*70 + "\n")
        
        return self.costs
    
    def save_costs(self):
        """計算したコストをJSONファイルに保存"""
        # 入力ファイル名から出力ファイル名を生成
        # 例: partial_migration_non_leaf_100.json -> partial_migration_costs_non_leaf_100.json
        input_stem = Path(self.input_file).stem
        if input_stem.startswith("partial_migration_"):
            output_stem = input_stem.replace("partial_migration_", "partial_migration_costs_")
        else:
            output_stem = f"{input_stem}_costs"
        
        output_file = self.output_dir / f"{output_stem}.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            
            print(f"✓ マイグレーションコストを保存: {output_file}")
            
            # 統計情報を表示
            total_plans = sum(len(plans) for plans in self.costs.values())
            total_cost = sum(
                cost for plans in self.costs.values() 
                for cost in plans.values()
            )
            
            print(f"  - ノード数: {len(self.costs)}個")
            print(f"  - 総プラン数: {total_plans}個")
            print(f"  - 総コスト: {total_cost:.2f}")
            
        except Exception as e:
            print(f"✗ JSONファイルの保存に失敗: {e}")
    
    def save_explain_samples(self):
        """各ノードの代表的なプランのEXPLAIN JSONを保存"""
        print("\n" + "="*70)
        print("サンプルEXPLAIN JSONを保存中...")
        print("="*70)
        
        for node_id, plans in self.partial_plans.items():
            samples = {}
            
            # []プラン（MV無し）を取得
            if "[]" in plans:
                samples["no_mv"] = {
                    "plan_key": "[]",
                    "sql": plans["[]"],
                    "explain_json": self.explain_results.get(node_id, {}).get("[]", {}),
                    "cost": self.costs.get(node_id, {}).get("[]", 0.0)
                }
            
            # MVありプランを2つ取得（[]以外）
            mv_plans = [(k, v) for k, v in plans.items() if k != "[]" and v not in ["NON_MIGRATE", "CREATE MATERIALIZED VIEW (generation failed)"]]
            
            # 最初の2つのMVありプランを選択
            for i, (plan_key, sql) in enumerate(mv_plans[:2], 1):
                samples[f"with_mv_{i}"] = {
                    "plan_key": plan_key,
                    "sql": sql,
                    "explain_json": self.explain_results.get(node_id, {}).get(plan_key, {}),
                    "cost": self.costs.get(node_id, {}).get(plan_key, 0.0)
                }
            
            # サンプルが存在する場合のみ保存
            if samples:
                output_file = self.output_dir / f"partial_explain_{node_id}.json"
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(samples, f, indent=2, ensure_ascii=False)
                    print(f"  ✓ {node_id}: {len(samples)}個のプランを保存 -> {output_file.name}")
                except Exception as e:
                    print(f"  ✗ {node_id}: 保存失敗 - {e}")
        
        print("\n" + "="*70)
        print("サンプルEXPLAIN JSON保存完了")
        print("="*70 + "\n")
    
    def cleanup_mvs(self):
        """作成したMVをクリーンアップ（削除）"""
        if not self.required_mvs:
            return
        
        print("\n" + "="*70)
        print("作成したMVをクリーンアップ中...")
        print("="*70)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for mv_id in sorted(self.required_mvs):
                print(f"  DROP {mv_id}", end=" ... ")
                
                try:
                    drop_sql = f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;"
                    cursor.execute(drop_sql)
                    conn.commit()
                    print("✓ 削除完了")
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    error_msg = str(e).split('\n')[0]
                    print(f"✗ エラー: {error_msg}")
        
        finally:
            cursor.close()
            conn.close()
        
        print("\n" + "="*70)
        print("クリーンアップ完了")
        print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="partial_migration_plans.jsonのマイグレーションコストを実測"
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセット名 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="partial_migration_plans.json",
        help="入力ファイル名 (デフォルト: partial_migration_plans.json)"
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="計算後にMVを削除しない"
    )
    
    args = parser.parse_args()
    
    # config.yamlから設定を読み込み
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    temp_config = config_path.parent / '.temp_config.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
    finally:
        if temp_config.exists():
            temp_config.unlink()
    
    # コスト計算クラスのインスタンス化
    calculator = PartialMigrationCostCalculator(
        settings=settings,
        query_set=args.query_set,
        input_file=args.input
    )
    
    try:
        # ステップ1: 必要なMVを収集
        print("\n【ステップ1】必要なMVを収集")
        calculator.collect_required_mvs()
        
        # ステップ2: 必要なMVを作成
        print("\n【ステップ2】必要なMVを作成")
        if not calculator.create_required_mvs():
            print("\nMV作成中にエラーが発生しました。")
            print("一部のコスト計算が不正確になる可能性があります。")
            print("続行しますか？ (y/N): ", end="")
            
            response = input().strip().lower()
            if response != 'y':
                print("処理を中断します。")
                sys.exit(1)
        
        # ステップ3: 統計情報を更新
        print("\n【ステップ3】統計情報を更新")
        calculator.analyze_required_mvs()
        
        # ステップ4: コストを計算
        print("\n【ステップ4】マイグレーションコストを計算")
        calculator.calculate_all_costs()
        
        # ステップ5: 結果を保存
        print("\n【ステップ5】結果を保存")
        calculator.save_costs()
        
        # ステップ6: サンプルEXPLAIN JSONを保存
        print("\n【ステップ6】サンプルEXPLAIN JSONを保存")
        calculator.save_explain_samples()
        
    finally:
        # クリーンアップ（オプション）
        if not args.no_cleanup:
            calculator.cleanup_mvs()
    
    print("\n✓ 処理完了")


if __name__ == "__main__":
    main()
