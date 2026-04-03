from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SCRIPT = ROOT / 'scripts' / 'systemd_watchdog.sh'


def _write_executable(path: Path, content: str):
    path.write_text(content, encoding='utf-8')
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _prepare_app(
    tmp_path: Path,
    *,
    health_exit: int,
    smoke_exit: int,
) -> tuple[Path, Path, Path, Path]:
    app_dir = tmp_path / 'app'
    (app_dir / 'scripts').mkdir(parents=True, exist_ok=True)
    (app_dir / 'data').mkdir(parents=True, exist_ok=True)

    health_script = (
        '#!/usr/bin/env python3\n'
        'import sys\n'
        f'sys.exit({int(health_exit)})\n'
    )
    _write_executable(app_dir / 'healthcheck.py', health_script)

    smoke_script = (
        '#!/usr/bin/env python3\n'
        'import os\n'
        'from pathlib import Path\n'
        'Path(os.environ["SMOKE_MARKER"]).write_text("ran", encoding="utf-8")\n'
        f'raise SystemExit({int(smoke_exit)})\n'
    )
    _write_executable(app_dir / 'scripts' / 'smoke_profiles_api.py', smoke_script)

    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    systemctl_log = tmp_path / 'systemctl.log'
    fake_systemctl = (
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        'echo "$*" >> "${SYSTEMCTL_LOG}"\n'
    )
    _write_executable(bin_dir / 'systemctl', fake_systemctl)
    smoke_marker = tmp_path / 'smoke.marker'
    return app_dir, bin_dir, systemctl_log, smoke_marker


def _run_watchdog(
    *,
    app_dir: Path,
    bin_dir: Path,
    systemctl_log: Path,
    smoke_marker: Path,
    watch_smoke: int,
    service_name: str = 'monitoring-bot.service',
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            'APP_DIR': str(app_dir),
            'BOT_SERVICE_NAME': service_name,
            'WATCHDOG_RUN_SMOKE': str(watch_smoke),
            'PYTHON_BIN': sys.executable,
            'SYSTEMCTL_LOG': str(systemctl_log),
            'SMOKE_MARKER': str(smoke_marker),
            'PATH': f'{bin_dir}{os.pathsep}{env.get("PATH", "")}',
        }
    )
    return subprocess.run(
        ['bash', str(WATCHDOG_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_watchdog_ok_when_health_and_smoke_pass(tmp_path: Path):
    app_dir, bin_dir, systemctl_log, smoke_marker = _prepare_app(
        tmp_path,
        health_exit=0,
        smoke_exit=0,
    )
    proc = _run_watchdog(
        app_dir=app_dir,
        bin_dir=bin_dir,
        systemctl_log=systemctl_log,
        smoke_marker=smoke_marker,
        watch_smoke=1,
    )
    assert proc.returncode == 0
    assert '[watchdog] ok' in proc.stdout
    assert smoke_marker.exists()
    assert not systemctl_log.exists()


def test_watchdog_restarts_on_healthcheck_failure(tmp_path: Path):
    app_dir, bin_dir, systemctl_log, smoke_marker = _prepare_app(
        tmp_path,
        health_exit=1,
        smoke_exit=0,
    )
    proc = _run_watchdog(
        app_dir=app_dir,
        bin_dir=bin_dir,
        systemctl_log=systemctl_log,
        smoke_marker=smoke_marker,
        watch_smoke=1,
        service_name='custom-bot.service',
    )
    assert proc.returncode == 0
    assert 'reason=stale_or_missing_heartbeat' in proc.stdout
    assert systemctl_log.exists()
    assert 'restart custom-bot.service' in systemctl_log.read_text(encoding='utf-8')
    assert not smoke_marker.exists()


def test_watchdog_restarts_on_smoke_failure(tmp_path: Path):
    app_dir, bin_dir, systemctl_log, smoke_marker = _prepare_app(
        tmp_path,
        health_exit=0,
        smoke_exit=1,
    )
    proc = _run_watchdog(
        app_dir=app_dir,
        bin_dir=bin_dir,
        systemctl_log=systemctl_log,
        smoke_marker=smoke_marker,
        watch_smoke=1,
    )
    assert proc.returncode == 0
    assert 'reason=seller_api_smoke_failed' in proc.stdout
    assert smoke_marker.exists()
    assert systemctl_log.exists()
    assert 'restart monitoring-bot.service' in systemctl_log.read_text(
        encoding='utf-8'
    )


def test_watchdog_skips_smoke_when_disabled(tmp_path: Path):
    app_dir, bin_dir, systemctl_log, smoke_marker = _prepare_app(
        tmp_path,
        health_exit=0,
        smoke_exit=1,
    )
    proc = _run_watchdog(
        app_dir=app_dir,
        bin_dir=bin_dir,
        systemctl_log=systemctl_log,
        smoke_marker=smoke_marker,
        watch_smoke=0,
    )
    assert proc.returncode == 0
    assert '[watchdog] ok' in proc.stdout
    assert not smoke_marker.exists()
    assert not systemctl_log.exists()
