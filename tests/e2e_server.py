import atexit
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as webapp  # noqa: E402


def create_fixture_db(path: Path) -> None:
    now = int(time.time() * 1000)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            title TEXT,
            directory TEXT,
            model TEXT,
            agent TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            cost REAL,
            tokens_input INTEGER,
            tokens_output INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            data TEXT
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

    sessions = [
        (
            "ses_alpha",
            "Alpha release planning",
            "C:/repo/alpha",
            "provider/model-a",
            now - 20_000,
            now - 1_000,
            0.12,
            120,
            80,
        ),
        (
            "ses_beta",
            "Beta error followup",
            "C:/repo/beta",
            "provider/model-b",
            now - 40_000,
            now - 2_000,
            0.04,
            40,
            35,
        ),
        (
            "ses_empty",
            "Empty archive session",
            "C:/repo/archive",
            "provider/model-c",
            now - 60_000,
            now - 3_000,
            0.0,
            0,
            0,
        ),
    ]
    conn.executemany(
        """INSERT INTO session
           (id, title, directory, model, agent, time_created, time_updated, cost, tokens_input, tokens_output)
           VALUES (?, ?, ?, ?, 'e2e', ?, ?, ?, ?, ?)""",
        sessions,
    )

    def insert_message(session_id: str, message_id: str, role: str, offset: int) -> None:
        created = now + offset
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, created, created, json.dumps({"role": role})),
        )

    def insert_part(session_id: str, message_id: str, part_id: str, payload: dict, offset: int) -> None:
        created = now + offset
        updated = created + int(payload.pop("_duration", 0))
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (part_id, message_id, session_id, created, updated, json.dumps(payload)),
        )

    insert_message("ses_alpha", "msg_alpha_user", "user", 10)
    insert_part(
        "ses_alpha",
        "msg_alpha_user",
        "part_alpha_user_text",
        {"type": "text", "text": "Review the alpha release plan."},
        10,
    )
    insert_message("ses_alpha", "msg_alpha_assistant", "assistant", 20)
    insert_part(
        "ses_alpha",
        "msg_alpha_assistant",
        "part_alpha_tool",
        {
            "type": "tool",
            "tool": "bash",
            "state": {
                "status": "completed",
                "input": {"command": "npm test", "description": "Run alpha checks"},
                "output": "8 tests passed",
            },
            "_duration": 450,
        },
        20,
    )
    insert_part(
        "ses_alpha",
        "msg_alpha_assistant",
        "part_alpha_text",
        {"type": "text", "text": "Alpha release is ready after the checks passed."},
        30,
    )
    insert_part(
        "ses_alpha",
        "msg_alpha_assistant",
        "part_alpha_finish",
        {
            "type": "step-finish",
            "reason": "stop",
            "tokens": {"input": 120, "output": 80, "total": 200},
            "cost": 0.12,
        },
        40,
    )

    insert_message("ses_beta", "msg_beta_user", "user", 50)
    insert_part(
        "ses_beta",
        "msg_beta_user",
        "part_beta_user_text",
        {"type": "text", "text": "Check the beta error followup."},
        50,
    )
    insert_message("ses_beta", "msg_beta_assistant", "assistant", 60)
    insert_part(
        "ses_beta",
        "msg_beta_assistant",
        "part_beta_text",
        {"type": "text", "text": "Beta followup needs a clearer error message."},
        60,
    )
    insert_part(
        "ses_beta",
        "msg_beta_assistant",
        "part_beta_finish",
        {
            "type": "step-finish",
            "reason": "stop",
            "tokens": {"input": 40, "output": 35, "total": 75},
            "cost": 0.04,
        },
        70,
    )

    conn.commit()
    conn.close()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18765
    temp_dir = Path(tempfile.mkdtemp(prefix="opencode-session-web-e2e-"))
    atexit.register(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
    db_path = temp_dir / "opencode.db"
    create_fixture_db(db_path)

    flask_app = webapp.create_app(
        {
            "OPENCODE_DB_PATH": str(db_path),
            "OPENCODE_USE_FRONTEND_DIST": True,
            "OPENCODE_FRONTEND_DIST_DIR": str(ROOT / "frontend" / "dist"),
            "OPENCODE_WEB_LOG_DIR": str(temp_dir / "logs"),
        }
    )
    flask_app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
