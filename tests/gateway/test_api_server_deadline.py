"""Deadline stops native work, including late-starting workers; ordinary calls stay unchanged."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from aiohttp import web

from agent.interrupt_scope import track_in_interrupt_scope
from gateway.platforms.api_server_deadline import with_deadline, execution_scope, request_scope


@pytest.mark.asyncio
async def test_timeout_cancels_worker_scope_and_late_registration():
    release = threading.Event()
    stopped = threading.Event()
    agent = SimpleNamespace(hard_interrupt=lambda *a, **kw: release.set())
    async def run(**kw):
        scope = request_scope()
        def work():
            with execution_scope(True, scope):
                with track_in_interrupt_scope(agent):
                    release.wait(2)
                    assert release.is_set()
                # A second agent that registers after expiry must be interrupted too.
                late = threading.Event()
                with track_in_interrupt_scope(SimpleNamespace(hard_interrupt=lambda *a, **kw: late.set())):
                    assert late.is_set()
            stopped.set()
            return {}, {}
        return await asyncio.to_thread(work)
    with pytest.raises(web.HTTPGatewayTimeout):
        await with_deadline(SimpleNamespace(_run_agent=run), {'model_options': {'wall_timeout_seconds': .05}})
    assert await asyncio.to_thread(stopped.wait, 2)
    assert request_scope() is None


@pytest.mark.asyncio
async def test_deadline_validation_and_unbudgeted_call_preserved():
    calls = []
    async def run(**kw):
        calls.append(kw)
        return {'final_response': 'fixture'}, {}
    adapter = SimpleNamespace(_run_agent=run)
    for value in [True, '2', -1, 0, float('nan'), float('inf'), 201]:
        with pytest.raises(ValueError):
            await with_deadline(adapter, {'model_options': {'wall_timeout_seconds': value}})
    assert not calls
    assert (await with_deadline(adapter, {}))[0]['final_response'] == 'fixture'
    assert calls == [{}]
