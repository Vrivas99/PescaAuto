# PescaAuto

Pesca automática para WoW 3.3.5a en **Windows y Linux**. La ventana permite calibrar la zona, calibrar el cursor e iniciar o detener la pesca.

## Instalar

Descarga el paquete de tu sistema desde [Versiones de GitHub](https://github.com/Vrivas99/PescaAuto/releases/latest) o desde `dist/` si recibiste el proyecto completo.

- **Linux:** crea una carpeta, por ejemplo `Documentos/PescaAuto`, y mueve allí `PescaAuto-Linux.tar.gz`. Haz clic derecho sobre el archivo y elige **Extraer aquí**. Abre `PescaAuto` en esa carpeta. Para crear un acceso directo con el icono, ejecuta `CrearAccesoDirecto`.
- **Windows:** haz clic derecho sobre `PescaAuto-Windows.zip`, elige **Extraer todo** y abre `PescaAuto.exe` en la carpeta extraída.

Conserva juntos los archivos extraídos. La calibración se guarda como `config.json` en esa carpeta; puedes moverla o copiarla completa.

No necesitas instalar Python para usar estos paquetes.

En Linux, WoW debe verse en una sesión X11 o XWayland. Si el archivo `PescaAuto` no se puede abrir, activa **Permitir ejecutar como programa** en sus propiedades.

## Preparar WoW

- Pon **Pesca en la tecla `1`** de la barra de habilidades y **Adorno brillante en la tecla `2`**.
- Activa **Saqueo automático**. Juega en modo ventana y deja al personaje quieto frente al agua.

## Calibrar una vez por lugar de pesca

1. Pulsa **Calibrar zona**. Con WoW enfocado, pon el puntero en la esquina superior izquierda del agua y pulsa `F8`. Mueve el puntero: verás un recuadro verde. Pulsa `F8` otra vez en la esquina inferior derecha.
2. Pulsa **Calibrar cursor**. Lanza la caña manualmente, coloca el puntero sobre **tu corcho** cuando aparezca la tuerca y pulsa `F8`. Después colócalo sobre agua vacía u otro corcho y pulsa `F8`. Mantén el ratón quieto un segundo tras cada pulsación.

Repite la calibración si cambias la resolución, el lugar de pesca o el tamaño del cursor.

## Usar

Pulsa **Iniciar** y vuelve a WoW durante la cuenta inicial. El botón cambiará a **Detener** mientras pesca. Puedes detenerlo con ese botón o con `F9`. La ventana muestra el progreso y los errores en el registro.

Si no encuentra WoW, comprueba que el juego esté abierto en modo ventana. Si no reconoce tu corcho, repite **Calibrar zona** y **Calibrar cursor**.

## Para quienes usan el código fuente

Las instrucciones de instalación con Python, pruebas y creación de ejecutables están en [docs/DESARROLLO.md](docs/DESARROLLO.md).
