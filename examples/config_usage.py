"""Example of using the new configuration system."""

from config.settings import Settings, get_settings, set_settings

print("=" * 60)
print("Configuration System Examples")
print("=" * 60)

# Method 1: Use global settings (loads default config)
print("\n1. Using global settings (default config):")
settings = get_settings()
print(f"   Database: {settings.database.host}:{settings.database.port}/{settings.database.database}")
print(f"   Storage limit: {settings.optimization.storage_limit_mb} MB")
print(f"   Use CEB: {settings.query.use_ceb}")
print(f"   Num queries: {settings.query.num_queries}")

# Method 2: Load specific configuration
print("\n2. Loading JOB benchmark configuration:")
settings_job = Settings.from_yaml(
    'config/default.yaml',
    experiment_config='config/experiments/job_benchmark.yaml'
)
print(f"   Use CEB: {settings_job.query.use_ceb}")
print(f"   Num queries: {settings_job.query.num_queries}")
print(f"   Log level: {settings_job.logging.level}")

# Method 3: Load CEB benchmark configuration
print("\n3. Loading CEB benchmark configuration:")
settings_ceb = Settings.from_yaml(
    'config/default.yaml',
    experiment_config='config/experiments/ceb_benchmark.yaml'
)
print(f"   Use CEB: {settings_ceb.query.use_ceb}")
print(f"   Num queries: {settings_ceb.query.num_queries}")
print(f"   Log level: {settings_ceb.logging.level}")

# Method 4: Environment variable override
print("\n4. Environment variable override:")
import os
os.environ['DB_HOST'] = 'production-db'
os.environ['USE_CEB'] = 'true'
os.environ['STORAGE_LIMIT_MB'] = '100'

settings_env = Settings.from_yaml('config/default.yaml')
print(f"   Database (from env): {settings_env.database.host}")
print(f"   Use CEB (from env): {settings_env.query.use_ceb}")
print(f"   Storage (from env): {settings_env.optimization.storage_limit_mb} MB")

# Clean up environment variables
del os.environ['DB_HOST']
del os.environ['USE_CEB']
del os.environ['STORAGE_LIMIT_MB']

# Method 5: Backward compatibility
print("\n5. Backward compatibility properties:")
print(f"   GET_CEB (old style): {settings_ceb.GET_CEB}")
print(f"   B_max (old style): {settings_ceb.B_max} bytes")
print(f"   q_num (old style): {settings_ceb.q_num}")

# Method 6: Accessing specific configurations
print("\n6. Accessing specific configuration sections:")
print(f"   Algorithms enabled:")
for algo, enabled in settings.optimization.algorithms.items():
    if enabled:
        print(f"     - {algo}")

print(f"\n   Paths:")
print(f"     - Output dir: {settings.paths.output_dir}")
print(f"     - Logs dir: {settings.paths.logs_dir}")
print(f"     - Experiments dir: {settings.paths.experiments_dir}")

# Method 7: Convert to dictionary
print("\n7. Convert settings to dictionary:")
settings_dict = settings.to_dict()
print(f"   Database config keys: {list(settings_dict['database'].keys())}")
print(f"   Optimization config keys: {list(settings_dict['optimization'].keys())}")

print("\n" + "=" * 60)
print("All examples completed successfully!")
print("=" * 60)
