"""Comprobaciones de compatibilidad después de mover el código al paquete."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pescaauto import engine
from pescaauto.engine import CONFIG_PATH
from pescaauto.paths import PROJECT_ROOT, data_directory, icon_path


class EntrypointTests(unittest.TestCase):
    def test_legacy_cli_still_runs(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "pesca_auto.py"), "--help"],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("calibrar", result.stdout)
        self.assertIn("iniciar", result.stdout)

    def test_project_data_stays_in_original_location(self):
        self.assertEqual(CONFIG_PATH, PROJECT_ROOT / "config.json")
        self.assertEqual(data_directory(), PROJECT_ROOT)

    def test_data_directory_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"PESCAAUTO_DATA_DIR": directory}):
                self.assertEqual(data_directory(), Path(directory).resolve())

    def test_icon_is_available_to_gui(self):
        self.assertTrue(icon_path().is_file())

    def test_portable_data_lives_next_to_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = str(Path(directory) / "PescaAuto")
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", executable):
                self.assertEqual(data_directory(), Path(directory).resolve())

    def test_zone_calibration_uses_packaged_overlay(self):
        config = {}
        with (
            patch.object(engine, "wait_f8"),
            patch.object(engine, "pointer_in_game", side_effect=[(10, 20), (100, 120)]),
            patch("pescaauto.zone_overlay.select_zone") as preview,
            patch.object(engine, "save_config") as save,
            patch.object(engine, "log"),
        ):
            engine.calibrate(object(), None, object(), config, "zona")
        preview.assert_called_once()
        save.assert_called_once_with(config)
        self.assertEqual(config["zone"], [10, 20, 90, 100])


if __name__ == "__main__":
    unittest.main()
