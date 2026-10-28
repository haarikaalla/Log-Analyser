import pytest

from log_analyzer.cli import main


@pytest.mark.parametrize("value", ["0", "-60", "abc"])
def test_cli_rejects_invalid_bucket_size(value, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["sample_logs/app.log", "--bucket-seconds", value])
    assert exit_info.value.code == 2
    assert "must be a positive integer" in capsys.readouterr().err
