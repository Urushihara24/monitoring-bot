#!/usr/bin/env python3
"""Reject obvious hard-coded credentials in Git-tracked text files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

SECRET_KEYS = (
    'TELEGRAM_BOT_TOKEN',
    'GGSEL_API_KEY',
    'GGSEL_API_SECRET',
    'GGSEL_ACCESS_TOKEN',
    'DIGISELLER_API_KEY',
    'DIGISELLER_API_SECRET',
    'DIGISELLER_ACCESS_TOKEN',
)

_ASSIGNMENT_RE = re.compile(
    r'^\s*(?:export\s+)?('
    + '|'.join(re.escape(key) for key in SECRET_KEYS)
    + r')\s*=\s*(.*?)\s*$'
)

_IGNORED_PATHS = {
    '.env.example',
}
_IGNORED_PREFIXES = (
    'tests/',
    '.git/',
)
_PLACEHOLDER_PREFIXES = (
    'your_',
    'example',
    'placeholder',
    '<',
    '${',
)


def _normalize_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def looks_like_real_secret(raw: str) -> bool:
    """Conservatively identify literal secret-looking assignment values."""
    value = _normalize_value(raw)
    if not value or len(value) < 8:
        return False

    lower = value.lower()
    if lower.startswith(_PLACEHOLDER_PREFIXES):
        return False

    # Runtime interpolation / code expressions are not hard-coded values.
    if any(marker in value for marker in ('{', '}', '$(', '`')):
        return False
    if 'os.getenv' in value or 'os.environ' in value:
        return False

    return True


def scan_lines(lines: Iterable[str], *, source: str = '<memory>') -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        match = _ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        if looks_like_real_secret(raw_value):
            findings.append(f'{source}:{line_number}: {key}=<redacted>')
    return findings


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ['git', 'ls-files', '-z'],
        check=True,
        capture_output=True,
    )
    paths = completed.stdout.decode('utf-8').split('\0')
    return [Path(path) for path in paths if path]


def scan_repository(paths: Iterable[Path] | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths if paths is not None else tracked_files():
        normalized = path.as_posix()
        if normalized in _IGNORED_PATHS or normalized.startswith(_IGNORED_PREFIXES):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_lines(text.splitlines(), source=normalized))
    return findings


def main() -> int:
    findings = scan_repository()
    if not findings:
        print('secret-scan: no obvious hard-coded credential assignments found')
        return 0

    print('secret-scan: potential hard-coded credentials found:', file=sys.stderr)
    for finding in findings:
        print(f'- {finding}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
