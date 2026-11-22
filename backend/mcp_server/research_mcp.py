"""
Step 1: MarketPulse Research MCP Server (`backend/mcp_server/research_mcp.py`)

Wraps the deterministic corporate research tools in `ingestion/tools/research_tools.py`
into a Model Context Protocol (MCP) Server supporting:
  1. `tools/list`  — Discovers all registered tools and their JSON Input Schemas.
  2. `tools/call`  — Executes a tool by name with validated arguments and returns MCP content blocks.
  3. JSON-RPC 2.0 over stdio — Can be attached directly to Antigravity IDE, Claude Desktop, or n8n MCP Client.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

# Ensure `backend/` is on sys.path when launched standalone as a stdio MCP server
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ingestion.tools.research_tools import (
    fetch_sec_properties,
    fetch_source_fingerprint,
    fetch_wikipedia_facilities,
    search_web_sources,
)

logger = logging.getLogger("marketpulse.mcp_server")


class MCPToolRegistry:
    """
    Holds MCP tool definitions (`name`, `description`, `inputSchema`) and their async handlers.
    """

    def __init__(self, server_name: str = "marketpulse-research-mcp", version: str = "1.0.0"):
        self.server_name = server_name
        self.version = version
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Registers an async Python function as an MCP tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self._handlers[name] = handler

    def list_tools(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Standard MCP `tools/list` response payload.
        Optionally filters to a subset of tool names (e.g. only `search_web_sources`).
        """
        if names is None:
            return list(self._tools.values())
        return [self._tools[n] for n in names if n in self._tools]

    def to_llm_tools(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Converts MCP `inputSchema` definitions into the OpenAI / Groq / Mistral
        `{"type": "function", "function": {...}}` format expected by LLM APIs.
        """
        selected = self.list_tools(names)
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"],
                },
            }
            for t in selected
        ]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Standard MCP `tools/call` execution.
        Returns both the MCP-formatted `content` list and `structuredContent` dict.
        """
        args = arguments or {}
        if name not in self._handlers:
            error_payload = {"error": f"Unknown MCP tool: {name}"}
            return {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps(error_payload)}],
                "structuredContent": error_payload,
            }

        try:
            raw_result = await self._handlers[name](**args)
            # Wrap list results (like search_web_sources) in a dict for uniform structured output
            structured = {"results": raw_result} if isinstance(raw_result, list) else raw_result
            return {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
            }
        except Exception as exc:
            logger.error(f"MCP tool '{name}' failed: {exc}")
            error_payload = {"error": str(exc), "tool": name}
            return {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps(error_payload)}],
                "structuredContent": error_payload,
            }


# =====================================================================
# Instantiate & Register the 4 Corporate Footprint Research Tools
# =====================================================================

mcp_registry = MCPToolRegistry()

# 1. SEC EDGAR Item 2 Properties Tool
mcp_registry.register_tool(
    name="fetch_sec_properties",
    description=(
        "Fetches official SEC 10-K / 20-F Item 2 (Properties) and supply-chain disclosures "
        "directly from SEC EDGAR for a given stock ticker."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. 'NVDA', 'AAPL', 'TSLA'",
            }
        },
        "required": ["ticker"],
    },
    handler=fetch_sec_properties,
)

# 2. Wikipedia Facilities & Supply Chain Tool
mcp_registry.register_tool(
    name="fetch_wikipedia_facilities",
    description=(
        "Fetches facility, manufacturing, operational campus, and subsidiary paragraphs "
        "from Wikipedia for a given company name."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Full or common company name, e.g. 'NVIDIA Corporation' or 'Apple Inc.'",
            }
        },
        "required": ["company_name"],
    },
    handler=fetch_wikipedia_facilities,
)

# 3. Targeted Open Web Search Tool
mcp_registry.register_tool(
    name="search_web_sources",
    description=(
        "Searches the web for missing Tier-1 suppliers, contract manufacturers (e.g. Foxconn, TSMC), "
        "or specific facility locations missing from the SEC/Wikipedia evidence."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query e.g. 'NVIDIA tier 1 packaging suppliers TSMC CoWoS'",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of search results to return (default: 4)",
                "default": 4,
            },
        },
        "required": ["query"],
    },
    handler=search_web_sources,
)

# 4. Source Change-Detection Fingerprint Tool
mcp_registry.register_tool(
    name="fetch_source_fingerprint",
    description=(
        "Probes the latest SEC 10-K/20-F accession number, Wikipedia revision ID (lastrevid), "
        "and optional SHA-256 facility paragraph hash to detect if cached footprint data is stale."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. 'NVDA'"},
            "company_name": {"type": "string", "description": "Company name, e.g. 'NVIDIA Corporation'"},
            "cik": {"type": "string", "description": "Optional 10-digit SEC CIK number"},
            "include_content_hash": {
                "type": "boolean",
                "description": "Whether to compute the SHA-256 hash of Wikipedia facility paragraphs",
                "default": False,
            },
        },
        "required": ["ticker", "company_name"],
    },
    handler=fetch_source_fingerprint,
)


# =====================================================================
# Standard JSON-RPC 2.0 over stdio Handler (for external MCP hosts)
# =====================================================================

async def handle_jsonrpc_message(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Processes a single MCP JSON-RPC 2.0 request and returns the response object."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    # Notifications (no id) do not return a JSON-RPC response
    if req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": mcp_registry.server_name,
                    "version": mcp_registry.version,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": mcp_registry.list_tools()},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        result = await mcp_registry.call_tool(tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": result["content"],
                "isError": result["isError"],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def run_stdio_server() -> None:
    """Runs the MCP server over stdin/stdout for external MCP clients (Antigravity, Claude, n8n)."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        raw = line.decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            resp = await handle_jsonrpc_message(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    # If launched with `--self-test`, print registered tools and exit cleanly
    if "--self-test" in sys.argv:
        tools = mcp_registry.list_tools()
        print(f"MCP Server '{mcp_registry.server_name}' v{mcp_registry.version} ready with {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}: {t['description'][:70]}...")
    else:
        asyncio.run(run_stdio_server())

