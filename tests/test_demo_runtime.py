import json
import subprocess
import sys


def test_demo_runtime_executes_multiple_cycles_without_real_writes():
    completed = subprocess.run(
        [
            sys.executable,
            'scripts/demo_runtime.py',
            '--mode',
            'DUMPING',
            '--competitors',
            '0.35',
            '0.37',
            '0.34',
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

    assert payload['network_calls'] == 0
    assert payload['real_marketplace_writes'] == 0
    assert len(payload['cycles']) == 3
    assert payload['cycles'][0]['before'] == 0.36
    assert all('after' in cycle for cycle in payload['cycles'])
    assert payload['final_price'] == payload['cycles'][-1]['after']
