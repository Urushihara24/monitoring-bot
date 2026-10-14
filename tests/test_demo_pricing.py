import json
import subprocess
import sys


def test_demo_pricing_runs_without_credentials():
    completed = subprocess.run(
        [
            sys.executable,
            'scripts/demo_pricing.py',
            '--mode',
            'DUMPING',
            '--competitor',
            '0.35',
            '--current',
            '0.36',
            '--format',
            'json',
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload['mode'] == 'DUMPING'
    assert payload['action'] in {'update', 'skip'}
    assert payload['target_price'] is not None
    assert payload['minimum_competitor_price'] == 0.35
