"""ClaudeBackend against a stand-in SDK, so the isolation settings are tested without one."""

import asyncio
import sys
from types import SimpleNamespace

import pytest

from jjv.backend import BackendError, ClaudeBackend, Request, allowed, repo_guard


class SDKError(Exception):
    pass


class Result:
    def __init__(self, **kw):
        self.__dict__.update(dict(is_error=False, subtype="success", total_cost_usd=0.1,
                                  errors=None, result="text", structured_output=None) | kw)


@pytest.fixture
def sdk(monkeypatch):
    state = SimpleNamespace(options=None, messages=[Result()], raises=None)

    async def query(prompt, options):
        state.options = options
        for m in state.messages:
            yield m
        if state.raises:
            raise state.raises

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", SimpleNamespace(
        ClaudeAgentOptions=lambda **kw: SimpleNamespace(**kw), ClaudeSDKError=SDKError,
        HookMatcher=lambda **kw: SimpleNamespace(**kw),
        ResultMessage=Result, query=query))
    return state


def ask(**kw):
    return asyncio.run(ClaudeBackend().ask(Request(label="judge:x", system="s", prompt="p", **kw)))


def test_judges_are_isolated_from_user_settings_and_mcp(sdk):
    ask()
    o = sdk.options
    assert o.setting_sources == [] and o.strict_mcp_config is True
    assert o.permission_mode == "dontAsk" and o.tools == [] and o.hooks is None


def test_tools_always_come_with_the_repo_guard(sdk, tmp_path):
    ask(tools=["Read"], cwd=str(tmp_path))
    (matcher,) = sdk.options.hooks["PreToolUse"]
    assert matcher.matcher == "Read|Grep|Glob" and matcher.on_failure == "block"


def test_sdk_exceptions_become_backend_errors_with_cost(sdk):
    sdk.messages, sdk.raises = [], SDKError("process died")
    with pytest.raises(BackendError) as e:
        ask(max_usd=0.4)
    assert e.value.cost == 0.4 and e.value.retry


def test_hitting_the_budget_does_not_retry_and_uses_the_real_cost(sdk):
    sdk.messages = [Result(total_cost_usd=0.33)]
    sdk.raises = SDKError("Reached maximum budget ($0.33)")
    with pytest.raises(BackendError) as e:
        ask(max_usd=0.4)
    assert e.value.cost == 0.33 and not e.value.retry


def test_structured_output_and_json_fallback(sdk):
    sdk.messages = [Result(structured_output={"a": 1})]
    assert ask(schema={}).data == {"a": 1}
    sdk.messages = [Result(result='{"b": 2}')]
    assert ask(schema={}).data == {"b": 2}
    sdk.messages = [Result(result="prose")]
    with pytest.raises(BackendError):
        ask(schema={})


@pytest.mark.parametrize("tool, tool_input, expected", [
    ("Read", {"file_path": "src/a.py"}, True),
    ("Glob", {"pattern": "**/*.py"}, True),
    ("Grep", {"pattern": "secret", "path": "src", "glob": "*.py"}, True),
    ("Grep", {"pattern": "/api/v1/.."}, True),          # a regex, not a path
    ("Read", {"file_path": "~/.ssh/id_rsa"}, False),
    ("Read", {"file_path": "/etc/passwd"}, False),
    ("Read", {"file_path": "../outside"}, False),
    ("Grep", {"pattern": "x", "path": "/"}, False),
    ("Glob", {"pattern": "/etc/*"}, False),
    ("Glob", {"pattern": "../*"}, False),
    ("Glob", {"pattern": "{..,x}/secret"}, False),
    ("Grep", {"pattern": "x", "glob": "../../*"}, False),
    ("Read", {"file_path": 123}, False),
    ("Glob", {"pattern": ["x"]}, False),
])
def test_allowed_keeps_tools_in_the_repo(tmp_path, tool, tool_input, expected):
    assert allowed(str(tmp_path), tool, tool_input) is expected


@pytest.mark.parametrize("path", [".env", ".env.local", "config/server.pem", "certs/a.P12",
                                  "deploy.key", ".git/config", "sub/.ssh/id_rsa", ".npmrc"])
def test_secret_files_inside_the_repo_are_denied(tmp_path, path):
    assert not allowed(str(tmp_path), "Read", {"file_path": path})
    assert not allowed(str(tmp_path), "Grep", {"pattern": "x", "path": path})


def test_ordinary_files_are_not_mistaken_for_secrets(tmp_path):
    for path in ("environment.py", "docs/keys.md", "gitignore.txt"):
        assert allowed(str(tmp_path), "Read", {"file_path": path})


def test_a_symlink_out_of_the_repo_is_denied(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "link").symlink_to(tmp_path)
    assert not allowed(str(repo), "Read", {"file_path": "link/secret"})


def run_guard(root, tool_input, tool="Read"):
    return asyncio.run(repo_guard(root)({"tool_name": tool, "tool_input": tool_input}, "id", None))


def test_guard_denies_outside_and_stays_silent_inside(tmp_path):
    assert run_guard(str(tmp_path), {"file_path": "a.py"}) == {}
    denied = run_guard(str(tmp_path), {"file_path": "/etc/passwd"})
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("tool_input", [{"file_path": "~nosuchuser/x"}, {"file_path": "a\0b"},
                                        {"file_path": 123}, "not a dict"])
def test_guard_fails_closed_when_the_check_cannot_run(tmp_path, tool_input):
    """Found by the panel: these crashed the check, and a crashed hook lets the tool run."""
    denied = run_guard(str(tmp_path), tool_input)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
