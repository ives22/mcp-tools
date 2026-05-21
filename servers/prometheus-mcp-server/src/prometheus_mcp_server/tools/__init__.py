"""MCP tools for Prometheus operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..client import PrometheusClient, PrometheusError
from ..config import MCPConfig

logger = logging.getLogger(__name__)


def _format_instant_result(data: dict[str, Any], env: str) -> dict[str, Any]:
    """Format instant query result for human readability."""
    result_type = data.get("resultType", "unknown")
    results = data.get("result", [])

    if not results:
        return {
            "environment": env,
            "result_type": result_type,
            "count": 0,
            "message": "No results found",
            "results": [],
        }

    formatted = []
    for item in results:
        metric = item.get("metric", {})
        value = item.get("value", [])
        if len(value) >= 2:
            ts = float(value[0])
            val = value[1]
            formatted.append({
                "labels": metric,
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "value": val,
            })
        else:
            formatted.append({
                "labels": metric,
                "value": "no value",
            })

    return {
        "environment": env,
        "result_type": result_type,
        "count": len(formatted),
        "results": formatted,
    }


def _format_range_result(data: dict[str, Any], env: str) -> dict[str, Any]:
    """Format range query result for human readability."""
    result_type = data.get("resultType", "unknown")
    results = data.get("result", [])

    if not results:
        return {
            "environment": env,
            "result_type": result_type,
            "count": 0,
            "message": "No results found",
            "results": [],
        }

    formatted = []
    for item in results:
        metric = item.get("metric", {})
        values = item.get("values", [])
        formatted_values = []
        for v in values:
            ts = float(v[0])
            val = v[1]
            formatted_values.append({
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "value": val,
            })
        formatted.append({
            "labels": metric,
            "data_points": len(formatted_values),
            "values": formatted_values,
        })

    return {
        "environment": env,
        "result_type": result_type,
        "count": len(formatted),
        "results": formatted,
    }


# ===== Tool Definitions =====

def get_tool_definitions() -> list[dict[str, Any]]:
    """Return all Prometheus tool definitions for MCP registration."""
    return [
        {
            "name": "prometheus_query",
            "description": (
                "Execute an instant PromQL query against a Prometheus environment. "
                "Returns the current value of the expression at a specific time (default: now). "
                "Use for checking current metric values, service status, etc."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name (e.g., 'production', 'staging', 'local')",
                    },
                    "query": {
                        "type": "string",
                        "description": "PromQL expression to evaluate (e.g., 'up', 'node_memory_MemAvailable_bytes')",
                    },
                    "time": {
                        "type": "string",
                        "description": "Optional: RFC3339 or Unix timestamp to query at. Default: current time",
                    },
                },
                "required": ["environment", "query"],
            },
        },
        {
            "name": "prometheus_query_range",
            "description": (
                "Execute a range PromQL query to get historical metric data over a time window. "
                "Returns a series of data points between start and end times. "
                "Use for analyzing trends, creating charts, or investigating past incidents."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "query": {
                        "type": "string",
                        "description": "PromQL expression to evaluate",
                    },
                    "start": {
                        "type": "string",
                        "description": "Start time (RFC3339 or Unix timestamp, e.g., '2024-01-01T00:00:00Z' or '1h' for 1 hour ago)",
                    },
                    "end": {
                        "type": "string",
                        "description": "End time (RFC3339 or Unix timestamp, default: now)",
                    },
                    "step": {
                        "type": "string",
                        "description": "Query resolution step (e.g., '1m', '5m', '1h'). Smaller step = more data points",
                    },
                },
                "required": ["environment", "query", "start"],
            },
        },
        {
            "name": "prometheus_list_rules",
            "description": (
                "List alerting and recording rules configured in Prometheus. "
                "Can filter by rule type ('alert' for alerting rules, 'record' for recording rules). "
                "Returns rule names, expressions, labels, annotations, and health status."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "rule_type": {
                        "type": "string",
                        "enum": ["alert", "record"],
                        "description": "Optional: filter by rule type ('alert' or 'record')",
                    },
                },
                "required": ["environment"],
            },
        },
        {
            "name": "prometheus_list_alerts",
            "description": (
                "Get the current state of all active alerts in Prometheus. "
                "Returns alerts with their state (inactive, pending, firing), labels, annotations, and activeSince time. "
                "Use for checking what is currently alerting."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                },
                "required": ["environment"],
            },
        },
        {
            "name": "prometheus_list_targets",
            "description": (
                "List scrape targets known to Prometheus. "
                "Shows target URLs, health status (up/down), last scrape time, and scrape duration. "
                "Use for verifying monitoring coverage and debugging scrape issues."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["active", "dropped", "any"],
                        "description": "Filter by target state (default: active)",
                    },
                },
                "required": ["environment"],
            },
        },
        {
            "name": "prometheus_get_metadata",
            "description": (
                "Get metadata about metrics: type (counter, gauge, histogram, summary), help text, and unit. "
                "Can filter by metric name. Use to understand what a metric measures and its type."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "metric": {
                        "type": "string",
                        "description": "Optional: filter by specific metric name (e.g., 'http_requests_total')",
                    },
                },
                "required": ["environment"],
            },
        },
        {
            "name": "prometheus_get_label_values",
            "description": (
                "Get all possible values for a specific label across all metrics. "
                "Use to discover valid values for labels like 'job', 'instance', 'service', 'method', etc."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "label_name": {
                        "type": "string",
                        "description": "Label name to query values for (e.g., 'job', 'instance', 'method')",
                    },
                },
                "required": ["environment", "label_name"],
            },
        },
        {
            "name": "prometheus_list_environments",
            "description": (
                "List all configured Prometheus environments with their URLs. "
                "Use to discover which environments are available for querying."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "prometheus_health",
            "description": (
                "Check Prometheus server health and build information. "
                "Returns version, revision, branch, and build details. "
                "Use to verify the server is running and get version info."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                },
                "required": ["environment"],
            },
        },
    ]


# ===== Tool Handlers =====

async def handle_query(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_query tool call."""
    query = arguments["query"]
    time = arguments.get("time")
    logger.info(f"Query (env={env}): {query}")
    try:
        data = await client.query(query, time=time)
        return _format_instant_result(data, env)
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "query": query}


async def handle_query_range(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_query_range tool call."""
    query = arguments["query"]
    start = arguments["start"]
    end = arguments.get("end", "now")
    step = arguments.get("step", "1m")
    logger.info(f"Range query (env={env}): {query} [{start} -> {end}] step={step}")
    try:
        data = await client.query_range(query, start=start, end=end, step=step)
        return _format_range_result(data, env)
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "query": query}


async def handle_list_rules(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_rules tool call."""
    rule_type = arguments.get("rule_type")
    logger.info(f"List rules (env={env}, type={rule_type})")
    try:
        data = await client.get_rules(type=rule_type)
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_list_alerts(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_alerts tool call."""
    logger.info(f"List alerts (env={env})")
    try:
        data = await client.get_alerts()
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_list_targets(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_targets tool call."""
    state = arguments.get("state")
    logger.info(f"List targets (env={env}, state={state})")
    try:
        data = await client.get_targets(state=state)
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_get_metadata(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_get_metadata tool call."""
    metric = arguments.get("metric")
    logger.info(f"Get metadata (env={env}, metric={metric})")
    try:
        data = await client.get_metadata(metric=metric)
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_get_label_values(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_get_label_values tool call."""
    label_name = arguments["label_name"]
    logger.info(f"Get label values (env={env}, label={label_name})")
    try:
        data = await client.get_label_values(label_name)
        return {"environment": env, "label_name": label_name, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "label_name": label_name}


async def handle_list_environments(config: MCPConfig) -> dict:
    """Handle prometheus_list_environments tool call."""
    envs = {}
    for name, env_config in config.environments.items():
        envs[name] = {
            "url": env_config.url,
            "auth_type": env_config.auth.type.value,
            "timeout": env_config.timeout,
        }
    return {"environments": envs, "count": len(envs)}


async def handle_health(client: PrometheusClient, env: str) -> dict:
    """Handle prometheus_health tool call."""
    logger.info(f"Health check (env={env})")
    try:
        data = await client.health()
        return {"environment": env, "status": "ok", "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "status": "error"}


# Handler dispatch table
HANDLERS = {
    "prometheus_query": handle_query,
    "prometheus_query_range": handle_query_range,
    "prometheus_list_rules": handle_list_rules,
    "prometheus_list_alerts": handle_list_alerts,
    "prometheus_list_targets": handle_list_targets,
    "prometheus_get_metadata": handle_get_metadata,
    "prometheus_get_label_values": handle_get_label_values,
    "prometheus_list_environments": handle_list_environments,
    "prometheus_health": handle_health,
}
