# 全プランをexplain
import json
import psycopg2
import yaml
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings

class MigrationCostCalculator:
    """マイグレーションプランのコストを計算するクラス
        
        migration_plans.jsonから各SQLを読み込み、EXPLAINでtotalcostを取得。
        SQLがない場合はコストを0とする。
    """

    def __init__(self, settings: Settings, query_set: str = "job_like"):
        """
        Args:
            settings: config.yamlから読み込んだSettings
            json_file_path: migration_plans.jsonのパス（省略時はデフォルトパス）
        """
        self.settings = settings
        self.query_set = query_set
        
        # JSONファイルのパス設定
        self.json_file_path = Path(__file__).parent.parent / "04_migration" / query_set / "migration_plans.json"
        
        # 出力ディレクトリのパス
        self.output_dir = self.json_file_path.parent
        
        self.plans = self._load_plans()
        self.costs = {}

    def _load_plans(self) -> Dict[str, Any]:
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    def _get_connection(self):
        """データベース接続を取得（config.yamlの設定を使用）"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    
    def create_all_mvs(self):
        """migration_plans.jsonの"[]"キーのSQLを使ってすべてのMVを作成する
        
        既存MVを使わないプラン（"[]"）のSQLを直接実行してMVを作成します。
        これにより、既存MVを使用するプランのコスト計算が可能になります。
        """
        print("\n" + "="*70)
        print("すべてのMVを作成中（migration_plans.jsonの\"[]\"プランを使用）...")
        print("="*70)
        
        # データベース接続
        conn = self._get_connection()
        cursor = conn.cursor()
        
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        try:
            for node_id in sorted(self.plans.keys()):
                print(f"  処理中: {node_id}", end=" ... ")
                
                # "[]"キーのSQLを取得（既存MVを使わないプラン）
                if "[]" not in self.plans[node_id]:
                    print("「[]」プランなし")
                    skipped_count += 1
                    continue
                
                mv_sql = self.plans[node_id]["[]"]
                
                if not mv_sql or not isinstance(mv_sql, str) or not mv_sql.startswith("CREATE MATERIALIZED VIEW"):
                    print("無効なSQL")
                    skipped_count += 1
                    continue
                
                try:
                    # 既存MVを削除（存在する場合）
                    drop_sql = f"DROP MATERIALIZED VIEW IF EXISTS {node_id} CASCADE;"
                    cursor.execute(drop_sql)
                    
                    # MV作成
                    cursor.execute(mv_sql)
                    conn.commit()
                    
                    print("✓ 作成完了")
                    created_count += 1
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    error_msg = str(e).split('\n')[0]  # 最初の行のみ表示
                    print(f"✗ エラー: {error_msg}")
                    error_count += 1
                    
        finally:
            cursor.close()
            conn.close()
        
        print("\n" + "="*70)
        print(f"MV作成完了: 成功={created_count}, スキップ={skipped_count}, エラー={error_count}")
        print("="*70 + "\n")
        
        return created_count > 0
    
    def analyze_all_mvs(self):
        """すべてのMaterialized Viewに対してANALYZEを実行して統計情報を更新する
        
        これによりクエリプランナーが正確なコスト見積もりを行えるようになります。
        """
        print("\n" + "="*70)
        print("すべてのMVの統計情報を更新中（ANALYZE）...")
        print("="*70)
        
        # データベース接続
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 既存のMV一覧を取得
            cursor.execute("""
                SELECT matviewname 
                FROM pg_matviews 
                WHERE schemaname = 'public'
                ORDER BY matviewname;
            """)
            
            mv_names = [row[0] for row in cursor.fetchall()]
            
            if not mv_names:
                print("  既存のMVが見つかりません")
                return
            
            print(f"  対象MV数: {len(mv_names)}")
            
            # 各MVに対してANALYZEを実行
            for mv_name in mv_names:
                print(f"  ANALYZE {mv_name}", end=" ... ")
                
                try:
                    cursor.execute(f"ANALYZE {mv_name};")
                    conn.commit()
                    print("✓ 完了")
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    error_msg = str(e).split('\n')[0]  # 最初の行のみ表示
                    print(f"✗ エラー: {error_msg}")
            
            print("\n" + "="*70)
            print(f"統計情報更新完了: {len(mv_names)}個のMV")
            print("="*70 + "\n")
            
        finally:
            cursor.close()
            conn.close()
    
    def _explain_sql(self, sql: str) -> float:
        """SQLをEXPLAINし、totalcostを取得
        
        Args:
            sql: 実行するSQL
            
        Returns:
            totalcost（float）、エラー時は0
        """
        if not sql or sql.strip() == "" or not isinstance(sql, str):
            return 0.0
        
        # "node_id"形式の文字列はSQLではないのでスキップ
        if not sql.startswith("CREATE MATERIALIZED VIEW"):
            return 0.0
        
        # CREATE MATERIALIZED VIEWの場合、正規表現でSELECT部分を抽出
        # re.DOTALLで改行も含めてマッチ
        match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
        else:
            # "AS" が見つからない場合はエラー
            print(f"  CREATE文のパースエラー: {sql[:80]}...")
            return 0.0
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # EXPLAIN を実行
                    explain_query = f"EXPLAIN (FORMAT JSON) {sql}"
                    cursor.execute(explain_query)
                    result = cursor.fetchone()

                    if result and result[0]:
                        # JSON形式の結果からtotal_costを取得
                        plan = result[0][0]  # 最初のプラン
                        return float(plan.get('Plan', {}).get('Total Cost', 0.0))
                    else:
                        return 0.0
        except Exception as e:
            print(f"  エラー: EXPLAINの実行失敗 - {e}")
            print(f"  SQL: {sql[:100]}...")
            return 0.0
        

    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのマイグレーションプランのコストを計算し、JSONファイルに保存
        
        Returns:
            ノード名 -> {プランキー: コスト} の辞書
        """
        print("マイグレーションコストを計算中...")
        
        for node, plans in self.plans.items():
            print(f"  ノード: {node}")
            self.costs[node] = {}
            
            for plan_key, sql in plans.items():
                cost = self._explain_sql(sql)
                self.costs[node][plan_key] = cost

        print(f"  計算完了: {len(self.costs)}個のノード")
        
        # コストをJSONファイルに保存
        self.save_costs()
        
        return self.costs
    
    def save_costs(self, output_file: str = "migration_costs.json"):
        """計算したコストをJSONファイルに保存"""
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"マイグレーションコストを保存しました: {output_path}")
        except Exception as e:
            print(f"JSONファイルの保存に失敗しました: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="マイグレーションプランのコスト計算")
    parser.add_argument(
        "--query-set",
        type = str,
        default = "job_like",
        help = "使用するクエリセットの名前 (デフォルト: job_like)"
    )

    args = parser.parse_args()

    # config.yamlから設定を読み込み（UTF-8で明示的に読み込み）
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    # UTF-8でYAMLを読み込む
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    # 一時ファイルに書き込んでからSettingsを読み込む
    temp_config = config_path.parent / '.temp_config.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
    finally:
        if temp_config.exists():
            temp_config.unlink()
    
    # コスト計算クラスのインスタンス化
    calculator = MigrationCostCalculator(settings, query_set=args.query_set)
    
    # ステップ1: すべてのMVを事前に作成
    print("\n【ステップ1】すべてのMVを作成")
    if not calculator.create_all_mvs():
        print("MV作成に失敗しました。処理を中断します。")
        sys.exit(1)
    
    # ステップ2: 統計情報を更新（ANALYZE）
    print("\n【ステップ2】統計情報を更新")
    calculator.analyze_all_mvs()
    
    # ステップ3: すべてのコストを計算（自動的に保存される）
    print("\n【ステップ3】マイグレーションコストを計算")
    costs = calculator.calculate_all_costs()
    
    print("\n処理完了")