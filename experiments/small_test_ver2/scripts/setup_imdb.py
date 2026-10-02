#!/usr/bin/env python3
"""
IMDBデータベースセットアップスクリプト

JOBベンチマーク用のIMDBデータベースをセットアップします。

使い方:
    python experiments/small_test_ver2/scripts/setup_imdb.py --download
    python experiments/small_test_ver2/scripts/setup_imdb.py --create-db
    python experiments/small_test_ver2/scripts/setup_imdb.py --all

オプション:
    --download      : IMDBデータのダウンロードと展開
    --create-db     : データベース作成とスキーマ定義
    --import-data   : CSVデータのインポート
    --create-indexes: インデックス作成
    --all           : すべての処理を実行
    --skip-download : ダウンロードをスキップ（既にデータがある場合）
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class IMDBSetup:
    """IMDBデータベースセットアップクラス"""
    
    def __init__(self, config_path: str = None):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス（Noneの場合はデフォルト設定を使用）
        """
        self.project_root = project_root
        self.data_dir = self.project_root / "data"
        self.imdb_url = "https://event.cwi.nl/da/job/imdb.tgz"
        self.imdb_archive = self.data_dir / "imdb.tgz"
        
        # 設定の読み込み
        if config_path:
            self.settings = Settings(config_path)
        else:
            # デフォルトのPostgreSQL接続情報
            self.db_config = {
                'host': 'localhost',
                'port': 5432,
                'user': 'postgres',
                'password': '1608',
                'database': 'imdbload'
            }
    
    def download_imdb_data(self) -> bool:
        """IMDBデータのダウンロードと展開
        
        Returns:
            成功時True
        """
        print("=" * 60)
        print("IMDBデータのダウンロード")
        print("=" * 60)
        
        # データディレクトリに移動
        import os
        original_dir = os.getcwd()
        os.chdir(self.data_dir)
        
        try:
            # 既にダウンロード済みかチェック
            if self.imdb_archive.exists():
                print(f"✓ {self.imdb_archive} は既に存在します")
                print("ダウンロードをスキップします")
                return True
            
            # ダウンロード
            print(f"IMDBデータをダウンロード中: {self.imdb_url}")
            print("(約2.5GB、30分程度かかる場合があります...)")
            print("※中断した場合は再実行すると続きから再開します")
            result = subprocess.run(
                [
                    "curl",
                    "-L",  # リダイレクトに従う
                    "-C", "-",  # 中断したダウンロードを続きから再開
                    "-O",  # ファイル名をURLから取得
                    "--progress-bar",  # 進捗バーを表示
                    "--retry", "10",  # 失敗時に10回リトライ
                    "--retry-delay", "5",  # リトライ間隔5秒
                    "--max-time", "3600",  # タイムアウト1時間
                    "--connect-timeout", "60",  # 接続タイムアウト60秒
                    self.imdb_url
                ],
                check=True,
                # 進捗バーを表示するためcapture_output=Falseに変更
                capture_output=False,
                text=True
            )
            print("✓ ダウンロード完了")
            
            # 展開
            print("データを展開中...")
            result = subprocess.run(
                ["tar", "-xzf", "imdb.tgz"],
                check=True,
                capture_output=False,  # 進捗を表示
                text=True
            )
            print("✓ 展開完了")
            
            # CSVファイルの確認
            csv_files = list(self.data_dir.glob("*.csv"))
            print(f"✓ {len(csv_files)} 個のCSVファイルを検出")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ エラー: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            return False
        finally:
            os.chdir(original_dir)
    
    def create_database(self) -> bool:
        """データベースの作成
        
        Returns:
            成功時True
        """
        print("\n" + "=" * 60)
        print("データベースの作成")
        print("=" * 60)
        
        try:
            # postgres データベースに接続
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # データベースの存在確認
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (self.db_config['database'],)
            )
            exists = cursor.fetchone()
            
            if exists:
                print(f"✓ データベース '{self.db_config['database']}' は既に存在します")
                user_input = input("再作成しますか? (y/N): ")
                if user_input.lower() == 'y':
                    print(f"データベース '{self.db_config['database']}' を削除中...")
                    cursor.execute(f"DROP DATABASE {self.db_config['database']}")
                    print("✓ 削除完了")
                else:
                    print("データベース作成をスキップします")
                    cursor.close()
                    conn.close()
                    return True
            
            # データベース作成
            print(f"データベース '{self.db_config['database']}' を作成中...")
            cursor.execute(f"CREATE DATABASE {self.db_config['database']}")
            print("✓ データベース作成完了")
            
            cursor.close()
            conn.close()
            
            # スキーマの適用
            return self.create_schema()
            
        except psycopg2.Error as e:
            print(f"✗ データベースエラー: {e}")
            return False
    
    def create_schema(self) -> bool:
        """スキーマの作成
        
        Returns:
            成功時True
        """
        print("\n" + "=" * 60)
        print("スキーマの作成")
        print("=" * 60)
        
        schema_file = self.data_dir / "schema.sql"
        if not schema_file.exists():
            print(f"✗ スキーマファイルが見つかりません: {schema_file}")
            return False
        
        try:
            # imdbloadデータベースに接続してスキーマを適用
            import os
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_config['password']
            
            result = subprocess.run(
                [
                    "psql",
                    "-h", self.db_config['host'],
                    "-p", str(self.db_config['port']),
                    "-U", self.db_config['user'],
                    "-d", self.db_config['database'],
                    "-f", str(schema_file)
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                shell=False
            )
            print("✓ スキーマ作成完了")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ スキーマ作成エラー: {e}")
            print(f"stderr: {e.stderr}")
            return False
    
    def import_data(self) -> bool:
        """CSVデータのインポート
        
        Returns:
            成功時True
        """
        print("\n" + "=" * 60)
        print("CSVデータのインポート")
        print("=" * 60)
        
        # インポートするテーブル一覧
        tables = [
            'aka_name', 'aka_title', 'cast_info', 'char_name',
            'comp_cast_type', 'company_name', 'company_type', 'complete_cast',
            'info_type', 'keyword', 'kind_type', 'link_type',
            'movie_companies', 'movie_info', 'movie_info_idx', 'movie_keyword',
            'movie_link', 'name', 'person_info', 'role_type', 'title'
        ]
        
        try:
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            cursor = conn.cursor()
            
            for table in tables:
                csv_file = self.data_dir / f"{table}.csv"
                if not csv_file.exists():
                    print(f"⚠ CSVファイルが見つかりません: {csv_file}")
                    continue
                
                print(f"インポート中: {table} ...")
                
                with open(csv_file, 'r', encoding='utf-8') as f:
                    cursor.copy_expert(
                        f"COPY {table} FROM STDIN WITH (FORMAT csv, ESCAPE '\\')",
                        f
                    )
                
                conn.commit()
                
                # レコード数確認
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  ✓ {count:,} レコードをインポート")
            
            cursor.close()
            conn.close()
            
            print("\n✓ すべてのデータインポートが完了しました")
            return True
            
        except Exception as e:
            print(f"✗ データインポートエラー: {e}")
            if conn:
                conn.rollback()
            return False
    
    def create_indexes(self) -> bool:
        """インデックスの作成
        
        Returns:
            成功時True
        """
        print("\n" + "=" * 60)
        print("インデックスの作成")
        print("=" * 60)
        
        indexes = [
            "CREATE INDEX company_id_movie_companies ON movie_companies(company_id)",
            "CREATE INDEX company_type_id_movie_companies ON movie_companies(company_type_id)",
            "CREATE INDEX info_type_id_movie_info_idx ON movie_info_idx(info_type_id)",
            "CREATE INDEX info_type_id_movie_info ON movie_info(info_type_id)",
            "CREATE INDEX info_type_id_person_info ON person_info(info_type_id)",
            "CREATE INDEX keyword_id_movie_keyword ON movie_keyword(keyword_id)",
            "CREATE INDEX kind_id_aka_title ON aka_title(kind_id)",
            "CREATE INDEX kind_id_title ON title(kind_id)",
            "CREATE INDEX linked_movie_id_movie_link ON movie_link(linked_movie_id)",
            "CREATE INDEX link_type_id_movie_link ON movie_link(link_type_id)",
            "CREATE INDEX movie_id_aka_title ON aka_title(movie_id)",
            "CREATE INDEX movie_id_cast_info ON cast_info(movie_id)",
            "CREATE INDEX movie_id_complete_cast ON complete_cast(movie_id)",
            "CREATE INDEX movie_id_movie_companies ON movie_companies(movie_id)",
            "CREATE INDEX movie_id_movie_info_idx ON movie_info_idx(movie_id)",
            "CREATE INDEX movie_id_movie_keyword ON movie_keyword(movie_id)",
            "CREATE INDEX movie_id_movie_link ON movie_link(movie_id)",
            "CREATE INDEX movie_id_movie_info ON movie_info(movie_id)",
            "CREATE INDEX person_id_aka_name ON aka_name(person_id)",
            "CREATE INDEX person_id_cast_info ON cast_info(person_id)",
            "CREATE INDEX person_id_person_info ON person_info(person_id)",
            "CREATE INDEX person_role_id_cast_info ON cast_info(person_role_id)",
            "CREATE INDEX role_id_cast_info ON cast_info(role_id)",
        ]
        
        try:
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            cursor = conn.cursor()
            
            for i, index_sql in enumerate(indexes, 1):
                print(f"[{i}/{len(indexes)}] {index_sql}")
                try:
                    cursor.execute(index_sql)
                    conn.commit()
                    print("  ✓ 作成完了")
                except psycopg2.Error as e:
                    if "already exists" in str(e):
                        print("  - 既に存在します")
                        conn.rollback()
                    else:
                        raise
            
            cursor.close()
            conn.close()
            
            print("\n✓ すべてのインデックス作成が完了しました")
            return True
            
        except Exception as e:
            print(f"✗ インデックス作成エラー: {e}")
            return False
    
    def verify_setup(self) -> bool:
        """セットアップの検証
        
        Returns:
            検証成功時True
        """
        print("\n" + "=" * 60)
        print("セットアップの検証")
        print("=" * 60)
        
        try:
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            cursor = conn.cursor()
            
            # テーブル数確認
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cursor.fetchone()[0]
            print(f"✓ テーブル数: {table_count}")
            
            # 主要テーブルのレコード数確認
            test_tables = ['title', 'cast_info', 'movie_companies', 'movie_info']
            for table in test_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  - {table}: {count:,} レコード")
            
            # インデックス数確認
            cursor.execute("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE schemaname = 'public'
            """)
            index_count = cursor.fetchone()[0]
            print(f"✓ インデックス数: {index_count}")
            
            cursor.close()
            conn.close()
            
            print("\n✓ セットアップの検証が完了しました")
            return True
            
        except Exception as e:
            print(f"✗ 検証エラー: {e}")
            return False


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='IMDBデータベースセットアップスクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--download', action='store_true',
                        help='IMDBデータのダウンロードと展開')
    parser.add_argument('--create-db', action='store_true',
                        help='データベース作成とスキーマ定義')
    parser.add_argument('--import-data', action='store_true',
                        help='CSVデータのインポート')
    parser.add_argument('--create-indexes', action='store_true',
                        help='インデックス作成')
    parser.add_argument('--all', action='store_true',
                        help='すべての処理を実行')
    parser.add_argument('--skip-download', action='store_true',
                        help='ダウンロードをスキップ')
    parser.add_argument('--verify', action='store_true',
                        help='セットアップの検証のみ実行')
    
    args = parser.parse_args()
    
    # デフォルトで --all を実行
    if not any([args.download, args.create_db, args.import_data, 
                args.create_indexes, args.all, args.verify]):
        args.all = True
    
    setup = IMDBSetup()
    
    success = True
    
    # 検証のみの場合
    if args.verify:
        setup.verify_setup()
        return
    
    # ダウンロード
    if (args.all or args.download) and not args.skip_download:
        if not setup.download_imdb_data():
            print("\n✗ ダウンロードに失敗しました")
            success = False
            return
    
    # データベース作成
    if (args.all or args.create_db) and success:
        if not setup.create_database():
            print("\n✗ データベース作成に失敗しました")
            success = False
            return
    
    # データインポート
    if (args.all or args.import_data) and success:
        if not setup.import_data():
            print("\n✗ データインポートに失敗しました")
            success = False
            return
    
    # インデックス作成
    if (args.all or args.create_indexes) and success:
        if not setup.create_indexes():
            print("\n✗ インデックス作成に失敗しました")
            success = False
            return
    
    # 検証
    if success:
        setup.verify_setup()
        print("\n" + "=" * 60)
        print("✓ すべてのセットアップが完了しました！")
        print("=" * 60)
        print("\n次のステップ:")
        print("1. config.yamlのdatabase.databaseを'imdbload'に変更")
        print("2. 実験スクリプトを実行:")
        print("   python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all")


if __name__ == "__main__":
    main()
