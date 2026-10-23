"""Request-scoped no-durable-content mode for host-owned conversation storage."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import threading

_active = ContextVar("api_transient_session", default=False)
_factory_lock = threading.Lock()


def install_log_guard():
    # Redact before queueing, so the logging thread never receives sensitive args
    # or tracebacks. Preserve logger/level/timing for operational diagnostics.
    with _factory_lock:
        previous = logging.getLogRecordFactory()
        if getattr(previous, "_transient_guard", False):
            return

        def factory(*args, **kwargs):
            record = previous(*args, **kwargs)
            if _active.get():
                record.msg, record.args = "transient API event (content omitted)", ()
                record.exc_info = record.exc_text = record.stack_info = None
            return record

        factory._transient_guard = True
        factory._hermes_session_injector = getattr(previous, "_hermes_session_injector", False)
        logging.setLogRecordFactory(factory)


@contextmanager
def transient_scope(enabled):
    if not enabled:
        yield
        return
    install_log_guard()
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)



def is_transient_session():
    return _active.get()
