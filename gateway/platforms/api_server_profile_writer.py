"""Profile-scoped API admission for external maintenance; inactive unless explicitly configured."""
import asyncio
from contextlib import suppress
from contextvars import copy_context
from functools import partial
from pathlib import Path

from aiohttp import web

from hermes_profile_writer import (
    WriterBusyError, WriterFenceError, WriterScope, writer_activity, pin_active_writer, pin_writer_future,
)


async def profile_writer_handler(adapter, request, handler):
    setting = (adapter.config.extra or {}).get("profile_writer_guard")
    if not setting:
        return await handler(request)
    if not isinstance(setting, dict) or setting.get("enabled") is not True:
        raise WriterFenceError("profile_writer_guard must be an explicit enabled mapping")
    from hermes_constants import get_hermes_home

    home = await asyncio.to_thread(Path(get_hermes_home()).resolve, strict=True)
    target = setting.get("profile")
    if not isinstance(target, str) or not target or "/" in target or target in {".", ".."}:
        raise WriterFenceError("profile writer target is invalid")
    if home.name != target:
        return await handler(request)
    tail = request.match_info.get("tail", request.path).strip("/")
    if request.method == "OPTIONS" or tail in {"health", "health/detailed", "v1/health"}:
        return await handler(request)
    try:
        scope = WriterScope(home, setting.get("runtime_id") or "")
        with writer_activity(scope):
            return await handler(request)
    except WriterBusyError:
        return web.json_response({"error": {"type": "profile_writer_busy", "message": "Profile maintenance in progress"}}, status=503)
    except WriterFenceError:
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
