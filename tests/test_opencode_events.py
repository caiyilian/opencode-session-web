from services.opencode_events import (
    CANDIDATE_DONE,
    DONE,
    RUNNING,
    WAITING_FOR_TOOLS,
    ConversationState,
    OpenCodePart,
    parse_event,
    parse_part,
)


def test_parse_part_normalizes_common_types():
    assert parse_part({"type": "text", "text": "hello"}).type == "text"
    assert parse_part({"type": "reasoning", "text": "thinking"}).text == "thinking"

    tool = parse_event({
        "type": "tool_use",
        "part": {"id": "part_1", "tool": "bash", "state": {"status": "running"}},
    })
    assert tool.type == "tool"
    assert tool.tool == "bash"
    assert tool.part_id == "part_1"
    assert tool.state["status"] == "running"

    finish = parse_event({"type": "step_finish", "part": {"reason": "stop", "cost": 0.5}})
    assert finish.type == "step-finish"
    assert finish.reason == "stop"
    assert finish.cost == 0.5


def test_tool_calls_step_finish_does_not_complete():
    state = ConversationState(stable_window_ms=1000)

    state.apply_part(OpenCodePart(type="step-start"), now_ms=0)
    state.apply_part(
        OpenCodePart(type="tool", tool="bash", part_id="tool_1", state={"status": "running"}),
        now_ms=10,
    )
    state.apply_part(OpenCodePart(type="step-finish", reason="tool-calls"), now_ms=20)
    state.tick(now_ms=5000)

    assert state.status == WAITING_FOR_TOOLS
    assert not state.done


def test_stop_reason_requires_stable_window():
    state = ConversationState(stable_window_ms=1000)

    state.apply_part(OpenCodePart(type="step-finish", reason="stop"), now_ms=100)
    assert state.status == CANDIDATE_DONE
    assert not state.done

    state.tick(now_ms=1099)
    assert state.status == CANDIDATE_DONE

    state.tick(now_ms=1100)
    assert state.status == DONE


def test_followup_content_after_candidate_done_returns_to_running():
    state = ConversationState(stable_window_ms=1000)

    state.apply_part(OpenCodePart(type="step-finish", reason="stop"), now_ms=100)
    state.apply_part(OpenCodePart(type="text", text="more output"), now_ms=200)
    state.tick(now_ms=5000)

    assert state.status == RUNNING
    assert state.candidate_since_ms is None
    assert not state.done


def test_completed_tool_allows_stop_to_become_done():
    state = ConversationState(stable_window_ms=1000)

    state.apply_part(
        OpenCodePart(type="tool", tool="bash", part_id="tool_1", state={"status": "running"}),
        now_ms=0,
    )
    assert state.status == WAITING_FOR_TOOLS

    state.apply_part(
        OpenCodePart(type="tool", tool="bash", part_id="tool_1", state={"status": "completed"}),
        now_ms=100,
    )
    state.apply_part(OpenCodePart(type="step-finish", reason="stop"), now_ms=200)
    state.tick(now_ms=1200)

    assert state.active_tools == set()
    assert state.status == DONE
