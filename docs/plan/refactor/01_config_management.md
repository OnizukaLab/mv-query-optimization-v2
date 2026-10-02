# Phase 1: 設定管理の外部化

## 🎯 目的

ハードコードされた設定値を外部ファイルに移動し、設定管理システムを構築します。
- グローバル変数 `GET_CEB` の削除
- YAML設定ファイルの導入
- 設定クラスの実装

## ⏱️ 推定時間: 3-4時間

## 📋 前提条件

- [x] Phase 0 が完了している
- [x] `config/` ディレクトリが存在
- [x] PyYAML がインストール済み

## 🔧 実行手順

### Step 1: YAML設定ファイルの作成

#### 1.1 デフォルト設定ファイル

```bash
cat > config/default.yaml << 'EOF'
# Database Configuration
database:
  host: localhost
  port: 5432
  database: imdbload
  user: postgres
  password: ""
  timeout: 1800  # 30 minutes in seconds

# Optimization Parameters
optimization:
  storage_limit_mb: 50
  storage_limit_bytes: 52428800  # 50 * 1024 * 1024
  insert_queries: 1000
  
  # Which algorithms to run
  algorithms:
    normal: true
    bigsubs: true
    utility_capacity: true
    utility: true
    frequency: true

# Benchmark Configuration
benchmark:
  type: job  # 'job' or 'ceb'
  workloads_dir: Output/RED_WORKLOADS
  queries_dir: dataset/RED_JSON
  sql_dir: dataset/RED_SQL

# Query Configuration
query:
  num_queries: 113  # JOB benchmark
  use_ceb: false    # Use CEB queries in addition to JOB

# Paths
paths:
  output_dir: Output
  experiments_dir: Output/experiments
  logs_dir: Output/logs
  artifacts_dir: Output/artifacts
  query_rewrite_dir: Output/query_rewrite
  mv_list_dir: Output

# Logging Configuration
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: output/logs/experiment.log
  console: true
EOF
```

#### 1.2 実験別設定（JOB）

```bash
cat > config/experiments/job_benchmark.yaml << 'EOF'
# Extends default.yaml
# Specific configuration for JOB benchmark

query:
  num_queries: 113
  use_ceb: false

benchmark:
  type: job
  queries_dir: dataset/RED_JSON/job
  sql_dir: dataset/RED_SQL/job

logging:
  level: DEBUG
  file: output/logs/job_experiment.log
EOF
```

#### 1.3 実験別設定（CEB）

```bash
cat > config/experiments/ceb_benchmark.yaml << 'EOF'
# Extends default.yaml
# Specific configuration for CEB benchmark

query:
  num_queries: 13759  # JOB + CEB
  use_ceb: true

benchmark:
  type: ceb
  queries_dir: dataset/RED_JSON
  sql_dir: dataset/RED_SQL

logging:
  level: DEBUG
  file: output/logs/ceb_experiment.log
EOF
```

### Step 2: 設定管理クラスの実装

```bash
cat > config/settings.py << 'EOF'
"""Configuration management for mv-query-optimization."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    """Database configuration."""
    
    host: str = "localhost"
    port: int = 5432
    database: str = "imdbload"
    user: str = "postgres"
    password: str = ""
    timeout: int = 1800


@dataclass
class OptimizationConfig:
    """Optimization parameters."""
    
    storage_limit_mb: int = 50
    storage_limit_bytes: int = 52428800
    insert_queries: int = 1000
    algorithms: Dict[str, bool] = field(default_factory=lambda: {
        "normal": True,
        "bigsubs": True,
        "utility_capacity": True,
        "utility": True,
        "frequency": True,
    })


@dataclass
class BenchmarkConfig:
    """Benchmark configuration."""
    
    type: str = "job"
    workloads_dir: str = "Output/RED_WORKLOADS"
    queries_dir: str = "dataset/RED_JSON"
    sql_dir: str = "dataset/RED_SQL"


@dataclass
class QueryConfig:
    """Query configuration."""
    
    num_queries: int = 113
    use_ceb: bool = False


@dataclass
class PathsConfig:
    """Path configuration."""
    
    output_dir: str = "Output"
    experiments_dir: str = "Output/experiments"
    logs_dir: str = "Output/logs"
    artifacts_dir: str = "Output/artifacts"
    query_rewrite_dir: str = "Output/query_rewrite"
    mv_list_dir: str = "Output"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "output/logs/experiment.log"
    console: bool = True


class Settings:
    """Application settings."""
    
    def __init__(
        self,
        database: Optional[DatabaseConfig] = None,
        optimization: Optional[OptimizationConfig] = None,
        benchmark: Optional[BenchmarkConfig] = None,
        query: Optional[QueryConfig] = None,
        paths: Optional[PathsConfig] = None,
        logging: Optional[LoggingConfig] = None,
    ):
        self.database = database or DatabaseConfig()
        self.optimization = optimization or OptimizationConfig()
        self.benchmark = benchmark or BenchmarkConfig()
        self.query = query or QueryConfig()
        self.paths = paths or PathsConfig()
        self.logging = logging or LoggingConfig()
    
    @classmethod
    def from_yaml(cls, config_path: str, experiment_config: Optional[str] = None) -> "Settings":
        """Load settings from YAML file.
        
        Args:
            config_path: Path to the main configuration file.
            experiment_config: Optional path to experiment-specific config.
            
        Returns:
            Settings instance.
        """
        # Load default config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load experiment config if provided
        if experiment_config and os.path.exists(experiment_config):
            with open(experiment_config, 'r') as f:
                exp_config = yaml.safe_load(f)
                # Merge configs (experiment overrides default)
                config = cls._merge_configs(config, exp_config)
        
        # Override with environment variables
        config = cls._apply_env_overrides(config)
        
        # Create config objects
        database = DatabaseConfig(**config.get('database', {}))
        optimization = OptimizationConfig(**config.get('optimization', {}))
        benchmark = BenchmarkConfig(**config.get('benchmark', {}))
        query = QueryConfig(**config.get('query', {}))
        paths = PathsConfig(**config.get('paths', {}))
        logging_cfg = LoggingConfig(**config.get('logging', {}))
        
        return cls(
            database=database,
            optimization=optimization,
            benchmark=benchmark,
            query=query,
            paths=paths,
            logging=logging_cfg,
        )
    
    @staticmethod
    def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge two configuration dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Settings._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    @staticmethod
    def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
        """Override configuration with environment variables."""
        # Database
        if 'DB_HOST' in os.environ:
            config.setdefault('database', {})['host'] = os.environ['DB_HOST']
        if 'DB_PORT' in os.environ:
            config.setdefault('database', {})['port'] = int(os.environ['DB_PORT'])
        if 'DB_NAME' in os.environ:
            config.setdefault('database', {})['database'] = os.environ['DB_NAME']
        if 'DB_USER' in os.environ:
            config.setdefault('database', {})['user'] = os.environ['DB_USER']
        if 'DB_PASSWORD' in os.environ:
            config.setdefault('database', {})['password'] = os.environ['DB_PASSWORD']
        
        # Optimization
        if 'STORAGE_LIMIT_MB' in os.environ:
            mb = int(os.environ['STORAGE_LIMIT_MB'])
            config.setdefault('optimization', {})['storage_limit_mb'] = mb
            config['optimization']['storage_limit_bytes'] = mb * 1024 * 1024
        
        # Query
        if 'USE_CEB' in os.environ:
            use_ceb = os.environ['USE_CEB'].lower() in ('true', '1', 'yes')
            config.setdefault('query', {})['use_ceb'] = use_ceb
        
        # Logging
        if 'LOG_LEVEL' in os.environ:
            config.setdefault('logging', {})['level'] = os.environ['LOG_LEVEL']
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            'database': self.database.__dict__,
            'optimization': self.optimization.__dict__,
            'benchmark': self.benchmark.__dict__,
            'query': self.query.__dict__,
            'paths': self.paths.__dict__,
            'logging': self.logging.__dict__,
        }
    
    # Backward compatibility properties
    @property
    def GET_CEB(self) -> bool:
        """Backward compatibility for GET_CEB global variable."""
        return self.query.use_ceb
    
    @property
    def B_max(self) -> int:
        """Backward compatibility for B_max."""
        return self.optimization.storage_limit_bytes
    
    @property
    def q_num(self) -> int:
        """Backward compatibility for q_num."""
        return self.query.num_queries


# Global settings instance (to be initialized)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        # Load default settings
        config_path = os.environ.get('CONFIG_PATH', 'config/default.yaml')
        experiment_config = os.environ.get('EXPERIMENT_CONFIG')
        _settings = Settings.from_yaml(config_path, experiment_config)
    return _settings


def set_settings(settings: Settings) -> None:
    """Set the global settings instance."""
    global _settings
    _settings = settings
EOF
```

### Step 3: 既存コードの移行（utils.py）

```bash
# utils.py をバックアップ
cp utils.py utils.py.phase0

cat > src/utils/legacy.py << 'EOF'
"""Legacy utility functions for backward compatibility."""

import os
import re
from config.settings import get_settings


def get_red_queries(source_path, workloads_dir, get_ceb=None):
    """
    Get all query JSON files used in RedBench workloads.
    
    Args:
        source_path: Path to JSON files
        workloads_dir: Path to workload directory
        get_ceb: Use CEB queries (deprecated, use settings instead)
        
    Returns:
        Tuple of (query_paths, query_count_dict)
    """
    # If get_ceb is None, use settings
    if get_ceb is None:
        settings = get_settings()
        get_ceb = settings.query.use_ceb
    
    query_paths = []
    query_count = {}
    
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path + '/job/' + line.split(",")[0].split('/')[-1]
                    query_path = query_path.split(".")[0] + ".json"
                else:
                    query_path = source_path + '/' + "/".join(line.split(",")[0].split('/')[2:])
                    query_path = query_path.split(".")[0] + ".json"
                    
                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue
                    
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


def get_red_queries_sql(source_path, workloads_dir, get_ceb=None):
    """Get all query SQL files used in RedBench workloads."""
    if get_ceb is None:
        settings = get_settings()
        get_ceb = settings.query.use_ceb
    
    query_paths = []
    query_count = {}
    
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path + '/job/' + line.split(",")[0].split('/')[-1]
                else:
                    query_path = source_path + '/' + "/".join(line.split(",")[0].split('/')[2:])
                    
                if not os.path.exists(query_path):
                    continue
                if get_ceb and "job" in query_path:
                    continue
                    
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


def natural_sort_key(s):
    """Natural sorting key for strings with numbers."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
EOF
```

### Step 4: 設定のテスト

```bash
cat > tests/unit/test_settings.py << 'EOF'
"""Test configuration management."""

import os
import tempfile
from pathlib import Path
import pytest
from config.settings import Settings, get_settings, set_settings


def test_default_settings():
    """Test default settings."""
    settings = Settings()
    
    assert settings.database.host == "localhost"
    assert settings.database.port == 5432
    assert settings.optimization.storage_limit_mb == 50
    assert settings.query.use_ceb is False


def test_load_from_yaml():
    """Test loading settings from YAML."""
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""
database:
  host: testhost
  port: 5433

optimization:
  storage_limit_mb: 100

query:
  use_ceb: true
""")
        config_path = f.name
    
    try:
        settings = Settings.from_yaml(config_path)
        
        assert settings.database.host == "testhost"
        assert settings.database.port == 5433
        assert settings.optimization.storage_limit_mb == 100
        assert settings.optimization.storage_limit_bytes == 100 * 1024 * 1024
        assert settings.query.use_ceb is True
    finally:
        os.unlink(config_path)


def test_env_override():
    """Test environment variable override."""
    os.environ['DB_HOST'] = 'envhost'
    os.environ['DB_PORT'] = '9999'
    os.environ['STORAGE_LIMIT_MB'] = '200'
    os.environ['USE_CEB'] = 'true'
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("database: {}\noptimization: {}\nquery: {}")
            config_path = f.name
        
        settings = Settings.from_yaml(config_path)
        
        assert settings.database.host == 'envhost'
        assert settings.database.port == 9999
        assert settings.optimization.storage_limit_mb == 200
        assert settings.query.use_ceb is True
    finally:
        os.unlink(config_path)
        del os.environ['DB_HOST']
        del os.environ['DB_PORT']
        del os.environ['STORAGE_LIMIT_MB']
        del os.environ['USE_CEB']


def test_backward_compatibility():
    """Test backward compatibility properties."""
    settings = Settings()
    settings.query.use_ceb = True
    
    assert settings.GET_CEB is True
    assert settings.B_max == 52428800
    assert settings.q_num == 113
EOF
```

### Step 5: 既存コードでの使用例

```bash
cat > examples/config_usage.py << 'EOF'
"""Example of using the new configuration system."""

from config.settings import Settings, get_settings

# Method 1: Use global settings
settings = get_settings()
print(f"Database: {settings.database.host}:{settings.database.port}")
print(f"Storage limit: {settings.optimization.storage_limit_mb} MB")
print(f"Use CEB: {settings.query.use_ceb}")

# Method 2: Load specific configuration
settings = Settings.from_yaml(
    'config/default.yaml',
    experiment_config='config/experiments/job_benchmark.yaml'
)

# Method 3: Load with environment override
import os
os.environ['DB_HOST'] = 'production-db'
settings = Settings.from_yaml('config/default.yaml')
print(f"Database (from env): {settings.database.host}")

# Backward compatibility
print(f"GET_CEB (old style): {settings.GET_CEB}")
print(f"B_max (old style): {settings.B_max}")
EOF
```

## ✅ 完了チェックリスト

### 設定ファイル
- [ ] `config/default.yaml` が作成済み
- [ ] `config/experiments/job_benchmark.yaml` が作成済み
- [ ] `config/experiments/ceb_benchmark.yaml` が作成済み

### Pythonモジュール
- [ ] `config/settings.py` が実装済み
- [ ] `src/utils/legacy.py` が作成済み

### テスト
- [ ] `tests/unit/test_settings.py` が作成済み
- [ ] テストが通る

### 動作確認
- [ ] 設定ファイルが読み込める
- [ ] 環境変数でオーバーライドできる
- [ ] 後方互換性プロパティが動作

## 🔍 検証方法

```bash
# 1. テストの実行
pytest tests/unit/test_settings.py -v

# 2. 設定ファイルの読み込みテスト
python << 'PYTHON'
from config.settings import Settings

# デフォルト設定
settings = Settings.from_yaml('config/default.yaml')
print(f"✅ Default config loaded")
print(f"   DB: {settings.database.host}:{settings.database.port}")
print(f"   Storage: {settings.optimization.storage_limit_mb} MB")
print(f"   Use CEB: {settings.query.use_ceb}")

# 実験設定
settings = Settings.from_yaml(
    'config/default.yaml',
    'config/experiments/ceb_benchmark.yaml'
)
print(f"✅ CEB config loaded")
print(f"   Use CEB: {settings.query.use_ceb}")

# 後方互換性
print(f"✅ Backward compatibility")
print(f"   GET_CEB: {settings.GET_CEB}")
print(f"   B_max: {settings.B_max}")
PYTHON

# 3. 環境変数オーバーライドのテスト
USE_CEB=true python << 'PYTHON'
from config.settings import Settings
settings = Settings.from_yaml('config/default.yaml')
print(f"✅ Environment override: USE_CEB={settings.query.use_ceb}")
PYTHON
```

## 📝 コミット

```bash
git add config/ src/utils/legacy.py tests/unit/test_settings.py examples/
git commit -m "Phase 1: 設定管理の外部化

- YAML設定ファイルシステムの導入
- config/settings.py で設定管理クラス実装
- 環境変数オーバーライド対応
- 後方互換性プロパティ（GET_CEB, B_max等）
- ユニットテスト追加"

git push origin fix/20251003-refactoring
```

## ⚠️ トラブルシューティング

### Q: yaml.safe_load でエラー

```bash
pip install --upgrade pyyaml
```

### Q: テストが失敗する

```bash
# パスの確認
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/unit/test_settings.py -v
```

## 📚 次のステップ

Phase 1 完了後、次のファイルに進んでください：

```
docs/plan/02_utility_modules.md
```

次のフェーズでは、既存の `utils.py` の関数を新しい構造に移行します。

---

**所要時間**: 3-4時間  
**難易度**: ⭐⭐ (Medium)  
**重要度**: ⭐⭐⭐⭐⭐ (Critical)
