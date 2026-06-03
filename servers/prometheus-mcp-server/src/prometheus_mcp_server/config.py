"""Configuration models for Prometheus MCP Server.

Supports two modes:
1. Multi-environment mode: reads from ~/.prometheus-mcp/config.yaml
2. Single-environment mode: reads PROMETHEUS_URL from environment variables
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class AuthType(str, Enum):
    """Authentication type for Prometheus."""
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


class AuthConfig(BaseModel):
    """Authentication configuration for a Prometheus environment."""
    type: AuthType = AuthType.NONE
    username: str | None = None
    password: str | None = None
    token: str | None = None

    @model_validator(mode="after")
    def validate_auth(self) -> AuthConfig:
        if self.type == AuthType.BASIC:
            if not self.username or not self.password:
                raise ValueError("Basic auth requires 'username' and 'password'")
        elif self.type == AuthType.BEARER:
            if not self.token:
                raise ValueError("Bearer auth requires 'token'")
        return self

    def get_headers(self) -> dict[str, str]:
        """Get HTTP headers for authentication."""
        import base64
        headers: dict[str, str] = {}
        if self.type == AuthType.BASIC:
            credentials = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"
        elif self.type == AuthType.BEARER:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class EnvironmentConfig(BaseModel):
    """Configuration for a single Prometheus environment."""
    url: str = Field(..., description="Prometheus server URL (e.g., http://localhost:9090)")
    auth: AuthConfig = Field(default_factory=AuthConfig, description="Authentication configuration")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")


class DefaultsConfig(BaseModel):
    """Default settings for all environments."""
    timeout: int = Field(default=30, ge=1, le=300, description="Default request timeout")
    max_results: int = Field(default=200, ge=1, le=10000, description="Maximum results to return")
    default_step: str = Field(default="1m", description="Default step for range queries")


class MCPConfig(BaseModel):
    """Top-level configuration for Prometheus MCP Server."""
    environments: dict[str, EnvironmentConfig] = Field(
        default_factory=dict,
        description="Named Prometheus environments (e.g., production, staging, local)"
    )
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    def get_environment(self, name: str) -> EnvironmentConfig:
        """Get environment config by name, raise if not found."""
        if name not in self.environments:
            available = ", ".join(sorted(self.environments.keys()))
            raise ValueError(
                f"Environment '{name}' not found. Available: {available}"
            )
        return self.environments[name]

    def list_environments(self) -> list[str]:
        """List all available environment names."""
        return sorted(self.environments.keys())


def load_config(config_path: str | Path | None = None) -> MCPConfig:
    """Load configuration from YAML file or environment variables.

    Priority:
    1. If config_path is provided and exists, use it
    2. Otherwise try ~/.prometheus-mcp/config.yaml
    3. Otherwise try PROMETHEUS_URL env var (single environment mode)
    4. Otherwise raise an error
    """
    # Try explicit config path first
    if config_path:
        path = Path(config_path).expanduser()
        if path.exists():
            logger.info(f"Loading config from: {path}")
            return _load_from_yaml(path)

    # Try default config path
    default_path = Path("~/.prometheus-mcp/config.yaml").expanduser()
    if default_path.exists():
        logger.info(f"Loading config from default path: {default_path}")
        return _load_from_yaml(default_path)

    # Fall back to environment variables
    prometheus_url = os.environ.get("PROMETHEUS_URL")
    if prometheus_url:
        logger.info(f"Loading config from PROMETHEUS_URL: {prometheus_url}")
        return _load_from_env(prometheus_url)

    # No config found
    raise FileNotFoundError(
        "No configuration found. Either:\n"
        f"  1. Create {default_path} with environments\n"
        "  2. Set PROMETHEUS_URL environment variable\n"
        "  3. Pass --config path/to/config.yaml"
    )


def _load_from_yaml(path: Path) -> MCPConfig:
    """Load configuration from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    return MCPConfig.model_validate(raw)


def _load_from_env(url: str) -> MCPConfig:
    """Load single environment from PROMETHEUS_URL env var."""
    auth_type = os.environ.get("PROMETHEUS_AUTH_TYPE", "none").lower()
    auth_config: dict[str, Any] = {"type": auth_type}

    if auth_type == "basic":
        auth_config["username"] = os.environ.get("PROMETHEUS_USERNAME")
        auth_config["password"] = os.environ.get("PROMETHEUS_PASSWORD")
    elif auth_type == "bearer":
        auth_config["token"] = os.environ.get("PROMETHEUS_TOKEN")

    timeout = int(os.environ.get("PROMETHEUS_TIMEOUT", "30"))
    verify_ssl = os.environ.get("PROMETHEUS_VERIFY_SSL", "true").lower() == "true"

    env_config = EnvironmentConfig(
        url=url,
        auth=AuthConfig(**auth_config),
        timeout=timeout,
        verify_ssl=verify_ssl,
    )

    return MCPConfig(
        environments={"default": env_config},
        defaults=DefaultsConfig(timeout=timeout),
    )
