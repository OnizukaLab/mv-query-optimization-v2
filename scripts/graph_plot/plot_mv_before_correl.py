#!/usr/bin/env python3
"""
mv_before_correl.csvの散布図を生成するスクリプト
Utility (K) と Workload execution time (s) の関係を可視化
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from graph_config_loader import GraphConfig

# グラフ設定を読み込み
config = GraphConfig()

# 日本語フォント設定
plt.rcParams['font.sans-serif'] = config.get_font()
plt.rcParams['axes.unicode_minus'] = False


def plot_mv_before_correlation():
    """
    Utility と Workload execution time の散布図を作成
    """
    
    # CSVファイルの読み込み
    csv_path = Path(__file__).parent.parent.parent / "data" / "csvfiles" / "mv_before_correl.csv"
    df = pd.read_csv(csv_path)
    
    # 列名の前後の空白を削除
    df.columns = df.columns.str.strip()
    
    print(f"データ読み込み完了: {len(df)} 件")
    print(f"列名: {df.columns.tolist()}")
    print(f"\nデータの概要:")
    print(df.describe())
    
    # プロット作成
    fig, ax = plt.subplots(figsize=config.get_figure_size())
    
    # 散布図を描画
    ax.scatter(df['Utility (K)'], df['Workload execution time (s)'], 
               alpha=0.7, s=100, color='#2E86AB', edgecolors='black', linewidth=1.5)
    
    # 軸ラベル設定
    xlabel_config = config.get_graph_config().get('xlabel', {})
    ylabel_config = config.get_graph_config().get('ylabel', {})
    
    ax.set_xlabel('Utility (K)', 
                  fontsize=xlabel_config.get('fontsize', 24), 
                  fontweight=xlabel_config.get('fontweight', 'bold'))
    ax.set_ylabel('Workload execution time (s)', 
                  fontsize=ylabel_config.get('fontsize', 24), 
                  fontweight=ylabel_config.get('fontweight', 'bold'))
    
    # 軸の目盛りラベルのサイズ設定
    tick_labelsize = config.get_graph_config().get('tick_labelsize', 20)
    ax.tick_params(axis='both', which='major', labelsize=tick_labelsize)
    
    # グリッド追加
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # 相関係数を計算して表示
    correlation = df['Utility (K)'].corr(df['Workload execution time (s)'])
    ax.text(0.95, 0.95, f'Pearson correlation coefficient: {correlation:.3f}', 
            transform=ax.transAxes, 
            fontsize=18,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # レイアウト調整
    plt.tight_layout()
    
    # 保存
    output_dir = Path(__file__).parent.parent.parent / "Output" / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mv_before_correlation.png"
    
    plt.savefig(output_path, dpi=config.get_dpi(), bbox_inches='tight')
    print(f"\nグラフを保存しました: {output_path}")
    print(f"相関係数: {correlation:.3f}")
    
    # 表示
    plt.show()


if __name__ == "__main__":
    plot_mv_before_correlation()
