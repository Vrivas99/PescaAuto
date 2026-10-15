#!/usr/bin/env python3
"""Pesca automática para WoW 3.3.5a en Linux y Windows.

Compara el agua antes y después de lanzar, confirma el corcho con el cursor
de tuerca y usa las API del sistema para interactuar. No lee la memoria del juego.
"""

import argparse
import ctypes
import ctypes.util
import json
import select
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np
if sys.platform == "win32":
    from . import platform_windows as windows
    DISPLAY_ERRORS = (OSError,)
else:
    from Xlib import X, XK, display, error
    from Xlib.ext import xtest
    DISPLAY_ERRORS = (error.XError, error.DisplayConnectionError)

from .paths import data_directory

CONFIG_PATH = data_directory() / "config.json"
POLL_SECONDS = 0.10
BITE_POLL_SECONDS = 0.025
CAST_SECONDS = 23.0
SETTLE_SECONDS = 1.0
FIND_RETRY_SECONDS = 0.4
BITE_ARM_SECONDS = 2.0
EARLY_BITE_PIXELS = 18
EARLY_BITE_CLUSTER = 16
LATE_BITE_PIXELS = 25
LATE_BITE_CLUSTER = 16
BOBBER_MIN_PIXELS = 40
BOBBER_SINK_RATIO = 0.82
FRAME_SAMPLES = 5
STOP_KEY = "F9"
BUFF_KEY = "2"
BUFF_INTERVAL_SECONDS = 10 * 60
BUFF_WAIT_SECONDS = 4
_active_stop_hotkey = None


def log(level, message):
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{level}] {message}", file=stream, flush=True)


class StopRequested(Exception):
    """El usuario detuvo la pesca con la tecla configurada."""


class StopHotkey:
    """Escucha F9 en una conexión X11 separada mientras WoW tiene el foco."""

    def __init__(self, key=STOP_KEY):
        self.key = key
        self.requested = threading.Event()
        self.shutdown = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._listen, daemon=True)

    def _listen(self):
        dpy = None
        root = None
        code = None
        grabbed = False
        try:
            dpy = display.Display()
            root = dpy.screen().root
            code = key_code(dpy, self.key)
            root.grab_key(code, X.AnyModifier, False, X.GrabModeAsync, X.GrabModeAsync)
            dpy.sync()
            grabbed = True
            self.ready.set()
            while not self.shutdown.is_set() and not self.requested.is_set():
                if dpy.pending_events():
                    event = dpy.next_event()
                    if event.type == X.KeyPress and event.detail == code:
                        self.requested.set()
                else:
                    select.select([dpy.fileno()], [], [], 0.1)
        except Exception as exc:
            self.error = exc
            self.requested.set()
        finally:
            self.ready.set()
            if dpy is not None:
                try:
                    if grabbed:
                        root.ungrab_key(code, X.AnyModifier)
                        dpy.sync()
                finally:
                    dpy.close()

    def __enter__(self):
        self.thread.start()
        if not self.ready.wait(5):
            self.shutdown.set()
            raise RuntimeError(f"No pude activar la tecla {self.key} para detener la pesca.")
        if self.error is not None:
            raise RuntimeError(f"No pude reservar {self.key} para detener la pesca: {self.error}")
        return self

    def __exit__(self, _type, _value, _traceback):
        self.shutdown.set()
        self.thread.join(timeout=1)


def sleep(seconds):
    """Pausa que responde de inmediato a la tecla de parada durante la pesca."""
    hotkey = _active_stop_hotkey
    if hotkey is None:
        time.sleep(seconds)
    elif hotkey.requested.wait(seconds):
        check_stop()


def check_stop():
    hotkey = _active_stop_hotkey
    if hotkey is not None and hotkey.requested.is_set():
        if hotkey.error is not None:
            raise RuntimeError(f"Falló la escucha de {hotkey.key}: {hotkey.error}")
        raise StopRequested


@dataclass(frozen=True)
class Detection:
    x: int
    y: int
    count: int


class _XFixesCursorImage(ctypes.Structure):
    # Prefijo de XFixesCursorImage en /usr/include/X11/extensions/Xfixes.h.
    _fields_ = [
        ("x", ctypes.c_short),
        ("y", ctypes.c_short),
        ("width", ctypes.c_ushort),
        ("height", ctypes.c_ushort),
        ("xhot", ctypes.c_ushort),
        ("yhot", ctypes.c_ushort),
        ("cursor_serial", ctypes.c_ulong),
        ("pixels", ctypes.POINTER(ctypes.c_ulong)),
    ]


class NativeCursorReader:
    """Lee el cursor mediante libXfixes; evita un fallo de python-xlib."""

    def __init__(self):
        x11_name = ctypes.util.find_library("X11")
        xfixes_name = ctypes.util.find_library("Xfixes")
        if not x11_name or not xfixes_name:
            raise RuntimeError("Faltan libX11 o libXfixes en el sistema.")
        self.x11 = ctypes.CDLL(x11_name)
        self.xfixes = ctypes.CDLL(xfixes_name)
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x11.XCloseDisplay.restype = ctypes.c_int
        self.x11.XFree.argtypes = [ctypes.c_void_p]
        self.x11.XFree.restype = ctypes.c_int
        self.xfixes.XFixesGetCursorImage.argtypes = [ctypes.c_void_p]
        self.xfixes.XFixesGetCursorImage.restype = ctypes.POINTER(_XFixesCursorImage)
        self.handle = self.x11.XOpenDisplay(None)
        if not self.handle:
            raise RuntimeError("libX11 no pudo abrir la pantalla gráfica para leer el cursor.")

    def read(self):
        pointer = self.xfixes.XFixesGetCursorImage(self.handle)
        if not pointer:
            raise RuntimeError("libXfixes no devolvió la imagen del cursor.")
        try:
            image = pointer.contents
            width, height = image.width, image.height
            if not (1 <= width <= 256 and 1 <= height <= 256) or not image.pixels:
                raise RuntimeError("libXfixes devolvió una imagen de cursor inválida.")
            pixels = np.ctypeslib.as_array(image.pixels, shape=(width * height,))
            return pixels.astype(np.uint32).reshape(height, width).copy()
        finally:
            self.x11.XFree(ctypes.cast(pointer, ctypes.c_void_p))

    def close(self):
        if self.handle:
            self.x11.XCloseDisplay(self.handle)
            self.handle = None


def defaults():
    return {
        "window_title": "World of Warcraft",
        "cast_key": "1",
        "click_offset": [0, 0],
        "max_casts": 0,
    }


def load_config():
    config = defaults()
    if CONFIG_PATH.exists():
        config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return config


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def game_window(dpy, title):
    if sys.platform == "win32":
        return dpy.game_window(title)
    matches = []
    pending = [dpy.screen().root]
    while pending:
        window = pending.pop()
        try:
            if title.casefold() in str(window.get_wm_name() or "").casefold():
                geometry = window.get_geometry()
                matches.append((geometry.width * geometry.height, window))
            pending.extend(window.query_tree().children)
        except error.XError:
            continue
    if not matches:
        raise RuntimeError(f"No encontré la ventana {title!r}. Abre WoW en modo ventana.")
    return max(matches, key=lambda pair: pair[0])[1]


def focused(dpy, game):
    if sys.platform == "win32":
        return dpy.focused(game)
    try:
        current = dpy.get_input_focus().focus
        root = dpy.screen().root
        while hasattr(current, "id") and current.id != root.id:
            if current.id == game.id:
                return True
            current = current.query_tree().parent
    except error.XError:
        pass
    return False


def pointer_in_game(dpy, game):
    if sys.platform == "win32":
        return dpy.pointer_in_game(game)
    root = dpy.screen().root
    pointer = root.query_pointer()
    # En python-xlib, self es la ventana de destino y el argumento es origen.
    point = game.translate_coords(root, pointer.root_x, pointer.root_y)
    geometry = game.get_geometry()
    if not (0 <= point.x < geometry.width and 0 <= point.y < geometry.height):
        raise RuntimeError("El cursor debe estar dentro de la ventana de WoW.")
    return int(point.x), int(point.y)


def wait_f8(dpy, on_idle=None):
    if sys.platform == "win32":
        return dpy.wait_f8(on_idle)
    root = dpy.screen().root
    code = dpy.keysym_to_keycode(XK.XK_F8)
    root.grab_key(code, X.AnyModifier, False, X.GrabModeAsync, X.GrabModeAsync)
    dpy.sync()
    try:
        while True:
            if on_idle is not None and not dpy.pending_events():
                on_idle()
                if not dpy.pending_events() and not select.select([dpy.fileno()], [], [], 0.03)[0]:
                    continue
            event = dpy.next_event()
            if event.type == X.KeyPress and event.detail == code:
                return
    finally:
        root.ungrab_key(code, X.AnyModifier)
        dpy.sync()


def visual_masks(dpy, game):
    if sys.platform == "win32":
        return None
    geometry = game.get_geometry()
    visual = game.get_attributes().visual
    visual_id = getattr(visual, "id", visual)
    for allowed in dpy.screen().allowed_depths:
        if allowed.depth == geometry.depth:
            for candidate in allowed.visuals:
                if candidate.visual_id == visual_id:
                    return (candidate.red_mask, candidate.green_mask, candidate.blue_mask)
    raise RuntimeError("No pude identificar el formato de color de WoW.")


def image_rgb(dpy, game, rect, masks):
    if sys.platform == "win32":
        return dpy.image_rgb(game, rect)
    x, y, width, height = rect
    geometry = game.get_geometry()
    if x < 0 or y < 0 or width < 1 or height < 1 or x + width > geometry.width or y + height > geometry.height:
        raise RuntimeError("La zona calibrada quedó fuera de la ventana. Recalibra la zona.")
    image = game.get_image(x, y, width, height, X.ZPixmap, 0xFFFFFFFF)
    if image is None:
        raise RuntimeError("No pude capturar WoW. Usa el modo ventana.")
    fmt = next((item for item in dpy.display.info.pixmap_formats if item.depth == geometry.depth), None)
    if fmt is None or fmt.bits_per_pixel not in (16, 32):
        raise RuntimeError("Formato de imagen no compatible (se requiere 16 o 32 bits por píxel).")
    bytes_per_pixel = fmt.bits_per_pixel // 8
    row_bytes = len(image.data) // height
    endian = "<" if dpy.display.info.image_byte_order == X.LSBFirst else ">"
    dtype = np.dtype(endian + ("u2" if bytes_per_pixel == 2 else "u4"))
    raw = np.ndarray(
        (height, width), dtype=dtype, buffer=image.data,
        strides=(row_bytes, bytes_per_pixel),
    )
    channels = []
    for mask in masks:
        shift = (mask & -mask).bit_length() - 1
        maximum = mask >> shift
        channels.append(((raw & mask) >> shift).astype(np.uint32) * 255 // maximum)
    return np.stack(channels, axis=-1).astype(np.uint8)


def median_frames(dpy, game, rect, masks, count=FRAME_SAMPLES):
    """Reduce el movimiento normal del agua con varias capturas de la zona."""
    frames = []
    for index in range(count):
        frames.append(image_rgb(dpy, game, rect, masks))
        if index + 1 < count:
            sleep(POLL_SECONDS)
    stack = np.stack(frames).astype(np.int16)
    median = np.median(stack, axis=0).astype(np.int16)
    noise = np.median(np.abs(stack - median), axis=(0, 3))
    return median, noise


def change_map(before, before_noise, after, after_noise):
    """Cambios persistentes tras el lance, sin suponer un color de agua."""
    delta = np.abs(after - before).mean(axis=2)
    noise = before_noise + after_noise
    return np.maximum(delta - 2.5 * noise, 0).astype(np.float32)


def changed_candidates(before, before_noise, after, after_noise, limit=24):
    signal = change_map(before, before_noise, after, after_noise)
    height, width = signal.shape
    if height < 9 or width < 9:
        return []
    integral = np.pad(signal, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def peaks(radius, threshold, count, separation):
        size = radius * 2 + 1
        if height < size or width < size:
            return []
        scores = (integral[size:, size:] - integral[:-size, size:]
                  - integral[size:, :-size] + integral[:-size, :-size]).copy()
        found = []
        for _ in range(count):
            index = int(np.argmax(scores))
            peak = float(scores.flat[index])
            if peak < threshold:
                break
            row, col = np.unravel_index(index, scores.shape)
            found.append(Detection(int(col + radius), int(row + radius), int(peak)))
            x1, x2 = max(0, col - separation), min(scores.shape[1], col + separation + 1)
            y1, y2 = max(0, row - separation), min(scores.shape[0], row + separation + 1)
            scores[y1:y2, x1:x2] = 0
        return found

    # El corcho lejano puede ocupar pocos píxeles y quedar bajo el umbral de 19×19.
    large = peaks(radius=9, threshold=400, count=limit, separation=14)
    small = peaks(radius=4, threshold=120, count=max(1, limit // 2), separation=8)
    options = []
    for index in range(max(len(large), len(small))):
        for group in (large, small):
            if index < len(group):
                item = group[index]
                if all((item.x - old.x) ** 2 + (item.y - old.y) ** 2 >= 8 ** 2 for old in options):
                    options.append(item)
                    if len(options) >= limit:
                        return options
    return options


def local_bobber_view(config, own):
    """Prepara una captura pequeña para seguir la picada más rápido."""
    zx, zy, width, height = config["zone"]
    radius = 38
    left, top = max(0, own.x - radius), max(0, own.y - radius)
    right, bottom = min(width, own.x + radius + 1), min(height, own.y + radius + 1)
    rect = (zx + left, zy + top, right - left, bottom - top)
    center = Detection(own.x - left, own.y - top, own.count)
    return rect, center


def largest_connected_region(mask):
    """Tamaño del mayor grupo de píxeles vecinos, incluidas diagonales."""
    remaining = set(zip(*np.nonzero(mask)))
    largest = 0
    while remaining:
        pending = [remaining.pop()]
        count = 1
        while pending:
            y, x = pending.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    neighbor = (y + dy, x + dx)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
                        count += 1
        largest = max(largest, count)
    return largest


def warm_bobber_area(frame, area):
    """Cuenta los píxeles cálidos del corcho, separados del agua azul."""
    red, green, blue = np.moveaxis(frame.astype(np.int16), -1, 0)
    return int(np.count_nonzero(
        (red > green + 25) & (red > blue + 12) & (red > 80) & area
    ))


class SplashTracker:
    """Busca un destello localizado de agua respecto al aspecto reciente."""

    def __init__(self, frames, center):
        stack = np.stack(frames).astype(np.float32)
        luminance = (stack[:, :, :, 0] * 0.299
                     + stack[:, :, :, 1] * 0.587
                     + stack[:, :, :, 2] * 0.114)
        chroma = stack[:, :, :, 2] - stack[:, :, :, 1]
        self.reference = np.median(luminance, axis=0)
        self.noise = np.median(np.abs(luminance - self.reference), axis=0)
        self.chroma_reference = np.median(chroma, axis=0)
        self.chroma_noise = np.median(np.abs(chroma - self.chroma_reference), axis=0)
        ys, xs = np.indices(self.reference.shape)
        distance = (xs - center.x) ** 2 + (ys - center.y) ** 2
        # Incluye la salpicadura cercana en corchos pequeños o lejanos.
        self.inner = (distance >= 4 ** 2) & (distance <= 32 ** 2)
        self.outer = (distance > 32 ** 2) & (distance <= 38 ** 2)
        self.bobber_area = distance <= 32 ** 2
        self.bobber_reference = warm_bobber_area(np.median(stack, axis=0), self.bobber_area)
        self.last_bobber_area = self.bobber_reference
        self.consecutive = 0
        self.last_count = 0
        self.last_cluster = 0

    def observe(self, frame):
        pixels = frame.astype(np.float32)
        luminance = pixels[:, :, 0] * 0.299 + pixels[:, :, 1] * 0.587 + pixels[:, :, 2] * 0.114
        bright = luminance - self.reference > np.maximum(24.0, self.noise * 3.0 + 12.0)
        chroma = pixels[:, :, 2] - pixels[:, :, 1]
        more_blue = chroma - self.chroma_reference > np.maximum(10.0, self.chroma_noise * 2.0 + 6.0)
        splash_pixels = bright & more_blue
        inside = int(np.count_nonzero(splash_pixels & self.inner))
        outside = int(np.count_nonzero(splash_pixels & self.outer))
        inner_area = max(1, int(self.inner.sum()))
        outer_area = max(1, int(self.outer.sum()))
        localized = inside >= 10 and inside / inner_area > (outside / outer_area) * 1.4
        self.consecutive = self.consecutive + 1 if localized else 0
        self.last_count = inside
        self.last_bobber_area = warm_bobber_area(pixels, self.bobber_area)
        self.last_cluster = (
            largest_connected_region(splash_pixels & self.inner)
            if inside >= EARLY_BITE_PIXELS else 0
        )
        if not localized:
            difference = np.abs(luminance - self.reference)
            self.noise = self.noise * 0.96 + difference * 0.04
            self.reference = self.reference * 0.96 + luminance * 0.04
            chroma_difference = np.abs(chroma - self.chroma_reference)
            self.chroma_noise = self.chroma_noise * 0.96 + chroma_difference * 0.04
            self.chroma_reference = self.chroma_reference * 0.96 + chroma * 0.04
        return self.consecutive >= 2


def bite_confirmed(tracker, splash, late_calibrated):
    if not splash:
        return False
    if not late_calibrated:
        return tracker.last_count >= EARLY_BITE_PIXELS and tracker.last_cluster >= EARLY_BITE_CLUSTER
    bobber_sank = (
        tracker.bobber_reference >= BOBBER_MIN_PIXELS
        and tracker.last_bobber_area <= tracker.bobber_reference * BOBBER_SINK_RATIO
    )
    strong_splash = (
        tracker.last_count >= LATE_BITE_PIXELS
        and tracker.last_cluster >= LATE_BITE_CLUSTER
    )
    return bobber_sank or strong_splash


def key_code(dpy, name):
    if sys.platform == "win32":
        return windows.key_code(name)
    symbol = XK.string_to_keysym(name)
    code = dpy.keysym_to_keycode(symbol)
    if not code:
        raise RuntimeError(f"Tecla no reconocida: {name!r}.")
    return code


def tap_key(dpy, code):
    check_stop()
    if sys.platform == "win32":
        windows.send_key(code)
        try:
            sleep(0.07)
        finally:
            windows.send_key(code, release=True)
        return
    xtest.fake_input(dpy, X.KeyPress, code)
    dpy.sync()
    try:
        sleep(0.07)
    finally:
        xtest.fake_input(dpy, X.KeyRelease, code)
        dpy.sync()


def right_click(dpy, game, x, y):
    check_stop()
    move_mouse(dpy, game, x, y)
    sleep(0.07)
    if sys.platform == "win32":
        windows.send_right_button()
        try:
            sleep(0.07)
        finally:
            windows.send_right_button(release=True)
        return
    xtest.fake_input(dpy, X.ButtonPress, 3)
    dpy.sync()
    try:
        sleep(0.07)
    finally:
        xtest.fake_input(dpy, X.ButtonRelease, 3)
        dpy.sync()


def move_mouse(dpy, game, x, y):
    check_stop()
    if sys.platform == "win32":
        return windows.move_mouse(game, x, y)
    root = dpy.screen().root
    point = root.translate_coords(game, x, y)
    xtest.fake_input(dpy, X.MotionNotify, x=point.x, y=point.y)
    dpy.sync()


def cursor_feature(reader):
    """Imagen ARGB del cursor, reducida a 16×16 para comparar formas."""
    pixels = reader.read()
    height, width = pixels.shape
    y = np.arange(16) * height // 16
    x = np.arange(16) * width // 16
    sampled = pixels[np.ix_(y, x)]
    channels = np.stack(
        [(sampled >> shift) & 255 for shift in (16, 8, 0, 24)], axis=-1
    ).astype(np.uint8)
    channels[channels[:, :, 3] == 0] = 0
    return channels.ravel().tolist()


def cursor_distance(first, second):
    a = np.asarray(first, dtype=np.int16)
    b = np.asarray(second, dtype=np.int16)
    if a.shape != (1024,) or b.shape != (1024,):
        raise RuntimeError("Muestras de cursor inválidas en config.json.")
    return float(np.abs(a - b).mean() / 255)


def cursor_samples(reader):
    result = []
    for _ in range(5):
        result.append(cursor_feature(reader))
        sleep(0.12)
    return result


def own_cursor(reader, config):
    sample = cursor_feature(reader)
    own = min(cursor_distance(sample, old) for old in config["own_cursor"])
    other = min(cursor_distance(sample, old) for old in config["other_cursor"])
    return own <= config["cursor_tolerance"] and own < other * 0.75


def hover_is_own(dpy, reader, game, config, item):
    zx, zy = config["zone"][:2]
    dx, dy = config["click_offset"]
    move_mouse(dpy, game, zx + item.x + dx, zy + item.y + dy)
    sleep(0.14)
    return own_cursor(reader, config)


def calibrate(dpy, reader, game, config, what):
    if what == "cursor":
        if not dpy.has_extension("XFIXES"):
            raise RuntimeError("XFixes no está disponible; no puedo reconocer el cursor de tuerca.")
        log("INFO", "Cursor: F8 sobre tu corcho con la tuerca. Mantén el mouse quieto 1 s.")
        wait_f8(dpy)
        if not focused(dpy, game):
            raise RuntimeError("WoW debe tener el foco al calibrar el cursor. Vuelve a ejecutar y enfócalo con Alt+Tab.")
        own = cursor_samples(reader)
        log("INFO", "Cursor: F8 sobre agua vacía u otro corcho. Mantén el mouse quieto 1 s.")
        wait_f8(dpy)
        if not focused(dpy, game):
            raise RuntimeError("WoW debe tener el foco al calibrar el cursor.")
        other = cursor_samples(reader)
        separation = min(cursor_distance(a, b) for a in own for b in other)
        if separation < 0.07:
            raise RuntimeError(
                "El sistema ve el mismo cursor en ambos casos. Puede que WoW dibuje la tuerca dentro de la ventana; no usaré esta señal para automatizar."
            )
        config["own_cursor"] = own
        config["other_cursor"] = other
        config["cursor_tolerance"] = min(0.22, separation * 0.65)
        save_config(config)
        log("OK", f"Cursor calibrado (separación {separation:.3f}).")
        return
    if what == "zona":
        log("INFO", "Zona: F8 en la esquina superior izquierda.")
        wait_f8(dpy)
        x1, y1 = pointer_in_game(dpy, game)
        log("INFO", "Mueve el cursor y pulsa F8 en la esquina inferior derecha.")
        from .zone_overlay import select_zone

        select_zone(dpy, game, (x1, y1), pointer_in_game, wait_f8)
        x2, y2 = pointer_in_game(dpy, game)
        if x2 - x1 < 40 or y2 - y1 < 40:
            raise RuntimeError("La zona debe medir al menos 40 × 40 píxeles.")
        config["zone"] = [x1, y1, x2 - x1, y2 - y1]
        config["coord_version"] = 2
        save_config(config)
        log("OK", f"Zona guardada: {config['zone']}.")
        return


def check_config(config, need_cursor=False):
    if "zone" in config and config.get("coord_version") != 2:
        raise RuntimeError("La zona fue guardada con coordenadas incorrectas. Repite: python3 pesca_auto.py calibrar zona")
    if "zone" not in config:
        raise RuntimeError("Falta calibrar zona. Consulta README.md.")
    if len(config["zone"]) != 4:
        raise RuntimeError("config.json no tiene un formato válido.")
    if len(config["click_offset"]) != 2:
        raise RuntimeError("click_offset debe contener dos números.")
    if int(config["max_casts"]) < 0:
        raise RuntimeError("max_casts no puede ser negativo.")
    if need_cursor and ("own_cursor" not in config or "other_cursor" not in config):
        raise RuntimeError("Falta calibrar el cursor de tuerca: python3 pesca_auto.py calibrar cursor")


def locate_own(dpy, reader, game, config, candidates):
    zx, zy, width, height = config["zone"]
    checked = set()
    # Primero los centros: con varios corchos evita rodear cada uno antes
    # de comprobar si el siguiente candidato ya muestra nuestra tuerca.
    for offsets in (((0, 0),), ((-7, 0), (7, 0), (0, -7), (0, 7))):
        for candidate in candidates:
            for dx, dy in offsets:
                x, y = candidate.x + dx, candidate.y + dy
                if (x, y) in checked or not (0 <= x < width and 0 <= y < height):
                    continue
                checked.add((x, y))
                point = Detection(x, y, candidate.count)
                if hover_is_own(dpy, reader, game, config, point):
                    if own_cursor(reader, config):
                        return point
    move_mouse(dpy, game, 5, 5)
    return None


def find_own_after_cast(dpy, reader, game, config, masks, before, before_noise, verbose=False):
    """Busca pronto el corcho y repite si todavía no terminó de caer."""
    sleep(SETTLE_SECONDS)
    for attempt in range(2):
        after, after_noise = median_frames(dpy, game, config["zone"], masks)
        candidates = changed_candidates(before, before_noise, after, after_noise)
        if verbose:
            log("INFO", f"Búsqueda {attempt + 1}: {[(c.x, c.y, c.count) for c in candidates]}")
        own = locate_own(dpy, reader, game, config, candidates)
        if own is not None:
            return own
        if attempt == 0:
            sleep(FIND_RETRY_SECONDS)
    return None


def inspect(dpy, reader, game, config, masks):
    log("INFO", "Prueba: enfoca WoW. Comienza en 5 s; no habrá clic derecho.")
    sleep(5)
    if not focused(dpy, game):
        raise RuntimeError("Enfoca la ventana de WoW antes de la prueba.")
    before, before_noise = median_frames(dpy, game, config["zone"], masks)
    tap_key(dpy, key_code(dpy, config["cast_key"]))
    own = find_own_after_cast(dpy, reader, game, config, masks, before, before_noise, verbose=True)
    if own is None:
        log("WARN", "No se confirmó tu corcho en este lance.")
    else:
        zx, zy = config["zone"][:2]
        log("OK", f"Corcho confirmado en ({zx + own.x}, {zy + own.y}).")


def run(dpy, reader, game, config, masks, diagnostic=False, max_lances=None):
    cast = key_code(dpy, config["cast_key"])
    buff = key_code(dpy, BUFF_KEY)
    max_casts = max_lances if max_lances is not None else (3 if diagnostic else int(config["max_casts"]))
    attempts = 0
    catches = 0
    failures = 0
    next_buff_at = 0.0
    log("INFO", f"Enfoca WoW. Comienza en 5 s; {STOP_KEY} para detener.")
    sleep(5)
    while max_casts == 0 or attempts < max_casts:
        if not focused(dpy, game):
            log("WARN", "WoW perdió el foco; esperando.")
            while not focused(dpy, game):
                sleep(0.3)
            log("INFO", "WoW enfocado; continúo en 2 s.")
            sleep(2)
        if time.monotonic() >= next_buff_at:
            log("INFO", f"Buff ({BUFF_KEY}); espero {BUFF_WAIT_SECONDS} s.")
            tap_key(dpy, buff)
            next_buff_at = time.monotonic() + BUFF_INTERVAL_SECONDS
            sleep(BUFF_WAIT_SECONDS)
            if not focused(dpy, game):
                continue
        before, before_noise = median_frames(dpy, game, config["zone"], masks)
        tap_key(dpy, cast)
        attempts += 1
        log("INFO", f"Lance {attempts}.")
        started = time.monotonic()
        own = find_own_after_cast(dpy, reader, game, config, masks, before, before_noise)
        hooked = False
        recorded_frames = []
        recorded_times = []
        click_time = -1.0
        late_start_index = -1
        if own is not None:
            log("OK", f"Corcho confirmado en ({own.x}, {own.y}) dentro de la zona.")
            rect, local_center = local_bobber_view(config, own)
            calibration_started = time.monotonic() - started
            calibration_frames = []
            for _ in range(5):
                calibration_frames.append(image_rgb(dpy, game, rect, masks))
                sleep(BITE_POLL_SECONDS)
            splash_tracker = SplashTracker(calibration_frames, local_center)
            late_calibrated = calibration_started >= BITE_ARM_SECONDS
            if late_calibrated:
                late_start_index = 0
            early_reference = splash_tracker.reference.copy()
            early_noise = splash_tracker.noise.copy()
            early_chroma_reference = splash_tracker.chroma_reference.copy()
            early_chroma_noise = splash_tracker.chroma_noise.copy()
            early_bobber_reference = splash_tracker.bobber_reference
            initial_reference = splash_tracker.reference.copy()
            initial_noise = splash_tracker.noise.copy()
            initial_chroma_reference = splash_tracker.chroma_reference.copy()
            initial_chroma_noise = splash_tracker.chroma_noise.copy()
            initial_bobber_reference = splash_tracker.bobber_reference
        while own is not None and time.monotonic() - started < CAST_SECONDS:
            if not focused(dpy, game):
                log("WARN", "Se perdió el foco durante el lance.")
                while time.monotonic() - started < CAST_SECONDS:
                    sleep(0.3)
                break
            if not late_calibrated and time.monotonic() - started >= BITE_ARM_SECONDS:
                # Descarta la salpicadura de la caída antes de usar el umbral normal.
                calibration_frames = []
                for _ in range(5):
                    calibration_frames.append(image_rgb(dpy, game, rect, masks))
                    sleep(BITE_POLL_SECONDS)
                splash_tracker = SplashTracker(calibration_frames, local_center)
                late_calibrated = True
                late_start_index = len(recorded_frames)
                initial_reference = splash_tracker.reference.copy()
                initial_noise = splash_tracker.noise.copy()
                initial_chroma_reference = splash_tracker.chroma_reference.copy()
                initial_chroma_noise = splash_tracker.chroma_noise.copy()
                initial_bobber_reference = splash_tracker.bobber_reference
            frame = image_rgb(dpy, game, rect, masks)
            elapsed = time.monotonic() - started
            if diagnostic:
                recorded_frames.append(frame)
                recorded_times.append(elapsed)
            splash = splash_tracker.observe(frame)
            if bite_confirmed(splash_tracker, splash, late_calibrated):
                zx, zy = config["zone"][:2]
                offset_x, offset_y = config["click_offset"]
                click_x = zx + own.x + offset_x
                click_y = zy + own.y + offset_y
                if not focused(dpy, game):
                    break
                right_click(dpy, game, click_x, click_y)
                catches += 1
                hooked = True
                click_time = elapsed
                log("OK", f"Posible picada; clic en ({click_x}, {click_y}).")
                sleep(0.8)
                break
            sleep(BITE_POLL_SECONDS)
        if diagnostic and own is not None and recorded_frames:
            folder = data_directory() / "diagnosticos"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"lance_{time.strftime('%Y%m%d_%H%M%S')}_{attempts:03d}.npz"
            np.savez_compressed(
                path, frames=np.stack(recorded_frames), times=np.asarray(recorded_times),
                reference=initial_reference, noise=initial_noise,
                chroma_reference=initial_chroma_reference, chroma_noise=initial_chroma_noise,
                bobber_reference=initial_bobber_reference,
                early_reference=early_reference, early_noise=early_noise,
                early_chroma_reference=early_chroma_reference,
                early_chroma_noise=early_chroma_noise,
                early_bobber_reference=early_bobber_reference,
                late_start_index=late_start_index,
                center=[local_center.x, local_center.y],
                click_time=click_time,
            )
            log("INFO", f"Diagnóstico guardado en {path}")
        if hooked:
            failures = 0
        else:
            failures += 1
            log("WARN", "Sin picada confirmada en este lance.")
            if failures >= 3:
                raise RuntimeError("Tres lances sin picada confirmada. Revisa calibración y zona.")
            remaining = CAST_SECONDS - (time.monotonic() - started)
            if remaining > 0:
                sleep(remaining)
    cast_label = "lance" if attempts == 1 else "lances"
    bite_label = "picada detectada" if catches == 1 else "picadas detectadas"
    log("OK", f"Terminado: {attempts} {cast_label}, {catches} {bite_label}.")


def main():
    global _active_stop_hotkey
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("calibrar", "probar", "iniciar"))
    parser.add_argument("what", nargs="?", choices=("zona", "cursor"))
    parser.add_argument("--titulo", help="Parte del título de la ventana")
    parser.add_argument("--diagnostico", action="store_true", help="Guardar solo la zona del corcho durante cada lance")
    parser.add_argument("--max-lances", type=int, help="Limitar el número de lances en esta ejecución")
    args = parser.parse_args()
    if args.action == "calibrar" and not args.what:
        parser.error("calibrar necesita zona o cursor")
    if args.action != "calibrar" and args.what:
        parser.error("zona/cursor solo se usan con calibrar")
    if args.diagnostico and args.action != "iniciar":
        parser.error("--diagnostico solo se usa con iniciar")
    if args.max_lances is not None and (args.action != "iniciar" or args.max_lances < 1):
        parser.error("--max-lances necesita iniciar y un número positivo")
    config = load_config()
    if args.titulo:
        config["window_title"] = args.titulo
    reader = None
    try:
        dpy = windows.WindowsBackend() if sys.platform == "win32" else display.Display()
        if not dpy.has_extension("XTEST"):
            raise RuntimeError("El servidor X11/XWayland no ofrece XTEST.")
        game = game_window(dpy, config["window_title"])
        masks = visual_masks(dpy, game)
        if (args.action == "calibrar" and args.what == "cursor") or args.action in ("probar", "iniciar"):
            if not dpy.has_extension("XFIXES"):
                raise RuntimeError("XFixes no está disponible; no puedo reconocer el cursor de tuerca.")
            reader = windows.NativeCursorReader() if sys.platform == "win32" else NativeCursorReader()
        if args.action == "calibrar":
            calibrate(dpy, reader, game, config, args.what)
        else:
            check_config(config, need_cursor=True)
            if args.action == "probar":
                inspect(dpy, reader, game, config, masks)
            else:
                with (windows.StopHotkey() if sys.platform == "win32" else StopHotkey()) as hotkey:
                    _active_stop_hotkey = hotkey
                    try:
                        run(dpy, reader, game, config, masks, args.diagnostico, args.max_lances)
                    finally:
                        _active_stop_hotkey = None
    except (RuntimeError, ValueError, *DISPLAY_ERRORS) as exc:
        log("ERROR", str(exc))
        return 1
    except StopRequested:
        log("INFO", "Pesca detenida con F9.")
    except KeyboardInterrupt:
        log("INFO", "Detenido.")
    finally:
        if reader is not None:
            reader.close()
        if "dpy" in locals():
            dpy.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
