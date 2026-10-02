#!/usr/bin/env python3
"""
既存のサンプリングテーブルを全て削除するスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from experiments.small_test_ver2.migration.sampling_migration_cost_calculator import SamplingMigrationCostCalculator

def main():
    print("=" * 80)
    print("サンプリングテーブル削除")
    print("=" * 80)
    
    # Settingsを初期化
    settings = Settings()
    
    # SamplingMigrationCostCalculatorのインスタンスを作成
    calculator = SamplingMigrationCostCalculator(
        settings=settings,
        query_set="cluster_53"  # query_setは何でも良い（テーブル削除のみ実行）
    )
    
    # データベース接続を取得
    print("\nデータベースに接続中...")
    conn = calculator._get_connection()
    
    try:
        print("\nサンプリングテーブルを削除中...")
        calculator.drop_sample_tables(conn)
        print("\n✓ 全てのサンプリングテーブルを削除しました")
        
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()
        print("\nデータベース接続を閉じました")
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
