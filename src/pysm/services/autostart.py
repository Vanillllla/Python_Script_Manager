from __future__ import annotations

import os
import subprocess
import sys

from pysm.domain.exceptions import PysmError


class AutostartService:
    TASK_NAME = "PythonScriptManager"

    def enable_manager_autostart(self) -> None:
        target = _build_launch_command()
        result = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/SC",
                "ONLOGON",
                "/TN",
                self.TASK_NAME,
                "/TR",
                target,
                "/RL",
                "LIMITED",
                "/F",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PysmError(
                code="autostart.manager_enable_failed",
                message_key="errors.autostart.manager_enable_failed",
            )

    def disable_manager_autostart(self) -> None:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", self.TASK_NAME, "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, 1):
            raise PysmError(
                code="autostart.manager_disable_failed",
                message_key="errors.autostart.manager_disable_failed",
            )


def _build_launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" serve'
    python_exe = sys.executable
    command = f'"{python_exe}" -m pysm serve'
    if os.environ.get("PYSM_HOME"):
        command = f'cmd /c "set PYSM_HOME={os.environ["PYSM_HOME"]} && {command}"'
    return command

