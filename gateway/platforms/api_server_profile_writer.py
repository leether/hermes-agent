"""Profile-scoped API admission for external maintenance; inactive unless explicitly configured."""
import asyncio
from contextlib import suppress
from contextvars import copy_context
from functools import partial

from aiohttp import web

from hermes_profile_writer import (
    WriterBusyError, WriterFenceError, writer_activity, pin_active_writer, pin_writer_future,
)


def _request_writer_scope(adapter):
    from hermes_constants import get_hermes_home
    from hermes_profile_maintenance import configured_writer_scope, profile_writer_scope

    configured = profile_writer_scope()
    adapter_scope = configured_writer_scope(
        get_hermes_home(), (adapter.config.extra or {}).get("profile_writer_guard"))
    if configured is not None and adapter_scope is not None and configured != adapter_scope:
        raise WriterFenceError("request and profile runtime configuration disagree")
    return configured or adapter_scope


async def profile_writer_handler(adapter, request, handler):
    tail = request.match_info.get("tail", request.path).strip("/")
    if request.method == "OPTIONS" or tail in {"health", "health/detailed", "v1/health"}:
        return await handler(request)
    try:
        scope = _request_writer_scope(adapter)
        with writer_activity(scope):
            return await handler(request)
    except WriterBusyError:
        return web.json_response({"error": {"type": "profile_writer_busy", "message": "Profile maintenance in progress"}},
                                 status=503, headers={"Retry-After": "60"})
    except (WriterFenceError, OSError):
        return web.json_response({"error": {"type": "profile_runtime_mismatch", "message": "Profile runtime admission failed"}}, status=503)


def track_background_task(adapter, task, *, tolerate_missing=False):
    pin_writer_future(task)
    if tolerate_missing:
        with suppress(TypeError, AttributeError):
            adapter._background_tasks.add(task)
            task.add_done_callback(adapter._background_tasks.discard)
        return
    with suppress(TypeError):
        adapter._background_tasks.add(task)
    if hasattr(task, "add_done_callback"):
        task.add_done_callback(adapter._background_tasks.discard)


async def run_profile_thread(function, *args, **kwargs):
    permit = pin_active_writer()
    if permit is None:
        return await asyncio.to_thread(function, *args, **kwargs)
    from gateway.platforms.api_server_runs import _submit_api_worker

    call = partial(copy_context().run, function, *args, **kwargs)
    try:
        return await _submit_api_worker(asyncio.get_running_loop(), call)
    finally:
        permit.release()


def profile_admission_status(adapter):
    """Read-only startup proof: liveness does not grant business admission."""
    import json
    try:
        scope = _request_writer_scope(adapter)
        if scope is None:
            return {"state": "unmanaged"}
        directory = scope.home / ".runtime-writer"
        pause, stamp = directory / "pause.json", directory / "runtime.json"
        if directory.is_symlink() or stamp.is_symlink():
            return {"state": "invalid"}
        value = json.loads(stamp.read_bytes())
        if value.get("runtime_id") != scope.runtime_id or value.get("version") != 1 or not value.get("generation"):
            return {"state": "invalid"}
        if value.get("blocked"):
            return {"state": "blocked"}
        if pause.exists() or pause.is_symlink() or value.get("maintenance"):
            return {"state": "paused"}
        return {"state": "open"}
    except (WriterFenceError, OSError, ValueError, AttributeError):
        return {"state": "invalid"}
