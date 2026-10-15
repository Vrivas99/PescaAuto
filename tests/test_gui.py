"""La ventana debe poder iniciar el motor desde la nueva ubicación."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QProcess, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from pescaauto.gui import FishingWindow, worker_command  # noqa: E402


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gui_starts_package_engine(self):
        window = FishingWindow()
        loop = QEventLoop()
        window.process.finished.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        window.start_operation("pesca", ["--help"])
        loop.exec()
        self.assertEqual(window.process.state(), QProcess.ProcessState.NotRunning)
        self.assertEqual(window.process.exitCode(), 0)
        self.assertIn("calibrar", window.log.toPlainText())
        self.assertIn("automática", window.log.toPlainText())
        window.close()

    def test_bundle_uses_neighboring_worker(self):
        with patch.object(sys, "frozen", True, create=True):
            program, arguments = worker_command(["iniciar"])
        self.assertTrue(program.endswith("PescaAutoMotor.exe" if sys.platform == "win32" else "PescaAutoMotor"))
        self.assertEqual(arguments, ["iniciar"])


if __name__ == "__main__":
    unittest.main()
