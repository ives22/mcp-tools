"""Configuration models for Prometheus MCP Server."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


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
    max_results: int = Field(default=100, ge=1, le=10000, description="Maximum results to return")
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


def load_config(config_path: str | Path) -> MCPConfig:
    """Load configuration from a YAML file."""
    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    return MCPConfig.model_validate(raw)
