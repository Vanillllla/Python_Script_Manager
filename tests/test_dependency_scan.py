from pathlib import Path

from pysm.services.dependencies import DependencyService


def test_scan_imports_filters_stdlib(tmp_path: Path) -> None:
    script = tmp_path / "demo.py"
    script.write_text(
        "import os\nimport requests\nfrom bs4 import BeautifulSoup\nfrom .local import helper\n",
        encoding="utf-8",
    )
    service = DependencyService()
    imports = service.scan_imports(script)
    assert imports == ["bs4", "requests"]


def test_build_report_maps_common_package_names(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "demo.py"
    script.write_text("import yaml\n", encoding="utf-8")
    service = DependencyService()
    monkeypatch.setattr(service, "get_installed_modules", lambda _: [])
    report = service.build_report(script, tmp_path / "python.exe")
    assert report.missing_modules == ["pyyaml"]

