from dataclasses import dataclass, field
import time
from typing import Any


RUNNING = "running"
WAITING_FOR_TOOLS = "waiting_for_tools"
CANDIDATE_DONE = "candidate_done"
DONE = "done"
ERROR = "error"

TYPE_ALIASES = {
    "step_start": "step-start",
    "step_finish": "step-finish",
    "tool_use": "tool",
    "tool-result": "tool_result",
}

CONTENT_PART_TYPES = {"text", "reasoning", "patch", "file", "agent", "subtask"}
TERMINAL_TOOL_STATUSES = {
    "cancelled",
    "canceled",
    "complete",
    "completed",
    "done",
    "error",
    "errored",
    "failed",
    "success",
    "succeeded",
}


@dataclass(frozen=True)
class OpenCodePart:
    type: str
    text: str = ""
    tool: str = ""
    part_id: str = ""
    message_id: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    tokens: dict[str, Any] = field(default_factory=dict)
    cost: float = 0
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_key(self) -> str:
        return self.part_id or self.tool


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _normalize_type(value: Any) -> str:
    if not value:
        return "unknown"
    return TYPE_ALIASES.get(str(value), str(value))


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_part(data: dict[str, Any], event_type: str | None = None) -> OpenCodePart:
    """Normalize a raw OpenCode event or part payload into one internal shape."""
    raw = data or {}
    payload = raw
    if isinstance(raw.get("part"), dict):
        event_type = event_type or raw.get("type")
        payload = raw["part"]

    part_type = _normalize_type(payload.get("type") or event_type or raw.get("type"))
    state = _dict_or_empty(payload.get("state"))

    return OpenCodePart(
        type=part_type,
        text=str(payload.get("text") or payload.get("content") or raw.get("text") or ""),
        tool=str(payload.get("tool") or payload.get("tool_name") or payload.get("name") or ""),
        part_id=str(payload.get("id") or raw.get("partID") or raw.get("part_id") or ""),
        message_id=str(payload.get("message_id") or payload.get("messageID") or raw.get("messageID") or ""),
        state=state,
        tokens=_dict_or_empty(payload.get("tokens")),
        cost=_number_or_zero(payload.get("cost")),
        reason=str(payload.get("reason") or ""),
        raw=raw,
    )


def parse_event(event: dict[str, Any]) -> OpenCodePart:
    return parse_part(event)


@dataclass
class ConversationState:
    stable_window_ms: int = 1500
    status: str = RUNNING
    candidate_since_ms: int | None = None
    active_tools: set[str] = field(default_factory=set)
    last_reason: str = ""
    error_message: str = ""

    @property
    def done(self) -> bool:
        return self.status == DONE

    @property
    def waiting_for_tools(self) -> bool:
        return self.status == WAITING_FOR_TOOLS

    def apply_event(self, event: dict[str, Any], now_ms: int | None = None):
        return self.apply_part(parse_event(event), now_ms=now_ms)

    def apply_part(self, part: OpenCodePart, now_ms: int | None = None):
        now_ms = _now_ms() if now_ms is None else now_ms
        self.last_reason = part.reason or self.last_reason

        if part.type in CONTENT_PART_TYPES:
            self._mark_running()
        elif part.type == "step-start":
            self._mark_running()
        elif part.type == "tool":
            self._apply_tool(part)
        elif part.type == "tool_result":
            self._complete_tool(part)
        elif part.type == "step-finish":
            self._apply_step_finish(part, now_ms)

        return self

    def tick(self, now_ms: int | None = None):
        now_ms = _now_ms() if now_ms is None else now_ms
        if (
            self.status == CANDIDATE_DONE
            and self.candidate_since_ms is not None
            and now_ms - self.candidate_since_ms >= self.stable_window_ms
        ):
            self.status = DONE
        return self

    def mark_error(self, message: str):
        self.status = ERROR
        self.error_message = message
        self.candidate_since_ms = None
        return self

    def _mark_running(self):
        self.status = RUNNING
        self.candidate_since_ms = None

    def _apply_tool(self, part: OpenCodePart):
        key = part.tool_key
        status = self._tool_status(part)
        if key and status in TERMINAL_TOOL_STATUSES:
            self.active_tools.discard(key)
            self._mark_running()
            return

        if key:
            self.active_tools.add(key)
        self.status = WAITING_FOR_TOOLS
        self.candidate_since_ms = None

    def _complete_tool(self, part: OpenCodePart):
        if part.tool_key:
            self.active_tools.discard(part.tool_key)
        self._mark_running()

    def _apply_step_finish(self, part: OpenCodePart, now_ms: int):
        if part.reason == "tool-calls":
            self.status = WAITING_FOR_TOOLS
            self.candidate_since_ms = None
            return

        if part.reason == "stop":
            if self.active_tools:
                self.status = WAITING_FOR_TOOLS
                self.candidate_since_ms = None
                return
            self.status = CANDIDATE_DONE
            self.candidate_since_ms = now_ms
            return

        self._mark_running()

    def _tool_status(self, part: OpenCodePart) -> str:
        value = part.state.get("status") or part.state.get("state") or part.raw.get("status")
        return str(value or "").lower()
