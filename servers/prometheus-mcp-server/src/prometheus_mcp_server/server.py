"""Prometheus MCP Server - main server logic with HTTP transport."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool

from .config import MCPConfig, load_config
from .client import PrometheusClient
from .tools import HANDLERS, get_tool_definitions

logger = logging.getLogger("prometheus-mcp-server")


def create_server(config: MCPConfig) -> Server:
    """Create the MCP server with all Prometheus tools."""
    server = Server("prometheus-mcp-server")

    tool_defs = get_tool_definitions()

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
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        from mcp.types import TextContent

        logger.info(f"Tool call: {name} with args: {arguments}")

        try:
            if name == "prometheus_list_environments":
                from .tools import handle_list_environments
                result = await handle_list_environments(config)
            else:
                env = arguments.get("environment", "")
                if not env and name != "prometheus_list_environments":
                    return [
                        TextContent(
                            type="text",
                            text=f"Error: 'environment' parameter is required for {name}",
                        )
                    ]

                env_config = config.get_environment(env)
                client = PrometheusClient(env_config)
                try:
                    handler = HANDLERS.get(name)
                    if handler is None:
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: Unknown tool '{name}'",
                            )
                        ]

                    if name == "prometheus_health":
                        from .tools import handle_health
                        result = await handle_health(client, env)
                    else:
                        result = await handler(client, env, arguments)
                finally:
                    await client.close()

            import json
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
                    text=json.dumps({"error": str(e), "tool": name}, indent=2),
                )
            ]

    return server


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Entry point for prometheus-mcp-server."""
    parser = argparse.ArgumentParser(
        description="Prometheus MCP Server - Query metrics via natural language"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="~/.prometheus-mcp/config.yaml",
        help="Path to configuration file (default: ~/.prometheus-mcp/config.yaml)",
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
        default="http",
        help="Transport mode: stdio (for local) or http (for remote) (default: http)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load configuration
    try:
        config = load_config(args.config)
        logger.info(f"Loaded config from {args.config}")
        logger.info(f"Environments: {', '.join(config.list_environments())}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Create server
    server = create_server(config)

    if args.transport == "stdio":
        logger.info("Starting in stdio mode")
        import asyncio
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

        import asyncio
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        # Create session manager
        session_manager = StreamableHTTPSessionManager(
            app=server,
            event_store=None,  # In-memory only
            json_response=True,
        )

        # Create ASGI app (session_manager handles routing internally)
        app = Starlette(
            routes=[
                Mount("/", app=session_manager.handle_request),
            ],
        )

        # Run server with session manager context
        async def run_server():
            async with session_manager.run():
                config = uvicorn.Config(
                    app,
                    host=args.host,
                    port=args.port,
                    log_level="debug" if args.verbose else "info",
                )
                srv = uvicorn.Server(config)
                await srv.serve()

        asyncio.run(run_server())


if __name__ == "__main__":
    main()
