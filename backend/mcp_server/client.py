"""
Step 2: MarketPulse MCP Client Bridge (`backend/mcp_server/client.py`)

Allows any agent in the backend (`footprint_agent`, `contradiction_agent`, `research_agent`, etc.)
to request tool schemas ON DEMAND (`tools/list`) and invoke tools (`tools/call`) through the
Model Context Protocol (MCP) Server without hardcoding tool JSON or `if/elif` dispatchers.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from agents.observability import trace_mcp_tool_call
from mcp_server.research_mcp import handle_jsonrpc_message, mcp_registry

logger = logging.getLogger("marketpulse.mcp_client")


class MCPClientBridge:
    """
    Client interface to the MarketPulse Research MCP Server.
    Communicates via MCP JSON-RPC 2.0 requests (`initialize`, `tools/list`, `tools/call`).
    """

    def __init__(self) -> None:
        self._request_counter = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def ensure_initialized(self) -> Dict[str, Any]:
        """Performs the MCP `initialize` handshake on first request."""
        if self._initialized:
            return {"status": "already_initialized"}

        resp = await handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "marketpulse-agent-client", "version": "1.0.0"},
                },
            }
        )
        self._initialized = True
        return (resp or {}).get("result", {})

    async def list_mcp_tools(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Queries the MCP Server via `tools/list` on demand.
        If `names` is provided, filters to only the requested tools so the agent's context window
        isn't bloated with unused tool schemas.
        """
        await self.ensure_initialized()
        resp = await handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            }
        )
        all_tools = (resp or {}).get("result", {}).get("tools", [])
        if names is None:
            return all_tools
        wanted = set(names)
        return [t for t in all_tools if t.get("name") in wanted]

    async def request_llm_tools(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Requests tool schemas from the MCP Server on demand and converts their `inputSchema`
        into the OpenAI / Groq / Mistral `{"type": "function", "function": ...}` format.
        """
        mcp_tools = await self.list_mcp_tools(names=names)
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"],
                },
            }
            for t in mcp_tools
        ]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Invokes a tool on the MCP Server via JSON-RPC `tools/call`, parses the JSON text block,
        and logs a nested `retriever` / `tool` observation in Langfuse.
        """
        await self.ensure_initialized()
        args = arguments or {}
        t0 = time.time()
        logger.debug(f"[MCP Client] Calling tool '{name}' with args={args}")
        resp = await handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": args,
                },
            }
        )
        duration_ms = round((time.time() - t0) * 1000, 2)
        result_block = (resp or {}).get("result", {})
        content_list = result_block.get("content", [])
        parsed: Dict[str, Any] = {"error": f"Empty MCP response from tool '{name}'"}
        if content_list and isinstance(content_list[0], dict):
            raw_text = content_list[0].get("text", "{}")
            try:
                parsed = json.loads(raw_text)
            except Exception:
                parsed = {"raw": raw_text}

        try:
            trace_mcp_tool_call(name, args, parsed, duration_ms=duration_ms)
        except Exception as exc:
            logger.debug(f"MCP trace skipped: {exc}")

        return parsed


# Singleton MCP Client used by agents across the backend
mcp_client = MCPClientBridge()

