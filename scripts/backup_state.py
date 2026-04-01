#!/usr/bin/env python3
"""
Ручной backup SQLite state.db
"""

import os
import shutil
from datetime import datetime
from pathlib import Path


def main():
    source = Path(os.getenv('BACKUP_SOURCE_DB', 'data/state.db'))
    backup_dir = Path(os.getenv('BACKUP_DIR', 'data/backups'))
    keep = int(os.getenv('BACKUP_KEEP', '20'))

    if not source.exists():
        print(f'backup: source db not found: {source}')
        return 1

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = backup_dir / f'state-{stamp}.db'
    shutil.copy2(source, dest)
    print(f'backup: created {dest}')

    backups = sorted(backup_dir.glob('state-*.db'))
    if len(backups) > keep:
        to_delete = backups[: len(backups) - keep]
        for item in to_delete:
            item.unlink(missing_ok=True)
            print(f'backup: removed old {item}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
