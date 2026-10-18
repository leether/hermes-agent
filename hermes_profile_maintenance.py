"""Persistent, profile-local maintenance admission, independent of runtime activation.

The short admission lock orders pause against entry. Existing writers retain the main
barrier while draining; a pause never revokes their authority halfway through a commit.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid

from hermes_profile_writer import WriterBusyError, WriterFenceError, WriterScope


@contextmanager
def _admission_lock(scope, *, exclusive=False):
    from hermes_profile_writer import fcntl

    if fcntl is None:
        raise WriterFenceError("profile maintenance requires POSIX flock support")
    lock, _ = scope.paths()
    path = lock.with_name("admission.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WriterBusyError("profile admission is changing") from exc
        opened, current = os.fstat(fd), path.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or opened.st_nlink != 1:
            raise WriterFenceError("profile admission lock was replaced")
        yield lock.with_name("pause.json")
    finally:
        os.close(fd)


@contextmanager
def admission_entry(scope):
    with _admission_lock(scope) as pause:
        if pause.is_symlink() or pause.exists():
            raise WriterBusyError("profile is persistently paused for maintenance")
        yield


def _read_pause(path):
    try:
        if path.is_symlink():
            raise WriterFenceError("maintenance pause must not be a symlink")
        value = json.loads(path.read_bytes())
        if value.get("version") != 1 or not isinstance(value.get("token"), str) or not value["token"]:
            raise ValueError("invalid pause")
        return value
    except (OSError, ValueError, AttributeError) as exc:
        raise WriterFenceError("maintenance pause is unreadable") from exc


def pause_profile(scope):
    """Stop new admission first, even while old workers still hold the main barrier."""
    from hermes_profile_writer import _sync_stamp_directory

    with _admission_lock(scope, exclusive=True) as path:
        if path.is_symlink() or path.exists():
            return _read_pause(path)["token"]
        value = {"version": 1, "token": uuid.uuid4().hex}
        temporary = path.with_name("pause." + value["token"] + ".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_stamp_directory(path)
        return value["token"]


def resume_profile(scope, token):
    """Explicit operator action, after drain/reconciliation; never an API/startup action."""
    from hermes_profile_writer import maintenance_activity, _sync_stamp_directory

    with _admission_lock(scope, exclusive=True) as path:
        if _read_pause(path)["token"] != token:
            raise WriterFenceError("maintenance resume token does not match")
        # A live, queued or detached worker keeps this exclusive acquisition closed.
        # Runtime mismatch/blocked/partial publication remain independent hard failures.
        with maintenance_activity(scope):
            verify_profile_drained(scope)
            path.unlink()
            _sync_stamp_directory(path)


def configured_writer_scope(home, setting):
    """Resolve an explicit target against the owning home, never the launch profile."""
    if setting is None:
        return None
    if not isinstance(setting, dict) or setting.get("enabled") is not True:
        raise WriterFenceError("profile_writer_guard must be an explicit enabled mapping")
    target, runtime = setting.get("profile"), setting.get("runtime_id")
    if not isinstance(target, str) or not target or "/" in target or "\\" in target or target in {".", ".."}:
        raise WriterFenceError("profile writer target is invalid")
    home = Path(home).resolve(strict=True)
    if home.name != target:
        return None
    if not isinstance(runtime, str) or not runtime.strip():
        raise WriterFenceError("profile writer runtime is invalid")
    return WriterScope(home, runtime)


def profile_writer_scope():
    """Cron and API share the profile's configured guard; YAML contains no new secret."""
    from hermes_constants import get_hermes_home
    import hermes_yaml as yaml

    from gateway.config import PlatformConfig
    from gateway.config_loader import load_legacy_gateway_json, merge_platform_sections, read_yaml_layers

    home = Path(get_hermes_home()).resolve()
    try:
        config = read_yaml_layers(home)
        blocks = merge_platform_sections(config, config.get("gateway"), load_legacy_gateway_json(home))
        setting = PlatformConfig.from_dict(blocks.get("api_server", {})).extra.get("profile_writer_guard")
    except (OSError, ValueError, AttributeError, TypeError, yaml.YAMLError) as exc:
        raise WriterFenceError("profile writer configuration is unreadable") from exc
    return configured_writer_scope(home, setting)


def verify_profile_drained(scope):
    """A dead process or an expired timestamp never resolves an unfinished effect."""
    import sqlite3

    checks = {
        "state.db": (("session_turn_leases", None), ("compression_locks", None)),
        "cron/executions.db": (("executions", "status IN ('claimed', 'running', 'unknown')"),),
    }
    counts = {}
    for relative, tables in checks.items():
        path = scope.home / relative
        if not path.exists():
            continue
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2) as conn:
            conn.execute("PRAGMA query_only=ON")
            for table, predicate in tables:
                sql = "SELECT count(*) FROM " + table
                count = conn.execute(sql + (" WHERE " + predicate if predicate else "")).fetchone()[0]
                counts[relative + ":" + table] = count
    if any(counts.values()):
        raise WriterFenceError("native work or unknown effects require explicit reconciliation")
    return counts
