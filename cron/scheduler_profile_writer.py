"""Profile maintenance admission before cron scans, claims and execution side effects."""
from contextlib import contextmanager
from functools import wraps
import logging
import weakref

from hermes_profile_maintenance import profile_writer_scope
from hermes_profile_writer import (
    WriterBusyError, WriterFenceError, pin_active_writer, writer_activity,
)

logger = logging.getLogger(__name__)
_RAISE = object()


class _ClaimedFire(dict):
    """The exact claim snapshot also owns queued admission until handoff or abandonment."""
    def __init__(self, job, permit):
        super().__init__(job)
        self.permit = permit.pin()
        self.release = weakref.finalize(self, self.permit.release)


@contextmanager
def cron_writer_activity():
    scope = profile_writer_scope()
    current = pin_active_writer()
    if current is not None:
        if current.scope == scope:
            try:
                with current.context():
                    yield current
            finally:
                current.release()
            return
        current.release()
    with writer_activity(scope) as permit:
        yield permit


@contextmanager
def _claimed_activity(args):
    claim = next((arg for arg in args if isinstance(arg, _ClaimedFire)), None)
    if claim is None:
        with cron_writer_activity() as permit:
            yield permit
        return
    try:
        with claim.permit.context():
            yield claim.permit
    finally:
        claim.release()


def guarded_cron(*, paused_result=_RAISE, retain_claim=False):
    """Paused scans/recovery skip; explicit fire callers receive a retryable refusal."""
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            activity = _claimed_activity(args)
            try:
                permit = activity.__enter__()
            except (WriterBusyError, WriterFenceError, OSError):
                if paused_result is _RAISE:
                    raise
                logger.info("Cron profile maintenance: %s deferred before store mutation", function.__name__)
                return paused_result
            try:
                result = function(*args, **kwargs)
                if retain_claim and permit is not None and isinstance(result, dict):
                    return _ClaimedFire(result, permit)
                return result
            finally:
                activity.__exit__(None, None, None)
        return guarded
    return decorate
