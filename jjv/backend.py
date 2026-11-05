"""The one place that talks to a model.

The orchestrator depends only on ``Backend.ask``, so tests drive every phase with a fake
and need neither an API key nor the SDK. ``ClaudeBackend`` imports the SDK when first used.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from jjv.knowledge import SERVER_NAME


class BackendError(RuntimeError):
    """A model call failed. ``cost`` is what it spent before failing.

    ``retry=False`` means asking again cannot help, such as running out of budget.
    """

    def __init__(self, message: str, cost: float = 0.0, retry: bool = True):
        super().__init__(message)
        self.cost = cost
        self.retry = retry


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
    knowledge: object | None = None  # a jjv.knowledge.KnowledgeSession, for grounded Judges


@dataclass
class Reply:
    data: object                     # parsed object when a schema was given, else text
    cost: float = 0.0


class Backend(Protocol):
    async def ask(self, request: Request) -> Reply: ...


SECRET_NAMES = (".env", ".env.*", "*.pem", "*.p12", "*.pfx", "*.key", "id_rsa*", "id_ed25519*",
                ".netrc", ".npmrc", ".pypirc")
SECRET_DIRS = {".git", ".ssh", ".aws", ".gnupg"}


def is_secret(path: Path) -> bool:
    """Is this repo-relative path a file no Judge should read?"""
    # Lowercased because macOS and Windows treat .GIT and .git as the same folder.
    parts = {part.lower() for part in path.parts}
    return (bool(SECRET_DIRS & parts)
            or any(fnmatch(path.name.lower(), name) for name in SECRET_NAMES))


def allowed(root: str, tool: str, tool_input: dict) -> bool:
    """May this Read, Grep or Glob call run? It must stay in ``root`` and off secret files.

    Grep's ``pattern`` is a regex, not a path, so only Glob's is checked. A Grep over a
    directory skips gitignored files, but a secret that git does not ignore is searchable.
    """
    base = Path(root).resolve()
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            return False
        target = Path(value).expanduser()
        target = (target if target.is_absolute() else base / target).resolve()
        if not target.is_relative_to(base) or is_secret(target.relative_to(base)):
            return False
    patterns = [tool_input.get("glob")] + ([] if tool == "Grep" else [tool_input.get("pattern")])
    for value in patterns:
        if value is None:
            continue
        # A substring check, because brace expansion hides ".." from path parsing.
        if not isinstance(value, str) or value.startswith(("/", "~")) or ".." in value:
            return False
    return True


def repo_guard(root: str):
    """A PreToolUse hook that denies file access outside ``root`` and to secret files.

    A bare ``Read`` in allowed_tools approves every path on the machine, and the subject is
    untrusted, so without this a hostile document could steer a Judge to ~/.ssh. Any failure
    in the check is a denial: the CLI treats a crashed hook as no decision, and runs the tool.
    """
    async def guard(hook_input, tool_use_id, context):
        try:
            ok = allowed(root, hook_input.get("tool_name", ""), hook_input.get("tool_input") or {})
        except Exception:
            ok = False
        if ok:
            return {}
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Only non-secret files inside {root} may be read.",
        }}
    return guard


def knowledge_server(session, create_server, tool):
    """An in-process MCP server exposing one Judge's session, and nothing else."""
    def expose(spec: dict):
        async def run(args: dict) -> dict:
            return {"content": [{"type": "text", "text": session.call(spec["name"], args)}]}
        return tool(spec["name"], spec["description"], spec["input_schema"])(run)
    return create_server(SERVER_NAME, tools=[expose(spec) for spec in session.tools])


class ClaudeBackend:
    """One isolated ``query()`` per request, on the Claude Agent SDK.

    Each Judge sees only what the orchestrator gives it. ``setting_sources=[]`` and
    ``strict_mcp_config`` keep the user's settings, memory and connected MCP servers out,
    ``dontAsk`` denies any tool outside the archetype's read-only allow-list, and
    ``repo_guard`` confines those tools to the repository. That matters because the subject
    under review is untrusted text. A grounded Judge also gets its own in-process server, the
    only MCP server it can reach, whose tools are read-only.
    """

    MAX_TURNS = 30

    def __init__(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="jjv-")

    async def ask(self, request: Request) -> Reply:
        try:
            from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKError, HookMatcher,
                                          ResultMessage, query)
        except ImportError as e:
            raise BackendError("claude-agent-sdk is not installed; run "
                               "`pip install -r requirements-live.txt`") from e

        servers, allowed = {}, list(request.tools)
        if request.knowledge is not None:
            from claude_agent_sdk import create_sdk_mcp_server, tool
            servers = {SERVER_NAME: knowledge_server(request.knowledge, create_sdk_mcp_server, tool)}
            allowed += request.knowledge.tool_names

        options = ClaudeAgentOptions(
            system_prompt=request.system,
            model=request.model,
            effort=request.effort,
            tools=request.tools,
            allowed_tools=allowed,
            mcp_servers=servers,
            permission_mode="dontAsk",
            setting_sources=[],
            strict_mcp_config=True,
            cwd=request.cwd or self._scratch.name,
            max_turns=self.MAX_TURNS,
            max_budget_usd=request.max_usd,
            output_format=({"type": "json_schema", "schema": request.schema}
                           if request.schema else None),
            hooks=({"PreToolUse": [HookMatcher(matcher="Read|Grep|Glob",
                                               hooks=[repo_guard(request.cwd)],
                                               on_failure="block")]}
                   if request.tools else None),
        )
        final = None
        try:
            async for message in query(prompt=request.prompt, options=options):
                if isinstance(message, ResultMessage):
                    final = message
        except ClaudeSDKError as e:
            # The SDK raises on an error result, and the call may have spent up to its cap.
            spent = final.total_cost_usd if final else request.max_usd
            raise BackendError(str(e), spent or 0.0,
                               retry="maximum budget" not in str(e)) from e
        if final is None:
            raise BackendError("no result from the model")

        cost = final.total_cost_usd or 0.0
        if final.is_error:
            detail = "; ".join(final.errors or []) or final.result or ""
            raise BackendError(f"{final.subtype}: {detail}".strip(": "), cost,
                               retry=final.subtype != "error_max_budget_usd")
        if request.schema is None:
            return Reply(final.result or "", cost)
        if final.structured_output is not None:
            return Reply(final.structured_output, cost)
        try:
            return Reply(json.loads(final.result or ""), cost)
        except json.JSONDecodeError as e:
            raise BackendError("reply was not the requested JSON", cost) from e
