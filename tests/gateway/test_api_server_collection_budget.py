"""Collection expiry retains completed receipts, never an interrupted answer."""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from aiohttp import web

from agent.interrupt_scope import track_in_interrupt_scope
from gateway.platforms.api_server_deadline import execution_scope, request_scope
from gateway.platforms.api_server_transient import run_completion


@pytest.mark.asyncio
async def test_cutoff_freezes_completed_receipts_and_discards_late_draft():
    stopped = threading.Event()
    release = threading.Event()
    callbacks = []
    def raw(url):
        return json.dumps({'results': [{'url': url, 'content': 'Genuine source paragraph. ' * 8}]})
    async def run(**kw):
        cb = kw['tool_complete_callback']; callbacks.append(cb)
        cb('before', 'web_extract', {}, raw('https://example.org/before'))
        scope = request_scope()
        def work():
            with execution_scope(True, scope):
                with track_in_interrupt_scope(SimpleNamespace(hard_interrupt=lambda *a, **k: release.set())):
                    release.wait(2)
                    assert release.is_set()
            stopped.set()
            return {'final_response': 'UNCHECKED MEDICAL DRAFT'}, {}
        return await asyncio.to_thread(work)
    adapter = SimpleNamespace(_transient_sessions=True, _run_agent=run)
    result, _ = await run_completion(adapter, {'model_options': {
        'wall_timeout_seconds': 3, 'evidence_collection_seconds': .05}})
    assert result['_collection_status'] == 'budget_exhausted'
    assert result['final_response'] == '{}' and result['completed'] is False and result['partial']
    assert await asyncio.to_thread(stopped.wait, 2)
    callbacks[0]('late', 'web_extract', {}, raw('https://example.org/late'))
    assert [p['url'] for p in result['_transient_pages']] == ['https://example.org/before']
    assert result['_transient_read_urls'] == ['https://example.org/before']


@pytest.mark.asyncio
async def test_only_opt_in_stage_expiry_is_recoverable():
    async def failed(**kw):
        raise RuntimeError('provider_failure')
    adapter = SimpleNamespace(_transient_sessions=True, _run_agent=failed)
    for seconds in [True, 0, -1, float('nan'), float('inf'), 3, 4]:
        with pytest.raises(ValueError):
            await run_completion(adapter, {'model_options': {
                'wall_timeout_seconds': 3, 'evidence_collection_seconds': seconds}})
    with pytest.raises(RuntimeError, match='provider_failure'):
        await run_completion(adapter, {'model_options': {
            'wall_timeout_seconds': 3, 'evidence_collection_seconds': 1}})
    async def timeout(**kw):
        raise web.HTTPGatewayTimeout()
    adapter._run_agent = timeout
    with pytest.raises(web.HTTPGatewayTimeout):
        await run_completion(adapter, {'model_options': {'wall_timeout_seconds': 3}})
    with pytest.raises(web.HTTPGatewayTimeout):
        await run_completion(adapter, {'model_options': {
            'wall_timeout_seconds': 3, 'evidence_collection_seconds': 1}})
    async def cancelled(**kw):
        raise asyncio.CancelledError()
    adapter._run_agent = cancelled
    with pytest.raises(asyncio.CancelledError):
        await run_completion(adapter, {'model_options': {
            'wall_timeout_seconds': 3, 'evidence_collection_seconds': 1}})
