"""FastMCP server entry point."""

import argparse
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from web_search_mcp.config import Settings, get_settings
from web_search_mcp.errors import AppError
from web_search_mcp.services.search_client import SearchClient
from web_search_mcp.services.webpage_client import WebpageClient
from web_search_mcp.tools.search import web_search as run_web_search
from web_search_mcp.tools.webpage import fetch_webpage as run_fetch_webpage

_CONSOLE_PATH = Path(__file__).parent / "static" / "index.html"
_CONSOLE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _error_response(error: AppError) -> dict[str, Any]:
    """Build a safe structured tool error."""

    return {"ok": False, "error": {"code": error.code, "message": error.message}}


def create_mcp(settings: Settings | None = None) -> FastMCP:
    """Create a configured FastMCP server instance."""

    resolved_settings = settings or get_settings()
    http_client = httpx.AsyncClient(
        timeout=resolved_settings.request_timeout_seconds,
        follow_redirects=False,
    )
    search_client = SearchClient(resolved_settings, http_client)
    webpage_client = WebpageClient(resolved_settings, http_client)

    @asynccontextmanager
    async def lifespan(_server: FastMCP[Any]):
        try:
            yield {}
        finally:
            await http_client.aclose()

    mcp = FastMCP(
        name=resolved_settings.app_name,
        instructions=(
            "Search the public web and fetch readable text from public webpages. "
            "Search requires SEARCH_API_KEY to be configured."
        ),
        host=resolved_settings.host,
        port=resolved_settings.port,
        streamable_http_path="/api/mcp",
        lifespan=lifespan,
        stateless_http=True,
    )

    @mcp.tool(description="Search the web and return structured results.")
    async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
        try:
            result = await run_web_search(search_client, query, max_results)
            return {"ok": True, **result.model_dump()}
        except AppError as error:
            return _error_response(error)
        except Exception:
            return _error_response(
                AppError("internal_error", "The search request could not be completed.")
            )

    @mcp.tool(description="Fetch a public webpage and extract readable text.")
    async def fetch_webpage(url: str) -> dict[str, Any]:
        try:
            result = await run_fetch_webpage(webpage_client, url)
            return {"ok": True, **result.model_dump()}
        except AppError as error:
            return _error_response(error)
        except Exception:
            return _error_response(
                AppError("internal_error", "The webpage request could not be completed.")
            )

    @mcp.resource(
        "server://info",
        name="server-info",
        description="Metadata about this Web Search MCP Server.",
        mime_type="application/json",
    )
    def server_info() -> str:
        return json.dumps(
            {
                "name": resolved_settings.app_name,
                "version": resolved_settings.version,
                "tools": ["web_search", "fetch_webpage"],
                "project_description": (
                    "A secure MCP server for web search and readable webpage extraction."
                ),
            }
        )

    @mcp.custom_route("/api/healthz", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": resolved_settings.app_name,
                "version": resolved_settings.version,
            }
        )

    async def console(_request: Request) -> HTMLResponse:
        return HTMLResponse(_CONSOLE_PATH.read_text(encoding="utf-8"), headers=_CONSOLE_HEADERS)

    # Served at "/" and also under "/api" for hosts that only route /api/* to this service.
    mcp.custom_route("/", methods=["GET"])(console)
    mcp.custom_route("/api/ui", methods=["GET"])(console)

    return mcp


def main() -> None:
    """Start the server using the configured local or remote transport."""

    parser = argparse.ArgumentParser(description="Run the Web Search MCP Server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=None,
        help="Override MCP_TRANSPORT for this process.",
    )
    args = parser.parse_args()
    settings = get_settings()
    create_mcp(settings).run(transport=args.transport or settings.mcp_transport)


if __name__ == "__main__":
    main()