"""Acceso a ventanas, pantalla, cursor y entrada en Windows."""

import ctypes
from ctypes import wintypes
import threading
import time

import mss
import numpy as np


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t
VK_F8 = 0x77
VK_F9 = 0x78


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hCursor", wintypes.HANDLE), ("ptScreenPos", POINT)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class INPUT_DATA(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", INPUT_DATA)]


ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                              wintypes.HANDLE, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT, wintypes.HANDLE, wintypes.UINT]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO),
                                    wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                    wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HANDLE
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
gdi32.SelectObject.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


def _check(ok, operation):
    if not ok:
        code = ctypes.get_last_error()
        detail = str(ctypes.WinError(code)) if code else "Windows rechazó la operación"
        raise RuntimeError(f"{operation}: {detail}")


def client_rect(window):
    rect, point = RECT(), POINT()
    _check(user32.GetClientRect(window, ctypes.byref(rect)), "GetClientRect")
    _check(user32.ClientToScreen(window, ctypes.byref(point)), "ClientToScreen")
    return point.x, point.y, rect.right - rect.left, rect.bottom - rect.top


def key_down(code):
    return bool(user32.GetAsyncKeyState(code) & 0x8000)


class WindowsBackend:
    def __init__(self):
        # Mantiene las coordenadas de WinAPI y de la captura en píxeles físicos.
        user32.SetProcessDPIAware()
        try:
            self.capture = mss.mss()
        except mss.exception.ScreenShotError as exc:
            raise RuntimeError(f"No pude iniciar la captura de pantalla: {exc}") from exc

    def has_extension(self, name):
        return name in ("XTEST", "XFIXES")

    def close(self):
        self.capture.close()

    def game_window(self, title):
        matches = []

        @ENUMPROC
        def visit(window, _unused):
            if not user32.IsWindowVisible(window) or user32.IsIconic(window):
                return True
            length = user32.GetWindowTextLengthW(window)
            if length:
                text = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(window, text, length + 1)
                if title.casefold() in text.value.casefold():
                    _, _, width, height = client_rect(window)
                    if width and height:
                        matches.append((width * height, window))
            return True

        _check(user32.EnumWindows(visit, 0), "EnumWindows")
        if not matches:
            raise RuntimeError(f"No encontré la ventana {title!r}. Abre WoW en modo ventana.")
        return max(matches, key=lambda pair: pair[0])[1]

    def focused(self, window):
        return user32.GetForegroundWindow() == window

    def pointer_in_game(self, window):
        point = POINT()
        _check(user32.GetCursorPos(ctypes.byref(point)), "GetCursorPos")
        left, top, width, height = client_rect(window)
        x, y = point.x - left, point.y - top
        if not (0 <= x < width and 0 <= y < height):
            raise RuntimeError("El cursor debe estar dentro de la ventana de WoW.")
        return x, y

    def wait_f8(self, on_idle=None):
        while key_down(VK_F8):
            if on_idle:
                on_idle()
            time.sleep(0.03)
        while not key_down(VK_F8):
            if on_idle:
                on_idle()
            time.sleep(0.03)

    def image_rgb(self, window, rect):
        x, y, width, height = rect
        left, top, game_width, game_height = client_rect(window)
        if x < 0 or y < 0 or width < 1 or height < 1 or x + width > game_width or y + height > game_height:
            raise RuntimeError("La zona calibrada quedó fuera de la ventana. Recalibra la zona.")
        try:
            shot = self.capture.grab({"left": left + x, "top": top + y,
                                      "width": width, "height": height})
        except mss.exception.ScreenShotError as exc:
            raise RuntimeError(f"No pude capturar WoW: {exc}") from exc
        return np.asarray(shot, dtype=np.uint8)[:, :, [2, 1, 0]].copy()


class NativeCursorReader:
    """Convierte el cursor visible de Windows al formato ARGB usado en la calibración."""

    def read(self):
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(info)
        _check(user32.GetCursorInfo(ctypes.byref(info)), "GetCursorInfo")
        if not info.flags & 1 or not info.hCursor:
            raise RuntimeError("Windows no muestra un cursor que pueda calibrarse.")
        width = max(1, user32.GetSystemMetrics(13))
        height = max(1, user32.GetSystemMetrics(14))
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = width
        bitmap_info.bmiHeader.biHeight = -height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        screen_dc = user32.GetDC(None)
        _check(screen_dc, "GetDC")
        memory_dc = bitmap = previous = None
        try:
            memory_dc = gdi32.CreateCompatibleDC(screen_dc)
            _check(memory_dc, "CreateCompatibleDC")
            bitmap = gdi32.CreateDIBSection(screen_dc, ctypes.byref(bitmap_info),
                                             0, ctypes.byref(bits), None, 0)
            _check(bitmap, "CreateDIBSection")
            previous = gdi32.SelectObject(memory_dc, bitmap)
            _check(previous, "SelectObject")
            ctypes.memset(bits, 0, width * height * 4)
            _check(user32.DrawIconEx(memory_dc, 0, 0, info.hCursor, width, height,
                                     0, None, 3), "DrawIconEx")
            gdi32.GdiFlush()
            bgra = np.frombuffer(ctypes.string_at(bits, width * height * 4),
                                 dtype=np.uint8).reshape(height, width, 4)
            alpha = bgra[:, :, 3].astype(np.uint32)
            if not np.any(alpha):
                alpha = np.where(np.any(bgra[:, :, :3], axis=2), 255, 0).astype(np.uint32)
            return ((alpha << 24) | (bgra[:, :, 2].astype(np.uint32) << 16)
                    | (bgra[:, :, 1].astype(np.uint32) << 8)
                    | bgra[:, :, 0].astype(np.uint32))
        finally:
            if previous:
                gdi32.SelectObject(memory_dc, previous)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)

    def close(self):
        pass


class StopHotkey:
    def __init__(self, key="F9"):
        self.key = key
        self.requested = threading.Event()
        self.shutdown = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._listen, daemon=True)

    def _listen(self):
        while not self.shutdown.is_set() and not self.requested.is_set():
            if key_down(VK_F9):
                self.requested.set()
            self.shutdown.wait(0.03)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, _type, _value, _traceback):
        self.shutdown.set()
        self.thread.join(timeout=1)


def key_code(name):
    upper = name.upper()
    if len(upper) == 1 and upper.isascii() and upper.isalnum():
        return ord(upper)
    if upper.startswith("F") and upper[1:].isdigit() and 1 <= int(upper[1:]) <= 24:
        return 0x6F + int(upper[1:])
    special = {"SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09}
    if upper in special:
        return special[upper]
    raise RuntimeError(f"Tecla no reconocida: {name!r}.")


def send_key(code, release=False):
    event = INPUT(type=1, data=INPUT_DATA(ki=KEYBDINPUT(
        wVk=code, dwFlags=0x0002 if release else 0)))
    _check(user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)), "SendInput")


def send_right_button(release=False):
    event = INPUT(type=0, data=INPUT_DATA(mi=MOUSEINPUT(
        dwFlags=0x0010 if release else 0x0008)))
    _check(user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)), "SendInput")


def move_mouse(window, x, y):
    left, top, _, _ = client_rect(window)
    _check(user32.SetCursorPos(left + x, top + y), "SetCursorPos")
