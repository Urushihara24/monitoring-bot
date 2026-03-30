#!/usr/bin/env python3
"""
Healthcheck для контейнера:
- проверяет доступность SQLite
- проверяет свежесть last_cycle (heartbeat планировщика)
"""

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    db_path = Path(os.getenv('HEALTHCHECK_DB_PATH', 'data/state.db'))
    max_age = int(os.getenv('HEALTHCHECK_MAX_AGE_SECONDS', '300'))

    if not db_path.exists():
        print(f'healthcheck: db not found: {db_path}')
        return 1

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT last_cycle FROM state WHERE id = 1').fetchone()
    except Exception as e:
        print(f'healthcheck: sqlite error: {e}')
        return 1

    if not row:
        print('healthcheck: state row not found')
        return 1

    last_cycle_raw = row['last_cycle']
    if not last_cycle_raw:
        # startup grace: если БД новая и heartbeat ещё не записан
        return 0

    try:
        last_cycle = datetime.fromisoformat(last_cycle_raw)
    except Exception:
        print(f'healthcheck: invalid last_cycle format: {last_cycle_raw}')
        return 1

    age = (datetime.now() - last_cycle).total_seconds()
    if age > max_age:
        print(f'healthcheck: stale heartbeat age={age:.1f}s > {max_age}s')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
