#!/usr/bin/env python3
"""
ルートノードMVのサイズ計測スクリプト

使用方法:
    python measure_root_mv_sizes.py --query-set job

処理内容:
    1. 既存のMVを全て削除
    2. ANALYZEを実行
    3. ルートノードに該当するMVを作成（113個）
    4. 各MVのサイズを計測
    5. 結果をJSONファイルに出力
"""

import json
import psycopg2
import yaml
import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Set

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class RootMVSizeMeasurer:
    """ルートノードMVのサイズを計測するクラス"""

    def __init__(self, settings: Settings, query_set: str = "job"):
        self.settings = settings
        self.query_set = query_set
        self.exp_dir = Path(__file__).parent.parent
        
        # パス設定
        self.json_dir = self.exp_dir / "02_json" / query_set
        self.migration_plans_path = self.exp_dir / "04_migration" / query_set / "simple_migration_plans.json"
        self.output_dir = self.exp_dir / "04_migration" / query_set
        
    def _get_connection(self):
        """データベース接続を取得"""
        return psycopg2.connect(
            database=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password,
            host='localhost'
        )
    
    def get_root_nodes(self) -> Set[str]:
        """各クエリのルートノードIDを取得"""
        root_nodes = set()
        
        if not self.json_dir.exists():
            print(f"Error: {self.json_dir} not found")
            return root_nodes
            
        for filepath in self.json_dir.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # EXPLAIN構造の差異に対応
                if isinstance(data, list) and len(data) > 0:
                    root = data[0].get('Plan')
                else:
                    root = data.get('Plan')
                    
                if root and 'node_id' in root:
                    root_nodes.add(root['node_id'])
                    
            except Exception as e:
                print(f"  Warning: Error parsing {filepath.name}: {e}")
                
        return root_nodes
    
    def load_migration_plans(self) -> Dict:
        """マイグレーションプランを読み込み"""
        if not self.migration_plans_path.exists():
            print(f"Error: {self.migration_plans_path} not found")
            return {}
            
        with open(self.migration_plans_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def drop_all_materialized_views(self, conn):
        """既存のMVを全て削除"""
        print("\n" + "=" * 70)
        print("既存のマテリアライズドビューを削除中...")
        print("=" * 70)
        
        with conn.cursor() as cursor:
            # MVの一覧を取得
            cursor.execute("""
                SELECT schemaname, matviewname 
                FROM pg_matviews 
                WHERE schemaname = 'public'
            """)
            mvs = cursor.fetchall()
            
            if not mvs:
                print("  削除対象のMVはありません")
                return 0
            
            count = 0
            for schema, mv_name in mvs:
                try:
                    cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {schema}.{mv_name} CASCADE")
                    count += 1
                except Exception as e:
                    print(f"  Warning: {mv_name} の削除に失敗: {e}")
                    conn.rollback()
                    continue
            
            conn.commit()
            print(f"  ✓ {count}個のMVを削除しました")
            return count
    
    def run_analyze(self, conn):
        """ANALYZE を実行"""
        print("\n" + "=" * 70)
        print("ANALYZEを実行中...")
        print("=" * 70)
        
        with conn.cursor() as cursor:
            cursor.execute("ANALYZE")
        conn.commit()
        print("  ✓ ANALYZE完了")
    
    def create_root_mvs(self, conn, root_nodes: Set[str], plans: Dict) -> Dict[str, bool]:
        """ルートノードに該当するMVを作成"""
        print("\n" + "=" * 70)
        print(f"ルートノードMVを作成中... ({len(root_nodes)}個)")
        print("=" * 70)
        
        created = {}
        total = len(root_nodes)
        
        for i, node_id in enumerate(sorted(root_nodes), 1):
            if node_id not in plans:
                print(f"  Warning: {node_id} のプランが見つかりません")
                created[node_id] = False
                continue
            
            # "[]" キーからCREATE文を取得
            sql = plans[node_id].get("[]")
            if not sql or sql == "NON_MIGRATE":
                print(f"  Warning: {node_id} の作成SQLがありません")
                created[node_id] = False
                continue
            
            try:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                conn.commit()
                created[node_id] = True
                
                if i % 10 == 0 or i == total:
                    print(f"  進捗: {i}/{total} ({i*100//total}%)")
                    
            except Exception as e:
                print(f"  Error: {node_id} の作成に失敗: {e}")
                conn.rollback()
                created[node_id] = False
        
        success_count = sum(1 for v in created.values() if v)
        print(f"  ✓ {success_count}/{total}個のMVを作成しました")
        return created
    
    def measure_mv_sizes(self, conn, created_mvs: Dict[str, bool]) -> Dict[str, int]:
        """各MVのサイズを計測"""
        print("\n" + "=" * 70)
        print("MVサイズを計測中...")
        print("=" * 70)
        
        sizes = {}
        successful_mvs = [mv for mv, success in created_mvs.items() if success]
        
        with conn.cursor() as cursor:
            for mv_name in successful_mvs:
                try:
                    cursor.execute(f"""
                        SELECT pg_total_relation_size('{mv_name}')
                    """)
                    result = cursor.fetchone()
                    if result:
                        sizes[mv_name] = result[0]
                except Exception as e:
                    print(f"  Warning: {mv_name} のサイズ取得に失敗: {e}")
                    sizes[mv_name] = 0
        
        total_size = sum(sizes.values())
        print(f"  ✓ {len(sizes)}個のMVサイズを計測しました")
        print(f"  合計サイズ: {self._format_bytes(total_size)}")
        
        return sizes
    
    def _format_bytes(self, size: int) -> str:
        """バイト数を読みやすい形式に変換"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if abs(size) < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
    
    def save_results(self, sizes: Dict[str, int], output_file: str = "root_mv_sizes.json"):
        """結果をJSONに保存"""
        output_path = self.output_dir / output_file
        
        # 統計情報を追加
        result = {
            "_metadata": {
                "query_set": self.query_set,
                "total_mvs": len(sizes),
                "total_size_bytes": sum(sizes.values()),
                "total_size_human": self._format_bytes(sum(sizes.values())),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "mv_sizes": sizes
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 結果を保存しました: {output_path}")
        return output_path
    
    def run(self):
        """メイン処理"""
        print("\n" + "=" * 70)
        print(f"ルートノードMVサイズ計測 - クエリセット: {self.query_set}")
        print("=" * 70)
        
        # 1. ルートノードを取得
        root_nodes = self.get_root_nodes()
        print(f"\nルートノード数: {len(root_nodes)}")
        
        if not root_nodes:
            print("Error: ルートノードが見つかりません")
            return
        
        # 2. マイグレーションプランを読み込み
        plans = self.load_migration_plans()
        if not plans:
            return
        
        # 3. データベース処理
        conn = self._get_connection()
        try:
            # 既存MVを削除
            self.drop_all_materialized_views(conn)
            
            # ANALYZEを実行
            self.run_analyze(conn)
            
            # ルートMVを作成
            created_mvs = self.create_root_mvs(conn, root_nodes, plans)
            
            # サイズを計測
            sizes = self.measure_mv_sizes(conn, created_mvs)
            
            # 結果を保存
            self.save_results(sizes)
            
        finally:
            conn.close()
        
        print("\n" + "=" * 70)
        print("処理完了")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="ルートノードMVのサイズ計測")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job",
        help="使用するクエリセットの名前 (デフォルト: job)"
    )
    
    args = parser.parse_args()
    
    # run_experiment_normal.pyと同様に、デフォルトコンストラクタを使用
    settings = Settings()
    
    # 計測を実行
    measurer = RootMVSizeMeasurer(settings, query_set=args.query_set)
    measurer.run()


if __name__ == "__main__":
    main()

