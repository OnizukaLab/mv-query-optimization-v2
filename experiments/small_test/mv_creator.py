#!/usr/bin/env python3
"""
MV作成モジュール

時刻依存型モードで、一つのタイムステップのMVのみを実体化するための処理を提供します。
"""

import subprocess
import json
from pathlib import Path
from typing import Optional, List, Dict


class MVCreator:
    """MV作成クラス"""
    
    def __init__(self, settings, mv_sql_dir: Path, output_dir: Path):
        """初期化
        
        Args:
            settings: 設定オブジェクト
            mv_sql_dir: MV SQLディレクトリ
            output_dir: 出力ディレクトリ（時刻依存型用）
        """
        self.settings = settings
        self.mv_sql_dir = mv_sql_dir
        self.output_dir = output_dir
        self.database = settings.database.database
    
    def create_mvs_for_single_timestep(
        self,
        algorithm: str,
        time_id: str,
        drop_existing: bool = True
    ) -> bool:
        """単一タイムステップのMVを作成
        
        Args:
            algorithm: アルゴリズム名
            time_id: タイムステップID
            drop_existing: 既存MVを削除するか
            
        Returns:
            成功したかどうか
        """
        print(f"\n{'='*70}")
        print(f"MV作成: {algorithm.upper()} - {time_id}")
        print(f"{'='*70}")
        
        # SQLファイルのパス
        sql_file = self.mv_sql_dir / algorithm / time_id / "create_mvs.sql"
        
        if not sql_file.exists():
            print(f"  ✗ SQLファイルが見つかりません: {sql_file}")
            return False
        
        # 既存MVを削除
        if drop_existing:
            print("  → 既存のMVを削除中...")
            if not self._drop_all_mvs():
                print("  ⚠ 既存MV削除でエラーが発生しましたが、続行します")
        
        # MVを作成
        print(f"  → {sql_file} を実行中...")
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
            
            # 作成されたMV数をカウント
            mv_count = result.stdout.count("CREATE MATERIALIZED VIEW")
            
            print(f"  ✓ {mv_count}個のMVを作成しました")
            
            # 作成されたMVを確認
            self._list_created_mvs()
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ エラー: {e}")
            if e.stderr:
                print(f"    stderr: {e.stderr}")
            return False
    
    def create_migration_mvs(
        self,
        algorithm: str,
        from_time_id: str,
        to_time_id: str,
        migration_plan_file: Optional[Path] = None
    ) -> bool:
        """マイグレーションプランに基づいてMVを作成
        
        Args:
            algorithm: アルゴリズム名
            from_time_id: 移行元タイムステップ
            to_time_id: 移行先タイムステップ
            migration_plan_file: マイグレーションプランJSONファイル
            
        Returns:
            成功したかどうか
        """
        print(f"\n{'='*70}")
        print(f"マイグレーション: {from_time_id} → {to_time_id}")
        print(f"{'='*70}")
        
        # マイグレーションプランを読み込み
        if migration_plan_file is None:
            migration_plan_file = self.output_dir / "migration_plan.json"
        
        if not migration_plan_file.exists():
            print(f"  ✗ マイグレーションプランが見つかりません: {migration_plan_file}")
            return False
        
        with open(migration_plan_file, 'r', encoding='utf-8') as f:
            migration_data = json.load(f)
        
        # 対応するマイグレーションキーを探す
        migration_key = f"{from_time_id}_to_{to_time_id}"
        if migration_key not in migration_data:
            # 代替キー形式を試す
            migration_key = f"{from_time_id} -> {to_time_id}"
            if migration_key not in migration_data:
                print(f"  ✗ マイグレーションプランが見つかりません: {migration_key}")
                return False
        
        plan = migration_data[migration_key]
        mv_plans = plan.get('migration_plans_sql', {})
        
        if not mv_plans:
            print("  ⚠ マイグレーションSQLが見つかりません")
            return False
        
        # 一時SQLファイルを作成
        temp_sql_file = self.output_dir / f"migration_{from_time_id}_to_{to_time_id}.sql"
        
        with open(temp_sql_file, 'w', encoding='utf-8') as f:
            f.write("-- =====================================================\n")
            f.write(f"-- マイグレーション: {from_time_id} → {to_time_id}\n")
            f.write("-- =====================================================\n\n")
            f.write(f"\\c {self.database}\n\n")
            
            # 各MVのDROPとCREATEを実行
            for node_id, sql_info in mv_plans.items():
                f.write(f"-- ノード: {node_id}\n")
                f.write(f"{sql_info['drop_sql']}\n")
                f.write(f"{sql_info['create_sql']}\n\n")
        
        print(f"  → マイグレーションSQLを生成: {temp_sql_file}")
        print(f"  → 実行中...")
        
        try:
            result = subprocess.run(
                ["psql", "-U", "postgres", "-f", str(temp_sql_file)],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',
                env={**subprocess.os.environ, 'PGPASSWORD': ''}
            )
            
            # 作成されたMV数をカウント
            mv_count = result.stdout.count("CREATE MATERIALIZED VIEW")
            
            print(f"  ✓ {mv_count}個のMVをマイグレーションしました")
            
            # 作成されたMVを確認
            self._list_created_mvs()
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ エラー: {e}")
            if e.stderr:
                print(f"    stderr: {e.stderr}")
            return False
    
    def _drop_all_mvs(self) -> bool:
        """すべてのMVを削除"""
        # 既存のMV一覧を取得
        query = """
        SELECT matviewname 
        FROM pg_matviews 
        WHERE schemaname = 'public';
        """
        
        try:
            result = subprocess.run(
                ["psql", "-U", "postgres", "-d", self.database,
                 "-t", "-A", "-c", query],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',
                env={**subprocess.os.environ, 'PGPASSWORD': ''}
            )
            
            mv_names = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
            
            if not mv_names:
                print("    削除するMVがありません")
                return True
            
            print(f"    {len(mv_names)}個のMVを削除します")
            
            # 各MVを削除
            for mv_name in mv_names:
                drop_sql = f"DROP MATERIALIZED VIEW IF EXISTS {mv_name} CASCADE;"
                subprocess.run(
                    ["psql", "-U", "postgres", "-d", self.database,
                     "-c", drop_sql],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env={**subprocess.os.environ, 'PGPASSWORD': ''}
                )
            
            print("    ✓ すべてのMVを削除しました")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"    ✗ MV削除エラー: {e}")
            return False
    
    def _list_created_mvs(self):
        """作成されたMVの一覧を表示"""
        print("\n  --- 作成されたMV一覧 ---")
        
        query = """
        SELECT matviewname, 
               pg_size_pretty(pg_total_relation_size('public.'||matviewname)) as size
        FROM pg_matviews 
        WHERE schemaname = 'public'
        ORDER BY matviewname;
        """
        
        try:
            result = subprocess.run(
                ["psql", "-U", "postgres", "-d", self.database,
                 "-c", query],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace',
                env={**subprocess.os.environ, 'PGPASSWORD': ''}
            )
            
            # 結果を整形して表示
            lines = result.stdout.strip().split('\n')
            for line in lines:
                print(f"    {line}")
            
        except subprocess.CalledProcessError:
            print("    ✗ MV一覧の取得に失敗")
    
    def get_available_timesteps(self, algorithm: str) -> List[str]:
        """利用可能なタイムステップのリストを取得
        
        Args:
            algorithm: アルゴリズム名
            
        Returns:
            タイムステップIDのリスト
        """
        algo_dir = self.mv_sql_dir / algorithm
        
        if not algo_dir.exists():
            return []
        
        timesteps = []
        for time_dir in sorted(algo_dir.iterdir()):
            if time_dir.is_dir() and (time_dir / "create_mvs.sql").exists():
                timesteps.append(time_dir.name)
        
        return timesteps
