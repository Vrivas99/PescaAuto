"""El acceso directo Linux debe apuntar al ejecutable portable y su icono."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pescaauto.paths import PROJECT_ROOT


@unittest.skipIf(sys.platform == "win32", "El acceso directo es de Linux")
class LauncherTests(unittest.TestCase):
    def test_portable_desktop_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            shutil.copy2(PROJECT_ROOT / "CrearAccesoDirecto", folder)
            binary = folder / "PescaAuto"
            binary.write_text("", encoding="utf-8")
            binary.chmod(0o755)
            (folder / "PescaAuto.png").write_bytes(b"icon")
            subprocess.run([str(folder / "CrearAccesoDirecto")], check=True,
                           capture_output=True, text=True)
            desktop = (folder / "PescaAuto.desktop").read_text(encoding="utf-8")
            self.assertIn(f'Exec="{binary}"', desktop)
            self.assertIn(f"Icon={folder / 'PescaAuto.png'}", desktop)


if __name__ == "__main__":
    unittest.main()
