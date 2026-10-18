"""Every direct API mutation is denied before side effects while health remains readable."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from gateway.platforms.api_server_profile_writer import profile_writer_handler, run_profile_thread
from hermes_profile_maintenance import pause_profile, resume_profile
from hermes_profile_writer import WriterScope, WriterBusyError, activate_runtime, maintenance_activity
from tests.waiting import async_wait_until

pytestmark = pytest.mark.platforms("posix")


@pytest.mark.asyncio
async def test_paused_api_all_routes_health_and_other_profile(tmp_path, monkeypatch):
    import hermes_constants
    home = tmp_path / "canary"
    home.mkdir()
    scope = WriterScope(home, "runtime")
    activate_runtime(scope)
    token = pause_profile(scope)
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    adapter = SimpleNamespace(config=SimpleNamespace(extra={"profile_writer_guard": {
        "enabled": True, "profile": home.name, "runtime_id": scope.runtime_id}}))
    effects = []

    async def handler(request):
        effects.append(request.path)
        return "handled"

    for method, path in [("POST", "/v1/chat/completions"), ("POST", "/v1/responses"),
                         ("POST", "/v1/runs"), ("POST", "/api/sessions"),
                         ("PATCH", "/api/sessions/s"), ("DELETE", "/api/sessions/s"),
                         ("POST", "/api/cron/fire"), ("GET", "/api/sessions")]:
        response = await profile_writer_handler(adapter, SimpleNamespace(path=path, method=method, match_info={}), handler)
        assert response.status == 503
    assert effects == []
    for path in ["/health", "/health/detailed"]:
        assert await profile_writer_handler(adapter, SimpleNamespace(path=path, method="GET", match_info={}), handler) == "handled"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: other)
    assert await profile_writer_handler(adapter, SimpleNamespace(path="/chat", method="POST", match_info={}), handler) == "handled"
    resume_profile(scope, token)


@pytest.mark.asyncio
async def test_cancelled_api_thread_retains_pin_until_actual_write_finishes(tmp_path):
    from hermes_profile_writer import writer_activity
    scope = WriterScope(tmp_path, "runtime")
    activate_runtime(scope)
    started, finish, done = threading.Event(), threading.Event(), threading.Event()
    effects = []

    def write():
        started.set()
        assert finish.wait(5)
        effects.append("committed")
        done.set()

    async def request():
        with writer_activity(scope):
            await run_profile_thread(write)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        token = pause_profile(scope)
        with pytest.raises(WriterBusyError):
            with maintenance_activity(scope):
                pytest.fail("cancelled request released its live thread")
    finally:
        finish.set()
        assert await asyncio.to_thread(done.wait, 2)
    from gateway.platforms.api_server_runs import api_worker_live_count
    await async_wait_until(lambda: api_worker_live_count() == 0, timeout=5)
    resume_profile(scope, token)
    assert effects == ["committed"]


@pytest.mark.asyncio
async def test_real_http_router_paused_cold_start_has_no_store_or_agent_side_effect(tmp_path, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter
    home = tmp_path / "canary"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    scope = WriterScope(home, "before-restart")
    activate_runtime(scope)
    pause_profile(scope)
    scope = WriterScope(home, "after-restart")
    activate_runtime(scope)
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"profile_writer_guard": {
        "enabled": True, "profile": home.name, "runtime_id": scope.runtime_id}}))

    def forbidden(**kwargs):
        pytest.fail("paused request created an agent")

    monkeypatch.setattr(adapter, "_create_agent", forbidden)
    app = web.Application(middlewares=[adapter._make_profile_prefix_middleware()])
    for method, path, handler in adapter._http_route_table():
        app.router.add_route(method, path, handler)
    before = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    async with TestClient(TestServer(app)) as client:
        health = await client.get("/health")
        assert health.status == 200
        assert (await health.json())["profile_admission"]["state"] == "paused"
        for path in ["/chat", "/v1/chat/completions", "/v1/responses", "/v1/runs", "/api/cron/fire"]:
            response = await client.post(path, json={"messages": [{"role": "user", "content": "synthetic"}]})
            assert response.status == 503, path
        assert adapter._session_db is None
    after = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.asyncio
async def test_routed_profile_guard_cannot_be_bypassed_by_unmanaged_launch_adapter(tmp_path, monkeypatch):
    import json
    home = tmp_path / "routed"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    scope = WriterScope(home, "routed-runtime")
    activate_runtime(scope)
    pause_profile(scope)
    (home / "config.yaml").write_text(json.dumps({"platforms": {"api_server": {"extra": {
        "profile_writer_guard": {"enabled": True, "profile": home.name, "runtime_id": scope.runtime_id}}}}}))
    adapter = SimpleNamespace(config=SimpleNamespace(extra={}))

    async def forbidden(request):
        pytest.fail("routed target borrowed unmanaged launch admission")

    response = await profile_writer_handler(adapter, SimpleNamespace(path="/chat", method="POST", match_info={}), forbidden)
    assert response.status == 503
