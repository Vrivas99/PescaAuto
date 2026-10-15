"""Ubicación de los datos generados por la aplicación."""

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def application_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if (PROJECT_ROOT / "IniciarPescaAuto").is_file():
        return PROJECT_ROOT
    return Path.home()


def icon_path():
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / "pescaauto" / "assets" / "pescaauto.png"


def data_directory():
    """Usa la carpeta del proyecto o el directorio de configuración al instalar."""
    override = os.environ.get("PESCAAUTO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return application_directory()
    if (PROJECT_ROOT / "IniciarPescaAuto").is_file():
        return PROJECT_ROOT
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home.expanduser() / "pescaauto"
