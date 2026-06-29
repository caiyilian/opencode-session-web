from typing import Any

from services import sse
from services.opencode_errors import format_stream_error_message
from services.opencode_events import parse_event


def truncate(text: Any, max_len: int = 500) -> str:
    if text is None:
        return ""
    return str(text)[:max_len]


def extract_error_message(event: dict[str, Any]) -> str:
    for key in ("error", "message"):
        value = event.get(key)
        message = _message_from_value(value)
        if message:
            return message

    data = event.get("data")
    if isinstance(data, dict):
        for key in ("error", "message"):
            message = _message_from_value(data.get(key))
            if message:
                return message

    name = event.get("name", "")
    if isinstance(name, str) and "error" in name.lower():
        data_message = ""
        if isinstance(data, dict):
            data_message = data.get("message") or data.get("error") or ""
        return str(data_message or name)

    return ""


def event_to_sse(
    event: dict[str, Any],
    *,
    session_id: str = "",
    done_on_stop_only: bool = True,
) -> str | None:
    error = extract_error_message(event)
    if error:
        return sse.stream_error(truncate(format_stream_error_message(error)))

    part_payload = event.get("part") if isinstance(event.get("part"), dict) else {}
    part = parse_event(event)

    if part.type == "text":
        return sse.event("text", part.text.replace("\n", "\\n"))

    if part.type == "reasoning":
        return sse.event("thinking", part.text.replace("\n", "\\n"))

    if part.type == "tool":
        tool_input = part_payload.get("input", "") or part_payload.get("arguments", "") or ""
        return sse.json_event("tool_use", {"tool": part.tool, "input": str(tool_input)[:200]})

    if part.type == "tool_result":
        status = part_payload.get("status", "done")
        return sse.json_event("tool_result", {"tool": part.tool, "status": status})

    if part.type == "step-start":
        return sse.status("step_start")

    if part.type == "step-finish":
        if done_on_stop_only and part.reason != "stop":
            return None
        return sse.done({
            "session_id": session_id,
            "tokens": part.tokens,
            "cost": part.cost,
        })

    return None


def _message_from_value(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        message = value.get("message") or value.get("error") or ""
        if message:
            return str(message)
    return ""
