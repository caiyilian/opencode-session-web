from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Iterable

from db import has_table_column, session_column_expr, table_exists
from services.opencode_events import CANDIDATE_DONE, ConversationState, parse_part


@dataclass(frozen=True)
class MonitorNotification:
    part_id: int
    session_id: str
    title: str
    directory: str
    model: str


def find_completed_sessions(
    conn,
    *,
    notified_part_ids: Iterable[int] = (),
    stable_window_ms: int = 1500,
    now_ms: int | None = None,
) -> list[MonitorNotification]:
    if not table_exists(conn, "message") or not table_exists(conn, "part"):
        return []

    now_ms = _now_epoch_ms() if now_ms is None else now_ms
    notified = {int(part_id) for part_id in notified_part_ids}
    states: dict[str, ConversationState] = {}
    candidate_part_ids: dict[str, int] = {}
    session_info: dict[str, MonitorNotification] = {}

    for row in _fetch_monitor_parts(conn):
        session_id = row["session_id"]
        state = states.setdefault(session_id, ConversationState(stable_window_ms=stable_window_ms))
        part_data = _json_object(row["part_data"])
        part = parse_part(part_data)
        state.apply_part(part, now_ms=_event_time_ms(row, now_ms))

        if state.status == CANDIDATE_DONE and part.type == "step-finish" and part.reason == "stop":
            candidate_part_ids[session_id] = row["part_id"]
        elif state.status != CANDIDATE_DONE:
            candidate_part_ids.pop(session_id, None)

        session_info[session_id] = MonitorNotification(
            part_id=row["part_id"],
            session_id=session_id,
            title=row["title"] or "",
            directory=row["directory"] or "",
            model=row["model"] or "",
        )

    notifications: list[MonitorNotification] = []
    for session_id, state in states.items():
        state.tick(now_ms=now_ms)
        part_id = candidate_part_ids.get(session_id)
        if not state.done or part_id is None or part_id in notified:
            continue
        info = session_info[session_id]
        notifications.append(
            MonitorNotification(
                part_id=part_id,
                session_id=session_id,
                title=info.title,
                directory=info.directory,
                model=info.model,
            )
        )

    return sorted(notifications, key=lambda notification: notification.part_id)


def _fetch_monitor_parts(conn):
    model_expr = session_column_expr(conn, "model", "s", "NULL")
    part_updated_expr = _column_expr(conn, "part", "p", "time_updated")
    part_created_expr = _column_expr(conn, "part", "p", "time_created")
    message_updated_expr = _column_expr(conn, "message", "m", "time_updated")
    message_created_expr = _column_expr(conn, "message", "m", "time_created")
    session_updated_expr = _column_expr(conn, "session", "s", "time_updated")
    return conn.execute(
        f"""SELECT p.rowid AS part_id,
                   p.data AS part_data,
                   COALESCE(
                       {part_updated_expr},
                       {part_created_expr},
                       {message_updated_expr},
                       {message_created_expr},
                       {session_updated_expr},
                       0
                   ) AS event_time,
                   s.id AS session_id,
                   s.title AS title,
                   s.directory AS directory,
                   {model_expr} AS model
            FROM session s
            JOIN message m ON m.session_id = s.id
            JOIN part p ON p.message_id = m.id
            ORDER BY s.id ASC, {message_created_expr} ASC, p.rowid ASC"""
    ).fetchall()


def _column_expr(conn, table: str, alias: str, column: str) -> str:
    if has_table_column(conn, table, column):
        return f"{alias}.{column}"
    return "NULL"


def _json_object(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _event_time_ms(row, fallback_ms: int) -> int:
    try:
        return int(row["event_time"] or fallback_ms)
    except (TypeError, ValueError):
        return fallback_ms


def _now_epoch_ms() -> int:
    return int(time.time() * 1000)
