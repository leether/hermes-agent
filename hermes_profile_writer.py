"""Opt-in profile maintenance barrier shared by API workers and external maintenance.

Kernel file locks have no expiry: a cancelled HTTP handler cannot outlive its worker's pin.
Runtime activation uses the same exclusive lock, so an old runtime cannot silently rejoin.
"""
from __future__ import annotations

import contextvars
import functools
import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

_ACTIVE = contextvars.ContextVar("hermes_profile_writer", default=None)


class WriterBusyError(RuntimeError):
    """The profile is being maintained; no stateful operation was admitted."""


class WriterFenceError(RuntimeError):
    """The runtime stamp or lock inode no longer matches the admitted authority."""


@dataclass(frozen=True)
class WriterScope:
    home: Path
    runtime_id: str

    def paths(self):
        home = Path(self.home).resolve(strict=True)
        if not self.runtime_id or not home.is_dir():
            raise WriterFenceError("profile home and runtime identity are required")
        directory = home / ".runtime-writer"
        if directory.is_symlink():
            raise WriterFenceError("writer directory must not be a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
        return directory / "barrier.lock", directory / "runtime.json"


def _open_lock(scope, exclusive, inherited_fd=None):
    if fcntl is None:
        raise WriterFenceError("profile writer barrier requires POSIX flock support")
    lock, stamp = scope.paths()
    fd = (os.dup(inherited_fd) if inherited_fd is not None else
          os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600))
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WriterBusyError("profile writer is busy") from exc
        opened, current = os.fstat(fd), lock.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or opened.st_nlink != 1:
            raise WriterFenceError("profile writer lock was replaced")
        return fd, lock, stamp
    except BaseException:
        os.close(fd)
        raise


def _sync_stamp_directory(stamp):
    directory = os.open(stamp.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def activate_runtime(scope):
    """Explicit operator bootstrap, never called by API or nightly admission."""
    fd, _, stamp = _open_lock(scope, True)
    try:
        if stamp.is_symlink():
            raise WriterFenceError("runtime stamp must not be a symlink")
        payload = {"version": 1, "runtime_id": scope.runtime_id, "generation": uuid.uuid4().hex}
        temporary = stamp.with_name("runtime." + payload["generation"] + ".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, stamp)
        _sync_stamp_directory(stamp)
        return payload
    finally:
        os.close(fd)


class WriterPermit:
    def __init__(self, scope, exclusive=False, *, inherited_fd=None):
        self.scope = scope
        self.exclusive = exclusive
        self.fd, self.lock_path, self.stamp_path = _open_lock(scope, exclusive, inherited_fd)
        self._mutex = threading.Lock()
        self._refs = 1
        try:
            if self.stamp_path.is_symlink():
                raise WriterFenceError("runtime stamp must not be a symlink")
            self.stamp = self.stamp_path.read_bytes()
            value = json.loads(self.stamp)
            if (value.get("version") != 1 or value.get("runtime_id") != scope.runtime_id or not value.get("generation") or value.get("blocked")
                    or (value.get("maintenance") and inherited_fd is None)):
                raise WriterFenceError("profile runtime identity does not match activation")
            self.assert_held()
        except (OSError, ValueError) as exc:
            os.close(self.fd)
            self._refs = 0
            raise WriterFenceError("profile runtime activation is unreadable") from exc
        except BaseException:
            os.close(self.fd)
            self._refs = 0
            raise

    def assert_held(self):
        if self._refs <= 0:
            raise WriterFenceError("writer permit is closed")
        try:
            a, b = os.fstat(self.fd), self.lock_path.stat(follow_symlinks=False)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) or a.st_nlink != 1:
                raise WriterFenceError("writer lock identity changed")
            if self.stamp_path.is_symlink() or self.stamp_path.read_bytes() != self.stamp:
                raise WriterFenceError("writer runtime generation changed")
        except OSError as exc:
            raise WriterFenceError("writer authority is unreadable") from exc

    def pin(self):
        with self._mutex:
            self.assert_held()
            self._refs += 1
        return self

    def release(self):
        with self._mutex:
            if self._refs <= 0:
                raise WriterFenceError("writer permit already released")
            self._refs -= 1
            if self._refs == 0:
                os.close(self.fd)

    @contextmanager
    def context(self):
        self.assert_held()
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)


@contextmanager
def writer_activity(scope, *, exclusive=False):
    if scope is None:
        yield None
        return
    permit = WriterPermit(scope, exclusive)
    try:
        with permit.context():
            yield permit
    finally:
        permit.release()


@contextmanager
def maintenance_activity(scope, *, inherited_fd=None):
    """Keep one exclusive open-file description across coordinator and prepare child."""
    current = _ACTIVE.get()
    if (inherited_fd is None and current is not None and current.exclusive
            and current.scope == scope):
        permit = current.pin()
    else:
        permit = WriterPermit(scope, True, inherited_fd=inherited_fd)
    try:
        with permit.context():
            yield permit
    finally:
        permit.release()


def _replace_permit_stamp(permit, payload):
    permit.assert_held()
    if not permit.exclusive:
        raise WriterFenceError("only exclusive maintenance may change runtime admission")
    temporary = permit.stamp_path.with_name("maintenance." + uuid.uuid4().hex + ".tmp")
    encoded = json.dumps(payload, sort_keys=True).encode()
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, permit.stamp_path)
    _sync_stamp_directory(permit.stamp_path)
    permit.stamp = encoded


def begin_maintenance(permit):
    """Persist before any child publication so SIGKILL cannot reopen partial state."""
    payload = json.loads(permit.stamp)
    if payload.get("maintenance"):
        raise WriterFenceError("maintenance reconciliation is already pending")
    payload["maintenance"] = uuid.uuid4().hex
    _replace_permit_stamp(permit, payload)


def finish_maintenance(permit):
    payload = json.loads(permit.stamp)
    if not payload.get("maintenance") or payload.get("blocked"):
        raise WriterFenceError("maintenance cannot finish without a successful publication")
    del payload["maintenance"]
    _replace_permit_stamp(permit, payload)


def block_runtime(permit):
    """Fail closed after a partial result; explicit operator reconciliation is required."""
    payload = json.loads(permit.stamp)
    payload["blocked"] = True
    _replace_permit_stamp(permit, payload)


def pin_active_writer():
    permit = _ACTIVE.get()
    return permit.pin() if permit is not None else None


def pin_writer_future(future):
    """Retain copied task context before its first tick and through shielded completion."""
    permit = pin_active_writer()
    if permit is not None:
        try:
            future.add_done_callback(lambda _: permit.release())
        except BaseException:
            permit.release()
            raise
    return future


@contextmanager
def pinned_writer_context(permit):
    if permit is None:
        yield
    else:
        with permit.context():
            yield


def submit_writer_worker(executor, function, *args):
    """Pin at submission, including queued work; release only on actual Future completion."""
    permit = pin_active_writer()
    if permit is None:
        return executor.submit(function, *args)

    @functools.wraps(function)
    def protected(*values):
        with permit.context():
            return function(*values)

    try:
        future = executor.submit(protected, *args)
    except BaseException:
        permit.release()
        raise
    future.add_done_callback(lambda _: permit.release())
    return future


@contextmanager
def profile_db_write(db_path):
    """Fence late native writers too, including workers outside the request executor."""
    home = Path(db_path).resolve().parent
    current = _ACTIVE.get()
    if current is not None and Path(current.scope.home).resolve() == home:
        current.assert_held()
        yield
        current.assert_held()
        return
    stamp = home / ".runtime-writer" / "runtime.json"
    if not stamp.exists():
        yield
        return
    try:
        data = json.loads(stamp.read_bytes())
        scope = WriterScope(home, data["runtime_id"])
    except (OSError, ValueError, KeyError) as exc:
        raise WriterFenceError("native writer runtime is unreadable") from exc
    with writer_activity(scope) as permit:
        permit.assert_held()
        yield
        permit.assert_held()
