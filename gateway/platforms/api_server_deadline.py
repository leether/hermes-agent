"""Opt-in transient request deadline using the native hard-interrupt scope."""
import asyncio
from contextlib import contextmanager
import math
from contextvars import ContextVar

from aiohttp import web
from agent.interrupt_scope import InterruptScope, bind_interrupt_scope
from agent.transient_session import transient_scope

_scope = ContextVar("transient_request_interrupt_scope", default=None)


class RequestDeadlineExpired(web.HTTPGatewayTimeout):
    """Identifies this host timer, rather than an arbitrary upstream 504."""


def request_scope():
    return _scope.get()


@contextmanager
def execution_scope(transient, scope):
    # Captured on the API event loop and explicitly rebound on its worker thread.
    with transient_scope(transient), bind_interrupt_scope(scope):
        yield


async def with_deadline(adapter, kwargs):
    value = (kwargs.get("model_options") or {}).get("wall_timeout_seconds")
    if value is None:
        return await adapter._run_agent(**kwargs)
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not 0 < value <= 200):
        raise ValueError("invalid_wall_timeout_seconds")
    scope = InterruptScope()
    token = _scope.set(scope)
    task = asyncio.create_task(adapter._run_agent(**kwargs))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=value)
    except (TimeoutError, asyncio.CancelledError) as error:
        scope.cancel("transient request deadline or cancellation", tool_reason="host request budget expired")
        # Retain the worker until the native request/ tool interrupt unwinds.
        # Never return its interrupted draft as a successful medical completion.
        task.add_done_callback(_consume_result)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise RequestDeadlineExpired(text="Transient request deadline exceeded") from None
    finally:
        _scope.reset(token)


def _consume_result(task):
    if not task.cancelled():
        task.exception()
