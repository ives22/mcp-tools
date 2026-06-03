"""Prometheus MCP Server - main server logic with stdio and HTTP transport."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    Prompt,
    PromptArgument,
    PromptMessage,
    GetPromptResult,
)

from .config import MCPConfig, load_config
from .client import PrometheusClient, PrometheusError
from .tools import HANDLERS, get_tool_definitions

logger = logging.getLogger("prometheus-mcp-server")


def create_server(config: MCPConfig) -> Server:
    """Create the MCP server with all Prometheus tools, resources, and prompts."""
    server = Server("prometheus-mcp-server")
    tool_defs = get_tool_definitions()

    # ===== Tools =====

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
            )
            for tool in tool_defs
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        logger.info(f"Tool call: {name} with args: {arguments}")

        try:
            if name == "prometheus_list_environments":
                from .tools import handle_list_environments
                result = await handle_list_environments(config)
            else:
                env_name = arguments.get("environment", "")
                if not env_name:
                    return [
                        TextContent(
                            type="text",
                            text=(
                                f"Error: 'environment' parameter is required for {name}. "
                                f"Available environments: {', '.join(config.list_environments())}"
                            ),
                        )
                    ]

                env_config = config.get_environment(env_name)
                client = PrometheusClient(env_config)
                try:
                    handler = HANDLERS.get(name)
                    if handler is None:
                        return [
                            TextContent(
                                type="text",
                                text=json.dumps(
                                    {"error": f"Unknown tool '{name}'"},
                                    indent=2,
                                ),
                            )
                        ]

                    if name == "prometheus_health":
                        from .tools import handle_health
                        result = await handle_health(client, env_name)
                    else:
                        result = await handler(client, env_name, arguments)
                finally:
                    await client.close()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, default=str, indent=2, ensure_ascii=False),
                )
            ]

        except Exception as e:
            logger.exception(f"Tool call failed: {name}")
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": str(e),
                            "tool": name,
                            "hint": "Check environment name, query syntax, and Prometheus connectivity",
                        },
                        indent=2,
                    ),
                )
            ]

    # ===== Resources =====

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        resources = []
        for env_name in config.list_environments():
            env_config = config.environments[env_name]
            resources.append(
                Resource(
                    uri=f"prometheus://{env_name}/info",  # type: ignore[arg-type]
                    name=f"{env_name} - Environment Info",
                    description=f"Prometheus environment: {env_config.url}",
                    mimeType="application/json",
                )
            )
        return resources

    @server.read_resource()
    async def read_resource(uri: Any) -> str:
        # Parse URI: prometheus://<env>/info
        uri_str = str(uri)
        if not uri_str.startswith("prometheus://"):
            raise ValueError(f"Invalid resource URI: {uri_str}")

        parts = uri_str.replace("prometheus://", "").split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid resource URI format: {uri_str}")

        env_name = parts[0]
        resource_type = parts[1]

        env_config = config.get_environment(env_name)
        client = PrometheusClient(env_config)
        try:
            if resource_type == "info":
                health = await client.health()
                return json.dumps(
                    {
                        "environment": env_name,
                        "url": env_config.url,
                        "health": health,
                    },
                    default=str,
                    indent=2,
                    ensure_ascii=False,
                )
            else:
                raise ValueError(f"Unknown resource type: {resource_type}")
        finally:
            await client.close()

    # ===== Prompts =====

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="query-metric",
                description="Query a specific metric in a Prometheus environment",
                arguments=[
                    PromptArgument(
                        name="environment",
                        description="Target environment (e.g., production, staging)",
                        required=True,
                    ),
                    PromptArgument(
                        name="metric",
                        description="Metric name to query (e.g., up, http_requests_total)",
                        required=True,
                    ),
                    PromptArgument(
                        name="time_range",
                        description="Time range (e.g., '1h', '24h', '7d')",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="troubleshoot-alert",
                description="Help troubleshoot a firing alert in Prometheus",
                arguments=[
                    PromptArgument(
                        name="environment",
                        description="Target environment",
                        required=True,
                    ),
                    PromptArgument(
                        name="alert_name",
                        description="Name of the alert to investigate",
                        required=True,
                    ),
                ],
            ),
            Prompt(
                name="service-health",
                description="Check overall health of a service using multiple metrics",
                arguments=[
                    PromptArgument(
                        name="environment",
                        description="Target environment",
                        required=True,
                    ),
                    PromptArgument(
                        name="service",
                        description="Service name or job label",
                        required=True,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        args = arguments or {}

        if name == "query-metric":
            env = args.get("environment", "production")
            metric = args.get("metric", "up")
            time_range = args.get("time_range", "1h")

            return GetPromptResult(
                description=f"Query {metric} in {env}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"Please check the current value of the metric '{metric}' "
                                f"in the '{env}' Prometheus environment. "
                                f"Also show me the trend over the last {time_range} using a range query. "
                                f"Summarize the results and highlight any anomalies."
                            ),
                        ),
                    )
                ],
            )

        elif name == "troubleshoot-alert":
            env = args.get("environment", "production")
            alert_name = args.get("alert_name", "")

            return GetPromptResult(
                description=f"Troubleshoot alert '{alert_name}' in {env}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"I need to troubleshoot the alert '{alert_name}' in the '{env}' environment.\n"
                                f"Please:\n"
                                f"1. Check if this alert is currently firing (use list_alerts)\n"
                                f"2. Find the alerting rule definition (use list_rules)\n"
                                f"3. Check the underlying metrics the alert depends on\n"
                                f"4. Check the health of relevant scrape targets\n"
                                f"5. Provide a summary of findings and possible root causes."
                            ),
                        ),
                    )
                ],
            )

        elif name == "service-health":
            env = args.get("environment", "production")
            service = args.get("service", "")

            return GetPromptResult(
                description=f"Check health of service '{service}' in {env}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"Please check the overall health of service '{service}' in the '{env}' "
                                f"Prometheus environment. Check:\n"
                                f"1. Is the service up? (query 'up{{job=~\".*{service}.*\"}}')\n"
                                f"2. CPU usage (query rate of container_cpu_usage_seconds_total)\n"
                                f"3. Memory usage (query container_memory_working_set_bytes)\n"
                                f"4. Any active alerts related to this service\n"
                                f"5. Target health status\n"
                                f"Summarize the health status in a concise report."
                            ),
                        ),
                    )
                ],
            )

        else:
            raise ValueError(f"Unknown prompt: {name}")

    return server


def setup_logging(verbose: bool = False) -> None:
    """Configure logging to stderr (so it doesn't interfere with stdio transport)."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def main() -> None:
    """Entry point for prometheus-mcp-server."""
    parser = argparse.ArgumentParser(
        description="Prometheus MCP Server - Query metrics via natural language"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: auto-detect ~/.prometheus-mcp/config.yaml or PROMETHEUS_URL)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="HTTP server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP server port (default: 8000)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (for local) or http (for remote) (default: stdio)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load configuration
    try:
        config = load_config(args.config)
        logger.info(f"Loaded config with environments: {', '.join(config.list_environments())}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Create server
    server = create_server(config)

    if args.transport == "stdio":
        logger.info("Starting in stdio mode")
        from mcp.server.stdio import stdio_server

        async def run_stdio() -> None:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        asyncio.run(run_stdio())
    else:
        logger.info(f"Starting HTTP server on {args.host}:{args.port}")
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        session_manager = StreamableHTTPSessionManager(
            app=server,
            event_store=None,
            json_response=True,
        )

        app = Starlette(
            routes=[
                Mount("/", app=session_manager.handle_request),
            ],
        )

        async def run_server():
            async with session_manager.run():
                srv_config = uvicorn.Config(
                    app,
                    host=args.host,
                    port=args.port,
                    log_level="debug" if args.verbose else "info",
                )
                srv = uvicorn.Server(srv_config)
                await srv.serve()

        asyncio.run(run_server())


if __name__ == "__main__":
    main()
