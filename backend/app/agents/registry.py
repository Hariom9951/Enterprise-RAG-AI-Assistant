"""
Enterprise RAG AI Assistant — Tool Registry
============================================
Central registry for discovering, listing, and securely executing tools.
The LLM orchestration layer interacts ONLY through this registry.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, PermissionLevel, ToolResult
from app.core.logging import logger
from app.models.user import User


class ToolRegistry:
    """
    Singleton-style registry that maps tool IDs to BaseTool instances.

    Responsibilities
    ----------------
    - register() : Add a new tool (raises on duplicate ID).
    - get()       : Retrieve tool by ID (raises on unknown ID).
    - list_all()  : Return schemas of all tools visible to a user role.
    - execute()   : Validate permission, then run tool.execute().
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Add a tool to the registry. Raises ValueError on duplicate id."""
        if not tool.id:
            raise ValueError("Tool must have a non-empty 'id'.")
        if tool.id in self._tools:
            raise ValueError(f"Tool '{tool.id}' is already registered.")
        self._tools[tool.id] = tool
        logger.debug(f"[ToolRegistry] Registered tool: {tool.id!r} ({tool.name!r})")

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, tool_id: str) -> BaseTool:
        """Retrieve a tool by ID. Raises KeyError if not found."""
        if tool_id not in self._tools:
            raise KeyError(f"Tool '{tool_id}' is not registered.")
        return self._tools[tool_id]

    def list_all(self, role: str = "user") -> list[dict[str, Any]]:
        """
        Return JSON schemas for all tools the given role is allowed to see.
        ADMIN sees all tools; USER sees only USER-level tools.
        """
        schemas = []
        for tool in self._tools.values():
            if role == "admin":
                schemas.append(tool.to_schema())
            elif tool.permission_level == PermissionLevel.USER:
                schemas.append(tool.to_schema())
        return schemas

    # ── Execution ─────────────────────────────────────────────────────────────

    async def execute(
        self,
        tool_id: str,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
        user: User | None = None,
    ) -> ToolResult:
        """
        Permission-check then delegate to tool.execute().

        Permission rules
        ----------------
        - ADMIN tools: require user.role == 'admin'
        - USER tools: any authenticated user
        """
        tool = self.get(tool_id)

        # Permission enforcement
        if tool.permission_level == PermissionLevel.ADMIN:
            if user is None or str(getattr(user, "role", "user")).lower() != "admin":
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Tool '{tool_id}' requires admin privileges.",
                )

        logger.debug(f"[ToolRegistry] Executing tool '{tool_id}' for user {user_id}")
        result = await tool.execute(params, user_id, db)
        if result.success:
            logger.debug(
                f"[ToolRegistry] Tool '{tool_id}' succeeded in {result.latency_ms}ms"
            )
        else:
            logger.warning(f"[ToolRegistry] Tool '{tool_id}' failed: {result.error}")
        return result

    @property
    def tool_ids(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


# =============================================================================
# Default Registry — populated at import time
# =============================================================================

from app.agents.tools.citation import CitationTool  # noqa: E402
from app.agents.tools.conversation_history import ConversationHistoryTool  # noqa: E402
from app.agents.tools.document_lookup import DocumentLookupTool  # noqa: E402
from app.agents.tools.semantic_search import SemanticSearchTool  # noqa: E402

_default_registry = ToolRegistry()
_default_registry.register(SemanticSearchTool())
_default_registry.register(DocumentLookupTool())
_default_registry.register(CitationTool())
_default_registry.register(ConversationHistoryTool())


def get_registry() -> ToolRegistry:
    """Return the application-wide default tool registry."""
    return _default_registry
