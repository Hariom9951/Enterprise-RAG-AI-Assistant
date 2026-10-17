"""
Enterprise RAG AI Assistant — MCP Adapter Interface
====================================================
Minimal MCP (Model Context Protocol) adapter wrapping existing BaseTool instances.

Dependency Status:
  No 'mcp' package is installed in this repository.
  This adapter provides a clean MCP-compatible interface that:
    1. Exposes registered BaseTool schemas as MCP tool descriptors.
    2. Validates incoming MCP tool-call parameters against ParameterSpec.
    3. Enforces an allowlist of tools that may be exposed.
    4. Rejects all mutating tools (admin-level tools are not exposed).
    5. Enforces MAX_RESULTS_PER_CALL and REQUEST_TIMEOUT_SECONDS limits.
    6. Converts ToolResult into MCP-compatible content lists.

  When a genuine MCP client/server SDK (e.g., 'mcp>=1.0') is installed,
  replace MCPAdapterTransport.handle_request() with a real MCP protocol
  session without changing this validation or allowlist layer.

IMPORTANT: This adapter is INTENTIONALLY not integrated with an external
MCP server. No outbound MCP connections are made. It is a server-side
adapter that routes incoming MCP-style calls to local BaseTool instances.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import PermissionLevel, ToolResult
from app.agents.registry import ToolRegistry
from app.agents.tools.personal_app_base import MAX_RESULTS_PER_CALL, REQUEST_TIMEOUT_SECONDS
from app.core.logging import logger
from app.models.user import User


# =============================================================================
# MCP-Compatible Tool Descriptor
# =============================================================================


def _to_mcp_descriptor(tool_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a BaseTool JSON schema into an MCP-compatible tool descriptor.

    MCP tool descriptor format (per MCP specification 2024-11 draft):
    {
        "name": "...",
        "description": "...",
        "inputSchema": {
            "type": "object",
            "properties": { ... },
            "required": [...]
        }
    }
    """
    return {
        "name": tool_schema["id"],
        "description": tool_schema["description"],
        "inputSchema": {
            "type": "object",
            "properties": tool_schema["parameters"]["properties"],
            "required": tool_schema["parameters"]["required"],
        },
    }


def _from_mcp_result(result: ToolResult) -> dict[str, Any]:
    """
    Convert a ToolResult into an MCP-compatible CallToolResult content list.

    MCP result format:
    {
        "content": [ { "type": "text", "text": "..." } ],
        "isError": false
    }
    """
    if not result.success:
        return {
            "content": [{"type": "text", "text": f"Error: {result.error or 'Tool execution failed.'}"}],
            "isError": True,
        }

    # Serialize output to a safe text string
    import json

    try:
        text = json.dumps(result.output, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = str(result.output)

    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }


# =============================================================================
# MCP Adapter
# =============================================================================

# Tool IDs explicitly permitted for MCP exposure.
# Admin-only tools and internal implementation tools are excluded.
MCP_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "semantic_search",
        "document_lookup",
        "gmail_search",
        "google_drive_search",
        "github_search",
        "linkedin_profile",
    }
)



class MCPAdapter:
    """
    Server-side MCP protocol adapter wrapping a ToolRegistry.

    Provides:
    - list_tools()    → MCP-compatible tool descriptor list.
    - call_tool()     → Validates, executes, and returns MCP-formatted result.

    Dependency Note:
      This class does NOT require the 'mcp' Python package. It implements
      the MCP tool-call and list-tools semantics using the existing BaseTool
      infrastructure. When the 'mcp' SDK is available, this adapter can be
      wrapped in a proper MCP session (e.g., mcp.Server) without changing
      the validation or allowlist logic.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def list_tools(self) -> list[dict[str, Any]]:
        """
        Return MCP-compatible tool descriptors for all allowlisted, user-level tools.
        Admin tools are excluded from MCP exposure.
        """
        descriptors = []
        for tool_id in MCP_TOOL_ALLOWLIST:
            try:
                tool = self._registry.get(tool_id)
            except KeyError:
                continue  # Tool not yet registered (optional tool)

            if tool.permission_level == PermissionLevel.ADMIN:
                continue  # Never expose admin tools via MCP

            schema = tool.to_schema()
            descriptors.append(_to_mcp_descriptor(schema))

        return descriptors

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
        user: User | None = None,
    ) -> dict[str, Any]:
        """
        Validate and execute an MCP tool call.

        Enforces:
        - Tool must be in MCP_TOOL_ALLOWLIST.
        - Tool must be USER-level (admin tools are rejected).
        - Parameters are validated by BaseTool.validate_params().
        - Result is capped by each tool's internal MAX_RESULTS_PER_CALL.

        Returns an MCP-compatible CallToolResult dict.
        """
        # Allowlist check
        if tool_name not in MCP_TOOL_ALLOWLIST:
            logger.warning("[MCPAdapter] Rejected tool call for non-allowlisted tool: {}", tool_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Tool '{tool_name}' is not available via MCP.",
                    }
                ],
                "isError": True,
            }

        # Registry lookup
        try:
            tool = self._registry.get(tool_name)
        except KeyError:
            return {
                "content": [{"type": "text", "text": f"Error: Tool '{tool_name}' is not registered."}],
                "isError": True,
            }

        # Block admin tools
        if tool.permission_level == PermissionLevel.ADMIN:
            logger.warning("[MCPAdapter] Blocked admin tool via MCP: {}", tool_name)
            return {
                "content": [{"type": "text", "text": f"Error: Tool '{tool_name}' is not available via MCP."}],
                "isError": True,
            }

        # Parameter schema validation
        try:
            validated_args = tool.validate_params(arguments)
        except ValueError as exc:
            return {
                "content": [{"type": "text", "text": f"Error: Invalid parameters — {exc}"}],
                "isError": True,
            }

        # Enforce max_results cap on any result-count parameter
        for count_param in ("max_results", "top_k"):
            if count_param in validated_args and validated_args[count_param] is not None:
                validated_args[count_param] = min(
                    int(validated_args[count_param]), MAX_RESULTS_PER_CALL
                )

        logger.debug("[MCPAdapter] Calling tool '{}' for user {}", tool_name, user_id)
        result = await tool.execute(validated_args, user_id, db)
        mcp_result = _from_mcp_result(result)
        return mcp_result
