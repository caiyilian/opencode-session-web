from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SessionSnapshot:
    id: str
    title: str
    directory: str
    time_updated: int

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
    rows = conn.execute(
        """SELECT id, title, directory, time_updated
           FROM session
           ORDER BY time_updated DESC"""
    ).fetchall()
    return {
        row["id"]: SessionSnapshot(
            id=row["id"],
            title=row["title"] or "",
            directory=row["directory"] or "",
            time_updated=row["time_updated"] or 0,
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
