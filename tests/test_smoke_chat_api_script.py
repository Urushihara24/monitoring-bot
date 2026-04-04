import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'smoke_chat_api.py'


def _run_script(args, env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    return result


def test_explicit_digiseller_profile_disabled_returns_nonzero():
    result = _run_script(
        ['--profile', 'digiseller'],
        {
            'DIGISELLER_ENABLED': 'false',
            'GGSEL_ENABLED': 'false',
        },
    )
    assert result.returncode == 1
    assert '[digiseller] disabled' in result.stdout


def test_explicit_ggsel_profile_disabled_returns_nonzero():
    result = _run_script(
        ['--profile', 'ggsel'],
        {
            'DIGISELLER_ENABLED': 'false',
            'GGSEL_ENABLED': 'false',
        },
    )
    assert result.returncode == 1
    assert '[ggsel] disabled' in result.stdout


def test_all_profiles_disabled_still_returns_zero():
    result = _run_script(
        [],
        {
            'DIGISELLER_ENABLED': 'false',
            'GGSEL_ENABLED': 'false',
        },
    )
    assert result.returncode == 0
    assert '[ggsel] skipped (disabled)' in result.stdout
    assert '[digiseller] skipped (disabled)' in result.stdout
