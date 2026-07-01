"""ACR MCP Server - main server logic with stdio transport."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .client import ACRClient
from .config import ACRConfig
from .tools import HANDLERS, get_tool_definitions

logger = logging.getLogger("acr-mcp-server")


def create_server(config: ACRConfig) -> Server:
    """Create the MCP server with all ACR tools."""
    server = Server("acr-mcp-server")
    client = ACRClient(config)
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

        try:
            result = await handler(client, arguments)
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
                            "hint": "Check namespace, repo_name, tag, and ACR connectivity",
                        },
                        indent=2,
                    ),
                )
            ]

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
    """Entry point for acr-mcp-server."""
    parser = argparse.ArgumentParser(
        description="ACR MCP Server - Query Alibaba Cloud Container Registry via natural language"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="ACR region ID (overrides ACR_REGION_ID env var, default: ap-southeast-1)",
    )
    parser.add_argument(
        "--access-key-id",
        type=str,
        default=None,
        help="Alibaba Cloud Access Key ID (overrides env var)",
    )
    parser.add_argument(
        "--access-key-secret",
        type=str,
        default=None,
        help="Alibaba Cloud Access Key Secret (overrides env var)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load configuration
    config = ACRConfig(
        access_key_id=args.access_key_id,
        access_key_secret=args.access_key_secret,
        region_id=args.region,
    )
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    logger.info(f"ACR region: {config.region_id}, endpoint: {config.endpoint}")

    # Create server
    server = create_server(config)

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


if __name__ == "__main__":
    main()
