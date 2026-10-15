"""Construye los dos ejecutables portables en el sistema actual."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "pescaauto" / "assets"
DIST = ROOT / "dist"


def build(name, entry, windowed=False):
    (ROOT / "build" / "specs").mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--name", name, "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build" / "specs"),
    ]
    if sys.platform == "win32":
        command.extend(["--icon", str(ASSETS / "pescaauto.ico"),
                        "--exclude-module=Xlib"])
        if not windowed:
            command.append("--hidden-import=pescaauto.platform_windows")
    else:
        command.extend(["--exclude-module=pescaauto.platform_windows",
                        "--exclude-module=pescaauto.process_windows"])
    if windowed:
        command.extend(["--windowed", "--add-data",
                        f"{ASSETS}{os.pathsep}pescaauto/assets"])
        if sys.platform == "win32":
            command.append("--hidden-import=pescaauto.process_windows")
    else:
        command.append("--console")
    command.append(str(ROOT / entry))
    subprocess.run(command, cwd=ROOT, check=True)


def make_archive():
    shutil.copy2(ASSETS / "pescaauto.png", DIST / "PescaAuto.png")
    if sys.platform == "win32":
        archive = DIST / "PescaAuto-Windows.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            for name in ("PescaAuto.exe", "PescaAutoMotor.exe", "PescaAuto.png"):
                package.write(DIST / name, name)
            package.write(ROOT / "README.md", "README.md")
            package.write(ROOT / "docs" / "DESARROLLO.md", "docs/DESARROLLO.md")
    else:
        archive = DIST / "PescaAuto-Linux.tar.gz"
        with tarfile.open(archive, "w:gz") as package:
            for name in ("PescaAuto", "PescaAutoMotor", "PescaAuto.png"):
                package.add(DIST / name, arcname=name)
            package.add(ROOT / "CrearAccesoDirecto", arcname="CrearAccesoDirecto")
            package.add(ROOT / "README.md", arcname="README.md")
            package.add(ROOT / "docs" / "DESARROLLO.md", arcname="docs/DESARROLLO.md")
    print(f"Paquete listo: {archive}")


def main():
    build("PescaAutoMotor", "pesca_auto.py")
    build("PescaAuto", "pesca_auto_gui.py", windowed=True)
    make_archive()


if __name__ == "__main__":
    main()
