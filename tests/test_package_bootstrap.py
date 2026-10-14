import os
import subprocess
import sys


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


def test_python_m_src_rejects_invalid_config_before_runtime_imports():
    env = os.environ.copy()
    env['GGSEL_PRODUCT_ID'] = 'not-a-number'
    env['DRY_RUN'] = 'true'

    completed = subprocess.run(
        [sys.executable, '-m', 'src'],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 2
    assert 'Configuration error:' in completed.stderr
    assert 'GGSEL_PRODUCT_ID must be an integer' in completed.stderr
    assert 'Traceback' not in completed.stderr
