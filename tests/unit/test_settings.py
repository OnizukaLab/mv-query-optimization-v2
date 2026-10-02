"""Test configuration management."""

import os
import tempfile

from config.settings import (
    DatabaseConfig,
    OptimizationConfig,
    Settings,
    get_settings,
)


def test_default_settings():
    """Test default settings."""
    settings = Settings()

    assert settings.database.host == "localhost"
    assert settings.database.port == 5432
    assert settings.database.database == "imdbload"
    assert settings.optimization.storage_limit_mb == 50
    # storage_limit_bytes should be storage_limit_mb * 1024 * 1024
    assert settings.optimization.storage_limit_bytes == settings.optimization.storage_limit_mb * 1024 * 1024
    assert settings.query.use_ceb is False
    assert settings.query.num_queries == 83  # default.yaml で Redbench JOB の 83 クエリに設定済み


def test_database_config():
    """Test database configuration."""
    db_config = DatabaseConfig(
        host="testhost", port=9999, database="testdb", user="testuser", password="testpass"
    )

    assert db_config.host == "testhost"
    assert db_config.port == 9999
    assert db_config.database == "testdb"
    assert db_config.user == "testuser"
    assert db_config.password == "testpass"


def test_optimization_config():
    """Test optimization configuration."""
    opt_config = OptimizationConfig(
        storage_limit_mb=100, storage_limit_bytes=104857600, insert_queries=2000
    )

    assert opt_config.storage_limit_mb == 100
    # storage_limit_bytes should match storage_limit_mb * 1024 * 1024
    assert opt_config.storage_limit_bytes == opt_config.storage_limit_mb * 1024 * 1024
    assert opt_config.insert_queries == 2000
    assert opt_config.algorithms["normal"] is True


def test_load_from_yaml():
    """Test loading settings from YAML."""
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            """
database:
  host: testhost
  port: 5433
  database: testdb

optimization:
  storage_limit_mb: 100
  storage_limit_bytes: 104857600

query:
  use_ceb: true
  num_queries: 500
"""
        )
        config_path = f.name

    try:
        settings = Settings.from_yaml(config_path)

        assert settings.database.host == "testhost"
        assert settings.database.port == 5433
        assert settings.database.database == "testdb"
        assert settings.optimization.storage_limit_mb == 100
        # storage_limit_bytes should match storage_limit_mb * 1024 * 1024
        assert settings.optimization.storage_limit_bytes == settings.optimization.storage_limit_mb * 1024 * 1024
        assert settings.query.use_ceb is True
        assert settings.query.num_queries == 500
    finally:
        os.unlink(config_path)


def test_merge_configs():
    """Test configuration merging."""
    # Create base config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            """
database:
  host: basehost
  port: 5432

query:
  use_ceb: false
"""
        )
        base_path = f.name

    # Create override config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            """
database:
  host: overridehost

query:
  use_ceb: true
  num_queries: 999
"""
        )
        override_path = f.name

    try:
        settings = Settings.from_yaml(base_path, override_path)

        # Overridden values
        assert settings.database.host == "overridehost"
        assert settings.query.use_ceb is True
        assert settings.query.num_queries == 999

        # Base values that weren't overridden
        assert settings.database.port == 5432
    finally:
        os.unlink(base_path)
        os.unlink(override_path)


def test_env_override():
    """Test environment variable override."""
    # Set environment variables
    os.environ["DB_HOST"] = "envhost"
    os.environ["DB_PORT"] = "9999"
    os.environ["STORAGE_LIMIT_MB"] = "200"
    os.environ["USE_CEB"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
database:
  host: filehost
  port: 5432

optimization:
  storage_limit_mb: 50

query:
  use_ceb: false
"""
            )
            config_path = f.name

        settings = Settings.from_yaml(config_path)

        # Environment variables should override file values
        assert settings.database.host == "envhost"
        assert settings.database.port == 9999
        assert settings.optimization.storage_limit_mb == 200
        # storage_limit_bytes should match storage_limit_mb * 1024 * 1024
        assert settings.optimization.storage_limit_bytes == settings.optimization.storage_limit_mb * 1024 * 1024
        assert settings.query.use_ceb is True
        assert settings.logging.level == "DEBUG"
    finally:
        os.unlink(config_path)
        # Clean up environment variables
        for key in ["DB_HOST", "DB_PORT", "STORAGE_LIMIT_MB", "USE_CEB", "LOG_LEVEL"]:
            if key in os.environ:
                del os.environ[key]


def test_backward_compatibility():
    """Test backward compatibility properties."""
    settings = Settings()
    settings.query.use_ceb = True
    settings.query.num_queries = 500
    storage_bytes = 100 * 1024 * 1024
    settings.optimization.storage_limit_bytes = storage_bytes

    # Test backward compatibility properties
    assert settings.GET_CEB is True
    assert settings.B_max == storage_bytes
    assert settings.q_num == 500


def test_to_dict():
    """Test converting settings to dictionary."""
    settings = Settings()
    settings_dict = settings.to_dict()

    assert "database" in settings_dict
    assert "optimization" in settings_dict
    assert "query" in settings_dict
    assert "paths" in settings_dict
    assert "logging" in settings_dict

    assert settings_dict["database"]["host"] == "localhost"
    assert settings_dict["query"]["use_ceb"] is False


def test_global_settings():
    """Test global settings functions."""
    # Create a test config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            """
query:
  use_ceb: true
"""
        )
        config_path = f.name

    try:
        # Set environment variable to use test config
        os.environ["CONFIG_PATH"] = config_path

        # Reset global settings
        from config import settings as settings_module

        settings_module._settings = None

        # Get settings
        settings = get_settings()
        assert settings.query.use_ceb is True

        # Getting again should return same instance
        settings2 = get_settings()
        assert settings is settings2
    finally:
        os.unlink(config_path)
        if "CONFIG_PATH" in os.environ:
            del os.environ["CONFIG_PATH"]
        # Reset global settings
        from config import settings as settings_module

        settings_module._settings = None
