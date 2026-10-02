#!/usr/bin/env python3
"""
MV最適化結果可視化ダッシュボード

実験結果を視覚的に確認するためのStreamlitダッシュボード。
サーバーで起動し、SSHポートフォワーディングでローカルPCから閲覧可能。

起動方法:
    streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0

SSHポートフォワード:
    ssh -L 8501:localhost:8501 user@server
    → ブラウザで http://localhost:8501 を開く
"""

import streamlit as st
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import graphviz
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def natural_sort_key(s):
    """自然数ソート用のキー関数（例: '2a' < '10a'）"""
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', str(s))]

# ページ設定
st.set_page_config(
    page_title="MV最適化ダッシュボード",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
<style>
    .stMetric {
        background-color: #1e1e2e;
        padding: 10px;
        border-radius: 8px;
    }
    .mv-selected {
        background-color: #a6e3a1;
        color: #1e1e2e;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .mv-node {
        fill: #89b4fa;
    }
</style>
""", unsafe_allow_html=True)

# ディレクトリパス（絶対パスで解決）
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = EXP_DIR / "time_dependent_output"
JSON_DIR = EXP_DIR / "02_json"



@st.cache_data
def load_optimization_result(filepath: str) -> Optional[Dict]:
    """最適化結果JSONを読み込み"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        return None


@st.cache_data
def load_benchmark_result(filepath: str) -> Optional[Dict]:
    """ベンチマーク結果JSONを読み込み"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        return None


@st.cache_data
def load_explain_json(filepath: str) -> Optional[Dict]:
    """EXPLAIN JSONを読み込み"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # PostgreSQLのEXPLAIN出力は配列の最初の要素
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        return None


def find_result_files(query_set: str) -> Dict[str, List[Path]]:
    """結果ファイルを検索"""
    output_path = OUTPUT_DIR / query_set
    if not output_path.exists():
        return {"optimization": [], "benchmark": []}
    
    opt_files = sorted(output_path.glob("td_mv_optimization_result_*.json"))
    bench_files = sorted(output_path.glob("benchmark_results_*.json"))
    static_files = sorted(output_path.glob("static_mv_optimization_result_*.json"))
    
    return {
        "optimization": opt_files,
        "benchmark": bench_files,
        "static": static_files
    }


def get_query_sets() -> List[str]:
    """利用可能なクエリセットを取得"""
    if not OUTPUT_DIR.exists():
        return []
    return [d.name for d in OUTPUT_DIR.iterdir() 
            if d.is_dir() and not d.name.startswith('.') and d.name not in ['log', 'store_result', 'migration_plan']]


def build_query_tree(plan: Dict, selected_mvs: List[str] = None) -> graphviz.Digraph:
    """EXPLAIN計画からGraphvizツリーを構築"""
    if selected_mvs is None:
        selected_mvs = []
    
    dot = graphviz.Digraph(comment='Query Execution Plan')
    dot.attr(rankdir='TB', bgcolor='transparent')
    dot.attr('node', shape='box', style='rounded,filled', fontname='Helvetica')
    
    def add_node(node: Dict, parent_id: Optional[str] = None):
        node_id = node.get('node_id', f"node_{id(node)}")
        node_type = node.get('Node Type', 'Unknown')
        
        # ノード情報
        relation = node.get('Relation Name', '')
        alias = node.get('Alias', '')
        rows = node.get('Plan Rows', '')
        cost = node.get('Total Cost', '')
        
        # ラベル作成
        label_parts = [node_type]
        if relation:
            label_parts.append(f"{relation}" + (f" ({alias})" if alias else ""))
        if rows:
            label_parts.append(f"Rows: {rows}")
        if cost:
            label_parts.append(f"Cost: {cost:.1f}")
        label = "\\n".join(label_parts)
        
        # MVとして選択されているかでスタイル変更
        if node_id in selected_mvs:
            dot.node(node_id, label, fillcolor='#a6e3a1', fontcolor='#1e1e2e', penwidth='3')
        elif node_id.startswith('leaf_'):
            dot.node(node_id, label, fillcolor='#fab387', fontcolor='#1e1e2e')
        elif node_id.startswith('non_leaf_'):
            dot.node(node_id, label, fillcolor='#89b4fa', fontcolor='#1e1e2e')
        else:
            dot.node(node_id, label, fillcolor='#cdd6f4', fontcolor='#1e1e2e')
        
        # 親ノードとのエッジ
        if parent_id:
            dot.edge(parent_id, node_id)
        
        # 子ノードを処理
        for child in node.get('Plans', []):
            add_node(child, node_id)
    
    if 'Plan' in plan:
        add_node(plan['Plan'])
    else:
        add_node(plan)
    
    return dot


def get_selected_mvs_at_timestep(opt_result: Dict, timestep: int) -> List[Dict]:
    """指定タイムステップで選択されているMVを取得"""
    # migration_analysis構造を使用
    if 'migration_analysis' in opt_result:
        for t_result in opt_result['migration_analysis']:
            # 文字列と整数の両方に対応
            t_val = t_result.get('timestep')
            if str(t_val) == str(timestep) or t_val == timestep:
                mvs = t_result.get('selected_mvs', [])
                total_size = t_result.get('total_size', 0)
                mv_count = t_result.get('mv_count', len(mvs))
                
                # creation_detailsから詳細情報を取得
                creation_details = {}
                if 'initial_creation' in t_result and 'creation_details' in t_result['initial_creation']:
                    for detail in t_result['initial_creation']['creation_details']:
                        creation_details[detail['mv']] = detail
                
                # 文字列リストの場合は辞書に変換
                if mvs and isinstance(mvs[0], str):
                    result = []
                    for mv in mvs:
                        if mv in creation_details:
                            result.append(creation_details[mv])
                        else:
                            # 均等分割で推定
                            est_size = total_size / mv_count if mv_count > 0 else 0
                            result.append({'mv': mv, 'size': est_size, 'cost': 0})
                    return result
                return mvs
    
    # 旧構造にもフォールバック
    if 'timestep_results' in opt_result:
        for t_result in opt_result['timestep_results']:
            if t_result.get('timestep_index', t_result.get('timestep')) == timestep:
                return t_result.get('selected_mvs', [])
    
    return []


def create_mv_timeline(opt_result: Dict) -> go.Figure:
    """MVの時系列変化をGanttチャート風に表示"""
    timesteps = opt_result.get('timesteps', [])
    if not timesteps:
        return None
    
    # MV選択データを整理（migration_analysis構造対応）
    mv_data = []
    data_source = opt_result.get('migration_analysis', opt_result.get('timestep_results', []))
    
    for t_result in data_source:
        t_idx = t_result.get('timestep', t_result.get('timestep_index', 0))
        mvs = t_result.get('selected_mvs', [])
        total_size = t_result.get('total_size', 0)
        mv_count = t_result.get('mv_count', len(mvs))
        
        for mv in mvs:
            mv_name = mv.get('mv', mv) if isinstance(mv, dict) else mv
            # 個別サイズがない場合は均等分割で推定
            est_size = total_size / mv_count if mv_count > 0 else 0
            mv_data.append({
                'timestep': t_idx,
                'mv': mv_name,
                'size': mv.get('size', est_size) if isinstance(mv, dict) else est_size,
                'cost': mv.get('cost', 0) if isinstance(mv, dict) else 0
            })
    
    if not mv_data:
        return None
    
    df = pd.DataFrame(mv_data)
    
    # ヒートマップ形式で表示
    pivot = df.pivot_table(index='mv', columns='timestep', values='size', aggfunc='first', fill_value=0)
    pivot_binary = (pivot > 0).astype(int)
    
    # タイムステップを数値順にソート
    sorted_columns = sorted(pivot_binary.columns, key=lambda x: int(x) if isinstance(x, (int, str)) and str(x).isdigit() else x)
    pivot_binary = pivot_binary[sorted_columns]
    
    # MV名を自然数順にソート
    sorted_index = sorted(pivot_binary.index, key=natural_sort_key)
    pivot_binary = pivot_binary.reindex(sorted_index)
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot_binary.values,
        x=[f"T{i}" for i in pivot_binary.columns],
        y=pivot_binary.index,
        colorscale=[[0, '#313244'], [1, '#a6e3a1']],
        showscale=False,
        hovertemplate='MV: %{y}<br>Timestep: %{x}<br><extra></extra>'
    ))
    
    fig.update_layout(
        title='MV選択タイムライン（緑 = 選択中）',
        xaxis_title='タイムステップ',
        yaxis_title='MV',
        height=max(400, len(pivot_binary.index) * 20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#1e1e2e',
        font=dict(color='#cdd6f4')
    )
    
    return fig


def create_cost_chart(opt_result: Dict) -> go.Figure:
    """ストレージ使用量推移チャート"""
    timesteps_list = []
    storage_used = []
    
    # migration_analysis構造対応
    data_source = opt_result.get('migration_analysis', opt_result.get('timestep_results', []))
    
    for t_result in data_source:
        t_idx = t_result.get('timestep', t_result.get('timestep_index', 0))
        timesteps_list.append(t_idx)
        
        # total_sizeがあれば使用、なければ計算
        if 'total_size' in t_result:
            total_storage = t_result['total_size']
        else:
            mvs = t_result.get('selected_mvs', [])
            total_storage = sum(mv.get('size', 0) for mv in mvs if isinstance(mv, dict))
        
        storage_used.append(total_storage / (1024 * 1024))  # MB単位
    
    if not timesteps_list:
        return None
    
    # タイムステップを数値順にソート
    sorted_data = sorted(zip(timesteps_list, storage_used), key=lambda x: int(x[0]) if str(x[0]).isdigit() else x[0])
    timesteps_list, storage_used = zip(*sorted_data) if sorted_data else ([], [])
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=list(timesteps_list),
        y=list(storage_used),
        name='ストレージ使用量 (MB)',
        line=dict(color='#89b4fa', width=2),
        fill='tozeroy',
        fillcolor='rgba(137, 180, 250, 0.2)'
    ))
    
    fig.update_layout(
        title='ストレージ使用量の推移',
        xaxis_title='タイムステップ',
        yaxis_title='ストレージ (MB)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='#1e1e2e',
        font=dict(color='#cdd6f4'),
        height=300
    )
    
    return fig


# =================
# メインUI
# =================
st.title("📊 MV最適化結果ダッシュボード")

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    
    # クエリセット選択
    query_sets = get_query_sets()
    if not query_sets:
        st.error("結果ディレクトリが見つかりません")
        st.stop()
    
    selected_query_set = st.selectbox("クエリセット", query_sets, index=query_sets.index('job_real') if 'job_real' in query_sets else 0)
    
    # 結果ファイル選択
    result_files = find_result_files(selected_query_set)
    
    if result_files['optimization']:
        opt_file = st.selectbox(
            "最適化結果ファイル",
            result_files['optimization'],
            format_func=lambda x: x.name
        )
    else:
        st.warning("最適化結果ファイルが見つかりません")
        st.stop()
    
    # ベンチマーク結果（オプション）
    bench_file = None
    if result_files['benchmark']:
        bench_file = st.selectbox(
            "ベンチマーク結果（オプション）",
            [None] + list(result_files['benchmark']),
            format_func=lambda x: x.name if x else "なし"
        )

# メインコンテンツ
opt_result = load_optimization_result(str(opt_file))
if not opt_result:
    st.stop()

timesteps = opt_result.get('timesteps', [])
n_timesteps = len(timesteps)

# タブ構成
tab1, tab2, tab3 = st.tabs(["📋 MV選択", "🌲 クエリツリー", "📈 時系列分析"])

# =================
# Tab 1: MV選択
# =================
with tab1:
    st.header("MV選択状況")
    
    # タイムステップ選択
    selected_timestep = st.slider("タイムステップ", 0, max(0, n_timesteps - 1), 0)
    
    selected_mvs = get_selected_mvs_at_timestep(opt_result, selected_timestep)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("選択MV数", len(selected_mvs))
    with col2:
        total_size = sum(mv.get('size', 0) for mv in selected_mvs if isinstance(mv, dict))
        st.metric("合計サイズ", f"{total_size / (1024*1024):.2f} MB")
    with col3:
        total_cost = sum(mv.get('cost', 0) for mv in selected_mvs if isinstance(mv, dict))
        st.metric("合計コスト削減", f"{total_cost:.2f}")
    
    # MV一覧テーブル
    if selected_mvs:
        mv_df = pd.DataFrame([
            {
                'MV名': mv.get('mv', mv) if isinstance(mv, dict) else mv,
                'サイズ (bytes)': mv.get('size', 0) if isinstance(mv, dict) else 0,
                'コスト削減': mv.get('cost', 0) if isinstance(mv, dict) else 0
            }
            for mv in selected_mvs
        ])
        mv_df = mv_df.sort_values('コスト削減', ascending=False)
        st.dataframe(mv_df, use_container_width=True, hide_index=True)
    else:
        st.info("このタイムステップにはMVが選択されていません")

# =================
# Tab 2: クエリツリー
# =================
with tab2:
    st.header("クエリ実行プランの可視化")
    
    # クエリ選択
    json_dir = JSON_DIR / selected_query_set
    if json_dir.exists():
        query_files = sorted(json_dir.glob("*.json"), key=lambda f: natural_sort_key(f.stem))
        query_names = [f.stem for f in query_files]
        
        if query_names:
            selected_query = st.selectbox("クエリを選択", query_names)
            
            # タイムステップ選択
            timestep_for_tree = st.slider("タイムステップ（ハイライト用）", 0, max(0, n_timesteps - 1), 0, key="tree_timestep")
            
            # EXPLAIN JSONを読み込み
            explain_path = json_dir / f"{selected_query}.json"
            explain_data = load_explain_json(str(explain_path))
            
            if explain_data:
                # 選択されたMVを取得
                mvs_at_timestep = get_selected_mvs_at_timestep(opt_result, timestep_for_tree)
                selected_mv_names = [mv.get('mv', mv) if isinstance(mv, dict) else mv for mv in mvs_at_timestep]
                
                # ツリー描画
                tree = build_query_tree(explain_data, selected_mv_names)
                st.graphviz_chart(tree, use_container_width=True)
                
                # 凡例
                st.markdown("""
                **凡例:**
                - 🟢 **緑**: 選択されたMV（実体化対象）
                - 🟠 **オレンジ**: リーフノード（テーブルスキャン）
                - 🔵 **青**: 非リーフノード（結合等）
                """)
            else:
                st.warning("EXPLAIN JSONを読み込めませんでした")
        else:
            st.warning("JSONファイルが見つかりません")
    else:
        st.warning(f"ディレクトリが見つかりません: {json_dir}")

# =================
# Tab 3: 時系列分析
# =================
with tab3:
    st.header("時系列分析")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # MVタイムライン
        timeline_fig = create_mv_timeline(opt_result)
        if timeline_fig:
            st.plotly_chart(timeline_fig, use_container_width=True)
        else:
            st.info("タイムラインデータがありません")
    
    with col2:
        # コスト推移
        cost_fig = create_cost_chart(opt_result)
        if cost_fig:
            st.plotly_chart(cost_fig, use_container_width=True)
    
    # MV変更サマリー
    st.subheader("MV変更サマリー")
    
    changes = []
    prev_mvs = set()
    data_source = opt_result.get('migration_analysis', opt_result.get('timestep_results', []))
    for t_result in data_source:
        t_idx = t_result.get('timestep', t_result.get('timestep_index', 0))
        current_mvs = set(
            mv.get('mv', mv) if isinstance(mv, dict) else mv 
            for mv in t_result.get('selected_mvs', [])
        )
        
        added = current_mvs - prev_mvs
        removed = prev_mvs - current_mvs
        
        if added or removed:
            changes.append({
                'タイムステップ': t_idx,
                '追加': ', '.join(sorted(added)) if added else '-',
                '削除': ', '.join(sorted(removed)) if removed else '-',
                '追加数': len(added),
                '削除数': len(removed)
            })
        
        prev_mvs = current_mvs
    
    if changes:
        changes_df = pd.DataFrame(changes)
        st.dataframe(changes_df, use_container_width=True, hide_index=True)
    else:
        st.info("MV変更はありません")

# フッター
st.markdown("---")
st.caption("MV最適化実験ダッシュボード | SSH経由でアクセス: `ssh -L 8501:localhost:8501 user@server`")
