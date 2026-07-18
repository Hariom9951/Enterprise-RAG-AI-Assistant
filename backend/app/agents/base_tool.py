"""
Enterprise RAG AI Assistant — BaseTool Contract
================================================
Every agent tool must inherit from BaseTool and implement execute().
Tools are the ONLY gateway through which the LLM can access enterprise data.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# =============================================================================
# Enums
# =============================================================================


class PermissionLevel(str, Enum):
    """Required minimum role to invoke a tool."""

    USER = "user"
    ADMIN = "admin"


# =============================================================================
# Result Container
# =============================================================================


@dataclass
class ToolResult:
    """
    Structured result returned by every tool execution.

    Attributes
    ----------
    success     Whether execution completed without an error.
    output      Primary payload (list, dict, str — tool-specific).
    metadata    Supplementary diagnostic information.
    latency_ms  Wall-clock execution time in milliseconds.
    error       Error message when success=False.
    """

    success: bool
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "metadata": self.metadata,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


# =============================================================================
# Parameter Schema
# =============================================================================


@dataclass
class ParameterSpec:
    """JSON-Schema-style parameter descriptor for a tool input."""

    name: str
    type: str  # "string" | "integer" | "number" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None


# =============================================================================
# Abstract Base Tool
# =============================================================================


class BaseTool(ABC):
    """
    Abstract base class for all enterprise agent tools.

    Subclasses must:
      1. Set class attributes: id, name, description, permission_level.
      2. Declare parameters as a list of ParameterSpec.
      3. Implement _run() — the actual async execution logic.

    execute() wraps _run() with:
      - Input validation
      - Timing measurement
      - Safe error capture
    """

    id: str = ""
    name: str = ""
    description: str = ""
    permission_level: PermissionLevel = PermissionLevel.USER
    parameters: list[ParameterSpec] = []

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and coerce params against this tool's parameter spec.
        Returns sanitized params dict; raises ValueError on violations.
        """
        validated: dict[str, Any] = {}

        for spec in self.parameters:
            val = params.get(spec.name)

            if val is None:
                if spec.required and spec.default is None:
                    raise ValueError(
                        f"Tool '{self.id}': required parameter '{spec.name}' is missing."
                    )
                val = spec.default

            if val is not None:
                # Type coercion
                if spec.type == "integer":
                    val = int(val)
                elif spec.type == "number":
                    val = float(val)
                elif spec.type == "boolean":
                    val = bool(val)
                elif spec.type == "string":
                    val = str(val)

                # Range guard
                if spec.minimum is not None and isinstance(val, int | float):
                    if val < spec.minimum:
                        raise ValueError(
                            f"Tool '{self.id}': parameter '{spec.name}' must be >= {spec.minimum}, got {val}."
                        )
                if spec.maximum is not None and isinstance(val, int | float):
                    if val > spec.maximum:
                        raise ValueError(
                            f"Tool '{self.id}': parameter '{spec.name}' must be <= {spec.maximum}, got {val}."
                        )

                # Enum guard
                if spec.enum is not None and val not in spec.enum:
                    raise ValueError(
                        f"Tool '{self.id}': parameter '{spec.name}' must be one of {spec.enum!r}, got {val!r}."
                    )

            validated[spec.name] = val

        return validated

    # ── Internal implementation (subclasses override) ─────────────────────────

    @abstractmethod
    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        """Core logic — called by execute() after validation."""
        ...

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        """
        Validate params, run the tool, and capture timing.
        Never raises — errors are returned inside ToolResult.
        """
        t0 = time.perf_counter()
        try:
            clean_params = self.validate_params(params)
            result = await self._run(clean_params, user_id, db)
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            return ToolResult(
                success=False,
                output=None,
                latency_ms=latency,
                error=str(exc),
            )
        result.latency_ms = int((time.perf_counter() - t0) * 1000)
        return result

    # ── Schema serialization ───────────────────────────────────────────────────

    def to_schema(self) -> dict[str, Any]:
        """Return a JSON-compatible tool descriptor for LLM function-calling."""
        props: dict[str, Any] = {}
        required_fields: list[str] = []

        for spec in self.parameters:
            prop: dict[str, Any] = {
                "type": spec.type,
                "description": spec.description,
            }
            if spec.enum:
                prop["enum"] = spec.enum
            if spec.minimum is not None:
                prop["minimum"] = spec.minimum
            if spec.maximum is not None:
                prop["maximum"] = spec.maximum
            if spec.default is not None:
                prop["default"] = spec.default
            props[spec.name] = prop
            if spec.required:
                required_fields.append(spec.name)

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "permission_level": self.permission_level.value,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required_fields,
            },
        }
