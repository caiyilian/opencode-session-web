import json
import sqlite3

import pytest

import app as webapp


def _create_db(path, *, old_usage_columns: bool):
    conn = sqlite3.connect(path)
    if old_usage_columns:
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
    else:
        conn.execute(
            """CREATE TABLE session (
                id TEXT PRIMARY KEY,
                title TEXT,
                directory TEXT,
                time_created INTEGER,
                time_updated INTEGER
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
        ("ses_old", "Older session", "C:/repo/one", 1_700_000_000_000, 1_700_000_001_000),
        ("ses_new", "Newer session", "C:/repo/two", 1_700_000_002_000, 1_700_000_003_000),
    ]
    if old_usage_columns:
        conn.executemany(
            """INSERT INTO session
               (id, title, directory, model, agent, time_created, time_updated, cost, tokens_input, tokens_output)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (*sessions[0][:3], "provider/model-a", "build", *sessions[0][3:], 1.25, 100, 50),
                (*sessions[1][:3], "provider/model-b", "build", *sessions[1][3:], 0.25, 7, 3),
            ],
        )
    else:
        conn.executemany(
            """INSERT INTO session
               (id, title, directory, time_created, time_updated)
               VALUES (?, ?, ?, ?, ?)""",
            sessions,
        )

    for sid in ("ses_old", "ses_new"):
        mid = f"msg_{sid}"
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (mid, sid, 1_700_000_004_000, 1_700_000_004_000, json.dumps({"role": "assistant"})),
        )

    part_usage = {
        "ses_old": {"input": 10, "output": 5, "cost": 0.10},
        "ses_new": {"input": 3, "output": 2, "cost": 0.20},
    }
    for sid, usage in part_usage.items():
        mid = f"msg_{sid}"
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"part_{sid}_text",
                mid,
                sid,
                1_700_000_004_000,
                1_700_000_004_000,
                json.dumps({"type": "text", "text": f"hello from {sid}"}),
            ),
        )
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"part_{sid}_finish",
                mid,
                sid,
                1_700_000_004_100,
                1_700_000_004_100,
                json.dumps(
                    {
                        "type": "step-finish",
                        "reason": "stop",
                        "tokens": {"input": usage["input"], "output": usage["output"], "total": usage["input"] + usage["output"]},
                        "cost": usage["cost"],
                    }
                ),
            ),
        )

    conn.commit()
    conn.close()


@pytest.fixture(params=[True, False], ids=["old-session-usage-columns", "new-part-usage"])
def client(tmp_path, request):
    db_path = tmp_path / "opencode.db"
    _create_db(db_path, old_usage_columns=request.param)
    app = webapp.create_app({
        "TESTING": True,
        "OPENCODE_DB_PATH": str(db_path),
    })
    with app.test_client() as test_client:
        yield test_client, request.param


def _expected_usage(old_usage_columns: bool):
    if old_usage_columns:
        return {"cost": 1.5, "input": 107, "output": 53}
    return {"cost": 0.3, "input": 13, "output": 7}


def test_create_app_applies_database_config(tmp_path):
    db_path = tmp_path / "configured.db"
    _create_db(db_path, old_usage_columns=False)

    app = webapp.create_app({
        "TESTING": True,
        "OPENCODE_DB_PATH": str(db_path),
    })

    assert app.config["OPENCODE_DB_PATH"] == str(db_path)
    assert webapp.DB_PATH == str(db_path)
    with app.test_client() as test_client:
        assert test_client.get("/api/stats").status_code == 200


def test_stats_schema_compatible(client):
    test_client, old_usage_columns = client
    expected = _expected_usage(old_usage_columns)

    response = test_client.get("/api/stats")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_sessions"] == 2
    assert payload["total_projects"] == 2
    assert payload["total_cost"] == pytest.approx(expected["cost"])
    assert payload["total_tokens_input"] == expected["input"]
    assert payload["total_tokens_output"] == expected["output"]


def test_sessions_list_schema_compatible(client):
    test_client, old_usage_columns = client
    expected = _expected_usage(old_usage_columns)

    response = test_client.get("/api/sessions?limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 2
    by_id = {item["id"]: item for item in payload["sessions"]}
    assert by_id["ses_new"]["message_count"] == 1
    assert by_id["ses_old"]["tokens_input"] + by_id["ses_new"]["tokens_input"] == expected["input"]
    assert by_id["ses_old"]["tokens_output"] + by_id["ses_new"]["tokens_output"] == expected["output"]
    assert by_id["ses_old"]["cost"] + by_id["ses_new"]["cost"] == pytest.approx(expected["cost"])


def test_session_detail_and_compare_include_usage(client):
    test_client, old_usage_columns = client
    expected = _expected_usage(old_usage_columns)

    detail = test_client.get("/api/sessions/ses_old")
    compare = test_client.get("/api/sessions/compare?id1=ses_old&id2=ses_new")

    assert detail.status_code == 200
    assert compare.status_code == 200
    detail_payload = detail.get_json()
    compare_payload = compare.get_json()
    assert detail_payload["session"]["tokens_input"] > 0
    assert detail_payload["session"]["tokens_output"] > 0
    assert detail_payload["session"]["cost"] >= 0
    parts = detail_payload["messages"][0]["parts"]
    text_part = next(part for part in parts if part["type"] == "text")
    step_finish_part = next(part for part in parts if part["type"] == "step-finish")
    assert text_part == {"type": "text", "text": "hello from ses_old"}
    assert step_finish_part["tokens"]["total"] == 15
    assert step_finish_part["cost"] >= 0
    assert step_finish_part["reason"] == "stop"
    assert "[步骤完成]" in compare_payload["session1"]["messages"][0]["content"]
    total_compare_input = compare_payload["session1"]["tokens_input"] + compare_payload["session2"]["tokens_input"]
    total_compare_output = compare_payload["session1"]["tokens_output"] + compare_payload["session2"]["tokens_output"]
    total_compare_cost = compare_payload["session1"]["cost"] + compare_payload["session2"]["cost"]
    assert total_compare_input == expected["input"]
    assert total_compare_output == expected["output"]
    assert total_compare_cost == pytest.approx(expected["cost"])


def test_message_detail_schema_compatible(client):
    test_client, _old_usage_columns = client

    response = test_client.get("/api/messages/msg_ses_old")
    missing = test_client.get("/api/messages/missing")

    assert response.status_code == 200
    assert missing.status_code == 404
    payload = response.get_json()
    assert payload["id"] == "msg_ses_old"
    assert payload["session_id"] == "ses_old"
    assert payload["data"]["role"] == "assistant"
    assert payload["time_created"] == 1_700_000_004_000


def test_token_stats_schema_compatible(client):
    test_client, old_usage_columns = client
    expected = _expected_usage(old_usage_columns)

    response = test_client.get("/api/stats/tokens")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_cost"] == pytest.approx(expected["cost"])
    assert sum(item["input"] for item in payload["by_model"]) == expected["input"]
    assert sum(item["output"] for item in payload["by_project"]) == expected["output"]
