"""Vista previa transparente de la zona durante la calibración."""

import time
import sys

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget
if sys.platform == "win32":
    from .platform_windows import VK_F8, client_rect, key_down
else:
    from Xlib import XK


class ZoneOverlay(QWidget):
    def __init__(self, origin, size, start):
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(origin[0], origin[1], size[0], size[1])
        self.start = start
        self.end = start

    def set_end(self, point):
        if point != self.end:
            self.end = point
            self.update()

    def paintEvent(self, _event):
        x1, y1 = self.start
        x2, y2 = self.end
        if x2 <= x1 or y2 <= y1:
            return
        rectangle = QRect(x1, y1, x2 - x1, y2 - y1)
        painter = QPainter(self)
        painter.fillRect(rectangle, QColor(0, 190, 80, 55))
        painter.setPen(QPen(QColor(0, 220, 90), 2))
        painter.drawRect(rectangle.adjusted(1, 1, -1, -1))


def select_zone(dpy, game, start, pointer_in_game, wait_f8):
    """Dibuja la vista previa hasta que la segunda pulsación de F8 la cierra."""
    arguments = ["PescaAuto"] if sys.platform == "win32" else ["PescaAuto", "-platform", "xcb"]
    app = QApplication.instance() or QApplication(arguments)
    if sys.platform == "win32":
        left, top, width, height = client_rect(game)
        screen = next(
            (candidate for candidate in app.screens()
             if candidate.geometry().x() <= left < candidate.geometry().x()
             + candidate.geometry().width() * candidate.devicePixelRatio()
             and candidate.geometry().y() <= top < candidate.geometry().y()
             + candidate.geometry().height() * candidate.devicePixelRatio()),
            app.primaryScreen(),
        )
        scale = screen.devicePixelRatio()
        screen_origin = screen.geometry().topLeft()
        left = screen_origin.x() + round((left - screen_origin.x()) / scale)
        top = screen_origin.y() + round((top - screen_origin.y()) / scale)
        width, height = round(width / scale), round(height / scale)
        start = (round(start[0] / scale), round(start[1] / scale))
    else:
        root = dpy.screen().root
        origin = root.translate_coords(game, 0, 0)
        geometry = game.get_geometry()
        left, top, width, height = origin.x, origin.y, geometry.width, geometry.height
    overlay = ZoneOverlay(
        (left, top), (width, height), start
    )

    def update_preview():
        app.processEvents()
        try:
            point = pointer_in_game(dpy, game)
            if sys.platform == "win32":
                point = (round(point[0] / scale), round(point[1] / scale))
            overlay.set_end(point)
        except RuntimeError:
            pass  # El cursor puede salir momentáneamente de WoW.

    overlay.show()
    overlay.raise_()
    try:
        update_preview()
        if sys.platform == "win32":
            is_pressed = lambda: key_down(VK_F8)
        else:
            code = dpy.keysym_to_keycode(XK.XK_F8)
            is_pressed = lambda: bool(dpy.query_keymap()[code // 8] & (1 << (code % 8)))
        while is_pressed():
            update_preview()
            time.sleep(0.03)
        wait_f8(dpy, on_idle=update_preview)
    finally:
        overlay.close()
        app.processEvents()
