import json
from typing import Any


def event(event_name: str, data: Any = "") -> str:
    lines = str(data).splitlines() or [""]
    payload = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event_name}\n{payload}\n\n"


def json_event(event_name: str, payload: dict[str, Any]) -> str:
    return event(event_name, json.dumps(payload, ensure_ascii=False))


def status(data: str) -> str:
    return event("status", data)


def stream_error(message: str) -> str:
    return event("stream_error", message)


def done(payload: dict[str, Any]) -> str:
    return json_event("done", payload)
