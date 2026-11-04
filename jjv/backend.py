"""The one place that talks to a model.

The orchestrator depends only on ``Backend.ask``, so tests drive every phase with a fake
and need neither an API key nor the SDK. ``ClaudeBackend`` imports the SDK when first used.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from typing import Protocol


class BackendError(RuntimeError):
    """A model call failed. ``cost`` is what it spent before failing."""

    def __init__(self, message: str, cost: float = 0.0):
        super().__init__(message)
        self.cost = cost


@dataclass
class Request:
    label: str                       # "<kind>:<archetype_id>", for logs and test fakes
    system: str
    prompt: str
    schema: dict | None = None       # JSON schema; None asks for plain text
    model: str | None = None
    effort: str | None = None
    tools: list[str] = field(default_factory=list)
    cwd: str | None = None
    max_usd: float | None = None


@dataclass
class Reply:
    data: object                     # parsed object when a schema was given, else text
    cost: float = 0.0


class Backend(Protocol):
    async def ask(self, request: Request) -> Reply: ...


class ClaudeBackend:
    """One isolated ``query()`` per request, on the Claude Agent SDK.

    Each Judge sees only what the orchestrator gives it. ``setting_sources=[]`` and
    ``strict_mcp_config`` keep the user's settings, memory and connected MCP servers out,
    and ``dontAsk`` denies any tool outside the archetype's read-only allow-list. That
    matters because the subject under review is untrusted text.
    """

    MAX_TURNS = 30

    def __init__(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="jjv-")

    async def ask(self, request: Request) -> Reply:
        try:
            from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
        except ImportError as e:
            raise BackendError("claude-agent-sdk is not installed; run "
                               "`pip install -r requirements-live.txt`") from e

        options = ClaudeAgentOptions(
            system_prompt=request.system,
            model=request.model,
            effort=request.effort,
            tools=request.tools,
            allowed_tools=request.tools,
            permission_mode="dontAsk",
            setting_sources=[],
            strict_mcp_config=True,
            cwd=request.cwd or self._scratch.name,
            max_turns=self.MAX_TURNS,
            max_budget_usd=request.max_usd,
            output_format=({"type": "json_schema", "schema": request.schema}
                           if request.schema else None),
        )
        final = None
        async for message in query(prompt=request.prompt, options=options):
            if isinstance(message, ResultMessage):
                final = message
        if final is None:
            raise BackendError("no result from the model")

        cost = final.total_cost_usd or 0.0
        if final.is_error:
            detail = "; ".join(final.errors or []) or final.result or ""
            raise BackendError(f"{final.subtype}: {detail}".strip(": "), cost)
        if request.schema is None:
            return Reply(final.result or "", cost)
        if final.structured_output is not None:
            return Reply(final.structured_output, cost)
        try:
            return Reply(json.loads(final.result or ""), cost)
        except json.JSONDecodeError as e:
            raise BackendError("reply was not the requested JSON", cost) from e
