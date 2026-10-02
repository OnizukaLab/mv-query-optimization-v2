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
    query_selection_mode: str = "redbench"  # 'redbench', 'all_job', or 'all_ceb'
    ceb_template: str = "1a"  # CEB template (e.g., "1a", "2a", "3b") - used when query_selection_mode is 'all_ceb'
    ceb_limit: int = None  # Max number of CEB queries to load (None = all)


@dataclass
class ExecutionPhasesConfig:
    """Execution phases configuration."""
    
    query_parsing: bool = True
    optimization: bool = True
    sql_generation: bool = True
    mv_creation: bool = True
    query_rewriting: bool = True
    benchmark: bool = True
    
    # Optional: start_from and end_at for range-based control
    start_from: Optional[str] = None  # Phase name to start from
    end_at: Optional[str] = None      # Phase name to end at
    
    def should_run_phase(self, phase_name: str) -> bool:
        """Check if a phase should be run based on configuration.
        
        Args:
            phase_name: Name of the phase ('query_parsing', 'optimization', 'sql_generation', etc.)
            
        Returns:
            True if the phase should be executed.
        """
        # If start_from/end_at are specified, use range-based logic
        if self.start_from or self.end_at:
            phases_order = ['query_parsing', 'optimization', 'sql_generation', 'mv_creation', 'query_rewriting', 'benchmark']
            try:
                phase_idx = phases_order.index(phase_name)
                start_idx = phases_order.index(self.start_from) if self.start_from else 0
                end_idx = phases_order.index(self.end_at) if self.end_at else len(phases_order) - 1
                return start_idx <= phase_idx <= end_idx
            except ValueError:
                # Invalid phase name, fall back to individual flags
                pass
        
        # Use individual phase flags
        return getattr(self, phase_name, True)


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
        execution: Optional[ExecutionPhasesConfig] = None,
        query: Optional[QueryConfig] = None,
        paths: Optional[PathsConfig] = None,
        logging: Optional[LoggingConfig] = None,
        auto_load: bool = True,
    ):
        if auto_load and all(x is None for x in [database, optimization, benchmark, execution, query, paths, logging]):
            # Auto-load from YAML if no configs provided
            config_path = os.environ.get('CONFIG_PATH', 'config/default.yaml')
            if os.path.exists(config_path):
                loaded = Settings.from_yaml(config_path)
                self.database = loaded.database
                self.optimization = loaded.optimization
                self.benchmark = loaded.benchmark
                self.execution = loaded.execution
                self.query = loaded.query
                self.paths = loaded.paths
                self.logging = loaded.logging
                return
        
        self.database = database or DatabaseConfig()
        self.optimization = optimization or OptimizationConfig()
        self.benchmark = benchmark or BenchmarkConfig()
        self.execution = execution or ExecutionPhasesConfig()
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
        
        # Handle execution phases config
        execution_config = config.get('execution', {})
        # Handle nested 'phases' key if present
        if 'phases' in execution_config:
            phases = execution_config['phases']
            execution_config = {
                'query_parsing': phases.get('query_parsing', True),
                'optimization': phases.get('optimization', True),
                'sql_generation': phases.get('sql_generation', True),
                'mv_creation': phases.get('mv_creation', True),
                'query_rewriting': phases.get('query_rewriting', True),
                'benchmark': phases.get('benchmark', True),
                'start_from': execution_config.get('start_from'),
                'end_at': execution_config.get('end_at'),
            }
        execution = ExecutionPhasesConfig(**execution_config)
        
        query = QueryConfig(**config.get('query', {}))
        paths = PathsConfig(**config.get('paths', {}))
        logging_cfg = LoggingConfig(**config.get('logging', {}))
        
        return cls(
            database=database,
            optimization=optimization,
            benchmark=benchmark,
            execution=execution,
            query=query,
            paths=paths,
            logging=logging_cfg,
            auto_load=False,  # Don't auto-load again to avoid recursion
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
            'execution': self.execution.__dict__,
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
