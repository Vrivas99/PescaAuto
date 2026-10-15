"""Proceso auxiliar sin ventana de consola en Windows."""

import os
import subprocess
import threading

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal


class WindowsProcess(QObject):
    started = pyqtSignal()
    readyReadStandardOutput = pyqtSignal()
    readyReadStandardError = pyqtSignal()
    finished = pyqtSignal(int, object)
    errorOccurred = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cwd = None
        self.child = None
        self.error_message = ""
        self.buffers = {"stdout": bytearray(), "stderr": bytearray()}
        self.lock = threading.Lock()
        self.readers = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)

    def setWorkingDirectory(self, directory):
        self.cwd = directory

    def setProcessChannelMode(self, _mode):
        pass

    def start(self, program, arguments):
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            self.child = subprocess.Popen(
                [program, *arguments], cwd=self.cwd,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
                env=environment,
            )
        except OSError as exc:
            self.error_message = str(exc)
            self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            return
        self.readers = [
            threading.Thread(target=self._read, args=(channel, stream), daemon=True)
            for channel, stream in (("stdout", self.child.stdout),
                                    ("stderr", self.child.stderr))
        ]
        for thread in self.readers:
            thread.start()
        self.timer.start(40)
        self.started.emit()

    def _read(self, channel, stream):
        signal = self.readyReadStandardOutput if channel == "stdout" else self.readyReadStandardError
        try:
            while chunk := os.read(stream.fileno(), 4096):
                with self.lock:
                    self.buffers[channel].extend(chunk)
                signal.emit()
        finally:
            stream.close()

    def _poll(self):
        if self.child is None or self.child.poll() is None:
            return
        self.timer.stop()
        for thread in self.readers:
            thread.join(timeout=0.2)
        code = self.child.returncode
        status = QProcess.ExitStatus.NormalExit if code == 0 else QProcess.ExitStatus.CrashExit
        self.finished.emit(code, status)

    def _take(self, channel):
        with self.lock:
            data = bytes(self.buffers[channel])
            self.buffers[channel].clear()
        return data

    def readAllStandardOutput(self):
        return self._take("stdout")

    def readAllStandardError(self):
        return self._take("stderr")

    def state(self):
        if self.child is not None and self.child.poll() is None:
            return QProcess.ProcessState.Running
        return QProcess.ProcessState.NotRunning

    def processId(self):
        return self.child.pid if self.child is not None else 0

    def exitCode(self):
        return self.child.returncode if self.child is not None else -1

    def errorString(self):
        return self.error_message

    def kill(self):
        if self.state() == QProcess.ProcessState.Running:
            self.child.kill()

    def waitForFinished(self, timeout):
        if self.child is None:
            return True
        try:
            self.child.wait(timeout=timeout / 1000)
        except subprocess.TimeoutExpired:
            return False
        self._poll()
        return True
