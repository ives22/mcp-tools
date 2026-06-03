"""Prometheus HTTP API client with async support."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from .config import EnvironmentConfig

logger = logging.getLogger(__name__)


class PrometheusError(Exception):
    """Base exception for Prometheus API errors."""
    pass


class PrometheusQueryError(PrometheusError):
    """Error during PromQL query execution."""
    pass


class PrometheusAPIError(PrometheusError):
    """Error from Prometheus API (non-200 response)."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class PrometheusClient:
    """Async HTTP client for Prometheus API."""

    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = self.config.auth.get_headers()
            self._client = httpx.AsyncClient(
                base_url=self.config.url.rstrip("/"),
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers=headers if headers else None,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, params: dict | None = None) -> dict[str, Any]:
        """Make an HTTP request to Prometheus API."""
        client = await self._get_client()
        try:
            response = await client.request(method, path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Try to parse Prometheus error response
            try:
                error_data = e.response.json()
                error_type = error_data.get("errorType", "unknown")
                error_msg = error_data.get("error", e.response.text)
                raise PrometheusAPIError(
                    e.response.status_code,
                    f"[{error_type}] {error_msg}"
                ) from e
            except (ValueError, AttributeError):
                raise PrometheusAPIError(e.response.status_code, e.response.text) from e
        except httpx.RequestError as e:
            raise PrometheusError(f"Request failed: {e}") from e

        data = response.json()
        if data.get("status") != "success":
            error_type = data.get("errorType", "unknown")
            error_msg = data.get("error", "Unknown error")
            raise PrometheusQueryError(f"[{error_type}] {error_msg}")

        return data.get("data", {})

    # --- Query APIs ---

    async def query(self, promql: str, time: str | None = None) -> dict[str, Any]:
        """Instant query (/api/v1/query).

        Args:
            promql: PromQL expression
            time: RFC3339 or unix timestamp (default: now)
        """
        params: dict[str, Any] = {"query": promql}
        if time:
            params["time"] = time
        return await self._request("GET", "/api/v1/query", params=params)

    async def query_range(
        self,
        promql: str,
        start: str,
        end: str,
        step: str,
    ) -> dict[str, Any]:
        """Range query (/api/v1/query_range).

        Args:
            promql: PromQL expression
            start: Start time (RFC3339 or unix timestamp)
            end: End time (RFC3339 or unix timestamp)
            step: Query resolution step (e.g., '1m', '5m', '1h')
        """
        params = {
            "query": promql,
            "start": start,
            "end": end,
            "step": step,
        }
        return await self._request("GET", "/api/v1/query_range", params=params)

    # --- Metadata APIs ---

    async def get_rules(self, type: str | None = None) -> dict[str, Any]:
        """Get alerting and recording rules (/api/v1/rules).

        Args:
            type: Filter by rule type ('alert' or 'record')
        """
        params: dict[str, Any] = {}
        if type:
            params["type"] = type
        return await self._request("GET", "/api/v1/rules", params=params)

    async def get_alerts(self) -> dict[str, Any]:
        """Get current alerts (/api/v1/alerts)."""
        return await self._request("GET", "/api/v1/alerts")

    async def get_targets(
        self,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Get scrape targets (/api/v1/targets).

        Args:
            state: Filter by state ('active', 'dropped', 'any')
        """
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        return await self._request("GET", "/api/v1/targets", params=params)

    async def get_metadata(self, metric: str | None = None) -> dict[str, Any]:
        """Get metric metadata (/api/v1/metadata).

        Args:
            metric: Filter by metric name (optional)
        """
        params: dict[str, Any] = {}
        if metric:
            params["metric"] = metric
        return await self._request("GET", "/api/v1/metadata", params=params)

    async def get_label_values(
        self,
        label_name: str,
        match: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Get label values (/api/v1/label/<name>/values).

        Args:
            label_name: Label name to query
            match: Series matchers (optional)
            start: Start time for filtering (optional)
            end: End time for filtering (optional)
        """
        params: dict[str, Any] = {}
        if match:
            params["match[]"] = match
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        result = await self._request(
            "GET", f"/api/v1/label/{label_name}/values", params=params
        )
        # This endpoint returns a list directly, not wrapped in data
        return {"values": result} if isinstance(result, list) else result

    async def get_label_names(
        self,
        match: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Get all label names (/api/v1/labels).

        Args:
            match: Series matchers (optional)
            start: Start time (optional)
            end: End time (optional)
        """
        params: dict[str, Any] = {}
        if match:
            params["match[]"] = match
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        result = await self._request("GET", "/api/v1/labels", params=params)
        # This endpoint returns a list directly
        return {"labels": result} if isinstance(result, list) else result

    async def get_series(
        self,
        match: list[str],
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Find series by label matchers (/api/v1/series).

        Args:
            match: Series matchers (required)
            start: Start time (optional)
            end: End time (optional)
        """
        params: dict[str, Any] = {"match[]": match}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._request("GET", "/api/v1/series", params=params)

    async def health(self) -> dict[str, str]:
        """Check Prometheus health (/api/v1/status/buildinfo)."""
        return await self._request("GET", "/api/v1/status/buildinfo")

    # --- Status APIs ---

    async def get_config(self) -> dict[str, Any]:
        """Get Prometheus runtime configuration (/api/v1/status/config)."""
        return await self._request("GET", "/api/v1/status/config")

    async def get_flags(self) -> dict[str, Any]:
        """Get Prometheus command-line flags (/api/v1/status/flags)."""
        return await self._request("GET", "/api/v1/status/flags")

    async def get_alertmanagers(self) -> dict[str, Any]:
        """Get Alertmanager instances (/api/v1/alertmanagers)."""
        return await self._request("GET", "/api/v1/alertmanagers")

    async def get_runtime_info(self) -> dict[str, Any]:
        """Get Prometheus runtime information (/api/v1/status/runtimeinfo)."""
        return await self._request("GET", "/api/v1/status/runtimeinfo")

    async def get_tsdb_stats(self) -> dict[str, Any]:
        """Get TSDB statistics (/api/v1/status/tsdb)."""
        return await self._request("GET", "/api/v1/status/tsdb")

    async def get_target_metadata(
        self,
        match_target: str | None = None,
        metric: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get target metadata (/api/v1/targets/metadata).

        Args:
            match_target: Target matcher (e.g., '{job="prometheus"}')
            metric: Filter by metric name
            limit: Maximum number of results
        """
        params: dict[str, Any] = {}
        if match_target:
            params["match_target"] = match_target
        if metric:
            params["metric"] = metric
        if limit is not None:
            params["limit"] = limit
        return await self._request("GET", "/api/v1/targets/metadata", params=params)
