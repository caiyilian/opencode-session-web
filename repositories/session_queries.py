from db import (
    get_total_usage,
    has_table_column,
    session_column_expr,
    session_usage_query_parts,
)


def fetch_stats_overview(conn):
    cursor = conn.cursor()

    total_sessions = cursor.execute("SELECT COUNT(*) FROM session").fetchone()[0]
    total_projects = cursor.execute("SELECT COUNT(DISTINCT directory) FROM session").fetchone()[0]
    total_usage = get_total_usage(conn)

    top_directories = cursor.execute(
        "SELECT directory, COUNT(*) as cnt FROM session GROUP BY directory ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    if has_table_column(conn, "session", "model"):
        top_models = cursor.execute(
            "SELECT model, COUNT(*) as cnt FROM session WHERE model IS NOT NULL AND model != '' GROUP BY model ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
    else:
        top_models = []

    recent_sessions = cursor.execute(
        "SELECT id, title, directory, time_updated FROM session ORDER BY time_updated DESC LIMIT 5"
    ).fetchall()

    return {
        "total_sessions": total_sessions,
        "total_projects": total_projects,
        "total_usage": total_usage,
        "top_directories": top_directories,
        "top_models": top_models,
        "recent_sessions": recent_sessions,
    }


def fetch_session_list(conn, *, q="", directory="", model="", limit=50, offset=0):
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
        if has_table_column(conn, "session", "model"):
            conditions.append("s.model = ?")
            params.append(model)
        else:
            conditions.append("0 = 1")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    total = cursor.execute(f"SELECT COUNT(*) FROM session s {where}", params).fetchone()[0]

    usage_cte, usage_join, usage_expr = session_usage_query_parts(conn, "s")
    model_expr = session_column_expr(conn, "model", "s", "NULL")
    agent_expr = session_column_expr(conn, "agent", "s", "NULL")

    rows = cursor.execute(
        f"""{usage_cte}
            SELECT s.id, s.title, s.directory,
                   {model_expr} AS model,
                   {agent_expr} AS agent,
                   s.time_created, s.time_updated,
                   {usage_expr["cost"]} AS cost,
                   {usage_expr["tokens_input"]} AS tokens_input,
                   {usage_expr["tokens_output"]} AS tokens_output,
                   (SELECT COUNT(*) FROM message m WHERE m.session_id = s.id) as msg_count
            FROM session s
            {usage_join}
            {where}
            ORDER BY s.time_updated DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    return total, rows


def fetch_token_stats(conn, *, since_ms):
    cursor = conn.cursor()
    usage_cte, usage_join, usage_expr = session_usage_query_parts(conn, "s")
    model_expr = session_column_expr(conn, "model", "s", "'N/A'")

    daily = cursor.execute(
        f"""{usage_cte}
           SELECT DATE(s.time_created / 1000, 'unixepoch') as day,
                  SUM({usage_expr["tokens_input"]}) as inp,
                  SUM({usage_expr["tokens_output"]}) as out
           FROM session s
           {usage_join}
           WHERE s.time_created > ?
           GROUP BY day
           ORDER BY day""",
        (since_ms,),
    ).fetchall()

    model_where = "WHERE s.model IS NOT NULL AND s.model != ''" if has_table_column(conn, "session", "model") else ""
    by_model = cursor.execute(
        f"""{usage_cte}
           SELECT {model_expr} AS model,
                  SUM({usage_expr["tokens_input"]}) as inp,
                  SUM({usage_expr["tokens_output"]}) as out,
                  SUM({usage_expr["cost"]}) as cst
           FROM session s
           {usage_join}
           {model_where}
           GROUP BY {model_expr}
           ORDER BY inp DESC
           LIMIT 15""",
    ).fetchall()

    by_project = cursor.execute(
        f"""{usage_cte}
           SELECT s.directory,
                  SUM({usage_expr["tokens_input"]}) as inp,
                  SUM({usage_expr["tokens_output"]}) as out,
                  COUNT(*) as cnt
           FROM session s
           {usage_join}
           GROUP BY s.directory
           ORDER BY inp DESC
           LIMIT 15""",
    ).fetchall()

    total_cost_all = cursor.execute(
        f"""{usage_cte}
           SELECT COALESCE(SUM({usage_expr["cost"]}), 0)
           FROM session s
           {usage_join}"""
    ).fetchone()[0]

    return daily, by_model, by_project, total_cost_all
