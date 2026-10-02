#!/usr/bin/env python3
"""
最適化時間の比較グラフを生成するスクリプト
棒グラフで各アルゴリズムの実行時間を比較し、軸の省略機能を使用して見やすく表示する
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.path import Path as MplPath
import numpy as np
from pathlib import Path
from graph_config_loader import GraphConfig

# グラフ設定を読み込み
config = GraphConfig()

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = config.get_font()
plt.rcParams['axes.unicode_minus'] = False

def plot_optimization_time_with_broken_axis(
    show_normal=True,
    show_bigsubs=True,
    show_proposed_u_b=False,
    show_proposed_u=False,
    show_proposed_f=True
):
    """
    最適化時間の棒グラフを軸省略機能付きで作成
    
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
    
    # 軸省略の閾値を決定
    threshold_lower = 2.0  # 下部グラフの上限を2秒に設定
    threshold_upper = 70.0  # 上部グラフの下限を70秒に設定
    
    # サブプロットを作成（上下に分割）
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, 
                                     gridspec_kw={'height_ratios': [2, 3], 'hspace': 0.001})
    
    # バーの設定
    x = np.arange(len(capacities))
    num_algorithms = len(algorithms)
    width = 0.7 / num_algorithms  # アルゴリズム数に応じて幅を調整
    
    # 各アルゴリズムのバーを描画
    for i, label in enumerate(algorithms.keys()):
        values = algorithms[label]
        algo_config = config.get_algorithm_config(label)
        offset = (i - (num_algorithms - 1) / 2) * width
        ax1.bar(x + offset, values, width, label=label, color=algo_config['color'])
        ax2.bar(x + offset, values, width, label=label, color=algo_config['color'])
    
    # 上部グラフの範囲設定（大きい値用：70秒以上）
    ax1.set_ylim(threshold_upper, max_val * 1.05)
    ax1.spines['bottom'].set_visible(False)
    ax1.tick_params(axis='x', which='both', length=0)
    # 上部グラフの下部の目盛を非表示にする（波線との重なりを避ける）
    ax1_yticks = ax1.get_yticks()
    ax1_yticks = ax1_yticks[ax1_yticks > threshold_upper + 1]  # 下から2単位以上離れたものだけ表示
    ax1.set_yticks(ax1_yticks)
    
    # 下部グラフの範囲設定（小さい値用：0-2秒）
    ax2.set_ylim(0, threshold_lower)
    ax2.spines['top'].set_visible(False)
    # 下部グラフの上部の目盛を非表示にする（波線との重なりを避ける）
    ax2_yticks = ax2.get_yticks()
    ax2_yticks = ax2_yticks[ax2_yticks < threshold_lower - 0.2]  # 上から0.3単位以上離れたものだけ表示
    ax2.set_yticks(ax2_yticks)
    
    # サブプロット間の間隔をゼロに設定
    fig.subplots_adjust(hspace=0.0)
    
    # ニョロニョロの波線を描画（Qiitaの方法を使用）
    d1 = 0.02  # X軸のはみだし量
    d2 = 0.02  # ニョロ波の高さ
    wn = 51    # ニョロ波の数（奇数値を指定）
    
    pp = (0, d2, 0, -d2)
    px = np.linspace(-d1, 1+d1, wn)
    py = np.array([1 + pp[i % 4] for i in range(0, wn)])
    p = MplPath(list(zip(px, py)), [MplPath.MOVETO] + [MplPath.CURVE3] * (wn-1))
    
    # 下部グラフの上側に波線を描画（黒い線）
    line1 = mpatches.PathPatch(p, lw=11, edgecolor='black',
                            facecolor='None', clip_on=False,
                            transform=ax2.transAxes, zorder=10)
    # 白い線で中を塗りつぶして立体感を出す
    line2 = mpatches.PathPatch(p, lw=9, edgecolor='white',
                            facecolor='None', clip_on=False,
                            transform=ax2.transAxes, zorder=10,
                            capstyle='round')
    
    ax2.add_patch(line1)
    ax2.add_patch(line2)
    
    # 上部グラフの下側にも波線を描画
    # py_bottom = np.array([pp[i % 4] for i in range(0, wn)])
    # p_bottom = MplPath(list(zip(px, py_bottom)), [MplPath.MOVETO] + [MplPath.CURVE3] * (wn-1))
    
    # line3 = mpatches.PathPatch(p_bottom, lw=3, edgecolor='black',
    #                         facecolor='None', clip_on=False,
    #                         transform=ax1.transAxes, zorder=10)
    # line4 = mpatches.PathPatch(p_bottom, lw=2, edgecolor='white',
    #                         facecolor='None', clip_on=False,
    #                         transform=ax1.transAxes, zorder=10,
    #                         capstyle='round')
    
    # ax1.add_patch(line3)
    # ax1.add_patch(line4)
    
    # X軸のラベル設定
    ax2.set_xticks(x)
    ax2.set_xticklabels([f'{int(c)}' for c in capacities])
    xlabel_config = config.get_graph_config().get('xlabel', {})
    ax2.set_xlabel('B_max (MB)', 
                   fontsize=xlabel_config.get('fontsize', 24), 
                   fontweight=xlabel_config.get('fontweight', 'bold'))
    
    # Y軸のラベル設定（中央に配置）
    ylabel_config = config.get_graph_config().get('ylabel', {})
    fig.text(0.04, 0.5, 'Optimization Time (s)', va='center', rotation='vertical', 
             fontsize=ylabel_config.get('fontsize', 24), 
             fontweight=ylabel_config.get('fontweight', 'bold'))
    
    # 軸の目盛りラベルのサイズ設定
    tick_labelsize = config.get_graph_config().get('tick_labelsize', 20)
    ax1.tick_params(axis='both', which='major', labelsize=tick_labelsize)
    ax2.tick_params(axis='both', which='major', labelsize=tick_labelsize)
    
    # グリッド追加
    ax1.grid(axis='y', alpha=0.3, linestyle='--')
    ax2.grid(axis='y', alpha=0.3, linestyle='--')
    
    # 凡例（右上に配置してデータに被らないようにする）
    legend_config = config.get_graph_config().get('legend', {})
    ax1.legend(loc=legend_config.get('loc', 'upper right'),
               framealpha=legend_config.get('framealpha', 0.95),
               edgecolor=legend_config.get('edgecolor', 'black'),
               fancybox=legend_config.get('fancybox', True),
               fontsize=legend_config.get('fontsize', 20))
    
    # レイアウト調整
    plt.tight_layout()
    
    # 保存
    output_dir = Path(__file__).parent.parent.parent / "Output" / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "optimization_time_comparison.png"
    
    plt.savefig(output_path, dpi=config.get_dpi(), bbox_inches='tight')
    print(f"\nグラフを保存しました: {output_path}")
    
    # 表示
    plt.show()


if __name__ == "__main__":
    # 各手法の表示/非表示を設定
    plot_optimization_time_with_broken_axis(
        show_normal=True,           # Normal を表示
        show_bigsubs=True,          # BigSubs を表示
        show_proposed_u_b=False,    # Proposed (U+B) を非表示
        show_proposed_u=False,      # Proposed (U) を非表示
        show_proposed_f=True        # Proposed (F) を表示
    )
