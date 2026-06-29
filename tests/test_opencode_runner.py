from services.opencode_runner import event_to_sse, extract_error_message, truncate


def test_event_to_sse_text_and_reasoning_escape_newlines():
    assert event_to_sse({"type": "text", "part": {"text": "a\nb"}}) == "event: text\ndata: a\\nb\n\n"
    assert event_to_sse({"type": "reasoning", "part": {"text": "think\nmore"}}) == (
        "event: thinking\ndata: think\\nmore\n\n"
    )


def test_event_to_sse_tool_use_and_result():
    assert event_to_sse({"type": "tool_use", "part": {"tool": "bash", "input": "echo hi"}}) == (
        'event: tool_use\ndata: {"tool": "bash", "input": "echo hi"}\n\n'
    )
    assert event_to_sse({"type": "tool_result", "part": {"tool_name": "bash", "status": "done"}}) == (
        'event: tool_result\ndata: {"tool": "bash", "status": "done"}\n\n'
    )


def test_event_to_sse_step_finish_respects_stop_mode():
    event = {
        "type": "step_finish",
        "part": {"reason": "tool-calls", "tokens": {"total": 2}, "cost": 0.01},
    }

    assert event_to_sse(event, session_id="ses_1") is None
    assert event_to_sse(event, session_id="ses_1", done_on_stop_only=False) == (
        'event: done\ndata: {"session_id": "ses_1", "tokens": {"total": 2}, "cost": 0.01}\n\n'
    )


def test_event_to_sse_step_finish_stop():
    event = {
        "type": "step_finish",
        "part": {"reason": "stop", "tokens": {"total": 2}, "cost": 0.01},
    }

    assert event_to_sse(event, session_id="ses_1") == (
        'event: done\ndata: {"session_id": "ses_1", "tokens": {"total": 2}, "cost": 0.01}\n\n'
    )


def test_event_to_sse_error_shapes():
    rate_limit = event_to_sse({"error": {"message": "quota"}})
    assert rate_limit is not None
    assert "event: stream_error" in rate_limit
    assert "模型额度或速率已受限" in rate_limit
    assert "quota" in rate_limit

    model_error = event_to_sse({"data": {"error": {"message": "model not found: bad model"}}})
    assert model_error is not None
    assert "event: stream_error" in model_error
    assert "模型不可用" in model_error
    assert "model not found: bad model" in model_error

    assert extract_error_message({"name": "UnknownError", "data": {"message": "boom"}}) == "boom"


def test_truncate_handles_none_and_length():
    assert truncate(None) == ""
    assert truncate("abcdef", max_len=3) == "abc"
