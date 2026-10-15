# Desarrollo

## Ejecutar desde el código

Usa Python 3.10 o posterior. Crea un entorno virtual, actívalo e instala el proyecto:

```bash
python -m venv .venv
python -m pip install -e .
python pesca_auto_gui.py
```

En Linux también puedes abrir `./IniciarPescaAuto`. El motor conserva la entrada `python pesca_auto.py calibrar zona|cursor`, `probar` e `iniciar`. `--max-lances N` limita los lances y `--diagnostico` guarda capturas pequeñas en `diagnosticos/`.

## Estructura

- `pescaauto/engine.py`: flujo de calibración, detección y pesca.
- `pescaauto/platform_windows.py`: WinAPI y captura con `mss`.
- `pescaauto/zone_overlay.py`: recuadro verde de calibración.
- `pescaauto/gui.py` y `process_windows.py`: interfaz y proceso auxiliar.
- `pescaauto/paths.py`: rutas de datos e icono.
- `referencias/`: imágenes y diagnósticos de ejemplo para estudiar la detección.

En desarrollo, `config.json` y `diagnosticos/` se guardan en la raíz del repositorio. En un paquete portable se guardan junto a los ejecutables. Una instalación normal de Python usa el directorio de configuración del usuario. `PESCAAUTO_DATA_DIR` permite cambiarlo.

## Pruebas y paquetes

```bash
python -m unittest discover -s tests -v
python -m pip install -e ".[build]"
python scripts/build.py
```

`scripts/build.py` crea `dist/PescaAuto-Windows.zip` en Windows o `dist/PescaAuto-Linux.tar.gz` en Linux. Cada paquete contiene la ventana y el motor como ejecutables separados. La ventana inicia el motor en segundo plano y muestra sus mensajes. El flujo de GitHub Actions en `.github/workflows/build.yml` ejecuta pruebas y construye ambos paquetes en sus respectivos sistemas. [PyInstaller requiere construir en cada sistema operativo](https://pyinstaller.org/en/stable/operating-mode.html).

La captura y las teclas de Linux necesitan X11/XWayland con XTEST y XFixes. Windows usa `mss` y las API nativas de ventanas, cursor y entrada. El cursor de tuerca debe estar visible para el sistema; la calibración informa de un error si no puede distinguirlo. La selección visual y la pesca real deben verificarse con WoW abierto en cada plataforma.
