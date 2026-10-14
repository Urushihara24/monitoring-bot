import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'smoke_profiles_api.py'


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
            'DRY_RUN': 'false',
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
            'DRY_RUN': 'false',
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
            'DRY_RUN': 'false',
        },
    )
    assert result.returncode == 0
    assert '[ggsel] skipped (disabled)' in result.stdout
    assert '[digiseller] skipped (disabled)' in result.stdout


def test_mutate_without_write_probe_returns_nonzero():
    result = _run_script(
        ['--mutate'],
        {
            'DIGISELLER_ENABLED': 'false',
            'GGSEL_ENABLED': 'false',
            'DRY_RUN': 'false',
        },
    )
    assert result.returncode == 1
    assert 'invalid args' in result.stdout


def test_dry_run_blocks_write_probe_before_profile_checks():
    result = _run_script(
        ['--profile', 'all', '--write-probe'],
        {
            'DRY_RUN': 'true',
            'GGSEL_ENABLED': 'true',
            'DIGISELLER_ENABLED': 'true',
            'GGSEL_API_KEY': '',
            'GGSEL_ACCESS_TOKEN': '',
            'DIGISELLER_API_KEY': '',
            'DIGISELLER_ACCESS_TOKEN': '',
        },
    )

    assert result.returncode == 2
    assert 'blocked: DRY_RUN=true' in result.stdout
    assert 'api_access=' not in result.stdout


def test_dry_run_blocks_mutation_even_with_write_probe():
    result = _run_script(
        ['--mutate', '--write-probe'],
        {
            'DRY_RUN': 'yes',
            'GGSEL_ENABLED': 'false',
            'DIGISELLER_ENABLED': 'false',
        },
    )

    assert result.returncode == 2
    assert 'blocked: DRY_RUN=true' in result.stdout


def test_invalid_dry_run_value_fails_closed():
    result = _run_script(
        ['--write-probe'],
        {
            'DRY_RUN': 'treu',
            'GGSEL_ENABLED': 'false',
            'DIGISELLER_ENABLED': 'false',
        },
    )

    assert result.returncode == 2
    assert 'configuration error: DRY_RUN must be one of' in result.stdout
