#!/usr/bin/env python3
"""Ventana de control para pesca_auto.py."""

import os
import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


DIRECTORY = Path(__file__).resolve().parent


class FishingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PescaAuto")
        self.resize(640, 420)

        self.start_button = QPushButton("Iniciar")
        self.start_button.clicked.connect(self.start_fishing)
        self.status = QLabel("Listo. Pulsa Iniciar y enfoca WoW durante los 5 segundos de espera.")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Aquí aparecerá el progreso de la pesca.")
        self.log.setMaximumBlockCount(1000)
        self.log.setFont(QFont("Monospace"))
        self.hint = QLabel("Pulsa F9 para detener la pesca, incluso con WoW enfocado.")

        layout = QVBoxLayout(self)
        layout.addWidget(self.start_button)
        layout.addWidget(self.status)
        layout.addWidget(self.log)
        layout.addWidget(self.hint)

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(DIRECTORY))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.started.connect(
            lambda: self.status.setText("Pesca activa. Enfoca WoW; F9 para detener.")
        )
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)

    def append_log(self, message):
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(message)
        self.log.ensureCursorVisible()

    def start_fishing(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.log.clear()
        self.status.setText("Iniciando... enfoca WoW.")
        self.start_button.setEnabled(False)
        self.process.start(sys.executable, ["-u", str(DIRECTORY / "pesca_auto.py"), "iniciar"])

    def read_output(self):
        self.append_log(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def finished(self, exit_code, _exit_status):
        self.read_output()
        self.status.setText("Pesca detenida." if exit_code == 0 else f"Pesca terminada con error ({exit_code}).")
        self.start_button.setEnabled(True)

    def process_error(self, _error):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.append_log(f"No se pudo iniciar la pesca: {self.process.errorString()}\n")
            self.status.setText("No se pudo iniciar la pesca.")
            self.start_button.setEnabled(True)

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            try:
                os.kill(int(self.process.processId()), signal.SIGINT)
            except (OSError, ValueError):
                pass
            if not self.process.waitForFinished(2500):
                self.process.kill()
                self.process.waitForFinished(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = FishingWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
