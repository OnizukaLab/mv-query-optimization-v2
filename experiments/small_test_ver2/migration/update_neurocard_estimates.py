#!/usr/bin/env python3
"""
NeuroCardの推定結果を使ってsimple_migration_costs.jsonのrowsとsizeを更新する
(高速化版: CSVを経由せず直接推定を実行)

処理内容:
1. neurocard_wrapper.pyを使ってNeuroCardモデルを初期化
2. simple_migration_plans.jsonからSQLを読み込む
3. sql_to_neurocard_csv.get_query_conditionsで条件を抽出
4. NeuroCardEstimator.estimate_cardinalityで推定
5. simple_migration_costs.jsonを更新
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.estimation.neurocard_wrapper import NeuroCardEstimator
from src.estimation.sql_to_neurocard_csv import get_query_conditions


def update_costs_with_estimates(
    costs_file: Path,
    plans_file: Path,
    output_file: Path
):
    """
    simple_migration_costs.jsonをNeuroCard推定値で更新
    
    Args:
        costs_file: 元のcostsファイル  
        plans_file: migration plansファイル（SQL取得用）
        output_file: 更新後の出力ファイル
    """
    print("\n" + "="*70)
    print("NeuroCard推定値によるコスト更新（高速化版）")
    print("="*70)
    print()
    
    # 1. NeuroCardモデルを初期化
    print("📊 NeuroCardモデルを初期化中...")
    try:
        # mv-queries-estimation設定を使用（checkpoint_to_loadが設定済み）
        estimator = NeuroCardEstimator(config_name='mv-queries-estimation')
        print("   ✓ モデル初期化完了")
    except Exception as e:
        print(f"   ❌ モデル初期化失敗: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 2. ファイル読み込み
    print(f"📖 プランファイルを読み込み中: {plans_file}")
    with open(plans_file, 'r', encoding='utf-8') as f:
        plans = json.load(f)
        
    print(f"📖 コストファイルを読み込み中: {costs_file}")
    with open(costs_file, 'r', encoding='utf-8') as f:
        costs_data = json.load(f)
    
    # 3. 推定と更新
    print(f"🚀 推定を実行中...")
    print()
    
    updated_count = 0
    skipped_count = 0
    start_time = time.time()
    
    # スキップ理由の集計
    skip_reasons = {
        'no_sql_key': 0,
        'condition_extraction_failed': 0,
        'no_table_aliases': 0, # job-m外テーブル含む
        'estimation_error': 0,
        'result_none': 0,
        'view_not_in_costs': 0
    }
    
    # 全ビューを処理
    total_views = len(plans)
    processed_count = 0
    
    for view_name, view_data in plans.items():
        processed_count += 1
        if processed_count % 100 == 0:
            print(f"   ... {processed_count}/{total_views} 件処理中")
            
        if '[]' not in view_data:
            skip_reasons['no_sql_key'] += 1
            continue
            
        sql = view_data['[]']
        
        # 条件抽出
        try:
            table_aliases, conditions = get_query_conditions(sql)
        except Exception as e:
            # print(f"  ⚠️  {view_name}: 条件抽出失敗 ({e})")
            skip_reasons['condition_extraction_failed'] += 1
            skipped_count += 1
            continue
            
        if not table_aliases:
            # job-m外テーブルやOR条件など
            skip_reasons['no_table_aliases'] += 1
            skipped_count += 1
            continue
            
        # 条件にテーブル存在フラグを追加
        for alias, table_name in table_aliases.items():
            conditions.append((f"__in_{table_name}", "=", 1))
            
        # 推定実行
        try:
            estimated_rows = estimator.estimate_cardinality(conditions)
        except Exception as e:
            print(f"Error during NeuroCard estimation: {e}")
            import traceback
            traceback.print_exc()
            skip_reasons['estimation_error'] += 1
            skipped_count += 1
            estimated_rows = None          
        if estimated_rows is None:
            skip_reasons['result_none'] += 1
            skipped_count += 1
            # デバッグ用: 最初の10件だけ詳細を表示
            if skip_reasons['result_none'] <= 10:
                print(f"  ⚠️  {view_name}: 推定結果None")
                print(f"     SQL: {sql}")
                print(f"     Conditions: {conditions}")
            continue
            
        # コスト更新
        if view_name not in costs_data:
            skip_reasons['view_not_in_costs'] += 1
            continue
            
        view_costs = costs_data[view_name]
        if '[]' not in view_costs:
            view_costs['[]'] = {
                'cost': 0.0,
                'rows': 0,
                'width': 100,
                'size': 0
            }
        
        empty_key_data = view_costs['[]']
        
        original_width = empty_key_data.get('width', 100)
        original_rows = empty_key_data.get('rows', 0)
        original_size = empty_key_data.get('size', 0)
        
        new_rows = int(estimated_rows)
        new_size = original_width * new_rows
        
        empty_key_data['rows'] = new_rows
        empty_key_data['size'] = new_size
        empty_key_data['estimation_method'] = 'neurocard'
        
        if 'original_rows' not in empty_key_data:
            empty_key_data['original_rows'] = original_rows
            empty_key_data['original_size'] = original_size
            
        updated_count += 1
        
        # 変化が大きい場合は表示（ログ量を抑えるため、極端なもののみ）
        # if original_rows > 0:
        #     ratio = new_rows / original_rows
        #     if ratio > 100 or ratio < 0.01:
        #         print(f"  ✓ {view_name}: {original_rows:,} -> {new_rows:,}")
    
    elapsed_time = time.time() - start_time
    
    # 4. 保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(costs_data, f, indent=2, ensure_ascii=False)
    
    print()
    print("="*70)
    print(f"✅ 更新完了: {updated_count}件のビューを更新、{skipped_count}件をスキップ")
    print(f"⏱️  所要時間: {elapsed_time:.1f}秒 ({elapsed_time/updated_count:.2f}秒/件)")
    print("⚠️  スキップ理由の内訳:")
    for reason, count in skip_reasons.items():
        if count > 0:
            print(f"   - {reason}: {count}件")
    print(f"📁 出力先: {output_file}")
    print("="*70)


def main():
    """メイン処理"""
    # パス設定
    base_dir = Path(__file__).parent.parent / "04_migration/job"
    plans_file = base_dir / "simple_migration_plans.json"
    costs_file = base_dir / "simple_migration_costs.json"
    output_file = base_dir / "simple_migration_costs_neurocard.json"
    
    # ファイルの存在確認
    if not plans_file.exists():
        print(f"❌ エラー: {plans_file} が見つかりません")
        return
    
    if not costs_file.exists():
        print(f"❌ エラー: {costs_file} が見つかりません")
        return
    
    # コスト更新を実行
    update_costs_with_estimates(
        costs_file,
        plans_file,
        output_file
    )


if __name__ == "__main__":
    main()
