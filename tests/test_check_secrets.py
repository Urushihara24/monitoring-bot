from pathlib import Path

from scripts.check_secrets import looks_like_real_secret, scan_lines, scan_repository


def test_secret_scanner_flags_literal_assignments_without_echoing_value():
    findings = scan_lines(
        [
            'GGSEL_API_SECRET=super-secret-value',
            'TELEGRAM_BOT_TOKEN="123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"',
        ],
        source='sample.env',
    )

    assert findings == [
        'sample.env:1: GGSEL_API_SECRET=<redacted>',
        'sample.env:2: TELEGRAM_BOT_TOKEN=<redacted>',
    ]
    assert 'super-secret-value' not in '\n'.join(findings)


def test_secret_scanner_ignores_placeholders_and_runtime_expressions():
    assert looks_like_real_secret('your_api_key_here') is False
    assert looks_like_real_secret('${GGSEL_API_SECRET}') is False
    assert looks_like_real_secret("os.getenv('GGSEL_API_SECRET')") is False
    assert looks_like_real_secret('') is False


def test_repository_scan_skips_example_and_tests(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('.env.example').write_text(
        'GGSEL_API_SECRET=your_api_key_here\n',
        encoding='utf-8',
    )
    Path('safe.py').write_text(
        "value = 'GGSEL_ACCESS_TOKEN=' + token\n",
        encoding='utf-8',
    )
    Path('bad.env').write_text(
        'DIGISELLER_API_KEY=definitely-a-real-looking-secret\n',
        encoding='utf-8',
    )

    findings = scan_repository(
        [Path('.env.example'), Path('safe.py'), Path('bad.env')]
    )

    assert findings == ['bad.env:1: DIGISELLER_API_KEY=<redacted>']
