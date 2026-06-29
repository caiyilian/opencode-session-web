from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SessionSnapshot:
    id: str
    title: str
    directory: str
    time_updated: int
    message_count: int = 0
    part_count: int = 0

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "title": self.title,
            "directory": self.directory,
            "time_updated": self.time_updated,
        }


@dataclass(frozen=True)
class SessionChange:
    type: str
    session: SessionSnapshot
    previous: SessionSnapshot | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.type,
            "session": self.session.to_dict(),
        }
        if self.previous is not None:
            payload["previous"] = self.previous.to_dict()
        return payload


def fetch_session_snapshots(conn) -> dict[str, SessionSnapshot]:
    message_count_sql = "0"
    if _has_table_column(conn, "message", "session_id"):
        message_count_sql = "(SELECT COUNT(*) FROM message m WHERE m.session_id = s.id)"

    part_count_sql = "0"
    if _has_table_column(conn, "part", "session_id"):
        part_count_sql = "(SELECT COUNT(*) FROM part p WHERE p.session_id = s.id)"
    elif _has_table_column(conn, "part", "message_id") and _has_table_column(conn, "message", "session_id"):
        part_count_sql = (
            "(SELECT COUNT(*) FROM part p "
            "JOIN message m ON m.id = p.message_id "
            "WHERE m.session_id = s.id)"
        )

    rows = conn.execute(
        f"""SELECT s.id, s.title, s.directory, s.time_updated,
                   {message_count_sql} AS message_count,
                   {part_count_sql} AS part_count
            FROM session s
            ORDER BY s.time_updated DESC"""
    ).fetchall()
    return {
        row["id"]: SessionSnapshot(
            id=row["id"],
            title=row["title"] or "",
            directory=row["directory"] or "",
            time_updated=row["time_updated"] or 0,
            message_count=row["message_count"] or 0,
            part_count=row["part_count"] or 0,
        )
        for row in rows
    }


def diff_session_snapshots(
    previous: Mapping[str, SessionSnapshot],
    current: Mapping[str, SessionSnapshot],
) -> list[SessionChange]:
    changes: list[SessionChange] = []

    for session_id, snapshot in current.items():
        old_snapshot = previous.get(session_id)
        if old_snapshot is None:
            changes.append(SessionChange("created", snapshot))
        elif old_snapshot != snapshot:
            changes.append(SessionChange("updated", snapshot, previous=old_snapshot))

    for session_id, old_snapshot in previous.items():
        if session_id not in current:
            changes.append(SessionChange("deleted", old_snapshot))

    return sorted(changes, key=_change_sort_key)


def _change_sort_key(change: SessionChange) -> tuple[int, str, str]:
    order = {"created": 0, "updated": 1, "deleted": 2}
    return (order.get(change.type, 99), change.session.id, change.type)


def _has_table_column(conn, table: str, column: str) -> bool:
    if not _has_table(conn, table):
        return False
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(_pragma_column_name(row) == column for row in rows)


def _has_table(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _pragma_column_name(row) -> str:
    try:
        return row["name"]
    except (IndexError, TypeError):
        return row[1]
