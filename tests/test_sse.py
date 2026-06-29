from services import sse


def test_event_formats_single_line_data():
    assert sse.event("status", "waiting") == "event: status\ndata: waiting\n\n"


def test_event_formats_multiline_data():
    assert sse.event("text", "a\nb") == "event: text\ndata: a\ndata: b\n\n"


def test_event_formats_empty_data():
    assert sse.event("ping") == "event: ping\ndata: \n\n"


def test_json_event_preserves_chinese_text():
    assert sse.json_event("done", {"message": "完成", "tokens": 3}) == (
        'event: done\ndata: {"message": "完成", "tokens": 3}\n\n'
    )


def test_common_helpers():
    assert sse.status("waiting") == "event: status\ndata: waiting\n\n"
    assert sse.stream_error("错误") == "event: stream_error\ndata: 错误\n\n"
    assert sse.done({"session_id": "ses_1"}) == 'event: done\ndata: {"session_id": "ses_1"}\n\n'
