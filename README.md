# PescaAuto para WoW 3.3.5a

Programa externo para WoW en Linux/Wine. Pulsa `1` para lanzar la caña, compara varias capturas del agua antes y después del lance y comprueba con el cursor de tuerca cuál de los objetos nuevos es tu corcho. No usa una plantilla del paisaje ni exige que el corcho sea rojo. Después observa cambios visuales junto al corcho y hace clic derecho ante una posible picada. No modifica el servidor ni la memoria del cliente.

## Preparación

1. Ejecuta WoW en modo ventana, visible y con la misma escala durante la sesión.
2. Activa **Saqueo automático** dentro del juego.
3. Mantén Pesca en la tecla `1`, el buff de pesca en la tecla `2` y al personaje quieto frente al agua.
4. Ten Python 3 con `numpy`, `python-xlib` y `PyQt6`, además de `libX11`, `libXfixes`, XTEST y XFixes en tu sesión gráfica. Estas bibliotecas ya estaban disponibles en este equipo.

## Calibración

Desde esta carpeta, ejecuta:

```bash
python3 pesca_auto.py calibrar zona
```

Marca con `F8` las esquinas superior izquierda e inferior derecha del área donde puede caer tu corcho. Incluye todas las posiciones posibles, pero deja fuera la interfaz y la mayor parte del paisaje. Al cambiar de sitio de pesca o resolución, repite este paso si el corcho puede caer fuera de esa zona.

La calibración del color rojo ya no se utiliza. Se retiraron los parámetros antiguos del color y del hundimiento de `config.json`.

La confirmación de la tuerca sigue usando el cursor X11. Si no la calibraste, ejecuta:

```bash
python3 pesca_auto.py calibrar cursor
```

Con WoW enfocado, pon el cursor sobre **tu** corcho y pulsa `F8`. Después ponlo sobre agua vacía o un corcho ajeno y pulsa `F8`. Mantén el ratón quieto aproximadamente un segundo después de cada pulsación. Si cambias la escala del cursor o Wine deja de exponer esa imagen mediante XFixes, vuelve a calibrarlo.

## Prueba segura de un lance

```bash
python3 pesca_auto.py probar
```

Tienes cinco segundos para enfocar WoW. El programa pulsa `1`, busca cambios persistentes en el agua y prueba la tuerca en los puntos candidatos. Imprime las posiciones encontradas y **no hace clic derecho**. Prueba primero en el lugar donde vas a pescar. Si no confirma tu corcho, reduce la zona o vuelve a calibrar el cursor.

La primera búsqueda empieza aproximadamente un segundo después de lanzar la caña. Si el corcho todavía está cayendo y no se confirma, realiza un segundo intento.

La búsqueda compara cambios grandes y pequeños para incluir corchos que se ven lejos. Un candidato solo se acepta cuando aparece el cursor de tuerca. Si el corcho cae fuera de la zona marcada, vuelve a ejecutar `calibrar zona` e incluye esa parte del agua.

Cuando hay varios candidatos, primero comprueba el centro de cada uno. Si ninguno muestra la tuerca, prueba cuatro puntos cercanos a cada centro. No repite una posición ya examinada.

Cuando confirma tu corcho, deja el puntero sobre él durante la espera. Al detectar una picada, hace clic derecho en esa posición.

## Pesca automática

Abre `IniciarPescaAuto` con doble clic y elige **Ejecutar** si Dolphin lo solicita. Se abrirá una ventana con el botón **Iniciar** y los registros. Pulsa **Iniciar** y enfoca WoW durante los cinco segundos de espera. Pulsa **F9** para detener la pesca. Cerrar la ventana también detiene el proceso. El lanzador no guarda diagnósticos por defecto.

Si quieres un acceso directo para KDE, ejecuta `./CrearAccesoDirecto` **después de mover esta carpeta a su ubicación definitiva**. Generará `PescaAuto.desktop` con la ruta correcta. Si vuelves a mover la carpeta, ejecuta el generador otra vez.

También puedes abrir la ventana desde esta carpeta con el archivo ejecutable `IniciarPescaAuto`. Para usar la terminal, sigue disponible el comando habitual:

```bash
python3 pesca_auto.py iniciar
```

Tras los cinco segundos iniciales, pulsa `2` para activar el buff, espera cuatro segundos y empieza a lanzar con `1`. Renueva el buff cada diez minutos, al terminar el lance en curso, y vuelve a esperar cuatro segundos antes de continuar. Se detiene con `F9`, `Ctrl+C` en la terminal o tras tres lances sin picada confirmada. `max_casts` en `config.json` limita los lances; `0` significa sin límite.

La picada se detecta **solo por la salpicadura localizada** cerca del corcho. Desde que lo encuentra hasta los 2 segundos del lance, exige una señal fuerte que forme un grupo de píxeles unidos; esto distingue la picada temprana observada en el lance 6 de los puntos dispersos del falso clic del lance 8. Entonces vuelve a calibrar el agua y usa el umbral habitual. El movimiento normal o hundimiento del corcho no provoca un clic. El detector exige tanto un aumento de brillo como el tono azul violáceo adicional que muestran las capturas de la picada. Compara ambos con el agua reciente del mismo lance, por lo que las pequeñas olas blancas que conservan el color del agua no deberían activar un clic. **El sonido aún no se analiza.** En otros biomas, una salpicadura sin ese cambio de tono puede pasar inadvertida. `click_offset` desplaza el clic respecto al punto que mostró la tuerca.

El seguimiento de la picada lee solo un recorte de hasta 77×77 píxeles alrededor del corcho. Requiere al menos diez píxeles que se iluminen y cambien de tono cerca del corcho durante dos lecturas; ahora incluye el área más cercana al centro para corchos pequeños. Para probar unos pocos lances sin editar `config.json`:

```bash
python3 pesca_auto.py iniciar --max-lances 3
```

Si vuelve a perder picadas, registra tres lances:

```bash
python3 pesca_auto.py iniciar --diagnostico
```

El programa guarda cada secuencia en `diagnosticos/lance_*.npz`; cada archivo contiene únicamente el recorte del corcho, los tiempos de captura y el instante del clic, si lo hubo. Ahora también guarda la etapa temprana y las dos referencias visuales usadas antes y después de los 2 segundos. Con `--diagnostico` se limita a tres lances por defecto. Puedes cambiar ese límite con `--max-lances N`. Esos archivos permiten revisar una picada perdida y ajustar los umbrales; no incluyen una captura completa del cliente ni audio.

Las imágenes facilitadas se guardaron en `referencias/` para documentar el corcho, la tuerca, la salpicadura y las olas blancas. El detector no depende de una captura completa fija; aprende el aspecto del agua de nuevo en cada lance. No pude probarlo contra una ventana activa de WoW desde esta sesión de herramientas.

## Repositorio personal

Las dependencias de Python están listadas en `requirements.txt`. `config.json` contiene tu calibración local y está excluido por `.gitignore`; consérvalo al mover esta carpeta. Los diagnósticos, la caché de Python y el acceso directo generado tampoco se suben a GitHub. Si clonas el repositorio en otro equipo, ejecuta `calibrar zona` y `calibrar cursor` antes de iniciar la pesca.
