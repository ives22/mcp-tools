"""ACR MCP Server configuration from environment variables."""

from __future__ import annotations

import os


class ACRConfig:
    """Configuration loaded from environment variables."""

    def __init__(
        self,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        region_id: str | None = None,
    ):
        self.access_key_id = access_key_id or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        self.access_key_secret = access_key_secret or os.environ.get(
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""
        )
        self.region_id = region_id or os.environ.get("ACR_REGION_ID", "ap-southeast-1")

    def validate(self) -> None:
        """Validate required configuration."""
        if not self.access_key_id:
            raise ValueError(
                "ALIBABA_CLOUD_ACCESS_KEY_ID is required. "
                "Set it as an environment variable or pass --access-key-id."
            )
        if not self.access_key_secret:
            raise ValueError(
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET is required. "
                "Set it as an environment variable or pass --access-key-secret."
            )

    @property
    def endpoint(self) -> str:
        """ACR Personal Edition endpoint."""
        return f"cr.{self.region_id}.aliyuncs.com"
