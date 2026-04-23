import pytest

from pysm.cli.app import main, normalize_legacy_args


def test_cli_lang_override_localizes_help(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("PYSM_HOME", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["--lang", "ru", "--help"])
    output = capsys.readouterr().out
    assert "Локальный Windows-first менеджер Python-скриптов." in output


def test_legacy_arg_normalization_preserves_lang() -> None:
    argv = ["--lang", "ru", "--add-script", "--script-path", r"C:\scripts\demo.py"]
    assert normalize_legacy_args(argv) == [
        "--lang",
        "ru",
        "scripts",
        "add",
        "--script-path",
        r"C:\scripts\demo.py",
    ]
