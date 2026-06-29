import json
import sqlite3

import opencode_monitor


def test_monitor_get_completed_notifications_uses_state_machine(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
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
    conn.close()
    monkeypatch.setattr(opencode_monitor, "DB_PATH", str(db_path))
    monkeypatch.setattr(opencode_monitor, "STABLE_WINDOW_MS", 1500)

    notifications = opencode_monitor.get_completed_notifications(now_ms=3000)
    legacy_rows = opencode_monitor.get_finished()

    assert [notification.session_id for notification in notifications] == ["ses_tool"]
    assert notifications[0].part_id == 4
    assert legacy_rows == [
        {
            "pid": 4,
            "sid": "ses_tool",
            "title": "Tool",
            "directory": "C:/repo",
            "model": "provider/model",
        }
    ]


def test_monitor_get_completed_notifications_suppresses_notified_ids(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
    _create_schema(conn)
    _insert_session(conn, "ses_seen", "Seen", "C:/repo", "provider/model", 1000)
    _insert_message(conn, "msg_seen", "ses_seen", 1000)
    _insert_part(conn, "part_stop", "msg_seen", "ses_seen", {"type": "step-finish", "reason": "stop"}, 1200)
    conn.close()
    monkeypatch.setattr(opencode_monitor, "DB_PATH", str(db_path))
    monkeypatch.setattr(opencode_monitor, "STABLE_WINDOW_MS", 1500)

    first = opencode_monitor.get_completed_notifications(now_ms=2800)
    repeated = opencode_monitor.get_completed_notifications(
        notified_part_ids={first[0].part_id},
        now_ms=2800,
    )

    assert len(first) == 1
    assert repeated == []


def _connect(path):
    conn = sqlite3.connect(path)
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
