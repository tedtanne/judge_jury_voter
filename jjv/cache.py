"""Reuse a finished review of the same content, so asking twice costs nothing.

A result is reused only when everything that shapes it matches: the content, the mode, the
panel and each archetype's version, and the settings that change how Judges are run or
settled. The spending limit is not part of it. Runs that failed, or lost a Judge, are never
reused, and neither are runs that read a repository, whose contents can change.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from jjv.orchestrator import _write

CACHE_VERSION = 1      # raise when prompts or rules change enough that old results mislead
RUN_ID = re.compile(r"^[0-9a-f]{12}$")


def fingerprint(content: str | bytes) -> str:
    """A fingerprint of the content alone, for an app to store beside its own record."""
    data = content.encode() if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def cache_key(mode: str, content_fingerprint: str, panel: list[dict], **settings) -> str:
    parts = {"version": CACHE_VERSION, "mode": mode, "content": content_fingerprint,
             "panel": sorted((a["id"], a["version"]) for a in panel), "settings": settings}
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _pointer(store: str, key: str) -> Path:
    return Path(store).expanduser() / "cache" / key


def reusable(run: dict) -> bool:
    return run.get("status") == "done" and not run.get("failures")


def lookup(store: str, key: str) -> dict | None:
    """The saved run for this key, or None. A damaged or unusable entry is a miss."""
    try:
        run_id = _pointer(store, key).read_text().strip()
        if not RUN_ID.fullmatch(run_id):
            return None
        run = json.loads((Path(store).expanduser() / f"{run_id}.json").read_text())
    except (OSError, ValueError):
        return None
    return run if reusable(run) else None


def remember(store: str, key: str, run: dict) -> bool:
    if not reusable(run):
        return False
    path = _pointer(store, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, run["id"])
    except OSError:
        return False
    return True
