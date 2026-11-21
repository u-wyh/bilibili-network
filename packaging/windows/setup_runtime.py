import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    python = Path(sys.executable)
    app = Path(__file__).resolve().parent
    library = python.parent / "Lib"
    target = library / "site-packages"
    marker = ".bili-cache-ready"
    library.mkdir(exist_ok=True)
    if not (target / marker).is_file():
        print("Installing Bilibili Cache dependencies. This only runs on first launch.", flush=True)
        with TemporaryDirectory(prefix="bili-runtime-", dir=library) as work:
            stage = Path(work) / "site-packages"
            subprocess.run([str(python), "-B", "-m", "pip", "install", "--disable-pip-version-check",
                            "-r", str(app / "requirements.txt"), "--target", str(stage)], check=True)
            (stage / marker).touch()
            try:
                stage.rename(target)
            except FileExistsError:
                if not (target / marker).is_file():
                    raise
    subprocess.Popen([str(python.with_name("pythonw.exe")), "-B", str(app / "main.py")])


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        input("Setup did not finish. Check the network and start Bilibili-Download.exe again.")
        raise SystemExit(1)
