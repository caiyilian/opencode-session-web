"""
OpenCode 会话 Web 查看器 — Flask 后端

读取本地的 opencode.db SQLite 数据库，提供 REST API。
"""

import json
import os
import subprocess
import sqlite3
from pathlib import Path
from flask import Flask, jsonify, request, render_template, Response, stream_with_context

app = Flask(__name__)

# ── 数据库路径 ──────────────────────────────────────────────

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def get_db():
    """获取数据库连接（每次请求独立，避免线程问题）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── 工具函数 ──────────────────────────────────────────────

def dict_from_row(row):
    """将 sqlite3.Row 转为 dict"""
    if row is None:
        return None
    return dict(row)


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
    cursor = conn.cursor()

    total_sessions = cursor.execute("SELECT COUNT(*) FROM session").fetchone()[0]
    total_projects = cursor.execute("SELECT COUNT(DISTINCT directory) FROM session").fetchone()[0]
    total_cost = cursor.execute("SELECT COALESCE(SUM(cost), 0) FROM session").fetchone()[0]
    total_tokens_input = cursor.execute("SELECT COALESCE(SUM(tokens_input), 0) FROM session").fetchone()[0]
    total_tokens_output = cursor.execute("SELECT COALESCE(SUM(tokens_output), 0) FROM session").fetchone()[0]

    # Top 目录
    dirs = cursor.execute(
        "SELECT directory, COUNT(*) as cnt FROM session GROUP BY directory ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    # Top 模型
    models = cursor.execute(
        "SELECT model, COUNT(*) as cnt FROM session WHERE model IS NOT NULL AND model != '' GROUP BY model ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    # 最近活动
    recent = cursor.execute(
        "SELECT id, title, directory, time_updated FROM session ORDER BY time_updated DESC LIMIT 5"
    ).fetchall()

    conn.close()

    return jsonify({
        "total_sessions": total_sessions,
        "total_projects": total_projects,
        "total_cost": round(total_cost, 6),
        "total_tokens_input": total_tokens_input,
        "total_tokens_output": total_tokens_output,
        "top_directories": [{"path": r["directory"], "count": r["cnt"]} for r in dirs],
        "top_models": [{"model": r["model"], "count": r["cnt"]} for r in models],
        "recent_sessions": [{
            "id": r["id"],
            "title": r["title"],
            "directory": r["directory"],
            "time_updated": format_time(r["time_updated"]),
        } for r in recent],
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
    cursor = conn.cursor()

    conditions = []
    params = []

    if q:
        conditions.append("(s.title LIKE ? OR s.directory LIKE ? OR s.id LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if directory:
        conditions.append("s.directory = ?")
        params.append(directory)
    if model:
        conditions.append("s.model = ?")
        params.append(model)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    # 总数
    total = cursor.execute(f"SELECT COUNT(*) FROM session s {where}", params).fetchone()[0]

    # 列表
    rows = cursor.execute(
        f"""SELECT s.id, s.title, s.directory, s.model, s.agent,
                   s.time_created, s.time_updated,
                   s.cost, s.tokens_input, s.tokens_output,
                   (SELECT COUNT(*) FROM message m WHERE m.session_id = s.id) as msg_count
            FROM session s
            {where}
            ORDER BY s.time_updated DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()

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


@app.route("/api/sessions/<session_id>")
def api_session_detail(session_id):
    """获取单个会话详情"""
    conn = get_db()
    cursor = conn.cursor()

    row = cursor.execute(
        "SELECT * FROM session WHERE id = ?", (session_id,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "会话不存在"}), 404

    session = dict_from_row(row)
    session["project"] = get_project_name(session["directory"])
    session["model"] = format_model(session.get("model"))
    session["agent"] = session.get("agent") or "N/A"
    session["time_created_fmt"] = format_time(session["time_created"])
    session["time_updated_fmt"] = format_time(session["time_updated"])

    # 获取消息（含内容）
    messages = cursor.execute(
        """SELECT m.id, m.time_created, m.data,
                  p.data as part_data
           FROM message m
           LEFT JOIN part p ON p.message_id = m.id
           WHERE m.session_id = ?
           ORDER BY m.time_created ASC, p.id ASC""",
        (session_id,)
    ).fetchall()

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
                msg_map[mid]["parts"].append(part)
            except (json.JSONDecodeError, TypeError):
                pass

    # 将 parts 渲染为文本
    msg_list = []
    for mid in sorted(msg_map.keys(), key=lambda x: msg_map[x]["time_created_raw"]):
        m = msg_map[mid]
        texts = []
        for p in m["parts"]:
            t = p.get("type", "")
            if t == "text":
                texts.append(p.get("text", ""))
            elif t == "reasoning":
                reasoning_text = p.get("text", "")
                if reasoning_text:
                    texts.append(f"[思考] {reasoning_text[:200]}{'...' if len(reasoning_text) > 200 else ''}")
            elif t == "tool":
                texts.append(f"[工具] {p.get('tool', p.get('state', {}).get('status', ''))}")
            elif t == "step-start":
                texts.append("---")
            elif t == "step-finish":
                reason = p.get("reason", "")
                tokens_info = p.get("tokens", {})
                if tokens_info:
                    texts.append(f"[步骤完成] {tokens_info.get('total', 0)} tokens")
        content = "\n".join(texts) if texts else ""

        msg_list.append({
            "id": m["id"],
            "role": m["role"],
            "content": content[:2000],
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
    cursor = conn.cursor()

    row = cursor.execute(
        "SELECT * FROM message WHERE id = ?", (message_id,)
    ).fetchone()
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
    for r in rows:
        dirs.append({
            "path": r["directory"],
            "name": get_project_name(r["directory"]),
            "session_count": r["session_count"],
            "last_active": format_time(r["last_active"]),
        })

    return jsonify({"directories": dirs})


@app.route("/api/models")
def api_models():
    """获取所有用过的模型"""
    conn = get_db()
    cursor = conn.cursor()

    rows = cursor.execute(
        """SELECT model, COUNT(*) as cnt
           FROM session
           WHERE model IS NOT NULL AND model != ''
           GROUP BY model
           ORDER BY cnt DESC"""
    ).fetchall()
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

    # 从 DB 读取会话信息，获取工作目录
    conn = get_db()
    row = conn.execute("SELECT directory FROM session WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "会话不存在"}), 404

    directory = row["directory"]

    def generate():
        proc = None
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
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
            )

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type", "")
                    part = event.get("part", {})

                    if event_type == "text":
                        text = part.get("text", "")
                        if text:
                            # SSE data 中不能包含换行符，替换为 \n 文本
                            safe_text = text.replace("\n", "\\n")
                            yield f"event: text\ndata: {safe_text}\n\n"

                    elif event_type == "reasoning" or part.get("type") == "reasoning":
                        text = part.get("text", event.get("text", ""))
                        if text:
                            safe_text = text.replace("\n", "\\n")
                            yield f"event: thinking\ndata: {safe_text}\n\n"

                    elif event_type == "step_finish":
                        tokens = part.get("tokens", {})
                        result = json.dumps({
                            "session_id": session_id,
                            "tokens": tokens,
                            "cost": part.get("cost", 0),
                        })
                        yield f"event: done\ndata: {result}\n\n"

                except json.JSONDecodeError:
                    pass

            # 等待子进程结束
            if proc:
                proc.wait(timeout=600)

        except FileNotFoundError:
            yield f"event: error\ndata: opencode CLI 未找到，请确认已安装 opencode\n\n"
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            yield "event: error\ndata: 请求超时\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        finally:
            # 确保最终发送 done 事件
            yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"

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

    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    if not directory or not os.path.isdir(directory):
        return jsonify({"error": "无效的工作目录"}), 400

    def generate():
        proc = None
        new_session_id = None
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
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
            )

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type", "")
                    part = event.get("part", {})

                    # 从第一个事件中提取新 session ID
                    if not new_session_id and "sessionID" in event:
                        new_session_id = event["sessionID"]

                    if event_type == "text":
                        text = part.get("text", "")
                        if text:
                            safe_text = text.replace("\n", "\\n")
                            yield f"event: text\ndata: {safe_text}\n\n"

                    elif event_type == "reasoning" or part.get("type") == "reasoning":
                        text = part.get("text", event.get("text", ""))
                        if text:
                            safe_text = text.replace("\n", "\\n")
                            yield f"event: thinking\ndata: {safe_text}\n\n"

                    elif event_type == "step_finish":
                        tokens = part.get("tokens", {})
                        result = json.dumps({
                            "session_id": new_session_id or "",
                            "tokens": tokens,
                            "cost": part.get("cost", 0),
                        })
                        yield f"event: done\ndata: {result}\n\n"

                except json.JSONDecodeError:
                    pass

            if proc:
                proc.wait(timeout=600)

        except FileNotFoundError:
            yield "event: error\ndata: opencode CLI 未找到，请确认已安装 opencode\n\n"
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            yield "event: error\ndata: 请求超时\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        finally:
            if not new_session_id:
                # 如果没拿到 session ID 也发 done
                yield f"event: done\ndata: {json.dumps({'session_id': ''})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        },
    )


# ── 前端页面 ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

    if not os.path.isfile(DB_PATH):
        print(f"[错误] 数据库不存在: {DB_PATH}")
        print("请确认 OpenCode 已运行并有会话记录。")
        sys.exit(1)

    print(f"  OpenCode 会话查看器")
    print(f"  {'=' * 40}")
    print(f"  数据库: {DB_PATH}")
    print(f"  地址:   http://127.0.0.1:{port}")
    print(f"  {'=' * 40}")

    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
