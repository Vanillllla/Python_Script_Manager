from __future__ import annotations

import ast
import json
import logging
import subprocess
import sys
from pathlib import Path

from pysm.domain.models import DependencyReport


LOGGER = logging.getLogger(__name__)

COMMON_IMPORT_PACKAGE_MAP = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "pil": "pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
}


class DependencyService:
    def scan_imports(self, script_path: Path) -> list[str]:
        tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    imports.add(node.module.split(".")[0])
        return sorted(name for name in imports if name and name not in sys.stdlib_module_names)

    def get_installed_modules(self, python_executable: Path) -> list[str]:
        result = subprocess.run(
            [str(python_executable), "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.warning("pip list failed for %s: %s", python_executable, result.stderr.strip())
            return []
        packages = json.loads(result.stdout or "[]")
        return sorted(str(item["name"]) for item in packages)

    def build_report(self, script_path: Path, python_executable: Path) -> DependencyReport:
        imports = self.scan_imports(script_path)
        installed = self.get_installed_modules(python_executable)
        installed_normalized = {_normalize(name) for name in installed}
        missing = []
        for module in imports:
            package = COMMON_IMPORT_PACKAGE_MAP.get(module.lower(), module)
            if _normalize(package) not in installed_normalized:
                missing.append(package)
        return DependencyReport(imports=imports, missing_modules=sorted(set(missing)), installed_modules=installed)


def _normalize(name: str) -> str:
    return name.replace("_", "-").lower()

