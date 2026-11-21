import os
import subprocess
import sys
from pathlib import Path


WINDOWS = sys.platform == "win32"
APP_DATA = (
    Path(os.environ["LOCALAPPDATA"])
    if WINDOWS else Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
) / "bilibili-network"


def downloads_folder():
    if WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            return Path(os.path.expandvars(value))
        except OSError:
            pass
    else:
        try:
            directory = subprocess.check_output(["xdg-user-dir", "DOWNLOAD"], text=True, timeout=3).strip()
            if directory and Path(directory).is_absolute():
                return Path(directory)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Downloads"
