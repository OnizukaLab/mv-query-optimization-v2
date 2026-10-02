# Phase 0: 準備・環境整備

## 🎯 目的

リファクタリングを開始する前の環境準備を行います。
- プロジェクト構造のディレクトリ作成
- 開発ツールのインストール
- 現状のバックアップ

## ⏱️ 推定時間: 1-2時間

## 📋 前提条件

- [ ] Python 3.10以上がインストール済み
- [ ] git がインストール済み
- [ ] 現在のブランチ: `fix/20251003-refactoring`

## 🔧 実行手順

### Step 1: 現状のバックアップ

```bash
# 現在の状態をタグ付け
git tag before-refactoring
git push origin before-refactoring

# バックアップブランチ作成
git checkout -b backup/original
git push origin backup/original
git checkout fix/20251003-refactoring
```

### Step 2: ディレクトリ構造の作成

```bash
# 新しいディレクトリ構造を作成
mkdir -p src/{core,optimization,rewrite,benchmark,database,utils}
mkdir -p src/core src/optimization src/rewrite src/benchmark src/database src/utils
mkdir -p config/experiments
mkdir -p scripts
mkdir -p tests/{unit,integration,fixtures}
mkdir -p output/{experiments,logs,artifacts}
mkdir -p docs/{api,experiments}

# __init__.py ファイルを作成
touch src/__init__.py
touch src/core/__init__.py
touch src/optimization/__init__.py
touch src/rewrite/__init__.py
touch src/benchmark/__init__.py
touch src/database/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch config/__init__.py
```

### Step 3: 開発ツールのインストール

```bash
# 既存の requirements.txt をバックアップ
cp requirements.txt requirements.txt.backup

# 開発ツールをインストール
pip install --upgrade pip

# 型チェック
pip install mypy types-PyYAML

# フォーマッター・リンター
pip install black ruff

# テストツール
pip install pytest pytest-cov pytest-mock

# その他ユーティリティ
pip install pyyaml python-dotenv

# requirements-dev.txt を作成
cat > requirements-dev.txt << 'EOF'
# Development tools
mypy>=1.5.0
types-PyYAML>=6.0.0
black>=23.0.0
ruff>=0.1.0
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0

# Utilities
pyyaml>=6.0
python-dotenv>=1.0.0
EOF

# インストール
pip install -r requirements-dev.txt
```

### Step 4: 設定ファイルの作成

#### 4.1 pyproject.toml

```bash
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mv-query-optimization"
version = "0.1.0"
description = "Materialized View Selection using ILP Optimization"
readme = "README.md"
requires-python = ">=3.10"
authors = [
    {name = "OnizukaLab"}
]

dependencies = [
    "gurobipy>=11.0.0",
    "sqlparse>=0.4.4",
    "psycopg2-binary>=2.9.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "mypy>=1.5.0",
    "types-PyYAML>=6.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.black]
line-length = 100
target-version = ['py310']
include = '\.pyi?$'
exclude = '''
/(
    \.git
  | \.mypy_cache
  | \.pytest_cache
  | \.venv
  | venv
  | build
  | dist
  | __pycache__
  | dataset
  | Output
)/
'''

[tool.ruff]
line-length = 100
target-version = "py310"
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by black)
]
exclude = [
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "venv",
    "dataset",
    "Output",
]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # 段階的に true にする
ignore_missing_imports = true
exclude = [
    "dataset/",
    "Output/",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--verbose",
    "--cov=src",
    "--cov-report=html",
    "--cov-report=term-missing",
]
EOF
```

#### 4.2 .gitignore の更新

```bash
cat >> .gitignore << 'EOF'

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# Project specific
Output/
*.pkl
*.log
.env
*.out

# Backup
*.backup
*.bak
EOF
```

#### 4.3 .env.example の作成

```bash
cat > .env.example << 'EOF'
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=imdbload
DB_USER=postgres
DB_PASSWORD=

# Optimization Parameters
STORAGE_LIMIT_MB=50
INSERT_QUERIES=1000

# Benchmark
BENCHMARK_TYPE=job
WORKLOADS_DIR=Output/RED_WORKLOADS
QUERIES_DIR=dataset/RED_JSON

# Logging
LOG_LEVEL=INFO
LOG_FILE=output/logs/experiment.log
EOF
```

### Step 5: setup.py の作成（互換性のため）

```bash
cat > setup.py << 'EOF'
#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name="mv-query-optimization",
    version="0.1.0",
    packages=find_packages(where=".", include=["src*"]),
    python_requires=">=3.10",
)
EOF
```

### Step 6: パッケージとしてインストール

```bash
# 編集可能モードでインストール
pip install -e .

# 開発ツールもインストール
pip install -e ".[dev]"
```

### Step 7: 動作確認

```bash
# Python パスの確認
python -c "import sys; print('\n'.join(sys.path))"

# 新しいディレクトリがインポート可能か確認
python -c "import src; print('src package OK')"
python -c "from src import core, utils; print('subpackages OK')"

# ツールの動作確認
black --version
ruff --version
mypy --version
pytest --version
```

## ✅ 完了チェックリスト

### ディレクトリ構造
- [ ] `src/` ディレクトリが存在
- [ ] `src/core/`, `src/optimization/`, `src/rewrite/` などのサブディレクトリが存在
- [ ] 各ディレクトリに `__init__.py` が存在
- [ ] `config/`, `scripts/`, `tests/` ディレクトリが存在

### 設定ファイル
- [ ] `pyproject.toml` が作成済み
- [ ] `.gitignore` が更新済み
- [ ] `.env.example` が作成済み
- [ ] `setup.py` が作成済み

### ツール
- [ ] black がインストール済み
- [ ] ruff がインストール済み
- [ ] mypy がインストール済み
- [ ] pytest がインストール済み

### 動作確認
- [ ] `pip install -e .` が成功
- [ ] `import src` が成功
- [ ] すべてのツールのバージョン確認が成功

### Git
- [ ] バックアップブランチが作成済み
- [ ] タグ `before-refactoring` が作成済み

## 🔍 検証方法

```bash
# 1. ディレクトリ構造の確認
tree -L 3 -I '__pycache__|*.pyc|dataset|Output' .

# 2. Pythonパッケージの確認
python << 'PYTHON'
import src
import src.core
import src.utils
print("✅ すべてのパッケージがインポート可能")
PYTHON

# 3. ツールの動作確認
echo "=== Black ==="
black --check src/ || echo "黒色化が必要なファイルがあります（正常）"

echo "=== Ruff ==="
ruff check src/ || echo "リントエラーがあります（正常）"

echo "=== Mypy ==="
mypy src/ || echo "型エラーがあります（正常、後で修正）"

echo "=== Pytest ==="
pytest --collect-only tests/ || echo "テストファイルがまだありません（正常）"
```

## 📝 コミット

```bash
git add .
git status

# 以下のファイルが追加されているか確認:
# - src/ ディレクトリ（__init__.py含む）
# - config/, scripts/, tests/ ディレクトリ
# - pyproject.toml
# - setup.py
# - .gitignore（更新）
# - .env.example
# - requirements-dev.txt

git commit -m "Phase 0: プロジェクト構造の準備と開発ツールのセットアップ

- src/, config/, scripts/, tests/ ディレクトリ作成
- pyproject.toml, setup.py 追加
- 開発ツール（black, ruff, mypy, pytest）導入
- .gitignore, .env.example 追加
- パッケージとしてインストール可能に"

git push origin fix/20251003-refactoring
```

## ⚠️ トラブルシューティング

### Q: `pip install -e .` がエラーになる

```bash
# setup.py を確認
cat setup.py

# 再度実行
pip install --upgrade pip setuptools wheel
pip install -e .
```

### Q: インポートエラーが発生する

```bash
# PYTHONPATH を設定
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# または .env ファイルに追加
echo "PYTHONPATH=$(pwd)" >> .env
```

### Q: ディレクトリ作成に失敗する

```bash
# 権限を確認
ls -la

# 手動で作成
mkdir -p src/core src/optimization src/rewrite src/utils
find src -type d -exec touch {}/__init__.py \;
```

## 📚 次のステップ

Phase 0 が完了したら、次のファイルに進んでください：

```
docs/plan/01_config_management.md
```

## 📊 進捗記録

`docs/plan/PROGRESS.md` を更新：

```markdown
- [x] Phase 0: 準備・環境整備
  - [x] ディレクトリ構造作成
  - [x] 開発ツールインストール
  - [x] 設定ファイル作成
  - [x] 動作確認
```

---

**所要時間**: 1-2時間  
**難易度**: ⭐ (Easy)  
**重要度**: ⭐⭐⭐⭐⭐ (Critical)
