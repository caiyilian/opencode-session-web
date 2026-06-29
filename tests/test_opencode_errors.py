from services.opencode_errors import (
    ErrorKind,
    classify_error_text,
    is_known_error_text,
    known_error_keywords,
)


def test_classify_rate_limit_error():
    classified = classify_error_text("429 quota exceeded, retrying in 30s")

    assert classified is not None
    assert classified.kind == ErrorKind.RATE_LIMIT
    assert classified.matched_keyword == "quota"
    assert "切换模型" in classified.friendly_message


def test_classify_auth_error():
    classified = classify_error_text("Unauthorized: invalid API key")

    assert classified is not None
    assert classified.kind == ErrorKind.AUTH
    assert "认证失败" in classified.friendly_message


def test_classify_model_error():
    classified = classify_error_text("model not found: provider/bad-model")

    assert classified is not None
    assert classified.kind == ErrorKind.MODEL_NOT_FOUND
    assert "模型不可用" in classified.friendly_message


def test_classify_network_error():
    classified = classify_error_text("connection reset by peer")

    assert classified is not None
    assert classified.kind == ErrorKind.NETWORK
    assert "网络连接异常" in classified.friendly_message


def test_classify_timeout_error():
    classified = classify_error_text("request timed out after 30s")

    assert classified is not None
    assert classified.kind == ErrorKind.TIMEOUT
    assert "响应超时" in classified.friendly_message


def test_unknown_error_preserves_message():
    classified = classify_error_text("provider returned an unexpected payload")

    assert classified is not None
    assert classified.kind == ErrorKind.UNKNOWN
    assert classified.message == "provider returned an unexpected payload"
    assert "技术细节" in classified.friendly_message
    assert not is_known_error_text(classified.message)


def test_empty_error_text_is_none():
    assert classify_error_text("") is None
    assert classify_error_text(None) is None


def test_known_error_keywords_include_existing_route_terms():
    keywords = known_error_keywords()

    for keyword in ("rate limit", "quota", "retry-after", "429"):
        assert keyword in keywords
