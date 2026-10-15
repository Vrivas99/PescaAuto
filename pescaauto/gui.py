#!/usr/bin/env python3
"""Ventana de control para pesca_auto.py."""

import codecs
import os
import signal
import sys

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .paths import application_directory, icon_path
if sys.platform == "win32":
    from .process_windows import WindowsProcess

DIRECTORY = application_directory()


def worker_command(arguments):
    if getattr(sys, "frozen", False):
        name = "PescaAutoMotor.exe" if sys.platform == "win32" else "PescaAutoMotor"
        return str(DIRECTORY / name), arguments
    return sys.executable, ["-u", "-m", "pescaauto.engine", *arguments]


class FishingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PescaAuto")
        self.setWindowIcon(QIcon(str(icon_path())))
        self.resize(640, 420)

        self.start_button = QPushButton("Iniciar")
        self.start_button.clicked.connect(self.toggle_fishing)
        self.set_start_button_running(False)
        self.zone_button = QPushButton("Calibrar zona")
        self.zone_button.clicked.connect(self.calibrate_zone)
        self.cursor_button = QPushButton("Calibrar cursor")
        self.cursor_button.clicked.connect(self.calibrate_cursor)
        self.buttons = (self.start_button, self.zone_button, self.cursor_button)
        self.operation = None
        self.stop_requested = False
        self.status = QLabel("Listo. Elige una acción y enfoca WoW cuando se indique.")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Aquí aparecerán las instrucciones y el progreso.")
        self.log.setMaximumBlockCount(1000)
        self.log.setFont(QFont("Monospace"))
        dark_background = self.log.palette().color(QPalette.ColorRole.Base).lightness() < 128
        colors = (
            {"INFO": "#b0bec5", "WARN": "#ffd54f", "ERROR": "#ff6b6b", "OK": "#66bb6a"}
            if dark_background else
            {"INFO": "#5f6368", "WARN": "#9a6700", "ERROR": "#c62828", "OK": "#2e7d32"}
        )
        self.log_formats = {}
        for level, color in colors.items():
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            self.log_formats[level] = text_format
        self.reset_output()
        self.hint = QLabel("F8 confirma cada paso de la calibración. F9 detiene la pesca.")

        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        for button in self.buttons:
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        layout.addWidget(self.log)
        layout.addWidget(self.hint)

        self.process = WindowsProcess(self) if sys.platform == "win32" else QProcess(self)
        self.process.setWorkingDirectory(str(DIRECTORY))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.started.connect(self.process_started)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)

    def reset_output(self):
        self.output_buffers = {"stdout": "", "stderr": ""}
        self.output_decoders = {
            channel: codecs.getincrementaldecoder("utf-8")(errors="replace")
            for channel in self.output_buffers
        }

    def append_log(self, message, fallback="INFO"):
        message = message.rstrip("\r")
        if not message:
            return
        level = message.split("]", 1)[0][1:] if message.startswith("[") else ""
        if level not in self.log_formats:
            level = fallback
            message = f"[{level}] {message}"
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(message + "\n", self.log_formats[level])
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def consume_output(self, channel, data, final=False):
        decoded = self.output_decoders[channel].decode(bytes(data), final=final)
        lines = (self.output_buffers[channel] + decoded).split("\n")
        self.output_buffers[channel] = lines.pop()
        for line in lines:
            self.append_log(line, "ERROR" if channel == "stderr" else "INFO")
        if final and self.output_buffers[channel]:
            self.append_log(self.output_buffers[channel], "ERROR" if channel == "stderr" else "INFO")
            self.output_buffers[channel] = ""

    def set_start_button_running(self, running):
        self.start_button.setText("Detener" if running else "Iniciar")
        color = "#c62828" if running else "#2e7d32"
        self.start_button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; padding: 6px; }}"
        )

    def toggle_fishing(self):
        if self.operation == "pesca" and self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_fishing()
        else:
            self.start_fishing()

    def start_fishing(self):
        self.start_operation("pesca", ["iniciar"])

    def stop_fishing(self):
        if self.process.state() != QProcess.ProcessState.Running:
            return
        self.stop_requested = True
        self.start_button.setEnabled(False)
        self.status.setText("Deteniendo pesca...")
        process_id = int(self.process.processId())
        if sys.platform == "win32":
            self.process.kill()
            return
        try:
            os.kill(process_id, signal.SIGINT)
        except (OSError, ValueError):
            self.process.kill()
            return
        QTimer.singleShot(2500, lambda: self.force_stop_if_running(process_id))

    def force_stop_if_running(self, process_id):
        if (
            self.process.state() != QProcess.ProcessState.NotRunning
            and int(self.process.processId()) == process_id
        ):
            self.process.kill()

    def calibrate_zone(self):
        self.start_operation("zona", ["calibrar", "zona"])

    def calibrate_cursor(self):
        self.start_operation("cursor", ["calibrar", "cursor"])

    def start_operation(self, operation, arguments):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.operation = operation
        self.stop_requested = False
        self.log.clear()
        self.reset_output()
        self.status.setText("Iniciando... enfoca WoW.")
        for button in self.buttons:
            button.setEnabled(False)
        program, params = worker_command(arguments)
        self.process.start(program, params)

    def process_started(self):
        if self.operation == "pesca":
            self.set_start_button_running(True)
            self.start_button.setEnabled(True)
            self.status.setText("Pesca activa. Enfoca WoW; usa Detener o F9 para pararla.")
        else:
            self.status.setText(
                f"Calibrando {self.operation}. Enfoca WoW y sigue las instrucciones del registro."
            )

    def read_output(self):
        self.consume_output("stdout", self.process.readAllStandardOutput())

    def read_error(self):
        self.consume_output("stderr", self.process.readAllStandardError())

    def finished(self, exit_code, _exit_status):
        self.read_output()
        self.read_error()
        self.consume_output("stdout", b"", final=True)
        self.consume_output("stderr", b"", final=True)
        if self.operation == "pesca":
            message = (
                "Pesca detenida." if exit_code == 0 or self.stop_requested
                else f"Pesca terminada con error ({exit_code})."
            )
        elif exit_code == 0:
            message = f"Calibración de {self.operation} completada."
        else:
            message = f"Calibración de {self.operation} terminada con error ({exit_code})."
        self.status.setText(message)
        self.set_start_button_running(False)
        for button in self.buttons:
            button.setEnabled(True)

    def process_error(self, _error):
        if _error == QProcess.ProcessError.FailedToStart:
            operation = "la pesca" if self.operation == "pesca" else f"la calibración de {self.operation}"
            self.append_log(f"[ERROR] No se pudo iniciar {operation}: {self.process.errorString()}")
            self.status.setText(f"No se pudo iniciar {operation}.")
            self.set_start_button_running(False)
            for button in self.buttons:
                button.setEnabled(True)

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if sys.platform == "win32":
                self.process.kill()
                self.process.waitForFinished(1000)
            else:
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
