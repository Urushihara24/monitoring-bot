from argparse import Namespace

from scripts.demo_runtime import simulate


def test_demo_runtime_reports_zero_external_effects():
    result = simulate(
        Namespace(
            competitors=[0.35, 0.34],
            current=0.36,
            mode='FOLLOW',
            min_price=0.25,
            max_price=10.0,
            desired_price=0.35,
            undercut=0.0051,
            raise_value=0.0049,
            round_step=0.01,
            max_down_step=0.03,
            ignore_delta=0.001,
            output_format='json',
        )
    )

    assert result['network_calls'] == 0
    assert result['real_marketplace_writes'] == 0
    assert result['final_price'] == 0.34
