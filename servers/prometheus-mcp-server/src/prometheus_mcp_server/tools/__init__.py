"""MCP tools for Prometheus operations."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from ..client import PrometheusClient, PrometheusError
from ..config import MCPConfig

logger = logging.getLogger(__name__)


def parse_relative_time(time_str: str) -> str:
    """Convert relative time like 'now-1h' to RFC3339 format.
    
    Supports:
    - 'now' -> current time
    - 'now-1h', 'now-2m', 'now-30s' -> relative time
    - RFC3339 or Unix timestamp -> pass through
    """
    if not time_str:
        return datetime.now(timezone.utc).isoformat()
    
    if time_str == "now":
        return datetime.now(timezone.utc).isoformat()
    
    # Check for relative time pattern: now-Xs/m/h/d
    match = re.match(r"^now-(\d+)([smhd])$", time_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
        }
        seconds = value * multipliers[unit]
        target_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        return target_time.isoformat()
    
    # Otherwise return as-is (assume RFC3339 or Unix timestamp)
    return time_str


def _format_instant_result(data: dict[str, Any], env: str, limit: int = 200) -> dict[str, Any]:
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
    for item in results[:limit]:
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

    result = {
        "environment": env,
        "result_type": result_type,
        "count": len(results),
        "returned": len(formatted),
        "results": formatted,
    }
    
    if len(results) > limit:
        result["truncated"] = True
        result["message"] = f"Showing {limit} of {len(results)} results"
    
    return result


def _format_range_result(data: dict[str, Any], env: str, limit: int = 200) -> dict[str, Any]:
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
    for item in results[:limit]:
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

    result = {
        "environment": env,
        "result_type": result_type,
        "count": len(results),
        "returned": len(formatted),
        "results": formatted,
    }
    
    if len(results) > limit:
        result["truncated"] = True
        result["message"] = f"Showing {limit} of {len(results)} series"
    
    return result


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
                        "description": "Optional: RFC3339/Unix timestamp or relative time (e.g., 'now-1h'). Default: now",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 200)",
                        "minimum": 1,
                        "maximum": 10000,
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
                        "description": "Start time: RFC3339/Unix timestamp or relative (e.g., 'now-1h', 'now-30m')",
                    },
                    "end": {
                        "type": "string",
                        "description": "End time: RFC3339/Unix timestamp or relative (default: now)",
                    },
                    "step": {
                        "type": "string",
                        "description": "Query resolution step (e.g., '1m', '5m', '1h'). Smaller step = more data points",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of series to return (default: 200)",
                        "minimum": 1,
                        "maximum": 10000,
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
                    "match": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: series matchers to filter results (e.g., ['up{job=\"prometheus\"}'])",
                    },
                    "start": {
                        "type": "string",
                        "description": "Optional: start time for filtering (RFC3339/Unix/relative)",
                    },
                    "end": {
                        "type": "string",
                        "description": "Optional: end time for filtering (RFC3339/Unix/relative)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of values to return (default: 200)",
                        "minimum": 1,
                        "maximum": 10000,
                    },
                },
                "required": ["environment", "label_name"],
            },
        },
        {
            "name": "prometheus_list_metrics",
            "description": (
                "List all available metric names in Prometheus. "
                "Can filter by pattern. Use to discover what metrics are available for querying."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional: filter metrics by substring pattern (e.g., 'http', 'node_')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of metrics to return (default: 200)",
                        "minimum": 1,
                        "maximum": 10000,
                    },
                },
                "required": ["environment"],
            },
        },
        {
            "name": "prometheus_list_labels",
            "description": (
                "List all label names available in Prometheus. "
                "Use to discover what labels exist for filtering and grouping metrics."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "match": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: series matchers to filter results",
                    },
                    "start": {
                        "type": "string",
                        "description": "Optional: start time for filtering (RFC3339/Unix/relative)",
                    },
                    "end": {
                        "type": "string",
                        "description": "Optional: end time for filtering (RFC3339/Unix/relative)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of labels to return (default: 200)",
                        "minimum": 1,
                        "maximum": 10000,
                    },
                },
                "required": ["environment"],
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
        {
            "name": "prometheus_query_series",
            "description": (
                "Find time series matching label matchers without evaluating a PromQL expression. "
                "Corresponds to /api/v1/series. Use to discover which series (label combinations) "
                "exist for a given metric or selector — lighter than a full query. "
                "Example: find all instances of up{job='node'} without fetching values."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Target environment name",
                    },
                    "match": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Series matchers (required, at least one). E.g. ['up{job=\"prometheus\"}', 'node_cpu_seconds_total']",
                    },
                    "start": {
                        "type": "string",
                        "description": "Optional: start time (RFC3339/Unix/relative)",
                    },
                    "end": {
                        "type": "string",
                        "description": "Optional: end time (RFC3339/Unix/relative)",
                    },
                },
                "required": ["environment", "match"],
            },
        },
        {
            "name": "prometheus_get_config",
            "description": (
                "Get the current Prometheus runtime configuration (YAML). "
                "Corresponds to /api/v1/status/config. "
                "Use to inspect scrape_interval, rule_files, remote_write, and other settings."
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
            "name": "prometheus_get_flags",
            "description": (
                "Get Prometheus command-line flags and their current values. "
                "Corresponds to /api/v1/status/flags. "
                "Use to check storage retention, WAL settings, query concurrency, and other runtime parameters."
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
            "name": "prometheus_list_alertmanagers",
            "description": (
                "List Alertmanager instances known to Prometheus, showing active and dropped endpoints. "
                "Corresponds to /api/v1/alertmanagers. "
                "Use to diagnose alert delivery issues and verify Alertmanager connectivity."
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
    time_str = arguments.get("time", "now")
    limit = arguments.get("limit", 200)
    
    time = parse_relative_time(time_str)
    logger.info(f"Query (env={env}): {query} @ {time}")
    
    try:
        data = await client.query(query, time=time)
        return _format_instant_result(data, env, limit=limit)
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "query": query}


async def handle_query_range(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_query_range tool call."""
    query = arguments["query"]
    start_str = arguments["start"]
    end_str = arguments.get("end", "now")
    step = arguments.get("step", "1m")
    limit = arguments.get("limit", 200)
    
    start = parse_relative_time(start_str)
    end = parse_relative_time(end_str)
    
    logger.info(f"Range query (env={env}): {query} [{start} -> {end}] step={step}")
    
    try:
        data = await client.query_range(query, start=start, end=end, step=step)
        return _format_range_result(data, env, limit=limit)
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
    match = arguments.get("match")
    start_str = arguments.get("start")
    end_str = arguments.get("end")
    limit = arguments.get("limit", 200)
    
    start = parse_relative_time(start_str) if start_str else None
    end = parse_relative_time(end_str) if end_str else None
    
    logger.info(f"Get label values (env={env}, label={label_name})")
    
    try:
        data = await client.get_label_values(label_name, match=match, start=start, end=end)
        values = data.get("values", [])
        
        result = {
            "environment": env,
            "label_name": label_name,
            "count": len(values),
            "returned": min(len(values), limit),
            "values": values[:limit],
        }
        
        if len(values) > limit:
            result["truncated"] = True
            result["message"] = f"Showing {limit} of {len(values)} values"
        
        return result
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "label_name": label_name}


async def handle_list_metrics(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_metrics tool call."""
    pattern = arguments.get("pattern", "")
    limit = arguments.get("limit", 200)
    
    logger.info(f"List metrics (env={env}, pattern={pattern})")
    
    try:
        # Use __name__ label to get all metric names
        data = await client.get_label_values("__name__")
        metrics = data.get("values", [])
        
        # Filter by pattern if provided
        if pattern:
            metrics = [m for m in metrics if pattern.lower() in m.lower()]
        
        result = {
            "environment": env,
            "count": len(metrics),
            "returned": min(len(metrics), limit),
            "metrics": metrics[:limit],
        }
        
        if pattern:
            result["pattern"] = pattern
        
        if len(metrics) > limit:
            result["truncated"] = True
            result["message"] = f"Showing {limit} of {len(metrics)} metrics"
        
        return result
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_list_labels(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_labels tool call."""
    match = arguments.get("match")
    start_str = arguments.get("start")
    end_str = arguments.get("end")
    limit = arguments.get("limit", 200)
    
    start = parse_relative_time(start_str) if start_str else None
    end = parse_relative_time(end_str) if end_str else None
    
    logger.info(f"List labels (env={env})")
    
    try:
        data = await client.get_label_names(match=match, start=start, end=end)
        labels = data.get("labels", [])
        
        result = {
            "environment": env,
            "count": len(labels),
            "returned": min(len(labels), limit),
            "labels": labels[:limit],
        }
        
        if len(labels) > limit:
            result["truncated"] = True
            result["message"] = f"Showing {limit} of {len(labels)} labels"
        
        return result
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


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


async def handle_query_series(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_query_series tool call."""
    match = arguments["match"]
    start_str = arguments.get("start")
    end_str = arguments.get("end")
    
    start = parse_relative_time(start_str) if start_str else None
    end = parse_relative_time(end_str) if end_str else None
    
    logger.info(f"Query series (env={env}, match={match})")
    
    try:
        data = await client.get_series(match=match, start=start, end=end)
        series_list = data if isinstance(data, list) else data.get("series", [])
        return {
            "environment": env,
            "count": len(series_list),
            "series": series_list,
        }
    except PrometheusError as e:
        return {"error": str(e), "environment": env, "match": match}


async def handle_get_config(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_get_config tool call."""
    logger.info(f"Get config (env={env})")
    
    try:
        data = await client.get_config()
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_get_flags(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_get_flags tool call."""
    logger.info(f"Get flags (env={env})")
    
    try:
        data = await client.get_flags()
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


async def handle_list_alertmanagers(client: PrometheusClient, env: str, arguments: dict) -> dict:
    """Handle prometheus_list_alertmanagers tool call."""
    logger.info(f"List alertmanagers (env={env})")
    
    try:
        data = await client.get_alertmanagers()
        return {"environment": env, "data": data}
    except PrometheusError as e:
        return {"error": str(e), "environment": env}


# Handler dispatch table
HANDLERS = {
    "prometheus_query": handle_query,
    "prometheus_query_range": handle_query_range,
    "prometheus_query_series": handle_query_series,
    "prometheus_list_rules": handle_list_rules,
    "prometheus_list_alerts": handle_list_alerts,
    "prometheus_list_targets": handle_list_targets,
    "prometheus_get_metadata": handle_get_metadata,
    "prometheus_get_label_values": handle_get_label_values,
    "prometheus_list_metrics": handle_list_metrics,
    "prometheus_list_labels": handle_list_labels,
    "prometheus_list_environments": handle_list_environments,
    "prometheus_health": handle_health,
    "prometheus_get_config": handle_get_config,
    "prometheus_get_flags": handle_get_flags,
    "prometheus_list_alertmanagers": handle_list_alertmanagers,
}
