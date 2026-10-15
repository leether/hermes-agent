"""Regression guard for #15000: --resume <id> after compression loses messages.

Context compression ends the current session and forks a new child session
(linked by ``parent_session_id``). The SQLite flush cursor is reset, so
only the latest descendant ends up with rows in the ``messages`` table —
the parent row has ``message_count = 0``. ``hermes --resume <parent_id>``
used to load zero rows and show a blank chat.

``SessionDB.resolve_resume_session_id()`` walks the parent → child chain
and redirects to the first descendant that actually has messages. These
tests pin that behaviour.
"""
import time

import pytest

from hermes_state import SessionDB


@pytest.fixture
def db(tmp_path):
    return SessionDB(tmp_path / "state.db")


def _make_chain(db: SessionDB, ids_with_parent):
    """Create sessions in order, forcing started_at so ordering is deterministic."""
    base = int(time.time()) - 10_000
    for i, (sid, parent) in enumerate(ids_with_parent):
        db.create_session(sid, source="cli", parent_session_id=parent)
        db._conn.execute(
            "UPDATE sessions SET started_at = ? WHERE id = ?",
            (base + i * 100, sid),
        )
    db._conn.commit()


def test_redirects_from_empty_head_to_descendant_with_messages(db):
    # Reproducer shape from #15000: 6 sessions, only the 5th holds messages.
    _make_chain(db, [
        ("head",   None),
        ("mid1",   "head"),
        ("mid2",   "mid1"),
        ("mid3",   "mid2"),
        ("bulk",   "mid3"),    # has messages
        ("tail",   "bulk"),    # empty tail after another compression
    ])
    for i in range(5):
        db.append_message("bulk", role="user", content=f"msg {i}")

    assert db.resolve_resume_session_id("head") == "bulk"


def test_returns_self_when_session_has_messages(db):
    _make_chain(db, [("root", None), ("child", "root")])
    db.append_message("root", role="user", content="hi")
    assert db.resolve_resume_session_id("root") == "root"


def test_returns_self_when_no_descendant_has_messages(db):
    _make_chain(db, [("root", None), ("child1", "root"), ("child2", "child1")])
    assert db.resolve_resume_session_id("root") == "root"


def test_returns_self_for_isolated_session(db):
    db.create_session("isolated", source="cli")
    assert db.resolve_resume_session_id("isolated") == "isolated"


def test_returns_self_for_nonexistent_session(db):
    assert db.resolve_resume_session_id("does_not_exist") == "does_not_exist"


def test_empty_session_id_passthrough(db):
    assert db.resolve_resume_session_id("") == ""
    assert db.resolve_resume_session_id(None) is None


def test_walks_from_middle_of_chain(db):
    # If the user happens to know an intermediate ID, we still find the msg-bearing descendant.
    _make_chain(db, [("a", None), ("b", "a"), ("c", "b"), ("d", "c")])
    db.append_message("d", role="user", content="x")
    assert db.resolve_resume_session_id("b") == "d"
    assert db.resolve_resume_session_id("c") == "d"


def test_prefers_most_recent_child_when_fork_exists(db):
    # If a session was somehow forked (two children), pick the latest one.
    # In practice, compression only produces single-chain shape, but the helper
    # should degrade gracefully.
    _make_chain(db, [
        ("parent", None),
        ("older_fork", "parent"),
        ("newer_fork", "parent"),
    ])
    db.append_message("newer_fork", role="user", content="x")
    assert db.resolve_resume_session_id("parent") == "newer_fork"


def test_compression_parent_with_messages_advances_to_continuation(db):
    db.create_session("parent", source="api_server")
    db.append_message("parent", role="user", content="pre-compression history")
    db.end_session("parent", "compression")
    db.create_session(
        "continuation",
        source="api_server",
        parent_session_id="parent",
    )
    db.append_message("continuation", role="assistant", content="compressed context")

    assert db.resolve_resume_session_id("parent") == "continuation"


def test_compression_siblings_prefer_latest_message_activity(db):
    db.create_session("parent", source="api_server")
    db.append_message("parent", role="user", content="pre-compression history")
    db.end_session("parent", "compression")
    db.create_session("active_child", source="api_server", parent_session_id="parent")
    db.create_session("later_retry", source="api_server", parent_session_id="parent")
    db.append_message("active_child", role="assistant", content="continued conversation")
    db.append_message("later_retry", role="assistant", content="stale retry")

    # The active child started first but received the latest real activity.
    db._conn.execute(
        "UPDATE messages SET timestamp = ? WHERE session_id = ?",
        (2_000.0, "active_child"),
    )
    db._conn.execute(
        "UPDATE messages SET timestamp = ? WHERE session_id = ?",
        (1_000.0, "later_retry"),
    )
    db._conn.commit()

    assert db.resolve_resume_session_id("parent") == "active_child"


def test_compression_does_not_follow_child_created_before_parent_ended(db):
    db.create_session("parent", source="api_server")
    db.create_session("delegate", source="api_server", parent_session_id="parent")
    db.append_message("delegate", role="assistant", content="subagent output")
    db.append_message("parent", role="user", content="main conversation")
    db.end_session("parent", "compression")

    assert db.resolve_resume_session_id("parent") == "parent"
