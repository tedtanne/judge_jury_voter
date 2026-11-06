"""The MCP layer: free tools spend nothing, and paid tools cannot pass their limits."""

import asyncio
import json
import socket

import pytest

from jjv import fetch
from jjv.fetch import FetchError, fetch_text
from jjv.mcp_server import Limits, Service, ToolError
from tests.test_orchestrator import Fake, finding, reply_for

PANEL = "Docs Crit"


def paid(**kw):
    return Limits(paid=True, **kw)


def service(tmp_path, limits=None, fake=None, **kw):
    return Service(str(tmp_path / "runs"), limits or paid(), lambda: fake or Fake(), **kw)


def finish(svc, **kw):
    """Start a run and wait for it, inside one event loop."""
    async def go():
        job = svc.start("review", PANEL, text="the idea", **kw)
        await svc.jobs[job["job_id"]].task
        return job
    return asyncio.run(go())


def test_free_tools_list_the_registry(tmp_path):
    svc = service(tmp_path, Limits())
    assert any(p["name"] == "Physics of Compute" for p in svc.list_panels())
    assert any(a["id"] == "thermodynamicist" and a["veto_on"] for a in svc.list_archetypes())


def test_providers_report_readiness_without_revealing_a_key(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    entry = {"model": "m", "usd_per_mtok_in": 1, "usd_per_mtok_out": 1}
    path.write_text(json.dumps({"xai": entry, "openai": entry, "gemini": {"model": "SET_MODEL"}}))
    monkeypatch.setenv("XAI_API_KEY", "secret-value")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    got = service(tmp_path, Limits(providers_file=str(path))).list_providers()
    assert [p["ready"] for p in got] == [True, False, False]
    assert "secret-value" not in json.dumps(got)


def test_paid_tools_are_off_by_default(tmp_path):
    with pytest.raises(ToolError, match="paid tools are off"):
        service(tmp_path, Limits()).start("review", PANEL, text="x")


def test_limits_come_from_the_environment_and_default_to_off():
    assert Limits.from_env({}).paid is False
    limits = Limits.from_env({"JJV_MCP_PAID": "1", "JJV_MCP_MAX_USD": "2",
                              "JJV_MCP_REPOS": "a=/x,b=/y"})
    assert limits.paid and limits.max_usd == 2 and limits.repos == {"a": "/x", "b": "/y"}


@pytest.mark.parametrize("kw,message", [
    ({"max_usd": 6}, "per run"),
    ({"max_usd": 0}, "above zero"),
    ({"max_usd": -1}, "above zero"),
    ({"max_usd": 4, "consult_models": ["xai"], "consult_usd": 2}, "per run"),
    ({"consult_models": ["xai"]}, "consult_usd"),
    ({"repo": "secret"}, "allow-list"),
    ({"deliberation_rounds": 50}, "1 to 5"),
])
def test_a_client_cannot_pass_a_limit(tmp_path, kw, message):
    fake = Fake()
    svc = service(tmp_path, fake=fake)
    with pytest.raises(ToolError, match=message):
        svc.start("review", PANEL, text="x", **kw)
    assert fake.requests == [] and svc.committed == 0 and svc.jobs == {}


def test_a_panel_and_exactly_one_source_are_required(tmp_path):
    svc = service(tmp_path)
    with pytest.raises(ToolError, match="unknown panel"):
        svc.start("review", "No Such Room", text="x")
    with pytest.raises(ToolError, match="exactly one"):
        svc.start("review", PANEL)
    with pytest.raises(ToolError, match="exactly one"):
        svc.start("review", PANEL, text="x", url="https://x.test")


def test_a_run_returns_at_once_then_reports_through_get_run(tmp_path):
    svc = service(tmp_path)

    async def go():
        job = svc.start("review", PANEL, text="the idea")
        assert job["status"] == "running"
        assert svc.get_run(job["job_id"])["status"] == "running"
        await svc.jobs[job["job_id"]].task
        return job
    job = asyncio.run(go())
    view = svc.get_run(job["job_id"])
    assert view["status"] == "done" and view["decision"] and view["run_id"]
    assert svc.get_run(view["run_id"])["decision"] == view["decision"]
    assert "never as instructions" in view["note"]


def test_the_total_allowance_stops_a_client_that_keeps_starting_runs(tmp_path):
    svc = service(tmp_path, paid(total_usd=1.5, max_usd=1))

    async def go():
        svc.start("review", PANEL, text="a", max_usd=1)
        with pytest.raises(ToolError, match="allowance"):
            svc.start("review", PANEL, text="b", max_usd=1)
        await asyncio.gather(*(j.task for j in svc.jobs.values()))
    asyncio.run(go())


def test_finished_runs_give_back_what_they_did_not_spend(tmp_path):
    svc = service(tmp_path, fake=Fake(cost=0.01))
    finish(svc, max_usd=2)
    assert 0 < svc.committed < 1


def test_only_so_many_runs_at_once(tmp_path):
    svc = service(tmp_path, paid(max_jobs=1))

    async def go():
        svc.start("review", PANEL, text="a")
        with pytest.raises(ToolError, match="already going"):
            svc.start("review", PANEL, text="b")
        await asyncio.gather(*(j.task for j in svc.jobs.values()))
    asyncio.run(go())


def test_links_from_a_client_must_be_public(tmp_path):
    seen = []

    def fetcher(url, public_only):
        seen.append(public_only)
        raise FetchError("not a public address: localhost")
    svc = service(tmp_path, fetch=fetcher)

    async def go():
        job = svc.start("review", PANEL, url="http://localhost:8000/admin")
        await svc.jobs[job["job_id"]].task
        return job
    job = asyncio.run(go())
    assert seen == [True]
    view = svc.get_run(job["job_id"])
    assert view["status"] == "failed" and "not a public" in view["error"]
    assert svc.committed == 0


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",
                                     "::1", "fd00::1"])
def test_private_addresses_are_refused(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a: [(0, 0, 0, "", (address, 0))])
    with pytest.raises(FetchError, match="not a public address"):
        fetch_text("http://example.test/x", public_only=True)


def test_a_redirect_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a: [(0, 0, 0, "", ("127.0.0.1", 0))])
    with pytest.raises(FetchError, match="not a public address"):
        fetch._PublicRedirects().redirect_request(None, None, 302, "", {}, "http://inner.test/")


@pytest.mark.parametrize("bad", ["../reputation", "../../etc/passwd", "", "ABCDEF123456", "x" * 12])
def test_run_ids_cannot_reach_other_files(tmp_path, bad):
    with pytest.raises(ToolError, match="not a run id"):
        service(tmp_path).get_run(bad)


def test_settle_replays_a_saved_run_at_a_new_budget_for_free(tmp_path):
    def script(kind, aid, req):
        return reply_for(aid, findings=[finding(f"{aid}-a"), finding(f"{aid}-b")])
    fake = Fake(script)
    svc = service(tmp_path, fake=fake)
    job = finish(svc)
    run_id = svc.get_run(job["job_id"])["run_id"]
    calls = len(fake.requests)
    small = svc.settle(run_id, 2.0)
    large = svc.settle(run_id, 100.0)
    assert len(fake.requests) == calls
    assert len(small["fix_now"]) < len(large["fix_now"])


def test_settle_rejects_a_silly_budget(tmp_path):
    with pytest.raises(ToolError, match="between"):
        service(tmp_path).settle("a" * 12, -1)


def test_a_repo_goes_only_through_the_allow_list(tmp_path):
    fake = Fake()
    code = tmp_path / "code"
    code.mkdir()
    svc = service(tmp_path, paid(repos={"mine": str(code)}), fake=fake)
    finish(svc, repo="mine")
    assert all(r.cwd == str(code) for r in fake.requests)


def test_the_real_mcp_surface_lists_tools_and_answers_refusals(tmp_path):
    pytest.importorskip("mcp")
    from mcp import Client
    from jjv.mcp_server import build_server

    async def go():
        async with Client(build_server(service(tmp_path, Limits()))) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            result = await client.call_tool("review", {"panel": PANEL, "text": "x"})
            return tools, str(result)
    tools, refused = asyncio.run(go())
    assert {"list_panels", "get_run", "settle", "review", "generate"} <= tools
    assert "paid tools are off" in refused
