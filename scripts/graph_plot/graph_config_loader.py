"""
グラフ設定ローダー
graph_config.yamlから設定を読み込むモジュール
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class GraphConfig:
    """グラフ設定クラス"""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        グラフ設定を初期化
        
        Args:
            config_path: 設定ファイルのパス。Noneの場合はデフォルトパスを使用
        """
        if config_path is None:
            config_path = Path(__file__).parent / "graph_config.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        YAMLファイルから設定を読み込む
        
        Returns:
            設定辞書
        """
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_algorithm_config(self, algorithm_name: str) -> Dict[str, Any]:
        """
        アルゴリズムの設定を取得
        
        Args:
            algorithm_name: アルゴリズム名
            
        Returns:
            アルゴリズムの設定辞書
        """
        if algorithm_name not in self.config['algorithms']:
            raise ValueError(f"アルゴリズム '{algorithm_name}' は設定ファイルに存在しません")
        return self.config['algorithms'][algorithm_name]
    
    def get_algorithms_config(self) -> Dict[str, Dict[str, Any]]:
        """
        全アルゴリズムの設定を取得
        
        Returns:
            全アルゴリズムの設定辞書
        """
        return self.config['algorithms']
    
    def get_graph_config(self) -> Dict[str, Any]:
        """
        グラフ全体の設定を取得
        
        Returns:
            グラフ設定辞書
        """
        return self.config.get('graph', {})
    
    def get_font(self) -> list:
        """
        フォント設定を取得
        
        Returns:
            フォントのリスト
        """
        return self.get_graph_config().get('font', [])
    
    def get_figure_size(self) -> tuple:
        """
        図のサイズを取得
        
        Returns:
            (幅, 高さ)のタプル
        """
        figsize = self.get_graph_config().get('figsize', [14, 8])
        return tuple(figsize)
    
    def get_dpi(self) -> int:
        """
        DPI設定を取得
        
        Returns:
            DPI値
        """
        return self.get_graph_config().get('dpi', 300)


def get_colors_for_algorithms(algorithm_names: list, config: Optional[GraphConfig] = None) -> Dict[str, str]:
    """
    複数のアルゴリズムの色を取得
    
    Args:
        algorithm_names: アルゴリズム名のリスト
        config: GraphConfigインスタンス。Noneの場合は新規作成
        
    Returns:
        アルゴリズム名をキー、色をバリューとする辞書
    """
    if config is None:
        config = GraphConfig()
    
    colors = {}
    for name in algorithm_names:
        colors[name] = config.get_algorithm_config(name)['color']
    return colors


def get_plot_kwargs_for_algorithm(algorithm_name: str, config: Optional[GraphConfig] = None) -> Dict[str, Any]:
    """
    アルゴリズムのプロット用キーワード引数を取得
    
    Args:
        algorithm_name: アルゴリズム名
        config: GraphConfigインスタンス。Noneの場合は新規作成
        
    Returns:
        plt.plot()に渡すキーワード引数辞書
    """
    if config is None:
        config = GraphConfig()
    
    algo_config = config.get_algorithm_config(algorithm_name)
    return {
        'color': algo_config['color'],
        'marker': algo_config['marker'],
        'linestyle': algo_config['linestyle'],
        'linewidth': algo_config['linewidth'],
        'markersize': algo_config['markersize'],
    }
