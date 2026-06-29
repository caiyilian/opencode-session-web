import sqlite3

from services.sync_watcher import (
    SessionSnapshot,
    diff_session_snapshots,
    fetch_session_snapshots,
)


def test_fetch_session_snapshots_reads_lightweight_session_rows(tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
    _create_session_table(conn)
    _insert_session(conn, "ses_1", "One", "C:/repo/one", 100)
    _insert_session(conn, "ses_2", None, None, None)

    snapshots = fetch_session_snapshots(conn)

    assert snapshots["ses_1"] == SessionSnapshot("ses_1", "One", "C:/repo/one", 100)
    assert snapshots["ses_2"] == SessionSnapshot("ses_2", "", "", 0)


def test_fetch_session_snapshots_counts_messages_and_parts(tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
    _create_session_table(conn)
    _create_message_table(conn)
    _create_part_table(conn)
    _insert_session(conn, "ses_1", "One", "C:/repo/one", 100)
    _insert_message(conn, "msg_1", "ses_1")
    _insert_message(conn, "msg_2", "ses_1")
    _insert_part(conn, "part_1", "msg_1", "ses_1")
    _insert_part(conn, "part_2", "msg_1", "ses_1")
    _insert_part(conn, "part_3", "msg_2", "ses_1")

    snapshots = fetch_session_snapshots(conn)

    assert snapshots["ses_1"] == SessionSnapshot(
        "ses_1",
        "One",
        "C:/repo/one",
        100,
        message_count=2,
        part_count=3,
    )


def test_diff_session_snapshots_detects_created_updated_and_deleted():
    previous = {
        "ses_old": SessionSnapshot("ses_old", "Old", "C:/repo/old", 100),
        "ses_update": SessionSnapshot("ses_update", "Before", "C:/repo/app", 200),
        "ses_delete": SessionSnapshot("ses_delete", "Delete", "C:/repo/app", 300),
    }
    current = {
        "ses_new": SessionSnapshot("ses_new", "New", "C:/repo/new", 400),
        "ses_update": SessionSnapshot("ses_update", "After", "C:/repo/app", 250),
        "ses_old": previous["ses_old"],
    }

    changes = diff_session_snapshots(previous, current)

    assert [change.type for change in changes] == ["created", "updated", "deleted"]
    assert [change.session.id for change in changes] == ["ses_new", "ses_update", "ses_delete"]
    assert changes[1].previous == previous["ses_update"]
    assert changes[0].to_dict() == {
        "type": "created",
        "session": {
            "id": "ses_new",
            "title": "New",
            "directory": "C:/repo/new",
            "time_updated": 400,
        },
    }


def test_diff_session_snapshots_detects_message_and_part_count_changes():
    previous = {
        "ses_message": SessionSnapshot("ses_message", "Same", "C:/repo", 100, message_count=1, part_count=1),
        "ses_part": SessionSnapshot("ses_part", "Same", "C:/repo", 100, message_count=1, part_count=1),
    }
    current = {
        "ses_message": SessionSnapshot("ses_message", "Same", "C:/repo", 100, message_count=2, part_count=1),
        "ses_part": SessionSnapshot("ses_part", "Same", "C:/repo", 100, message_count=1, part_count=2),
    }

    changes = diff_session_snapshots(previous, current)

    assert [change.type for change in changes] == ["updated", "updated"]
    assert [change.session.id for change in changes] == ["ses_message", "ses_part"]
    assert changes[0].previous == previous["ses_message"]
    assert changes[0].to_dict()["session"] == {
        "id": "ses_message",
        "title": "Same",
        "directory": "C:/repo",
        "time_updated": 100,
    }


def test_diff_session_snapshots_returns_empty_for_same_snapshot():
    snapshot = SessionSnapshot("ses_1", "Same", "C:/repo", 100)

    assert diff_session_snapshots({"ses_1": snapshot}, {"ses_1": snapshot}) == []


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _create_session_table(conn):
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            title TEXT,
            directory TEXT,
            time_updated INTEGER
        )"""
    )
    conn.commit()


def _create_message_table(conn):
    conn.execute(
        """CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT
        )"""
    )
    conn.commit()


def _create_part_table(conn):
    conn.execute(
        """CREATE TABLE part (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            session_id TEXT
        )"""
    )
    conn.commit()


def _insert_session(conn, session_id, title, directory, time_updated):
    conn.execute(
        "INSERT INTO session (id, title, directory, time_updated) VALUES (?, ?, ?, ?)",
        (session_id, title, directory, time_updated),
    )
    conn.commit()


def _insert_message(conn, message_id, session_id):
    conn.execute(
        "INSERT INTO message (id, session_id) VALUES (?, ?)",
        (message_id, session_id),
    )
    conn.commit()


def _insert_part(conn, part_id, message_id, session_id):
    conn.execute(
        "INSERT INTO part (id, message_id, session_id) VALUES (?, ?, ?)",
        (part_id, message_id, session_id),
    )
    conn.commit()
