#!/bin/bash
#
# MV最適化ダッシュボード起動スクリプト
#
# 使い方:
#   ./run_dashboard.sh              # デフォルトポート8501で起動
#   ./run_dashboard.sh 8888         # ポート8888で起動
#
# SSHポートフォワーディングでアクセス:
#   ssh -L 8501:localhost:8501 user@server
#   → ブラウザで http://localhost:8501 を開く
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PORT=${1:-8501}

echo "======================================"
echo "  MV最適化ダッシュボード"
echo "======================================"
echo ""
echo "ポート: $PORT"
echo ""
echo "アクセス方法:"
echo "  ローカル: ブラウザで http://localhost:$PORT"
echo "  リモート: ssh -L $PORT:localhost:$PORT user@server"
echo "           → ブラウザで http://localhost:$PORT"
echo ""
echo "======================================"
echo ""

# 仮想環境をアクティベート
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    echo "仮想環境をアクティベート中..."
    source "$PROJECT_DIR/.venv/bin/activate"
else
    echo "⚠️  仮想環境が見つかりません: $PROJECT_DIR/.venv"
    echo "   python -m venv .venv でvenvを作成してください"
    exit 1
fi

# 依存関係チェック
check_dependency() {
    python3 -c "import $1" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "⚠️  $1 がインストールされていません"
        return 1
    fi
    return 0
}

echo "依存関係をチェック中..."
MISSING_DEPS=0

check_dependency streamlit || MISSING_DEPS=1
check_dependency graphviz || MISSING_DEPS=1
check_dependency plotly || MISSING_DEPS=1
check_dependency pandas || MISSING_DEPS=1

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "必要なパッケージをインストールしますか？ (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        uv pip install streamlit graphviz plotly pandas --python "$PROJECT_DIR/.venv/bin/python"
    else
        echo "インストールをスキップしました。手動でインストールしてください:"
        echo "  uv pip install streamlit graphviz plotly pandas --python .venv/bin/python"
        exit 1
    fi
fi

echo ""
echo "✓ 依存関係OK"
echo ""
echo "ダッシュボードを起動中..."
echo ""

streamlit run "$SCRIPT_DIR/dashboard.py" \
    --server.port "$PORT" \
    --server.address 0.0.0.0 \
    --server.headless true
