"""A maintenance hold survives runtime activation and drains admitted workers only."""
import threading

import pytest

from hermes_profile_writer import WriterScope, activate_runtime, writer_activity, WriterBusyError, WriterFenceError

pytestmark = pytest.mark.platforms("posix")


def test_persistent_pause_survives_activation_and_requires_exact_resume(tmp_path):
    from hermes_profile_maintenance import pause_profile, resume_profile
    scope = WriterScope(tmp_path, "old")
    activate_runtime(scope)
    token = pause_profile(scope)
    changed = WriterScope(tmp_path, "new")
    activate_runtime(changed)
    with pytest.raises(WriterBusyError):
        with writer_activity(changed):
            pytest.fail("activation reopened maintenance admission")
    with pytest.raises(WriterFenceError, match="token"):
        resume_profile(changed, "wrong-token")
    resume_profile(changed, token)
    with writer_activity(changed):
        pass


def test_pause_blocks_new_work_before_existing_worker_drains(tmp_path):
    from hermes_profile_maintenance import pause_profile, resume_profile
    scope = WriterScope(tmp_path, "one")
    activate_runtime(scope)
    started, finish = threading.Event(), threading.Event()

    def worker():
        with writer_activity(scope) as permit:
            started.set()
            assert finish.wait(5)
            permit.assert_held()

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert started.wait(2)
        token = pause_profile(scope)
        with pytest.raises(WriterBusyError):
            with writer_activity(scope):
                pytest.fail("new work entered after pause")
        with pytest.raises(WriterBusyError):
            resume_profile(scope, token)
    finally:
        finish.set()
        thread.join(5)
    assert not thread.is_alive()
    resume_profile(scope, token)


def test_resume_never_expires_or_deletes_unresolved_native_lease(tmp_path):
    import sqlite3
    from hermes_profile_maintenance import pause_profile, resume_profile
    from hermes_profile_writer import WriterFenceError
    scope = WriterScope(tmp_path, "one")
    activate_runtime(scope)
    with sqlite3.connect(tmp_path / "state.db") as conn:
        conn.execute("CREATE TABLE session_turn_leases (holder TEXT, expires_at REAL)")
        conn.execute("INSERT INTO session_turn_leases VALUES ('interrupted', 0)")
        conn.execute("CREATE TABLE compression_locks (holder TEXT)")
    token = pause_profile(scope)
    with pytest.raises(WriterFenceError, match="reconciliation"):
        resume_profile(scope, token)
    with sqlite3.connect(tmp_path / "state.db") as conn:
        assert conn.execute("SELECT holder, expires_at FROM session_turn_leases").fetchall() == [("interrupted", 0)]
