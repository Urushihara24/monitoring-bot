import stat

from scripts.issue_access_token import _write_token_file


def test_issued_token_file_is_mode_0600_and_not_echoed(tmp_path, capsys):
    target = tmp_path / 'issued.env'
    secret = 'secret-token-value-for-test'

    result = _write_token_file(target, secret)

    assert result == target
    assert target.read_text(encoding='utf-8') == (
        'GGSEL_ACCESS_TOKEN=' + secret + '\n'
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
