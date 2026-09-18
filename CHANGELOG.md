# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [versionado semántico](https://semver.org/lang/es/). Al publicar una versión, actualiza el mismo número en los archivos que enumera [docs/instalacion.md](docs/instalacion.md#7-publicar-una-versión-nueva); `tests/test_packaging.py` lo comprueba.

## [0.1.0] - 2026-09-17

Primera versión. «Cambiado» y «Corregido» se refieren a las copias manuales sin versionar que había en `.claude/skills` y `.agents/skills` (véase [D-004](docs/decisiones.md#d-004--distribución-como-plugin-multiplataforma)), salvo las entradas sobre `check` e `install.py`: son nuevos en esta versión y recogen los fallos corregidos durante su verificación ([plan](docs/plan.md#validación-2026-09-17)).

### Añadido

- Empaquetado como plugin para Claude Code, GitHub Copilot (CLI y VS Code) y Codex: `plugins/resumir-video/` con manifiesto Agent Plugins 1.0, `.claude-plugin/plugin.json` y `.codex-plugin/plugin.json`, y catálogos `.claude-plugin/marketplace.json` y `.agents/plugins/marketplace.json`.
- Instalador `scripts/install.py` para copiar la skill en las carpetas personales o del proyecto de cada agente, con estado, actualización, desinstalación y simulación.
- Subcomando `video.py check`: comprueba Python, FFmpeg, libx264, AAC y `faster-whisper`, e informa del entorno virtual recomendado, del espacio libre y de los fallos de FFmpeg; siempre imprime su JSON.
- Opciones de `transcribe`: `--device`, `--compute-type`, `--beam-size` y `--no-vad`; la salida registra la configuración usada.
- Ayuda de la CLI con descripciones y valores por defecto, y opción `--version`.
- Licencia MIT a nombre de CAPTIA TECHNOLOGY S.L. (`LICENSE` en la raíz, copiada en el plugin y en la skill como `LICENSE.txt`).
- Documentación de instalación y catálogo de capacidades; pruebas de empaquetado y del instalador.
- Procedimientos en la referencia de operación: claves de `probe`, registro del análisis, sincronización de subtítulos y huecos sin escuchar, y revisión de uniones.

### Cambiado

- `render` codifica el audio una sola vez a partir de cortes PCM con la duración exacta de cada corte de vídeo; se elimina el desfase acumulado en las uniones.
- `render` recodifica cada corte a frecuencia de fotogramas constante desde el fotograma en pantalla en su inicio, y el audio del corte empieza exactamente en ese inicio: el desfase por unión es como máximo de medio fotograma.
- `render` comprueba libx264 y AAC antes de crear la salida, valida los cortes contra el final de la pista de vídeo, exige que cada corte produzca su duración (con un margen de dos fotogramas), verifica que vídeo y audio duran lo mismo y solo publica `resumen.mp4` tras validarlo.
- `resumen.md` muestra solo el nombre del archivo de origen, no su ruta completa.
- `prepare` añade un `.gitignore` a la carpeta de trabajo.
- `frames` muestrea el intervalo semiabierto [inicio, fin), redondea los tiempos a seis decimales y ajusta al último fotograma los tiempos posteriores a él.
- Una carpeta de salida existente se rechaza con un mensaje que propone otro nombre, en lugar de un error del sistema.
- `transcribe` indica cómo continuar cuando el modelo no está en caché (`--allow-download` o una carpeta local).
- La salida de la CLI es siempre UTF-8; los tiempos se pasan a FFmpeg sin notación exponencial.
- `install.py`: `--uninstall` exige `--force` para eliminar una copia desactualizada, `--project-dir` debe existir y el nombre del frontmatter se reconoce también entre comillas.
- Texto de la skill válido para cualquier agente; entorno virtual de transcripción compartido fuera de la skill.

### Corregido

- `render` fallaba si la ruta de salida contenía `#` o `?`.
- En grabaciones de pantalla de frecuencia variable, `frames` mostraba la diapositiva siguiente y `render` fallaba si un corte caía dentro de un fotograma mantenido.
- En MKV/WebM y en fuentes cuya pista de vídeo empieza tarde, el final de la pista se calculaba mal: un corte más allá del final se acortaba sin aviso o uno válido se rechazaba.
- `frames` podía añadir un fotograma en `--end` por redondeo y guardaba tiempos con ruido de coma flotante.
- En Windows, Ctrl+C durante `render` podía terminar con código 1 en lugar de 130.
- `check` no imprimía su JSON con Python anterior a 3.10 o con FFmpeg averiado, y daba `faster_whisper: true` aunque no pudiera importarse. En Windows ya no intenta usar envoltorios `.cmd` o `.bat` de FFmpeg.
- Los cortes muy cortos junto a otros más largos se truncaban al concatenar (fotogramas B con retardos distintos): el vídeo terminaba antes que el audio o el montaje se detenía.
- En fuentes MPEG-TS/M2TS, un corte podía salir congelado y `frames` devolvía una imagen posterior o fallaba cerca del final.
- La tolerancia del control de duración de cada corte usaba una frecuencia distinta de la del montaje.
- `install.py`: una primera instalación interrumpida dejaba una carpeta parcial irrecuperable y una desinstalación interrumpida dejaba la skill a medio borrar; los archivos de solo lectura bloqueaban `--force` y `--uninstall`; quedaban restos `.resumir-video.nuevo` y `.resumir-video.anterior` tras una interrupción; no se detectaban las uniones y enlaces rotos; `Thumbs.db` y `desktop.ini` marcaban la copia como desactualizada, y un `--project-dir` inexistente se creaba sin aviso.
