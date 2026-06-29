from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ErrorKind(str, Enum):
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    MODEL_NOT_FOUND = "model_not_found"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedError:
    kind: ErrorKind
    message: str
    friendly_message: str
    matched_keyword: str = ""


KEYWORDS_BY_KIND: dict[ErrorKind, tuple[str, ...]] = {
    ErrorKind.RATE_LIMIT: (
        "rate limit",
        "quota",
        "exceeded",
        "too many",
        "retry-after",
        "free usage",
        "subscribe",
        "retrying in",
        "429",
    ),
    ErrorKind.AUTH: (
        "unauthorized",
        "authentication",
        "auth failed",
        "invalid api key",
        "api key",
        "login required",
        "not logged in",
        "forbidden",
        "401",
        "403",
    ),
    ErrorKind.MODEL_NOT_FOUND: (
        "model not found",
        "unknown model",
        "invalid model",
        "model does not exist",
        "unsupported model",
        "no such model",
    ),
    ErrorKind.NETWORK: (
        "network",
        "connection reset",
        "connection refused",
        "socket hang up",
        "econnreset",
        "enotfound",
        "dns",
        "502",
        "503",
        "504",
    ),
    ErrorKind.TIMEOUT: (
        "timeout",
        "timed out",
        "no output",
        "无响应",
        "请求超时",
    ),
}

FRIENDLY_MESSAGES: dict[ErrorKind, str] = {
    ErrorKind.RATE_LIMIT: "模型额度或速率已受限，请切换模型或稍后重试。",
    ErrorKind.AUTH: "OpenCode 认证失败，请检查登录状态或 API Key。",
    ErrorKind.MODEL_NOT_FOUND: "模型不可用或名称无效，请切换模型后重试。",
    ErrorKind.NETWORK: "网络连接异常，请稍后重试。",
    ErrorKind.TIMEOUT: "模型响应超时，请稍后重试或切换模型。",
    ErrorKind.UNKNOWN: "OpenCode 返回错误，请查看技术细节。",
}


def classify_error_text(text: str | None) -> ClassifiedError | None:
    message = (text or "").strip()
    if not message:
        return None

    lowered = message.lower()
    for kind, keywords in KEYWORDS_BY_KIND.items():
        matched_keyword = _first_match(lowered, keywords)
        if matched_keyword:
            return ClassifiedError(
                kind=kind,
                message=message,
                friendly_message=FRIENDLY_MESSAGES[kind],
                matched_keyword=matched_keyword,
            )

    return ClassifiedError(
        kind=ErrorKind.UNKNOWN,
        message=message,
        friendly_message=FRIENDLY_MESSAGES[ErrorKind.UNKNOWN],
    )


def is_known_error_text(text: str | None) -> bool:
    classified = classify_error_text(text)
    return classified is not None and classified.kind is not ErrorKind.UNKNOWN


def format_stream_error_message(text: str | None) -> str:
    classified = classify_error_text(text)
    if classified is None:
        return ""
    if classified.kind is ErrorKind.UNKNOWN:
        return classified.message
    return f"{classified.friendly_message}\n\n技术细节：{classified.message}"


def known_error_keywords() -> tuple[str, ...]:
    return tuple(keyword for keywords in KEYWORDS_BY_KIND.values() for keyword in keywords)


def _first_match(text: str, keywords: Iterable[str]) -> str:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""
