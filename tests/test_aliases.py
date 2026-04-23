from pysm.cli.app import normalize_legacy_args


def test_add_script_alias_is_rewritten() -> None:
    argv = ["--add-script", "--script-path", r"C:\scripts\demo.py"]
    assert normalize_legacy_args(argv) == [
        "scripts",
        "add",
        "--script-path",
        r"C:\scripts\demo.py",
    ]


def test_pause_alias_is_rewritten() -> None:
    argv = ["--pause", "7"]
    assert normalize_legacy_args(argv) == ["scripts", "pause", "--script-id", "7"]

