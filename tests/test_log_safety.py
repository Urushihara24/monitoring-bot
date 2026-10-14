import logging

from src.log_safety import install_log_redaction, redact_text


def test_redact_text_removes_known_environment_secrets():
    env = {
        'GGSEL_API_SECRET': 'very-secret-signing-key',
        'TELEGRAM_BOT_TOKEN': '123456:telegram-secret-token',
    }
    raw = (
        'secret=very-secret-signing-key '
        'telegram=123456:telegram-secret-token'
    )

    redacted = redact_text(raw, env=env)

    assert 'very-secret-signing-key' not in redacted
    assert '123456:telegram-secret-token' not in redacted
    assert redacted.count('<redacted>') == 2


def test_redact_text_masks_structural_tokens_without_env():
    raw = (
        'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature '
        'url=https://example.test/api?token=plain-token-value&x=1 '
        'payload={"access_token":"second-secret-value"}'
    )

    redacted = redact_text(raw, env={})

    assert 'eyJhbGciOiJIUzI1NiJ9.payload.signature' not in redacted
    assert 'plain-token-value' not in redacted
    assert 'second-secret-value' not in redacted
    assert 'Bearer <redacted>' in redacted
    assert 'token=<redacted>' in redacted


def test_global_record_factory_redacts_structured_args(monkeypatch):
    monkeypatch.setenv('GGSEL_ACCESS_TOKEN', 'runtime-access-token-value')
    install_log_redaction()

    logger = logging.getLogger('tests.log-redaction')
    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        __file__,
        1,
        'API error: %s',
        ({
            'token': 'response-token-value',
            'detail': 'runtime-access-token-value',
        },),
        None,
    )

    rendered = record.getMessage()

    assert 'response-token-value' not in rendered
    assert 'runtime-access-token-value' not in rendered
    assert rendered.count('<redacted>') >= 2


def test_global_record_factory_redacts_exception_text(monkeypatch):
    monkeypatch.setenv('GGSEL_API_SECRET', 'exception-secret-value')
    install_log_redaction()

    logger = logging.getLogger('tests.log-redaction-exception')
    try:
        raise RuntimeError('failure with exception-secret-value')
    except RuntimeError:
        import sys

        record = logger.makeRecord(
            logger.name,
            logging.ERROR,
            __file__,
            1,
            'request failed',
            (),
            sys.exc_info(),
        )

    assert record.exc_text is not None
    assert 'exception-secret-value' not in record.exc_text
    assert '<redacted>' in record.exc_text
