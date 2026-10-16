"""Functional preservation probes for aicask HLP-004; real temporary SQLite."""
import pytest


@pytest.fixture
def db(tmp_path):
    from hermes_state import SessionDB
    database = SessionDB(tmp_path/'state.db')
    yield database
    database.close()


def _parent(db):
    db.create_session('parent',source='api_server')
    db.append_message('parent','user','pre-compression history')
    db.end_session('parent','compression')
    db._conn.execute("UPDATE sessions SET started_at=100,ended_at=150 WHERE id='parent'")
    db._conn.commit()


def test_ops_nonempty_parent_resumes_compressed_child(db):
    _parent(db)
    db.create_session('child',source='api_server',parent_session_id='parent')
    db.append_message('child','assistant','compressed context')
    db._conn.execute("UPDATE sessions SET started_at=200 WHERE id='child'")
    db._conn.commit()
    assert db.resolve_resume_session_id('parent') == 'child'


def test_ops_compression_fork_prefers_latest_persisted_activity(db):
    _parent(db)
    for name,started,timestamp in [('active',200,2000),('stale-retry',300,1000)]:
        db.create_session(name,source='api_server',parent_session_id='parent')
        db.append_message(name,'assistant',name)
        db._conn.execute('UPDATE sessions SET started_at=? WHERE id=?',(started,name))
        db._conn.execute('UPDATE messages SET timestamp=? WHERE session_id=?',(timestamp,name))
    db._conn.commit()
    assert db.resolve_resume_session_id('parent') == 'active'
