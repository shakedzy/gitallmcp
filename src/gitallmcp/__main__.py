"""CLI: stdio or streamable-http transport."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Literal, cast

import anyio

from gitallmcp.env_load import load_dotenv_files
from gitallmcp.server import create_mcp, run_streamable_http_with_cors


def main() -> None:
    load_dotenv_files()

    parser = argparse.ArgumentParser(description="Git-All-MCP GitHub MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for streamable-http (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9001,
        help="Port for streamable-http (default: 9001)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    mcp = create_mcp(host=args.host, port=args.port)
    transport = cast(Literal["stdio", "streamable-http"], args.transport)
    if transport == "streamable-http":
        anyio.run(run_streamable_http_with_cors, mcp)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
