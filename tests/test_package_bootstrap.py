import os
import subprocess
import sys

from src.__main__ import _print_write_safety_banner


def _run_src_with(env_overrides):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, '-m', 'src'],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_importing_package_does_not_eagerly_import_runtime_graph():
    completed = subprocess.run(
        [
            sys.executable,
            '-c',
            (
                "import sys; import src; "
                "assert 'src.config' not in sys.modules; "
                "assert 'src.scheduler' not in sys.modules; "
                "assert 'src.telegram_bot' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_python_m_src_rejects_invalid_id_before_runtime_imports():
    completed = _run_src_with(
        {
            'GGSEL_PRODUCT_ID': 'not-a-number',
            'DRY_RUN': 'true',
        }
    )

    assert completed.returncode == 2
    assert 'Configuration error:' in completed.stderr
    assert 'GGSEL_PRODUCT_ID must be numeric' in completed.stderr
    assert 'Startup safety:' not in completed.stderr
    assert 'Traceback' not in completed.stderr


def test_python_m_src_rejects_invalid_boolean_before_runtime_imports():
    completed = _run_src_with(
        {
            'GGSEL_ENABLED': 'treu',
            'DRY_RUN': 'true',
        }
    )

    assert completed.returncode == 2
    assert 'GGSEL_ENABLED must be one of true/false' in completed.stderr
    assert 'Startup safety:' not in completed.stderr
    assert 'Traceback' not in completed.stderr


def test_python_m_src_rejects_fractional_integer_before_runtime_imports():
    completed = _run_src_with(
        {
            'DIGISELLER_CHECK_INTERVAL': '20.5',
            'DRY_RUN': 'true',
        }
    )

    assert completed.returncode == 2
    assert 'DIGISELLER_CHECK_INTERVAL must be an integer' in completed.stderr
    assert 'Startup safety:' not in completed.stderr
    assert 'Traceback' not in completed.stderr


def test_startup_banner_reports_dry_run(monkeypatch, capsys):
    monkeypatch.setenv('DRY_RUN', 'true')

    _print_write_safety_banner()

    captured = capsys.readouterr()
    assert 'DRY_RUN=true' in captured.err
    assert 'writes are blocked' in captured.err
    assert 'WRITES ARMED' not in captured.err


def test_startup_banner_warns_when_writes_are_armed(monkeypatch, capsys):
    monkeypatch.setenv('DRY_RUN', 'false')

    _print_write_safety_banner()

    captured = capsys.readouterr()
    assert 'WRITES ARMED' in captured.err
    assert 'DRY_RUN is false or unset' in captured.err
