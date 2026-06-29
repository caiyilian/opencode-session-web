import sqlite3


SESSION_USAGE_COLUMNS = {"cost", "tokens_input", "tokens_output"}


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def has_table_column(conn, table_name: str, column_name: str) -> bool:
    return column_name in table_columns(conn, table_name)


def session_column_expr(conn, column_name: str, session_alias: str = "s", default_sql: str = "NULL") -> str:
    if has_table_column(conn, "session", column_name):
        return f"{session_alias}.{column_name}"
    return default_sql


def has_session_usage_columns(conn) -> bool:
    return SESSION_USAGE_COLUMNS.issubset(table_columns(conn, "session"))


def session_usage_query_parts(conn, session_alias: str = "s"):
    """Return SQL fragments for usage fields across old/new OpenCode schemas."""
    if has_session_usage_columns(conn):
        return "", "", {
            "cost": f"COALESCE({session_alias}.cost, 0)",
            "tokens_input": f"COALESCE({session_alias}.tokens_input, 0)",
            "tokens_output": f"COALESCE({session_alias}.tokens_output, 0)",
        }

    if not table_exists(conn, "part"):
        return "", "", {
            "cost": "0",
            "tokens_input": "0",
            "tokens_output": "0",
        }

    cte = """
        WITH usage AS (
            SELECT session_id,
                   COALESCE(SUM(CAST(json_extract(data, '$.cost') AS REAL)), 0) AS cost,
                   COALESCE(SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)), 0) AS tokens_input,
                   COALESCE(SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)), 0) AS tokens_output
            FROM part
            WHERE json_extract(data, '$.type') = 'step-finish'
            GROUP BY session_id
        )
    """
    join = f"LEFT JOIN usage u ON u.session_id = {session_alias}.id"
    return cte, join, {
        "cost": "COALESCE(u.cost, 0)",
        "tokens_input": "COALESCE(u.tokens_input, 0)",
        "tokens_output": "COALESCE(u.tokens_output, 0)",
    }


def get_total_usage(conn):
    if has_session_usage_columns(conn):
        row = conn.execute(
            """SELECT COALESCE(SUM(cost), 0) AS cost,
                      COALESCE(SUM(tokens_input), 0) AS tokens_input,
                      COALESCE(SUM(tokens_output), 0) AS tokens_output
               FROM session"""
        ).fetchone()
    elif table_exists(conn, "part"):
        row = conn.execute(
            """SELECT COALESCE(SUM(CAST(json_extract(data, '$.cost') AS REAL)), 0) AS cost,
                      COALESCE(SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)), 0) AS tokens_input,
                      COALESCE(SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)), 0) AS tokens_output
               FROM part
               WHERE json_extract(data, '$.type') = 'step-finish'"""
        ).fetchone()
    else:
        return {"cost": 0, "tokens_input": 0, "tokens_output": 0}

    return {
        "cost": row["cost"] or 0,
        "tokens_input": row["tokens_input"] or 0,
        "tokens_output": row["tokens_output"] or 0,
    }


def get_session_usage(conn, session_id: str):
    if has_session_usage_columns(conn):
        row = conn.execute(
            """SELECT COALESCE(cost, 0) AS cost,
                      COALESCE(tokens_input, 0) AS tokens_input,
                      COALESCE(tokens_output, 0) AS tokens_output
               FROM session
               WHERE id = ?""",
            (session_id,),
        ).fetchone()
    elif table_exists(conn, "part"):
        row = conn.execute(
            """SELECT COALESCE(SUM(CAST(json_extract(data, '$.cost') AS REAL)), 0) AS cost,
                      COALESCE(SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)), 0) AS tokens_input,
                      COALESCE(SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)), 0) AS tokens_output
               FROM part
               WHERE session_id = ?
                 AND json_extract(data, '$.type') = 'step-finish'""",
            (session_id,),
        ).fetchone()
    else:
        return {"cost": 0, "tokens_input": 0, "tokens_output": 0}

    if not row:
        return {"cost": 0, "tokens_input": 0, "tokens_output": 0}
    return {
        "cost": row["cost"] or 0,
        "tokens_input": row["tokens_input"] or 0,
        "tokens_output": row["tokens_output"] or 0,
    }
