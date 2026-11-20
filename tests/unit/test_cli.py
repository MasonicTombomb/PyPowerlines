import pytest

import pypowerlines
from pypowerlines.cli import main


def test_version_is_set() -> None:
    assert pypowerlines.__version__


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert pypowerlines.__version__ in capsys.readouterr().out


def test_no_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: pypowerlines" in capsys.readouterr().out
