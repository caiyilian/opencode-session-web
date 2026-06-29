import json
import sqlite3

from services.monitor_state import find_completed_sessions


def test_find_completed_sessions_notifies_plain_text_after_stable_window():
    conn = _connect()
    _create_schema(conn)
    _insert_session(conn, "ses_text", "Plain", "C:/repo", "provider/model", 1000)
    _insert_message(conn, "msg_text", "ses_text", 1000)
    _insert_part(conn, "part_text", "msg_text", "ses_text", {"type": "text", "text": "done"}, 1100)
    _insert_part(conn, "part_stop", "msg_text", "ses_text", {"type": "step-finish", "reason": "stop"}, 1200)

    notifications = find_completed_sessions(conn, now_ms=2800, stable_window_ms=1500)

    assert len(notifications) == 1
    assert notifications[0].session_id == "ses_text"
    assert notifications[0].title == "Plain"
    assert notifications[0].directory == "C:/repo"
    assert notifications[0].model == "provider/model"
    assert notifications[0].part_id == 2


def test_find_completed_sessions_waits_for_stable_window():
    conn = _connect()
    _create_schema(conn)
    _insert_session(conn, "ses_wait", "Wait", "C:/repo", "provider/model", 1000)
    _insert_message(conn, "msg_wait", "ses_wait", 1000)
    _insert_part(conn, "part_stop", "msg_wait", "ses_wait", {"type": "step-finish", "reason": "stop"}, 1200)

    assert find_completed_sessions(conn, now_ms=2200, stable_window_ms=1500) == []
    assert len(find_completed_sessions(conn, now_ms=2700, stable_window_ms=1500)) == 1


def test_find_completed_sessions_ignores_tool_calls_until_final_stop():
    conn = _connect()
    _create_schema(conn)
    _insert_session(conn, "ses_tool", "Tool", "C:/repo", "provider/model", 1000)
    _insert_message(conn, "msg_tool", "ses_tool", 1000)
    _insert_part(
        conn,
        "part_tool",
        "msg_tool",
        "ses_tool",
        {"type": "tool", "id": "tool_1", "tool": "bash", "state": {"status": "running"}},
        1100,
    )
    _insert_part(
        conn,
        "part_tool_calls",
        "msg_tool",
        "ses_tool",
        {"type": "step-finish", "reason": "tool-calls"},
        1200,
    )
    _insert_part(
        conn,
        "part_tool_result",
        "msg_tool",
        "ses_tool",
        {"type": "tool_result", "id": "tool_1", "tool": "bash", "text": "ok"},
        1300,
    )
    _insert_part(conn, "part_stop", "msg_tool", "ses_tool", {"type": "step-finish", "reason": "stop"}, 1400)

    notifications = find_completed_sessions(conn, now_ms=3000, stable_window_ms=1500)

    assert [notification.session_id for notification in notifications] == ["ses_tool"]
    assert notifications[0].part_id == 4


def test_find_completed_sessions_suppresses_notified_part_ids():
    conn = _connect()
    _create_schema(conn)
    _insert_session(conn, "ses_seen", "Seen", "C:/repo", "provider/model", 1000)
    _insert_message(conn, "msg_seen", "ses_seen", 1000)
    _insert_part(conn, "part_stop", "msg_seen", "ses_seen", {"type": "step-finish", "reason": "stop"}, 1200)

    first = find_completed_sessions(conn, now_ms=2800, stable_window_ms=1500)
    repeated = find_completed_sessions(
        conn,
        notified_part_ids={first[0].part_id},
        now_ms=2800,
        stable_window_ms=1500,
    )

    assert len(first) == 1
    assert repeated == []


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn):
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            title TEXT,
            directory TEXT,
            model TEXT,
            time_updated INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            time_created INTEGER,
            time_updated INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE part (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            session_id TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            data TEXT
        )"""
    )
    conn.commit()


def _insert_session(conn, session_id, title, directory, model, time_updated):
    conn.execute(
        "INSERT INTO session (id, title, directory, model, time_updated) VALUES (?, ?, ?, ?, ?)",
        (session_id, title, directory, model, time_updated),
    )
    conn.commit()


def _insert_message(conn, message_id, session_id, time_created):
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated) VALUES (?, ?, ?, ?)",
        (message_id, session_id, time_created, time_created),
    )
    conn.commit()


def _insert_part(conn, part_id, message_id, session_id, data, time_created):
    conn.execute(
        """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (part_id, message_id, session_id, time_created, time_created, json.dumps(data)),
    )
    conn.commit()
