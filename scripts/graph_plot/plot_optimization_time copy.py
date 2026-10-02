#!/usr/bin/env python3
"""
最適化時間の比較グラフを生成するスクリプト
片対数棒グラフで各アルゴリズムの実行時間を比較
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from graph_config_loader import GraphConfig

# グラフ設定を読み込み
config = GraphConfig()

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = config.get_font()
plt.rcParams['axes.unicode_minus'] = False

def plot_optimization_time_semilog(
    show_normal=True,
    show_bigsubs=True,
    show_proposed_u_b=False,
    show_proposed_u=False,
    show_proposed_f=True
):
    """
    最適化時間の棒グラフを片対数スケールで作成
    
    Args:
        show_normal: Normal アルゴリズムを表示するか (デフォルト: True)
        show_bigsubs: BigSubs アルゴリズムを表示するか (デフォルト: True)
        show_proposed_u_b: Proposed (U+B) を表示するか (デフォルト: True)
        show_proposed_u: Proposed (U) を表示するか (デフォルト: True)
        show_proposed_f: Proposed (F) を表示するか (デフォルト: True)
    """
    
    # CSVファイルの読み込み
    csv_path = Path(__file__).parent.parent.parent / "data" / "csvfiles" / "mv-ex2_exectime-compare.csv"
    df = pd.read_csv(csv_path)
    
    # データの準備
    capacities = df['capacity'].values
    algorithms = {}
    
    if show_normal:
        algorithms['Naive ILP'] = df['result_normal_T'].values
    if show_bigsubs:
        algorithms['BigSubs'] = df['result_bigsubs_T'].values
    if show_proposed_u_b:
        algorithms['Proposed (topk-E)'] = df['result_proposed_u_b_T'].values
    if show_proposed_u:
        algorithms['Proposed (topk-U)'] = df['result_proposed_u_T'].values
    if show_proposed_f:
        algorithms['Proposed (topk-F)'] = df['result_proposed_f_T'].values
    
    # 全データの最大値と最小値を確認
    all_values = np.concatenate([v for v in algorithms.values()])
    max_val = np.max(all_values)
    min_val = np.min(all_values)
    
    print(f"表示するアルゴリズム: {list(algorithms.keys())}")
    print(f"最大値: {max_val:.2f}s, 最小値: {min_val:.2f}s")
    
    # プロット作成
    fig, ax = plt.subplots(figsize=config.get_figure_size())
    
    # バーの設定
    x = np.arange(len(capacities))
    num_algorithms = len(algorithms)
    width = 0.7 / num_algorithms  # アルゴリズム数に応じて幅を調整
    
    # 各アルゴリズムのバーを描画
    for i, label in enumerate(algorithms.keys()):
        values = algorithms[label]
        algo_config = config.get_algorithm_config(label)
        offset = (i - (num_algorithms - 1) / 2) * width
        ax.bar(x + offset, values, width, label=label, color=algo_config['color'])
    
    # Y軸を対数スケールに設定
    ax.set_yscale('log')
    
    # X軸のラベル設定
    ax.set_xticks(x)
    ax.set_xticklabels([f'{int(c)}' for c in capacities])
    xlabel_config = config.get_graph_config().get('xlabel', {})
    ax.set_xlabel('B_max (MB)', 
                  fontsize=xlabel_config.get('fontsize', 24), 
                  fontweight=xlabel_config.get('fontweight', 'bold'))
    
    # Y軸のラベル設定
    ylabel_config = config.get_graph_config().get('ylabel', {})
    ax.set_ylabel('Optimization Time (s)', 
                  fontsize=ylabel_config.get('fontsize', 24), 
                  fontweight=ylabel_config.get('fontweight', 'bold'))
    
    # 軸の目盛りラベルのサイズ設定
    tick_labelsize = config.get_graph_config().get('tick_labelsize', 20)
    ax.tick_params(axis='both', which='major', labelsize=tick_labelsize)
    
    # グリッド追加
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # 凡例
    legend_config = config.get_graph_config().get('legend', {})
    ax.legend(loc=legend_config.get('loc', 'upper right'),
              framealpha=legend_config.get('framealpha', 0.95),
              edgecolor=legend_config.get('edgecolor', 'black'),
              fancybox=legend_config.get('fancybox', True),
              fontsize=legend_config.get('fontsize', 20))
    
    # レイアウト調整
    plt.tight_layout()
    
    # 保存
    output_dir = Path(__file__).parent.parent.parent / "Output" / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "optimization_time_comparison_semilog.png"
    
    plt.savefig(output_path, dpi=config.get_dpi(), bbox_inches='tight')
    print(f"\nグラフを保存しました: {output_path}")
    
    # 表示
    plt.show()


if __name__ == "__main__":
    # 各手法の表示/非表示を設定
    plot_optimization_time_semilog(
        show_normal=True,           # Normal を表示
        show_bigsubs=True,          # BigSubs を表示
        show_proposed_u_b=False,    # Proposed (U+B) を非表示
        show_proposed_u=False,      # Proposed (U) を非表示
        show_proposed_f=True        # Proposed (F) を表示
    )
