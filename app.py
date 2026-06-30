"""
OpenCode 会话 Web 查看器 — Flask 后端

读取本地的 opencode.db SQLite 数据库，提供 REST API。
"""

import json
import os
import subprocess
import queue
import threading
import time
from flask import Flask, jsonify, request, render_template, Response, stream_with_context, send_from_directory, abort
from config import AppConfig
from db import (
    connect_db,
    get_session_usage,
    has_table_column,
)
from logging_config import configure_logging
from repositories.session_queries import (
    fetch_message_detail,
    fetch_project_workspaces,
    fetch_session_detail,
    fetch_session_list,
    fetch_session_messages_with_parts,
    fetch_stats_overview,
    fetch_token_stats,
)
from repositories.workspace_tasks import (
    TASK_STATUSES,
    connect_workspace_db,
    create_task,
    fetch_command_runs,
    fetch_task_events,
    fetch_tasks,
    get_task,
    record_task_event,
    record_command_run,
    update_task,
)
from services import sse
from services.git_status import read_git_snapshot
from services.opencode_errors import format_stream_error_message, is_known_error_text
from services.opencode_events import parse_part
from services.opencode_runner import event_to_sse
from services.process_manager import ProcessManager
from services.sync_watcher import diff_session_snapshots, fetch_session_snapshots
from services.workspace_commands import (
    CommandExecution,
    find_workspace_command,
    parse_workspace_commands,
    resolve_workspace_command_cwd,
    run_workspace_command,
    truncate_command_output,
)
from services.workspace_reports import build_task_report

app = Flask(__name__)
logger = configure_logging()
process_manager = ProcessManager()
process_manager.register_atexit()

# ── 数据库路径 ──────────────────────────────────────────────

DEFAULT_CONFIG = AppConfig.from_env()
app.config.update(DEFAULT_CONFIG.to_flask_config())
DB_PATH = app.config["OPENCODE_DB_PATH"]


def create_app(test_config=None):
    """Configure and return the Flask app.

    The route table is still module-level in this phase. Returning the global app
    keeps behavior stable while giving tests and later refactors a single config
    injection point.
    """
    global DB_PATH
    app.config.update(AppConfig.from_env().to_flask_config())
    if test_config:
        app.config.update(test_config)
    DB_PATH = app.config["OPENCODE_DB_PATH"]
    return app


def get_db():
    """获取数据库连接（每次请求独立，避免线程问题）"""
    return connect_db(app.config.get("OPENCODE_DB_PATH", DB_PATH))


def get_workspace_db():
    """Connect to the OpenCode Session Web workspace database."""
    return connect_workspace_db(app.config["OPENCODE_WORKSPACE_DB_PATH"])


# ── 工具函数 ──────────────────────────────────────────────

def dict_from_row(row):
    """将 sqlite3.Row 转为 dict"""
    if row is None:
        return None
    return dict(row)


def safe_truncate(text, max_len=500):
    """安全截断文本，确保返回字符串"""
    if text is None:
        return ""
    return str(text)[:max_len]


def get_project_name(directory: str) -> str:
    """从目录路径中提取项目名"""
    parts = directory.replace("\\", "/").rstrip("/").split("/")
    return parts[-1] if parts else directory


def format_model(model_str) -> str:
    """格式化模型名，处理 JSON 字符串的情况"""
    if not model_str:
        return "N/A"
    if model_str.startswith("{"):
        try:
            d = json.loads(model_str)
            return d.get("id", model_str)
        except (json.JSONDecodeError, TypeError):
            pass
    return model_str


def format_time(ms: int) -> str:
    """Unix 毫秒 → 可读时间"""
    from datetime import datetime, timezone
    if not ms:
        return ""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()
    now = datetime.now().astimezone()
    diff = now - dt
    if diff.days == 0:
        if diff.seconds < 60:
            return "刚刚"
        elif diff.seconds < 3600:
            return f"{diff.seconds // 60} 分钟前"
        else:
            return f"{diff.seconds // 3600} 小时前"
    elif diff.days == 1:
        return "昨天"
    elif diff.days < 7:
        return f"{diff.days} 天前"
    else:
        return dt.strftime("%m-%d %H:%M")


def normalize_tool_status(*values) -> str:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized:
            return normalized
    return ""


def add_tool_timing_metadata(entry: dict, part_row: dict):
    created = part_row.get("time_created_raw")
    updated = part_row.get("time_updated_raw")
    if created is not None:
        entry["time_created_raw"] = created
    if updated is not None:
        entry["time_updated_raw"] = updated
    if isinstance(created, int) and isinstance(updated, int) and updated >= created:
        entry["duration_ms"] = updated - created


def extract_message_role(data: dict) -> str:
    """从 message.data JSON 中提取角色"""
    return data.get("role", "unknown")


def extract_message_content(data: dict) -> str:
    """从 message.data JSON 中提取文本内容"""
    parts = data.get("parts") or data.get("content") or []
    texts = []
    if isinstance(parts, str):
        return parts
    for p in parts:
        if isinstance(p, dict):
            if p.get("type") == "text":
                texts.append(p.get("text", ""))
            elif p.get("type") == "tool_result":
                texts.append(f"[工具结果: {p.get('tool_name', '')}]")
            elif p.get("type") == "tool_use":
                texts.append(f"[调用工具: {p.get('name', '')}]")
            elif p.get("type") == "reasoning":
                texts.append(f"[思考: {p.get('text', '')[:100]}...]")
        elif isinstance(p, str):
            texts.append(p)
    return "\n".join(texts)


# ── API 路由 ──────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    """获取统计信息"""
    conn = get_db()
    stats = fetch_stats_overview(conn)
    conn.close()
    total_usage = stats["total_usage"]

    return jsonify({
        "total_sessions": stats["total_sessions"],
        "total_projects": stats["total_projects"],
        "total_cost": round(total_usage["cost"], 6),
        "total_tokens_input": total_usage["tokens_input"],
        "total_tokens_output": total_usage["tokens_output"],
        "top_directories": [{"path": r["directory"], "count": r["cnt"]} for r in stats["top_directories"]],
        "top_models": [{"model": r["model"], "count": r["cnt"]} for r in stats["top_models"]],
        "recent_sessions": [{
            "id": r["id"],
            "title": r["title"],
            "directory": r["directory"],
            "time_updated": format_time(r["time_updated"]),
        } for r in stats["recent_sessions"]],
    })


@app.route("/api/sessions")
def api_sessions():
    """获取会话列表，支持搜索和筛选"""
    q = request.args.get("q", "").strip()
    directory = request.args.get("dir", "").strip()
    model = request.args.get("model", "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    total, rows = fetch_session_list(
        conn,
        q=q,
        directory=directory,
        model=model,
        limit=limit,
        offset=offset,
    )
    conn.close()

    sessions = []
    for r in rows:
        sessions.append({
            "id": r["id"],
            "title": r["title"],
            "directory": r["directory"],
            "project": get_project_name(r["directory"]),
            "model": format_model(r["model"]),
            "agent": r["agent"] or "N/A",
            "time_created": format_time(r["time_created"]),
            "time_updated": format_time(r["time_updated"]),
            "time_updated_raw": r["time_updated"],
            "cost": r["cost"],
            "tokens_input": r["tokens_input"],
            "tokens_output": r["tokens_output"],
            "message_count": r["msg_count"],
        })

    return jsonify({"sessions": sessions, "total": total})


# ── Phase 3: 会话对比 ──────────────────────────────────


@app.route("/api/sessions/compare")
def api_sessions_compare():
    """对比两个会话的消息"""
    id1 = request.args.get("id1", "").strip()
    id2 = request.args.get("id2", "").strip()
    if not id1 or not id2:
        return jsonify({"error": "需要 id1 和 id2 参数"}), 400

    conn = get_db()
    cursor = conn.cursor()

    def load_session(sid):
        row = cursor.execute("SELECT * FROM session WHERE id = ?", (sid,)).fetchone()
        if not row:
            return None
        s = dict(row)
        msgs = cursor.execute(
            """SELECT m.id, m.time_created, m.data,
                      p.data as part_data
               FROM message m
               LEFT JOIN part p ON p.message_id = m.id
               WHERE m.session_id = ?
               ORDER BY m.time_created ASC, p.id ASC""",
            (sid,),
        ).fetchall()
        msg_map = {}
        for m in msgs:
            mid = m["id"]
            if mid not in msg_map:
                try:
                    d = json.loads(m["data"])
                except (json.JSONDecodeError, TypeError):
                    d = {}
                msg_map[mid] = {
                    "id": mid,
                    "role": d.get("role", "unknown"),
                    "time": m["time_created"],
                    "parts": [],
                }
            if m["part_data"]:
                try:
                    msg_map[mid]["parts"].append(json.loads(m["part_data"]))
                except (json.JSONDecodeError, TypeError):
                    pass
        msg_list = []
        for mid in sorted(msg_map, key=lambda x: msg_map[x]["time"]):
            m = msg_map[mid]
            texts = []
            for p in m["parts"]:
                part = parse_part(p)
                if part.type == "text":
                    texts.append(part.text)
                elif part.type == "tool":
                    texts.append(f"[工具] {part.tool}")
                elif part.type == "step-finish":
                    tokens_info = part.tokens
                    if tokens_info:
                        texts.append(f"[步骤完成] {tokens_info.get('total', 0)} tokens")
            content = "\n".join(texts) if texts else ""
            msg_list.append({
                "id": m["id"],
                "role": m["role"],
                "parts": m["parts"],
                "content": content[:500],
                "time": m["time"],
            })
        return {
            "id": s["id"],
            "title": s["title"],
            "model": format_model(s.get("model", "")),
            "directory": s["directory"],
            "project": get_project_name(s["directory"]),
            "messages": msg_list,
            "message_count": len(msg_list),
            **get_session_usage(conn, sid),
        }

    s1 = load_session(id1)
    s2 = load_session(id2)
    conn.close()

    if not s1:
        return jsonify({"error": f"会话 {id1} 不存在"}), 404
    if not s2:
        return jsonify({"error": f"会话 {id2} 不存在"}), 404

    return jsonify({"session1": s1, "session2": s2})


@app.route("/api/sessions/<session_id>")
def api_session_detail(session_id):
    """获取单个会话详情"""
    conn = get_db()
    row, usage = fetch_session_detail(conn, session_id)

    if not row:
        conn.close()
        return jsonify({"error": "会话不存在"}), 404

    session = dict_from_row(row)
    session["project"] = get_project_name(session["directory"])
    session["model"] = format_model(session.get("model"))
    session["agent"] = session.get("agent") or "N/A"
    session["time_created_fmt"] = format_time(session["time_created"])
    session["time_updated_fmt"] = format_time(session["time_updated"])
    session.update(usage)

    # 获取消息（含内容）
    messages = fetch_session_messages_with_parts(conn, session_id)

    msg_map = {}  # message_id -> {msg_info, parts: []}
    for m in messages:
        mid = m["id"]
        if mid not in msg_map:
            try:
                data = json.loads(m["data"])
            except (json.JSONDecodeError, TypeError):
                data = {}
            role = extract_message_role(data)
            tokens = {}
            if role == "assistant":
                tokens = {
                    "input": data.get("tokens", {}).get("input", 0),
                    "output": data.get("tokens", {}).get("output", 0),
                }
            msg_map[mid] = {
                "id": mid,
                "role": role,
                "tokens": tokens,
                "time_created": format_time(m["time_created"]),
                "time_created_raw": m["time_created"],
                "parts": [],
            }
        if m["part_data"]:
            try:
                part = json.loads(m["part_data"])
                msg_map[mid]["parts"].append({
                    "data": part,
                    "time_created_raw": m["part_time_created"],
                    "time_updated_raw": m["part_time_updated"],
                })
            except (json.JSONDecodeError, TypeError):
                pass

    # 将 parts 按类型传递给前端
    msg_list = []
    for mid in sorted(msg_map.keys(), key=lambda x: msg_map[x]["time_created_raw"]):
        m = msg_map[mid]
        parts_out = []
        for part_row in m["parts"]:
            p = part_row["data"]
            part = parse_part(p)
            t = part.type
            entry = {"type": t}
            if t == "text":
                entry["text"] = part.text
            elif t == "reasoning":
                entry["text"] = part.text
            elif t == "tool":
                entry["tool"] = part.tool
                state = part.state
                sinp = state.get("input", {})
                if isinstance(sinp, dict):
                    # bash: {command, description}; glob: {pattern}; edit: {file_path, ...}
                    cmd = sinp.get("command") or sinp.get("pattern") or sinp.get("file_path") or ""
                    desc = sinp.get("description", "")
                    entry["input"] = str(cmd)[:500]
                    entry["description"] = str(desc)[:200]
                else:
                    entry["input"] = str(sinp)[:500]
                    entry["description"] = ""
                entry["output"] = state.get("output", "")[:2000]
                entry["is_hidden"] = state.get("metadata", {}).get("truncated", False) if isinstance(state.get("metadata"), dict) else False
                entry["status"] = normalize_tool_status(state.get("status"), state.get("state"), p.get("status"))
                add_tool_timing_metadata(entry, part_row)
            elif t == "tool_result":
                entry["tool_name"] = part.tool
                entry["content"] = part.text
                entry["status"] = normalize_tool_status(p.get("status"), part.raw.get("status")) or "success"
                entry["is_hidden"] = p.get("is_hidden", False)
                add_tool_timing_metadata(entry, part_row)
            elif t == "step-start":
                pass
            elif t == "step-finish":
                entry["tokens"] = part.tokens
                entry["cost"] = part.cost
                entry["reason"] = part.reason
            parts_out.append(entry)

        msg_list.append({
            "id": m["id"],
            "role": m["role"],
            "parts": parts_out,
            "time_created": m["time_created"],
            "time_created_raw": m["time_created_raw"],
            "tokens": m["tokens"],
        })

    conn.close()

    return jsonify({
        "session": session,
        "messages": msg_list,
        "message_count": len(msg_list),
    })


@app.route("/api/messages/<message_id>")
def api_message_detail(message_id):
    """获取单条消息的完整内容"""
    conn = get_db()
    row = fetch_message_detail(conn, message_id)
    conn.close()

    if not row:
        return jsonify({"error": "消息不存在"}), 404

    try:
        data = json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        data = {}

    return jsonify({
        "id": row["id"],
        "session_id": row["session_id"],
        "data": data,
        "time_created": row["time_created"],
    })


@app.route("/api/directories")
def api_directories():
    """获取所有有会话的工作目录"""
    conn = get_db()
    cursor = conn.cursor()

    rows = cursor.execute(
        """SELECT s.directory,
                  COUNT(*) as session_count,
                  MAX(s.time_updated) as last_active
           FROM session s
           GROUP BY s.directory
           ORDER BY last_active DESC"""
    ).fetchall()
    conn.close()

    dirs = []
    now = int(time.time()) * 1000
    one_day_ago = now - 86400 * 1000
    for r in rows:
        last_active = r["last_active"] or 0
        dirs.append({
            "path": r["directory"],
            "name": get_project_name(r["directory"]),
            "session_count": r["session_count"],
            "last_active": format_time(last_active),
            "recently_active": last_active > one_day_ago,
        })

    return jsonify({"directories": dirs})


@app.route("/api/workspace/projects")
def api_workspace_projects():
    """Return project-level workspace summaries."""
    limit = _bounded_int_arg("limit", 50, minimum=1, maximum=200)
    conn = get_db()
    projects = fetch_project_workspaces(conn, limit=limit)
    conn.close()

    return jsonify({
        "projects": [
            {
                "path": item["row"]["directory"],
                "name": get_project_name(item["row"]["directory"]),
                "session_count": item["row"]["session_count"] or 0,
                "message_count": item["row"]["message_count"] or 0,
                "first_active_raw": item["row"]["first_active"] or 0,
                "last_active_raw": item["row"]["last_active"] or 0,
                "last_active": format_time(item["row"]["last_active"]),
                "cost": round(item["row"]["cost"] or 0, 6),
                "tokens_input": item["row"]["tokens_input"] or 0,
                "tokens_output": item["row"]["tokens_output"] or 0,
                "top_models": [
                    {
                        "model": format_model(model_row["model"]),
                        "count": model_row["count"] or 0,
                    }
                    for model_row in item["top_models"]
                ],
                "recent_sessions": [
                    {
                        "id": session_row["id"],
                        "title": session_row["title"],
                        "model": format_model(session_row["model"]),
                        "time_updated": format_time(session_row["time_updated"]),
                        "time_updated_raw": session_row["time_updated"] or 0,
                    }
                    for session_row in item["recent_sessions"]
                ],
            }
            for item in projects
        ],
        "total": len(projects),
    })


@app.route("/api/workspace/tasks", methods=["GET"])
def api_workspace_tasks():
    project_path = request.args.get("project_path", "").strip()
    status = request.args.get("status", "").strip()
    conn = get_workspace_db()
    try:
        tasks = fetch_tasks(conn, project_path=project_path, status=status)
    except ValueError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400
    conn.close()

    return jsonify({
        "tasks": tasks,
        "statuses": sorted(TASK_STATUSES),
        "total": len(tasks),
    })


@app.route("/api/workspace/tasks", methods=["POST"])
def api_workspace_task_create():
    payload = request.get_json(silent=True) or {}
    conn = get_workspace_db()
    try:
        task = create_task(
            conn,
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            project_path=payload.get("project_path", ""),
            status=payload.get("status", "todo"),
            linked_session_ids=payload.get("linked_session_ids"),
        )
    except ValueError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400
    conn.close()
    return jsonify({"task": task}), 201


@app.route("/api/workspace/tasks/<task_id>", methods=["PATCH"])
def api_workspace_task_update(task_id):
    payload = request.get_json(silent=True) or {}
    conn = get_workspace_db()
    try:
        task = update_task(conn, task_id, payload)
    except ValueError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400
    conn.close()
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"task": task})


@app.route("/api/workspace/tasks/<task_id>/report", methods=["GET"])
def api_workspace_task_report(task_id):
    workspace_conn = get_workspace_db()
    task = get_task(workspace_conn, task_id)
    if not task:
        workspace_conn.close()
        return jsonify({"error": "任务不存在"}), 404
    command_runs = fetch_command_runs(workspace_conn, task_id=task_id, limit=10)
    linked_sessions = _fetch_linked_sessions(task["linked_session_ids"])
    git_snapshot = _read_task_git_snapshot(task)
    record_task_event(
        workspace_conn,
        task_id=task_id,
        event_type="task_report_generated",
        title="Task report generated",
        payload={"git": git_snapshot},
    )
    task_events = fetch_task_events(workspace_conn, task_id, limit=25)
    workspace_conn.close()

    markdown = build_task_report(
        task=task,
        linked_sessions=linked_sessions,
        command_runs=command_runs,
        git_snapshot=git_snapshot,
        task_events=task_events,
    )
    return jsonify({
        "report": {
            "task": task,
            "linked_sessions": linked_sessions,
            "command_runs": command_runs,
            "events": task_events,
            "git": git_snapshot,
            "markdown": markdown,
        }
    })


@app.route("/api/workspace/tasks/<task_id>/events", methods=["GET"])
def api_workspace_task_events(task_id):
    limit = _bounded_int_arg("limit", 50, minimum=1, maximum=100)
    conn = get_workspace_db()
    task = get_task(conn, task_id)
    if not task:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404
    events = fetch_task_events(conn, task_id, limit=limit)
    conn.close()
    return jsonify({"events": events, "total": len(events)})


def _fetch_linked_sessions(session_ids):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = get_db()
    model_expr = "model" if has_table_column(conn, "session", "model") else "NULL"
    rows = conn.execute(
        f"""SELECT id, title, directory, {model_expr} AS model, time_updated
            FROM session
            WHERE id IN ({placeholders})""",
        session_ids,
    ).fetchall()
    conn.close()
    by_id = {row["id"]: row for row in rows}
    return [
        {
            "id": session_id,
            "title": by_id[session_id]["title"] if session_id in by_id else "",
            "directory": by_id[session_id]["directory"] if session_id in by_id else "",
            "model": format_model(by_id[session_id]["model"]) if session_id in by_id else "",
            "time_updated": format_time(by_id[session_id]["time_updated"]) if session_id in by_id else "",
            "time_updated_raw": by_id[session_id]["time_updated"] if session_id in by_id else 0,
        }
        for session_id in session_ids
    ]


def _workspace_task_exists(task_id):
    if not task_id:
        return True
    conn = get_workspace_db()
    try:
        return get_task(conn, task_id) is not None
    finally:
        conn.close()


def _read_task_git_snapshot(task):
    if not task or not task.get("project_path"):
        return None
    try:
        return read_git_snapshot(task["project_path"]).to_dict()
    except Exception as exc:
        return {"is_git_repo": False, "error": str(exc)}


def _link_workspace_task_session(task_id, session_id, source="opencode"):
    if not task_id or not session_id:
        return False
    conn = get_workspace_db()
    try:
        task = get_task(conn, task_id)
        if not task:
            return False
        linked_ids = list(task["linked_session_ids"])
        if session_id not in linked_ids:
            linked_ids.append(session_id)
            update_task(conn, task_id, {"linked_session_ids": linked_ids})
        source_labels = {
            "continue": "OpenCode continue completed",
            "new": "OpenCode new session completed",
            "fork": "OpenCode fork completed",
        }
        record_task_event(
            conn,
            task_id=task_id,
            event_type="opencode_session_linked",
            title=source_labels.get(source, "OpenCode session linked"),
            payload={
                "session_id": session_id,
                "source": source,
                "git": _read_task_git_snapshot(task),
            },
        )
        return True
    finally:
        conn.close()


@app.route("/api/workspace/git")
def api_workspace_git():
    project_path = request.args.get("project_path", "").strip()
    if not project_path:
        return jsonify({"error": "project_path 参数不能为空"}), 400
    try:
        snapshot = read_git_snapshot(project_path)
    except FileNotFoundError as exc:
        if str(exc) == "项目目录不存在":
            return jsonify({"error": str(exc)}), 404
        return jsonify({"error": "git CLI 未找到"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "读取 Git 状态超时"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"git": snapshot.to_dict()})


@app.route("/api/workspace/commands")
def api_workspace_commands():
    try:
        commands = parse_workspace_commands(app.config.get("OPENCODE_WORKSPACE_COMMANDS", []))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"commands": [command.to_public_dict() for command in commands]})


@app.route("/api/workspace/command-runs", methods=["GET"])
def api_workspace_command_runs():
    project_path = request.args.get("project_path", "").strip()
    task_id = request.args.get("task_id", "").strip()
    limit = _bounded_int_arg("limit", 20, minimum=1, maximum=100)
    conn = get_workspace_db()
    runs = fetch_command_runs(conn, project_path=project_path, task_id=task_id, limit=limit)
    conn.close()
    return jsonify({"runs": runs, "total": len(runs)})


@app.route("/api/workspace/command-runs", methods=["POST"])
def api_workspace_command_run_create():
    payload = request.get_json(silent=True) or {}
    project_path = str(payload.get("project_path") or "").strip()
    command_key = str(payload.get("command_key") or "").strip()
    task_id = str(payload.get("task_id") or "").strip()
    if not project_path:
        return jsonify({"error": "project_path 参数不能为空"}), 400
    if not command_key:
        return jsonify({"error": "command_key 参数不能为空"}), 400

    try:
        commands = parse_workspace_commands(app.config.get("OPENCODE_WORKSPACE_COMMANDS", []))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    command = find_workspace_command(commands, command_key)
    if not command:
        return jsonify({"error": "命令不在白名单中"}), 400

    try:
        result = run_workspace_command(
            command,
            project_path=project_path,
            process_manager=process_manager,
            timeout=int(app.config.get("OPENCODE_WORKSPACE_COMMAND_TIMEOUT", 120)),
        )
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    run = _record_workspace_command_execution(
        project_path=project_path,
        task_id=task_id,
        command=command,
        result=result,
    )
    status_code = 201 if result.status == "success" else 200
    return jsonify({"run": run}), status_code


@app.route("/api/workspace/command-runs/stream", methods=["POST"])
def api_workspace_command_run_stream():
    payload = request.get_json(silent=True) or {}
    project_path = str(payload.get("project_path") or "").strip()
    command_key = str(payload.get("command_key") or "").strip()
    task_id = str(payload.get("task_id") or "").strip()
    if not project_path:
        return jsonify({"error": "project_path 参数不能为空"}), 400
    if not command_key:
        return jsonify({"error": "command_key 参数不能为空"}), 400

    try:
        commands = parse_workspace_commands(app.config.get("OPENCODE_WORKSPACE_COMMANDS", []))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500

    command = find_workspace_command(commands, command_key)
    if not command:
        return jsonify({"error": "命令不在白名单中"}), 400

    try:
        project_root = os.path.abspath(os.path.expanduser(project_path))
        if not os.path.isdir(project_root):
            return jsonify({"error": "项目目录不存在"}), 404
        command_cwd = resolve_workspace_command_cwd(project_root, command.cwd)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    timeout = int(app.config.get("OPENCODE_WORKSPACE_COMMAND_TIMEOUT", 120))

    def generate():
        started_at = int(time.time() * 1000)
        start = time.monotonic()
        proc = None
        output_parts = []
        stdout_thread = None
        output_queue = queue.Queue()

        try:
            yield sse.json_event(
                "started",
                {
                    "command_key": command.key,
                    "command_label": command.label,
                    "cwd": command_cwd,
                    "started_at": started_at,
                },
            )
            proc = process_manager.start(
                command.argv,
                cwd=command_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
            )

            def read_output():
                for line in proc.stdout:
                    output_queue.put(line)
                output_queue.put(None)

            stdout_thread = threading.Thread(target=read_output, daemon=True)
            stdout_thread.start()
            timed_out = False
            while True:
                try:
                    line = output_queue.get(timeout=1)
                except queue.Empty:
                    if time.monotonic() - start > timeout:
                        timed_out = True
                        process_manager.terminate(proc, timeout=2)
                        break
                    yield sse.status("running")
                    continue
                if line is None:
                    break
                output_parts.append(line)
                yield sse.event("output", line.rstrip("\n"))

            exit_code = None
            if timed_out:
                status = "timeout"
            else:
                proc.wait(timeout=timeout)
                exit_code = proc.returncode
                status = "success" if exit_code == 0 else "failed"
            finished_at = int(time.time() * 1000)
            result = CommandExecution(
                status=status,
                exit_code=exit_code,
                output=truncate_command_output("".join(output_parts), 20000),
                duration_ms=int((time.monotonic() - start) * 1000),
                started_at=started_at,
                finished_at=finished_at,
                cwd=command_cwd,
            )
            run = _record_workspace_command_execution(
                project_path=project_path,
                task_id=task_id,
                command=command,
                result=result,
            )
            yield sse.done({"run": run})
        except FileNotFoundError as exc:
            yield sse.stream_error(str(exc))
        except Exception as exc:
            yield sse.stream_error(str(exc))
        finally:
            if proc:
                process_manager.unregister(proc)
            if stdout_thread:
                stdout_thread.join(timeout=2)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Connection": "keep-alive", "Cache-Control": "no-cache"},
    )


def _record_workspace_command_execution(*, project_path, task_id, command, result):
    conn = get_workspace_db()
    try:
        run = record_command_run(
            conn,
            project_path=project_path,
            task_id=task_id,
            command_key=command.key,
            command_label=command.label,
            command_argv=command.argv,
            cwd=result.cwd,
            status=result.status,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            output=result.output,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
        if task_id:
            task = get_task(conn, task_id)
            if task:
                record_task_event(
                    conn,
                    task_id=task_id,
                    event_type="validation_run_completed",
                    title=f"Validation {command.label} {result.status}",
                    payload={
                        "run_id": run["id"],
                        "command_key": command.key,
                        "command_label": command.label,
                        "status": result.status,
                        "exit_code": result.exit_code,
                        "duration_ms": result.duration_ms,
                        "git": _read_task_git_snapshot(task),
                    },
                )
        return run
    finally:
        conn.close()


@app.route("/api/models")
def api_models():
    """获取所有用过的模型"""
    conn = get_db()
    cursor = conn.cursor()

    if has_table_column(conn, "session", "model"):
        rows = cursor.execute(
            """SELECT model, COUNT(*) as cnt
               FROM session
               WHERE model IS NOT NULL AND model != ''
               GROUP BY model
               ORDER BY cnt DESC"""
        ).fetchall()
    else:
        rows = []
    conn.close()

    return jsonify({"models": [{"name": format_model(r["model"]), "count": r["cnt"]} for r in rows]})


@app.route("/api/available-models")
def api_available_models():
    """获取所有可用模型列表（来自 opencode CLI）"""
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=30,
        )
        models = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return jsonify({"models": models})
    except FileNotFoundError:
        return jsonify({"error": "opencode CLI 未找到"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "获取模型列表超时"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 删除会话 ──────────────────────────────────────────


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_session_delete(session_id):
    """删\u9664会话及其所有消息和 part"""
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT id FROM session WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "会话不存在"}), 404
    cursor.execute("DELETE FROM part WHERE message_id IN (SELECT id FROM message WHERE session_id = ?)", (session_id,))
    cursor.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM session WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


# ── Phase 2: 子进程辅助函数 ─────────────────────────────


def run_opencode_stream(cmd, session_id, timeout=600):
    """运行 opencode CLI 子进程，产生 SSE 事件。

    同时读取 stdout 和 stderr。
    - stdout 中的 JSON 事件 → 转换为 SSE event（text/thinking/done）
    - stderr 中的内容 → 如果没有 stdout 输出则作为 error 事件发送
    - 进程异常退出时发送 stderr 内容
    """
    logger.debug("run_opencode_stream called cmd=%s", cmd)
    proc = process_manager.start(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # stderr 独立管道，Node.js 会立即刷新
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    logger.debug("opencode process started pid=%s", proc.pid)

    def terminate_stream_process():
        process_manager.terminate(proc, timeout=2)

    # 收集 stderr 的线程（stderr 无缓冲，Node 的 console.error 立即到达）
    stderr_lines = []
    stderr_lock = threading.Lock()
    def read_stderr():
        for line in proc.stderr:
            line = line.strip()
            if line:
                with stderr_lock:
                    stderr_lines.append(line)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    # 用队列实现带超时的 stdout 读取
    stdout_queue = queue.Queue()
    def read_stdout():
        for line in proc.stdout:
            stdout_queue.put(line)
        stdout_queue.put(None)
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stdout_thread.start()

    has_json_output = False
    last_output_time = time.time()
    loop_count = 0
    try:
        while True:
            loop_count += 1
            try:
                line = stdout_queue.get(timeout=5)
            except queue.Empty:
                elapsed = int(time.time() - last_output_time)
                # 每 5 秒无 stdout 输出时，检查 stderr
                with stderr_lock:
                    recent_stderr = list(stderr_lines[-10:])
                    stderr_count = len(stderr_lines)
                logger.debug(
                    "stream timeout check loop=%s has_json=%s stderr_count=%s elapsed=%ss proc_alive=%s",
                    loop_count,
                    has_json_output,
                    stderr_count,
                    elapsed,
                    proc.poll() is None,
                )
                if recent_stderr:
                    combined = "\n".join(recent_stderr)
                    has_known_error = is_known_error_text(combined)
                    logger.debug("recent stderr: %s", recent_stderr[-1][:200])
                    if has_known_error:
                        terminate_stream_process()
                        err_text = "\n".join(recent_stderr[-5:])
                        yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))
                        return
                    if not has_json_output:
                        terminate_stream_process()
                        err_text = "\n".join(recent_stderr[-5:])
                        yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))
                        return
                # 无任何输出超过 25 秒，终止（比前端 30 秒超时早）
                if elapsed > 25:
                    terminate_stream_process()
                    err_msg = "模型无响应（可能已达到使用限制），请切换模型后重试"
                    logger.warning("killing opencode process after %ss of silence", elapsed)
                    yield sse.stream_error(err_msg)
                    return
                # 发送状态事件，防止前端 30 秒超时
                yield sse.status("waiting")
                continue
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                has_json_output = True
                last_output_time = time.time()
                event_type = event.get("type", "")

                sse_event = event_to_sse(event, session_id=session_id, done_on_stop_only=True)
                if sse_event:
                    if "stream_error" in sse_event:
                        logger.warning("opencode stream error detected: %s", line[:200])
                        terminate_stream_process()
                        yield sse_event
                        return
                    yield sse_event
                elif event_type and event_type not in ("step_start", "step_finish"):
                    logger.debug("unknown opencode event_type=%s data=%s", event_type, line[:200])
            except json.JSONDecodeError:
                # 非 JSON 行 — 可能是错误信息（限流、模型不可用等）
                non_json = line.strip()
                logger.debug("non-json opencode stdout: %s", non_json[:200])
                if non_json and len(non_json) > 5:
                    if is_known_error_text(non_json):
                        terminate_stream_process()
                        yield sse.stream_error(safe_truncate(format_stream_error_message(non_json)))
                        return

        proc.wait(timeout=timeout)

        # stdout 关闭后，检查 stderr 是否有错误
        with stderr_lock:
            recent_stderr = list(stderr_lines[-10:])
        if recent_stderr:
            err_text = "\n".join(recent_stderr)
            yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))

    except GeneratorExit:
        process_manager.terminate(proc, timeout=5)
    except subprocess.TimeoutExpired:
        terminate_stream_process()
        yield sse.stream_error("请求超时")
    finally:
        process_manager.unregister(proc)
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)


# ── Phase 2: SSE 流式输出 ──────────────────────────────

@app.after_request
def add_cors_headers(response):
    """为 SSE 端点添加 CORS 和缓存控制头"""
    response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.route("/api/sessions/<session_id>/stream")
def api_session_stream(session_id):
    """SSE 流式继续对话

    从 DB 读取会话的工作目录，调用
    `opencode run --dir <directory> -s <session_id> <message> --format json`
    将 JSON 事件流转换为 SSE 事件推送到前端。
    """
    message = request.args.get("message", "").strip()
    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    model = request.args.get("model", "").strip()
    task_id = request.args.get("task_id", "").strip()
    if task_id and not _workspace_task_exists(task_id):
        return jsonify({"error": "任务不存在"}), 404

    # 从 DB 读取会话信息，获取工作目录
    conn = get_db()
    row = conn.execute("SELECT directory FROM session WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "会话不存在"}), 404

    directory = row["directory"]

    def generate():
        had_error = False
        try:
            cmd = [
                "opencode", "run",
                "--dir", directory,
                "-s", session_id,
                message,
                "--format", "json",
            ]
            if model:
                cmd.insert(2, "-m")
                cmd.insert(3, model)
            for event in run_opencode_stream(cmd, session_id):
                if "stream_error" in event:
                    had_error = True
                yield event
        except FileNotFoundError:
            had_error = True
            yield sse.stream_error("opencode CLI 未找到，请确认已安装 opencode")
        except Exception as e:
            had_error = True
            yield sse.stream_error(str(e))
        finally:
            if not had_error:
                _link_workspace_task_session(task_id, session_id, source="continue")
                yield sse.done({"session_id": session_id, "task_id": task_id})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        },
    )


# ── Phase 2: 新建会话 ──────────────────────────────────


@app.route("/api/sessions/new", methods=["POST"])
def api_session_new():
    """新建会话 — SSE 流式返回

    调用 `opencode run --dir <directory> <message> --format json`
    从 JSON 事件流中提取新 sessionID，转换为 SSE 事件推送到前端。
    """
    data = request.get_json(silent=True) or {}
    directory = (data.get("directory") or "").strip()
    message = (data.get("message") or "").strip()
    model = (data.get("model") or "").strip()
    task_id = (data.get("task_id") or "").strip()

    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    if not directory or not os.path.isdir(directory):
        return jsonify({"error": "无效的工作目录"}), 400
    if task_id and not _workspace_task_exists(task_id):
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        new_session_id = None
        had_error = False
        proc = None
        stderr_thread2 = None
        stdout_thread2 = None
        try:
            cmd = [
                "opencode", "run",
                "--dir", directory,
                message,
                "--format", "json",
            ]
            if model:
                cmd.insert(2, "-m")
                cmd.insert(3, model)

            proc = process_manager.start(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL,
            )

            def terminate_new_session_process():
                if proc:
                    process_manager.terminate(proc, timeout=2)

            # stderr 收集线程
            stderr_lines = []
            stderr_lock2 = threading.Lock()
            def read_stderr2():
                for line in proc.stderr:
                    line = line.strip()
                    if line:
                        with stderr_lock2:
                            stderr_lines.append(line)
            stderr_thread2 = threading.Thread(target=read_stderr2, daemon=True)
            stderr_thread2.start()

            # 用队列实现带超时的 stdout 读取
            stdout_queue2 = queue.Queue()
            def read_stdout2():
                for line in proc.stdout:
                    stdout_queue2.put(line)
                stdout_queue2.put(None)
            stdout_thread2 = threading.Thread(target=read_stdout2, daemon=True)
            stdout_thread2.start()

            new_session_id = None
            has_output = False
            last_output_time = time.time()
            while True:
                try:
                    line = stdout_queue2.get(timeout=5)
                except queue.Empty:
                    with stderr_lock2:
                        recent_stderr = list(stderr_lines[-10:])
                    if recent_stderr:
                        combined = "\n".join(recent_stderr)
                        if is_known_error_text(combined) or not has_output:
                            terminate_new_session_process()
                            err_text = "\n".join(recent_stderr[-5:])
                            had_error = True
                            yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))
                            return
                    # 无任何输出超过 25 秒，终止
                    elapsed = int(time.time() - last_output_time)
                    if elapsed > 25:
                        terminate_new_session_process()
                        had_error = True
                        yield sse.stream_error("模型无响应（可能已达到使用限制），请切换模型后重试")
                        return
                    # 发送状态事件，防止前端 30 秒超时
                    yield sse.status("waiting")
                    continue
                if line is None:
                    break
                has_output = True
                last_output_time = time.time()
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    # 捕获新 session ID
                    if not new_session_id and "sessionID" in ev:
                        new_session_id = ev["sessionID"]

                    ev_type = ev.get("type", "")
                    sse_event = event_to_sse(ev, session_id=new_session_id or "", done_on_stop_only=False)
                    if sse_event:
                        if "stream_error" in sse_event:
                            logger.warning("new-session stream error detected: %s", line[:200])
                            terminate_new_session_process()
                            had_error = True
                            yield sse_event
                            return
                        yield sse_event
                    elif ev_type and ev_type not in ("step_start", "step_finish"):
                        logger.debug("new-session unknown event_type=%s data=%s", ev_type, line[:200])
                except json.JSONDecodeError:
                    non_json = line.strip()
                    logger.debug("new-session non-json stdout: %s", non_json[:200])
                    if non_json and len(non_json) > 5:
                        if is_known_error_text(non_json):
                            terminate_new_session_process()
                            had_error = True
                            yield sse.stream_error(safe_truncate(format_stream_error_message(non_json)))
                            return

            proc.wait(timeout=600)

            # stdout 关闭后，检查 stderr 是否有错误（限流/异常退出等）
            with stderr_lock2:
                recent_stderr = list(stderr_lines[-10:])
            if recent_stderr:
                err_text = "\n".join(recent_stderr)
                had_error = True
                yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))

            stderr_thread2.join(timeout=2)

        except FileNotFoundError:
            had_error = True
            yield sse.stream_error("opencode CLI 未找到，请确认已安装 opencode")
        except subprocess.TimeoutExpired:
            had_error = True
            if proc:
                process_manager.terminate(proc, timeout=2)
            yield sse.stream_error("请求超时")
        except Exception as e:
            had_error = True
            yield sse.stream_error(str(e))
        finally:
            if proc:
                process_manager.unregister(proc)
            if stdout_thread2:
                stdout_thread2.join(timeout=2)
            if stderr_thread2:
                stderr_thread2.join(timeout=2)
            if not had_error:
                if new_session_id:
                    _link_workspace_task_session(task_id, new_session_id, source="new")
                yield sse.done({"session_id": new_session_id or "", "task_id": task_id})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        },
    )


# ── Phase 2: 文件浏览 ──────────────────────────────────


@app.route("/api/files")
def api_files():
    """列出指定目录的文件和子目录"""
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path 参数不能为空"}), 400

    # 安全检查：拒绝路径遍历
    norm = os.path.normpath(path)
    if not os.path.isdir(norm):
        return jsonify({"error": "目录不存在"}), 404

    try:
        entries = []
        with os.scandir(norm) as it:
            for entry in sorted(it, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower())):
                is_dir = entry.is_dir(follow_symlinks=False)
                stat = entry.stat(follow_symlinks=False)
                # 跳过隐藏文件/目录（以 . 开头）
                if entry.name.startswith("."):
                    continue
                entries.append({
                    "name": entry.name,
                    "type": "dir" if is_dir else "file",
                    "size": stat.st_size if not is_dir else 0,
                    "mtime": int(stat.st_mtime),
                })
        return jsonify({"path": norm, "entries": entries})
    except PermissionError:
        return jsonify({"error": "无权限访问该目录"}), 403
    except OSError as e:
        return jsonify({"error": str(e)}), 500


# ── Phase 2.1: 实时同步事件 ──────────────────────────────


@app.route("/api/events")
def api_events():
    """Broadcast lightweight database changes over SSE."""
    interval_ms = _bounded_int_arg("interval_ms", 1000, minimum=0, maximum=30000)
    max_polls_arg = request.args.get("max_polls")
    max_polls = None
    if max_polls_arg is not None:
        max_polls = _bounded_int_arg("max_polls", 1, minimum=1, maximum=1000)

    def generate():
        conn = get_db()
        try:
            previous = fetch_session_snapshots(conn)
        finally:
            conn.close()

        poll_count = 0
        while max_polls is None or poll_count < max_polls:
            conn = get_db()
            try:
                current = fetch_session_snapshots(conn)
            finally:
                conn.close()

            changes = diff_session_snapshots(previous, current)
            if changes:
                for change in changes:
                    yield sse.json_event("session_change", change.to_dict())
                previous = current
            else:
                yield sse.json_event("heartbeat", {"sessions": len(current)})

            poll_count += 1
            if max_polls is not None and poll_count >= max_polls:
                break
            if interval_ms > 0:
                time.sleep(interval_ms / 1000)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Connection": "keep-alive", "Cache-Control": "no-cache"},
    )


def _bounded_int_arg(name, default, *, minimum, maximum):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


# ── Phase 3: 统计图表数据 ──────────────────────────────


@app.route("/api/stats/tokens")
def api_stats_tokens():
    """Token 消耗统计（按天/模型/项目）"""
    conn = get_db()
    thirty_days_ago = (int(time.time()) - 30 * 86400) * 1000
    daily, by_model, by_project, total_cost_all = fetch_token_stats(conn, since_ms=thirty_days_ago)
    conn.close()

    return jsonify({
        "daily": [{"day": r["day"], "input": r["inp"] or 0, "output": r["out"] or 0} for r in daily],
        "by_model": [{
            "model": format_model(r["model"]),
            "input": r["inp"] or 0,
            "output": r["out"] or 0,
            "cost": round(r["cst"] or 0, 6),
        } for r in by_model],
        "by_project": [{
            "project": get_project_name(r["directory"]),
            "input": r["inp"] or 0,
            "output": r["out"] or 0,
            "sessions": r["cnt"],
        } for r in by_project],
        "total_cost": round(total_cost_all, 6),
    })


# ── Phase 3: 会话分支（Fork） ───────────────────────────


@app.route("/api/sessions/<session_id>/fork", methods=["POST"])
def api_session_fork(session_id):
    """分叉（fork）已有会话 — 创建分支后继续对话

    调用 `opencode run --fork -s <session_id> <message> --format json`
    从事件流中提取新 sessionID，通过 SSE 返回。
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    model = (data.get("model") or "").strip()
    task_id = (data.get("task_id") or "").strip()

    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    if task_id and not _workspace_task_exists(task_id):
        return jsonify({"error": "任务不存在"}), 404

    # 读取原会话的工作目录
    conn = get_db()
    row = conn.execute("SELECT directory FROM session WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "会话不存在"}), 404
    directory = row["directory"]

    def generate():
        new_session_id = None
        had_error = False
        proc = None
        stderr_thread = None
        stdout_thread3 = None
        try:
            cmd = [
                "opencode", "run",
                "--dir", directory,
                "--fork", "-s", session_id,
                message,
                "--format", "json",
            ]
            if model:
                cmd.insert(2, "-m")
                cmd.insert(3, model)

            proc = process_manager.start(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL,
            )

            def terminate_fork_process():
                if proc:
                    process_manager.terminate(proc, timeout=2)

            stderr_lines = []
            stderr_lock3 = threading.Lock()
            def rs():
                for line in proc.stderr:
                    line = line.strip()
                    if line:
                        with stderr_lock3:
                            stderr_lines.append(line)
            stderr_thread = threading.Thread(target=rs, daemon=True)
            stderr_thread.start()

            stdout_queue3 = queue.Queue()
            def read_stdout3():
                for line in proc.stdout:
                    stdout_queue3.put(line)
                stdout_queue3.put(None)
            stdout_thread3 = threading.Thread(target=read_stdout3, daemon=True)
            stdout_thread3.start()

            has_output = False
            last_output_time = time.time()
            while True:
                try:
                    line = stdout_queue3.get(timeout=5)
                except queue.Empty:
                    with stderr_lock3:
                        recent_stderr = list(stderr_lines[-10:])
                    if recent_stderr:
                        combined = "\n".join(recent_stderr)
                        if is_known_error_text(combined) or not has_output:
                            terminate_fork_process()
                            err_text = "\n".join(recent_stderr[-5:])
                            had_error = True
                            yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))
                            return
                    if has_output and (time.time() - last_output_time > 120):
                        terminate_fork_process()
                        had_error = True
                        yield sse.stream_error("请求超时（120 秒无输出）")
                        return
                    continue
                if line is None:
                    break
                has_output = True
                last_output_time = time.time()
                line = line.strip()
                if not line: continue
                try:
                    ev = json.loads(line)
                    if not new_session_id and "sessionID" in ev:
                        new_session_id = ev["sessionID"]
                    ev_type = ev.get("type", "")
                    sse_event = event_to_sse(ev, session_id=new_session_id or "", done_on_stop_only=False)
                    if sse_event:
                        if "stream_error" in sse_event:
                            logger.warning("fork-session stream error detected: %s", line[:200])
                            terminate_fork_process()
                            had_error = True
                            yield sse_event
                            return
                        yield sse_event
                    elif ev_type and ev_type not in ("step_start", "step_finish"):
                        logger.debug("fork-session unknown event_type=%s data=%s", ev_type, line[:200])
                except json.JSONDecodeError:
                    non_json = line.strip()
                    if non_json and len(non_json) > 5:
                        if is_known_error_text(non_json):
                            terminate_fork_process()
                            had_error = True
                            yield sse.stream_error(safe_truncate(format_stream_error_message(non_json)))
                            return

            proc.wait(timeout=600)
            # stdout 关闭后，检查 stderr
            with stderr_lock3:
                recent_stderr = list(stderr_lines[-10:])
            if recent_stderr:
                err_text = "\n".join(recent_stderr)
                had_error = True
                yield sse.stream_error(safe_truncate(format_stream_error_message(err_text)))
            stderr_thread.join(timeout=2)

        except FileNotFoundError:
            had_error = True
            yield sse.stream_error("opencode CLI 未找到")
        except subprocess.TimeoutExpired:
            had_error = True
            if proc:
                process_manager.terminate(proc, timeout=2)
            yield sse.stream_error("请求超时")
        except Exception as e:
            had_error = True
            yield sse.stream_error(str(e))
        finally:
            if proc:
                process_manager.unregister(proc)
            if stdout_thread3:
                stdout_thread3.join(timeout=2)
            if stderr_thread:
                stderr_thread.join(timeout=2)
            if not had_error:
                if new_session_id:
                    _link_workspace_task_session(task_id, new_session_id, source="fork")
                yield sse.done({"session_id": new_session_id or "", "task_id": task_id})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Connection": "keep-alive", "Cache-Control": "no-cache"},
    )


# ── Phase 3: Undo ──────────────────────────────────────


@app.route("/api/sessions/<session_id>/undo", methods=["POST"])
def api_session_undo(session_id):
    """撤销最后一次用户消息及其后的所有 AI 回复"""
    conn = get_db()
    cursor = conn.cursor()

    # 找到最后一个 user 角色的消息（用 LIKE 兼容低版本 SQLite）
    last_user = cursor.execute(
        """SELECT id, time_created FROM message
           WHERE session_id = ? AND data LIKE '%"role":"user"%'
           ORDER BY time_created DESC LIMIT 1""",
        (session_id,),
    ).fetchone()

    if not last_user:
        conn.close()
        return jsonify({"error": "没有可撤销的消息"}), 400

    last_user_id = last_user["id"]

    # 删除此消息及之后的所有消息的 part
    cursor.execute(
        """DELETE FROM part WHERE message_id IN (
            SELECT id FROM message WHERE session_id = ? AND time_created >= (
                SELECT time_created FROM message WHERE id = ?
            )
        )""",
        (session_id, last_user_id),
    )
    # 删除消息
    cursor.execute(
        "DELETE FROM message WHERE session_id = ? AND time_created >= (SELECT time_created FROM message WHERE id = ?)",
        (session_id, last_user_id),
    )

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": f"已撤销到 {last_user_id}"})


# ── 前端页面 ──────────────────────────────────────────────

@app.route("/")
def index():
    if should_serve_frontend_dist():
        return send_from_directory(app.config["OPENCODE_FRONTEND_DIST_DIR"], "index.html")

    static_dir = os.path.join(app.root_path, "static")
    asset_paths = [
        os.path.join(static_dir, "css", "main.css"),
        os.path.join(static_dir, "js", "app.js"),
    ]
    asset_version = int(max(os.path.getmtime(path) for path in asset_paths if os.path.exists(path)))
    return render_template("index.html", asset_version=asset_version)


@app.route("/frontend/assets/<path:filename>")
def frontend_dist_asset(filename):
    if not should_serve_frontend_dist():
        abort(404)
    return send_from_directory(
        os.path.join(app.config["OPENCODE_FRONTEND_DIST_DIR"], "assets"),
        filename,
    )


def should_serve_frontend_dist():
    return (
        bool(app.config.get("OPENCODE_USE_FRONTEND_DIST"))
        and os.path.isfile(os.path.join(app.config["OPENCODE_FRONTEND_DIST_DIR"], "index.html"))
    )


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    flask_app = create_app()
    db_path = flask_app.config["OPENCODE_DB_PATH"]

    if not os.path.isfile(db_path):
        logger.error("database not found: %s", db_path)
        logger.error("please run OpenCode first and ensure session records exist")
        sys.exit(1)

    logger.info("OpenCode session viewer starting")
    logger.info("database: %s", db_path)
    logger.info("url: http://127.0.0.1:%s", port)

    flask_app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
