import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


TASK_STATUSES = {"todo", "in_progress", "done", "blocked", "archived"}


def connect_workspace_db(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_workspace_db(conn)
    return conn


def init_workspace_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS workspace_task (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            project_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo',
            linked_session_ids TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_task_project_status ON workspace_task(project_path, status)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_task_updated ON workspace_task(updated_at)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS workspace_command_run (
            id TEXT PRIMARY KEY,
            project_path TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            command_key TEXT NOT NULL,
            command_label TEXT NOT NULL,
            command_argv TEXT NOT NULL,
            cwd TEXT NOT NULL,
            status TEXT NOT NULL,
            exit_code INTEGER,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            output TEXT NOT NULL DEFAULT '',
            started_at INTEGER NOT NULL,
            finished_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_command_run_project ON workspace_command_run(project_path, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_command_run_task ON workspace_command_run(task_id, created_at)"
    )
    conn.commit()


def fetch_tasks(conn: sqlite3.Connection, *, project_path: str = "", status: str = "") -> list[dict[str, Any]]:
    conditions = []
    params = []
    if project_path:
        conditions.append("project_path = ?")
        params.append(project_path)
    if status:
        _validate_status(status)
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT *
            FROM workspace_task
            {where}
            ORDER BY updated_at DESC, created_at DESC""",
        params,
    ).fetchall()
    return [serialize_task(row) for row in rows]


def create_task(
    conn: sqlite3.Connection,
    *,
    title: str,
    description: str = "",
    project_path: str = "",
    status: str = "todo",
    linked_session_ids: list[str] | None = None,
) -> dict[str, Any]:
    normalized_title = _normalize_title(title)
    normalized_status = _validate_status(status)
    now = _now_ms()
    task_id = f"task_{uuid.uuid4().hex}"
    linked_ids = _normalize_linked_session_ids(linked_session_ids)
    conn.execute(
        """INSERT INTO workspace_task
           (id, title, description, project_path, status, linked_session_ids, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            normalized_title,
            str(description or "").strip(),
            str(project_path or "").strip(),
            normalized_status,
            json.dumps(linked_ids, ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    return get_task(conn, task_id)


def update_task(conn: sqlite3.Connection, task_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_task(conn, task_id)
    if not existing:
        return None

    allowed = {
        "title",
        "description",
        "project_path",
        "status",
        "linked_session_ids",
    }
    updates = []
    params = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "title":
            value = _normalize_title(value)
        elif key == "status":
            value = _validate_status(value)
        elif key == "linked_session_ids":
            value = json.dumps(_normalize_linked_session_ids(value), ensure_ascii=False)
        else:
            value = str(value or "").strip()
        updates.append(f"{key} = ?")
        params.append(value)

    if not updates:
        return existing

    updates.append("updated_at = ?")
    params.append(_now_ms())
    params.append(task_id)
    conn.execute(f"UPDATE workspace_task SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return get_task(conn, task_id)


def get_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM workspace_task WHERE id = ?", (task_id,)).fetchone()
    return serialize_task(row) if row else None


def serialize_task(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "project_path": row["project_path"],
        "status": row["status"],
        "linked_session_ids": _loads_list(row["linked_session_ids"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def record_command_run(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    task_id: str,
    command_key: str,
    command_label: str,
    command_argv: list[str],
    cwd: str,
    status: str,
    exit_code: int | None,
    duration_ms: int,
    output: str,
    started_at: int,
    finished_at: int,
) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex}"
    created_at = _now_ms()
    conn.execute(
        """INSERT INTO workspace_command_run
           (id, project_path, task_id, command_key, command_label, command_argv, cwd, status,
            exit_code, duration_ms, output, started_at, finished_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            str(project_path or "").strip(),
            str(task_id or "").strip(),
            command_key,
            command_label,
            json.dumps(command_argv, ensure_ascii=False),
            cwd,
            status,
            exit_code,
            duration_ms,
            output,
            started_at,
            finished_at,
            created_at,
        ),
    )
    conn.commit()
    return get_command_run(conn, run_id)


def fetch_command_runs(
    conn: sqlite3.Connection,
    *,
    project_path: str = "",
    task_id: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    conditions = []
    params = []
    if project_path:
        conditions.append("project_path = ?")
        params.append(project_path)
    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT *
            FROM workspace_command_run
            {where}
            ORDER BY created_at DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [serialize_command_run(row) for row in rows]


def get_command_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM workspace_command_run WHERE id = ?", (run_id,)).fetchone()
    return serialize_command_run(row) if row else None


def serialize_command_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_path": row["project_path"],
        "task_id": row["task_id"],
        "command_key": row["command_key"],
        "command_label": row["command_label"],
        "command_argv": _loads_list(row["command_argv"]),
        "cwd": row["cwd"],
        "status": row["status"],
        "exit_code": row["exit_code"],
        "duration_ms": row["duration_ms"],
        "output": row["output"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "created_at": row["created_at"],
    }


def _normalize_title(value: Any) -> str:
    title = str(value or "").strip()
    if not title:
        raise ValueError("任务标题不能为空")
    if len(title) > 200:
        raise ValueError("任务标题不能超过 200 个字符")
    return title


def _validate_status(value: Any) -> str:
    status = str(value or "todo").strip()
    if status not in TASK_STATUSES:
        raise ValueError(f"任务状态无效: {status}")
    return status


def _normalize_linked_session_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("linked_session_ids 必须是数组")
    normalized = []
    for item in value:
        session_id = str(item or "").strip()
        if session_id and session_id not in normalized:
            normalized.append(session_id)
    return normalized


def _loads_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _now_ms() -> int:
    return int(time.time() * 1000)
