"""Configuration management for Listmonk MCP server using pydantic-settings."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Main configuration class with automatic environment variable loading."""

    # Listmonk configuration
    url: str = Field(..., description="Listmonk server URL")
    username: str = Field(..., description="API username")
    password: str = Field(..., description="API token")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")

    # Server configuration
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    server_name: str = Field(default="Listmonk MCP Server", description="Server name")
    allow_dangerous: bool = Field(
        default=False,
        description="Expose tools that act on every record, act by query, or reload Listmonk",
    )

    model_config = SettingsConfigDict(
        env_prefix='LISTMONK_MCP_',
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip('/')

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v

    @field_validator('max_retries')
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max_retries is non-negative."""
        if v < 0:
            raise ValueError("Max retries must be non-negative")
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v_upper



# Global configuration instance
_config: Config | None = None


def load_config(env_file: str | None = None) -> Config:
    """Load configuration from environment variables and optional .env file."""
    global _config

    # Pydantic-settings automatically loads from .env file
    # If a custom env_file is provided, we need to update the model config
    if env_file and Path(env_file).exists():
        # Create a temporary config class with custom env_file
        class TempConfig(Config):
            model_config = Config.model_config.copy()
            model_config['env_file'] = env_file
        _config = TempConfig()  # type: ignore[call-arg]
    else:
        _config = Config()  # type: ignore[call-arg]

    return _config


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def validate_config() -> None:
    """Validate that all required configuration is present."""
    config = get_config()

    if not config.url:
        raise ValueError("Listmonk URL is required (set LISTMONK_MCP_URL)")
    if not config.username:
        raise ValueError("Listmonk API username is required (set LISTMONK_MCP_USERNAME)")
    if not config.password:
        raise ValueError("Listmonk API token is required (set LISTMONK_MCP_PASSWORD)")


