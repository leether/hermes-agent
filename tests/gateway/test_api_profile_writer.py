"""API cancellation and queued/background work must retain the maintenance barrier."""
import asyncio
import concurrent.futures
import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from tests.waiting import async_wait_until

from gateway.platforms.api_server_profile_writer import profile_writer_handler
from gateway.platforms.api_server_runs import _submit_api_worker, api_worker_live_count
from hermes_profile_writer import (
    WriterBusyError, WriterFenceError, WriterScope, activate_runtime,
    submit_writer_worker, writer_activity, maintenance_activity, block_runtime, begin_maintenance, finish_maintenance,
)

pytestmark = pytest.mark.platforms("posix")


@pytest.fixture
def scope(tmp_path):
    home = tmp_path / "canary"
    home.mkdir()
    value = WriterScope(home, "candidate-runtime-1")
    activate_runtime(value)
    return value


def test_other_process_cannot_enter_maintenance_while_api_writes(scope):
    code = """import sys
from pathlib import Path
from hermes_profile_writer import WriterScope, writer_activity, WriterBusyError
try:
    with writer_activity(WriterScope(Path(sys.argv[1]), sys.argv[2]), exclusive=True):
        print('entered')
except WriterBusyError:
    print('blocked')
"""
    with writer_activity(scope):
        child = subprocess.run([sys.executable, "-c", code, str(scope.home), scope.runtime_id],
                               capture_output=True, text=True, timeout=10, check=False)
    assert child.returncode == 0 and child.stdout.strip() == "blocked"
    with writer_activity(scope, exclusive=True):
        pass


@pytest.mark.asyncio
async def test_cancelled_http_waiter_does_not_release_running_api_worker(scope):
    started, finish = threading.Event(), threading.Event()
    baseline = api_worker_live_count()

    def worker():
        started.set()
        assert finish.wait(5)

    try:
        with writer_activity(scope):
            future = _submit_api_worker(asyncio.get_running_loop(), worker)
            assert await asyncio.to_thread(started.wait, 2)
            future.cancel()
        with pytest.raises(WriterBusyError):
            with writer_activity(scope, exclusive=True):
                pytest.fail("maintenance entered a running API worker")
    finally:
        finish.set()
    for _ in range(200):
        if api_worker_live_count() == baseline:
            break
        await asyncio.sleep(0.01)
    assert api_worker_live_count() == baseline
    with writer_activity(scope, exclusive=True):
        pass


def test_background_compression_outlives_parent_and_retains_pin(scope):
    started, finish = threading.Event(), threading.Event()

    def compressor():
        started.set()
        assert finish.wait(5)
        return "committed"

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with writer_activity(scope):
                future = submit_writer_worker(pool, compressor)
                assert started.wait(2)
            with pytest.raises(WriterBusyError):
                with writer_activity(scope, exclusive=True):
                    pytest.fail("maintenance entered a detached compression worker")
        finally:
            finish.set()
        assert future.result(timeout=2) == "committed"
    with writer_activity(scope, exclusive=True):
        pass


def test_cancelled_queued_worker_releases_only_its_own_pin(scope):
    finish = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        blocker = pool.submit(finish.wait, 5)
        try:
            with writer_activity(scope):
                queued = submit_writer_worker(pool, lambda: pytest.fail("cancelled job ran"))
                assert queued.cancel()
                with pytest.raises(WriterBusyError):
                    with writer_activity(scope, exclusive=True):
                        pass
            with writer_activity(scope, exclusive=True):
                pass
        finally:
            finish.set()
        blocker.result(timeout=2)


def test_failed_api_submission_does_not_leak_pin_or_worker_count(scope):
    class ClosedLoop:
        def run_in_executor(self, *args):
            raise RuntimeError("executor shut down")

    before = api_worker_live_count()
    with writer_activity(scope):
        with pytest.raises(RuntimeError, match="executor shut down"):
            _submit_api_worker(ClosedLoop(), lambda: None)
    assert api_worker_live_count() == before
    with writer_activity(scope, exclusive=True):
        pass


def test_activation_cannot_replace_live_runtime_and_old_identity_fails(scope):
    changed = WriterScope(scope.home, "candidate-runtime-2")
    with writer_activity(scope):
        with pytest.raises(WriterBusyError):
            activate_runtime(changed)
    activate_runtime(changed)
    with pytest.raises(WriterFenceError):
        with writer_activity(scope):
            pass
    with writer_activity(changed):
        pass


@pytest.mark.parametrize("replacement", ["stamp", "lock"])
def test_replaced_authority_fences_publication(scope, replacement):
    with writer_activity(scope) as permit:
        lock, stamp = scope.paths()
        if replacement == "stamp":
            stamp.write_text(json.dumps({"version": 1, "runtime_id": scope.runtime_id, "generation": "other"}))
        else:
            lock.unlink()
            lock.write_text("")
        with pytest.raises(WriterFenceError):
            permit.assert_held()


@pytest.mark.asyncio
async def test_api_guard_busy_health_bypass_and_other_profile_isolation(scope, tmp_path, monkeypatch):
    import hermes_constants
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: scope.home)
    setting = {"enabled": True, "profile": "canary", "runtime_id": scope.runtime_id}
    adapter = SimpleNamespace(config=SimpleNamespace(extra={"profile_writer_guard": setting}))
    calls = []

    async def handler(request):
        calls.append(request.path)
        return "handled"

    request = SimpleNamespace(match_info={}, path="/v1/chat/completions", method="POST")
    with writer_activity(scope, exclusive=True):
        response = await profile_writer_handler(adapter, request, handler)
        assert response.status == 503 and not calls
        request.path = "/health"
        assert await profile_writer_handler(adapter, request, handler) == "handled"
        other = tmp_path / "unrelated"
        other.mkdir()
        monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: other)
        request.path = "/v1/chat/completions"
        assert await profile_writer_handler(adapter, request, handler) == "handled"
        assert not (other / ".runtime-writer").exists()


@pytest.mark.asyncio
async def test_unconfigured_adapter_keeps_existing_handler(scope, monkeypatch):
    async def handler(request):
        return "prior-owner"

    adapter = SimpleNamespace(config=SimpleNamespace(extra={}))
    request = SimpleNamespace(path="/v1/chat/completions", method="POST", match_info={})
    assert await profile_writer_handler(adapter, request, handler) == "prior-owner"


def test_native_late_writer_and_schema_open_obey_profile_barrier(scope):
    from hermes_state import SessionDB

    db = SessionDB(scope.home / "state.db")
    try:
        db.create_session("parent", "api_server")
        # Independent workers do not inherit the maintenance owner's ContextVar.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer_activity(scope, exclusive=True):
                late_write = pool.submit(db.append_message, "parent", "user", "late worker")
                with pytest.raises(WriterBusyError):
                    late_write.result(timeout=5)
                late_open = pool.submit(SessionDB, scope.home / "state.db")
                with pytest.raises(WriterBusyError):
                    late_open.result(timeout=5)
        assert db.get_messages_as_conversation("parent") == []
        db.append_message("parent", "user", "accepted after maintenance")
        assert db.get_messages_as_conversation("parent")[0]["content"] == "accepted after maintenance"
    finally:
        db.close()


def test_cancelled_queued_api_worker_releases_pin_without_running(scope):
    async def scenario():
        loop = asyncio.get_running_loop()
        finish = threading.Event()
        ran = threading.Event()
        baseline = api_worker_live_count()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            loop.set_default_executor(pool)
            blocker = loop.run_in_executor(None, finish.wait, 5)
            try:
                with writer_activity(scope):
                    queued = _submit_api_worker(loop, ran.set)
                    queued.cancel()
                    await async_wait_until(lambda: api_worker_live_count() == baseline, timeout=2,
                                           what="queued cancellation releasing worker admission")
                assert api_worker_live_count() == baseline
                with writer_activity(scope, exclusive=True):
                    pass
                assert not ran.is_set()
            finally:
                finish.set()
                await blocker
    asyncio.run(scenario())


def test_maintenance_child_inherits_same_lock_and_api_stays_blocked(scope):
    code = """import sys
from pathlib import Path
from hermes_profile_writer import WriterScope, maintenance_activity
with maintenance_activity(WriterScope(Path(sys.argv[1]), sys.argv[2]), inherited_fd=int(sys.argv[3])):
    print('same-exclusive-authority')
"""
    with maintenance_activity(scope) as permit:
        begin_maintenance(permit)
        result = subprocess.run([sys.executable, "-c", code, str(scope.home), scope.runtime_id, str(permit.fd)],
                                pass_fds=(permit.fd,), capture_output=True, text=True, timeout=10, check=True)
        assert result.stdout.strip() == "same-exclusive-authority"
        with pytest.raises(WriterBusyError):
            with writer_activity(scope):
                pass
        permit.assert_held()
        finish_maintenance(permit)
    with writer_activity(scope):
        pass


def test_partial_maintenance_blocks_profile_until_explicit_reconciliation(scope):
    with maintenance_activity(scope) as permit:
        block_runtime(permit)
    with pytest.raises(WriterFenceError):
        with writer_activity(scope):
            pass
    activate_runtime(scope)
    with writer_activity(scope):
        pass


def test_coordinator_sigkill_keeps_partial_profile_fenced(scope):
    code = """import os,signal,sys
from pathlib import Path
from hermes_profile_writer import WriterScope, maintenance_activity, begin_maintenance
with maintenance_activity(WriterScope(Path(sys.argv[1]), sys.argv[2])) as permit:
    begin_maintenance(permit)
    os.kill(os.getpid(), signal.SIGKILL)
"""
    child = subprocess.run([sys.executable, "-c", code, str(scope.home), scope.runtime_id],
                           capture_output=True, text=True, timeout=10, check=False)
    assert child.returncode == -9
    with pytest.raises(WriterFenceError):
        with writer_activity(scope):
            pass
    with pytest.raises(WriterFenceError):
        with maintenance_activity(scope):
            pass


@pytest.mark.asyncio
async def test_detached_background_task_can_start_worker_after_http_exit(scope):
    from gateway.platforms.api_server import APIServerAdapter
    gate = asyncio.Event()
    adapter = SimpleNamespace(_background_tasks=set())
    async def detached():
        await gate.wait()
        return await _submit_api_worker(asyncio.get_running_loop(), lambda: 'completed')
    with writer_activity(scope):
        task = asyncio.create_task(detached())
        APIServerAdapter._track_background_task(adapter, task)
    gate.set()
    assert await task == 'completed'
    await asyncio.sleep(0)
    with writer_activity(scope, exclusive=True):
        pass


@pytest.mark.asyncio
async def test_idempotent_compute_retains_admission_after_caller_cancels(scope):
    from gateway.platforms.api_server import _IdempotencyCache
    started, finish = asyncio.Event(), asyncio.Event()
    async def compute():
        started.set()
        await finish.wait()
        return await _submit_api_worker(asyncio.get_running_loop(), lambda: 'cached')
    cache = _IdempotencyCache()
    with writer_activity(scope):
        waiter = asyncio.create_task(cache.get_or_set('key', 'fingerprint', compute))
        await started.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
    try:
        with pytest.raises(WriterBusyError):
            with writer_activity(scope, exclusive=True):
                pass
    finally:
        finish.set()
    assert await cache.get_or_set('key', 'fingerprint', compute) == 'cached'
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_real_runs_route_keeps_admission_after_202(scope, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from unittest.mock import MagicMock
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter
    from tests.gateway.test_api_server_runs import _create_runs_app
    monkeypatch.setenv("HERMES_HOME", str(scope.home))
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"profile_writer_guard": {
        "enabled": True, "profile": scope.home.name, "runtime_id": scope.runtime_id}}))
    started, finish = threading.Event(), threading.Event()
    agent = MagicMock()
    def run(**kwargs):
        started.set()
        assert finish.wait(5)
        return {"final_response": "done", "messages": []}
    agent.run_conversation.side_effect = run
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_total_tokens = 0
    monkeypatch.setattr(adapter, "_create_agent", lambda **kwargs: agent)
    app = _create_runs_app(adapter)
    app.middlewares.insert(0, adapter._make_profile_prefix_middleware())
    try:
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/v1/runs", json={"input": "synthetic request"})
            assert response.status == 202
            data = await response.json()
            assert await asyncio.to_thread(started.wait, 2)
            with pytest.raises(WriterBusyError):
                with writer_activity(scope, exclusive=True):
                    pass
            finish.set()
            await async_wait_until(lambda: adapter._run_statuses[data["run_id"]]["status"] == "completed", timeout=3)
    finally:
        finish.set()
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_cron_thread_keeps_permit_after_task_cancellation(scope):
    from gateway.platforms.api_server_profile_writer import run_profile_thread
    from gateway.platforms.api_server import APIServerAdapter
    from contextvars import ContextVar
    owner = ContextVar("synthetic_profile_owner", default="wrong")
    started, finish = threading.Event(), threading.Event()
    baseline = api_worker_live_count()
    def fire():
        assert owner.get() == "canary"
        started.set()
        assert finish.wait(5)
    try:
        with writer_activity(scope):
            token = owner.set("canary")
            try:
                task = asyncio.create_task(run_profile_thread(fire))
                APIServerAdapter._track_background_task(SimpleNamespace(_background_tasks=set()), task)
            finally:
                owner.reset(token)
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        with pytest.raises(WriterBusyError):
            with writer_activity(scope, exclusive=True):
                pass
    finally:
        finish.set()
    await async_wait_until(lambda: api_worker_live_count() == baseline, timeout=3)
