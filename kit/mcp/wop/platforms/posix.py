"""What Mac and Linux do the same way: sh commands, sudo in a text window, detached processes."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .base import PlatformBehavior


class PosixBehavior(PlatformBehavior):
    gui_elevation: list[str] = []   # the program that asks for the password in a dialog, e.g. pkexec

    def launch_hidden(self, argv: list[str], cwd: Path) -> None:
        subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)

    def run_script_here(self, script: Path) -> int:
        os.execv("/bin/bash", ["bash", str(script)])
        return 0  # not reached: bash replaces this process

    def remove_folder_after_exit(self, folder: Path) -> None:
        shutil.rmtree(folder, ignore_errors=True)  # open files don't stop a delete here

    def run_elevated(self, commands: list[str], terminal: bool) -> bool:
        script = "; ".join(commands)
        try:
            if terminal:  # sudo asks for the password in the text window itself
                return subprocess.run(["sudo", "/bin/sh", "-c", script], stdout=subprocess.DEVNULL,
                                      check=False).returncode == 0
            return self._elevate_gui(script)
        except OSError:
            return False

    def _elevate_gui(self, script: str) -> bool:
        return subprocess.run([*self.gui_elevation, "/bin/sh", "-c", script], capture_output=True,
                              check=False).returncode == 0

    @staticmethod
    def quote(text: str | Path) -> str:
        return shlex.quote(str(text))

    @staticmethod
    def env_lines(env: dict[str, str]) -> str:
        return "\n".join(f'export {k}="{v}"' for k, v in env.items())
