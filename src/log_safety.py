"""Central log redaction for credentials, tokens and marketplace cookies."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import Any

_REDACTED = '<redacted>'

_SECRET_ENV_KEYS = (
    'TELEGRAM_BOT_TOKEN',
    'GGSEL_API_KEY',
    'GGSEL_API_SECRET',
    'GGSEL_ACCESS_TOKEN',
    'DIGISELLER_API_KEY',
    'DIGISELLER_API_SECRET',
    'DIGISELLER_ACCESS_TOKEN',
    'COMPETITOR_COOKIES',
    'GGSEL_COMPETITOR_COOKIES',
    'DIGISELLER_COMPETITOR_COOKIES',
)

_SENSITIVE_MAPPING_KEYS = {
    'token',
    'access_token',
    'refresh_token',
    'api_key',
    'api_secret',
    'client_secret',
    'authorization',
    'cookie',
    'cookies',
    'password',
    'sign',
    'signature',
}

_AUTHORIZATION_RE = re.compile(
    r'''(?ix)
    (\bAuthorization\b["']?\s*[:=]\s*["']?)
    (?:(Bearer)\s+)?
    ([^\s,"'}]+)
    '''
)
_BEARER_RE = re.compile(
    r'(?i)(\bBearer\s+)([A-Za-z0-9._~+/=-]{8,})'
)
_QUERY_SECRET_RE = re.compile(
    r'(?i)([?&](?:token|access_token|refresh_token|api_key|api_secret)=)([^&\s]+)'
)
_INLINE_SECRET_RE = re.compile(
    r'''(?ix)
    (\b(?:token|access_token|refresh_token|api_key|api_secret|client_secret|cookie|cookies|password|sign|signature)\b
     ["']?\s*[:=]\s*["']?)
    ([^\s,"'}]+)
    '''
)


def _environment_secrets(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    source = os.environ if env is None else env
    values: set[str] = set()
    for key in _SECRET_ENV_KEYS:
        raw = source.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        # Very short values are likely defaults/flags and create noisy replacements.
        if len(value) >= 6:
            values.add(value)
    return tuple(sorted(values, key=len, reverse=True))


def _redact_authorization(match: re.Match[str]) -> str:
    prefix, scheme, _credential = match.groups()
    if scheme:
        return f'{prefix}{scheme} {_REDACTED}'
    return f'{prefix}{_REDACTED}'


def redact_text(text: str, *, env: Mapping[str, str] | None = None) -> str:
    """Redact known and structurally recognizable secrets from text."""
    result = str(text)

    for secret in _environment_secrets(env):
        result = result.replace(secret, _REDACTED)

    result = _AUTHORIZATION_RE.sub(_redact_authorization, result)
    result = _BEARER_RE.sub(r'\1<redacted>', result)
    result = _QUERY_SECRET_RE.sub(r'\1<redacted>', result)
    result = _INLINE_SECRET_RE.sub(r'\1<redacted>', result)
    return result


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _SENSITIVE_MAPPING_KEYS:
                redacted[key] = _REDACTED
            else:
                redacted[key] = _redact_value(item)
        return redacted
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def install_log_redaction() -> None:
    """Install a process-wide LogRecordFactory redaction layer once.

    This protects logs created by the application, helper scripts and third-party
    libraries after ``src`` is imported. Structured args and exception text are
    sanitized before handlers/formatters emit them.
    """
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, '_monitoring_bot_redaction', False):
        return

    previous_factory = current_factory

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)

        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        record.args = _redact_value(record.args)

        if isinstance(record.stack_info, str):
            record.stack_info = redact_text(record.stack_info)

        if record.exc_info and not record.exc_text:
            formatter = logging.Formatter()
            record.exc_text = redact_text(
                formatter.formatException(record.exc_info)
            )

        return record

    redacting_factory._monitoring_bot_redaction = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(redacting_factory)
