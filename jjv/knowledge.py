"""Optional grounding: let Judges look things up in a personal knowledge base and cite them.

Off unless a run asks for it. The knowledge base is the separate, optional ``km`` package,
imported only when used, so JJV keeps its standard-library core.

Each Judge gets its own KnowledgeSession, which lasts for the whole run. The session records
what that Judge actually read, because a citation only counts if the Judge read the record.
What a session may see is fixed when it is created. Nothing in a tool call can widen it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

MAX_LOOKUPS = 20
READ_TOOL = "read_knowledge_record"
SERVER_NAME = "km"


class KnowledgeUnavailable(RuntimeError):
    """The run asked for grounding that cannot be provided."""


class KnowledgeSession:
    def __init__(self, tools: list[dict], handler: Callable[[str, dict], str],
                 withheld: Callable[[], int] = lambda: 0):
        self.tools = tools
        self._handler = handler
        self._withheld = withheld
        self.lookups = 0
        self.reads: dict[str, str] = {}      # record id -> hash of the version read

    @property
    def tool_names(self) -> list[str]:
        return [f"mcp__{SERVER_NAME}__{t['name']}" for t in self.tools]

    @property
    def withheld(self) -> int:
        return self._withheld()

    def call(self, name: str, tool_input: dict) -> str:
        """Run one lookup. Failures are returned to the Judge, not raised."""
        if self.lookups >= MAX_LOOKUPS:
            return json.dumps({"error": "lookup limit reached; decide from what you have read"})
        self.lookups += 1
        try:
            reply = self._handler(name, tool_input)
            data = json.loads(reply)
        except Exception as e:
            return json.dumps({"error": f"lookup failed: {type(e).__name__}"})
        if name == READ_TOOL and "content_hash" in data:
            self.reads[data["id"]] = data["content_hash"]
        return reply


def km_sessions(tag: str | None = None) -> Callable[[], KnowledgeSession]:
    """A factory for sessions backed by the ``km`` package."""
    try:
        from km.jjv_bridge import TOOLS, handle_tool
        from km.sensitive import Policy
    except ImportError as e:
        raise KnowledgeUnavailable(
            "--knowledge needs the km package, which is not installed or is too old") from e

    def make() -> KnowledgeSession:
        policy = Policy(tag=tag)
        return KnowledgeSession(TOOLS, lambda name, args: handle_tool(name, args, policy=policy),
                                lambda: policy.withheld)
    return make


def keep_out_of_git(store: str) -> None:
    """Run records can quote notes, so git must never pick up a grounded run's store."""
    root = Path(store).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("*\n")


def summarize(tag: str | None, sessions: dict[str, KnowledgeSession], rounds: list[dict]) -> dict:
    """The run record's knowledge section: ids and hashes only, never note text."""
    cited, rejected = {}, {}
    for rec in rounds:
        for verdicts in (rec.get("judge", []), rec.get("jury", [])):
            for v in verdicts:
                session = sessions.get(v["archetype_id"])
                for f in v["findings"]:
                    for record_id in f.get("citations", []):
                        cited[f["id"], record_id] = {
                            "finding": f["id"], "id": record_id,
                            "content_hash": session.reads.get(record_id) if session else None,
                        }
                for r in v.get("rejected_citations", []):
                    rejected[r["finding"], r["id"]] = r
    return {
        "enabled": True,
        "scope": {"tag": tag},
        "reads": [{"judge": judge, "id": record_id, "content_hash": content_hash}
                  for judge, session in sorted(sessions.items())
                  for record_id, content_hash in sorted(session.reads.items())],
        "cited": list(cited.values()),
        "rejected_citations": list(rejected.values()),
        "withheld": sum(s.withheld for s in sessions.values()),
    }
