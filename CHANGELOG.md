# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [versionado semántico](https://semver.org/lang/es/). Al publicar una versión, actualiza el mismo número en los archivos que enumera [docs/instalacion.md](docs/instalacion.md#7-publicar-una-versión-nueva); `tests/test_packaging.py` lo comprueba.

## [0.2.1] - 2026-09-23

Correcciones halladas en la primera aceptación real (videollamada de 26 min con ruido de fondo
constante) y rótulos opcionales sobre el resumen.

### Añadido

- `rotular --work W --version N [--labels rotulos.json]`: copia derivada `vN-rotulado/` con el tema
  de cada corte, su origen y su posición en el resumen, las líneas temporales del original y del
  resumen con el corte actual resaltado y un cursor que avanza. `vN/resumen.mp4` no se toca.
- El timeline del documento (`vN/timeline.png`) pasa a ser un gráfico etiquetado: de dónde sale
  cada corte, dónde cae en el resumen y una leyenda con los temas.

### Corregido

- Bordes que partían palabras cuando el audio no tiene silencios bajo el umbral: `plan` usa ahora
  las marcas por palabra y lleva el borde al hueco entre palabras; `borde_en_voz` queda para los
  casos sin marcas o con palabras de más de 1 s.
- La eliminación de pausas se comía el arranque de palabras dichas en voz baja («Pero», «Y») que
  quedaban bajo el umbral: con marcas por palabra, el primer medio segundo de cada palabra se
  conserva siempre.
- La validación de `render` fallaba («Las imágenes deben tener el mismo tamaño (0 y 4096)») cuando
  el MP4 muxado terminaba unos milisegundos antes de Σ N / F: el último punto de imagen se toma
  medio fotograma antes del final.
- `transcribe` informaba de una falta de memoria de la GPU como «el modelo no está en la caché
  local». Ahora lo dice como falta de memoria, y la segunda pasada reutiliza el modelo ya cargado en
  lugar de cargar una segunda copia (la causa de esa falta de memoria).

## [0.2.0] - 2026-09-18

Compresión con objetivo, revisión previa obligatoria y entrada de solo audio con documento. Incluye
cambios **incompatibles** con la 0.1.0 en los valores por defecto y en la forma de montar.

### Incompatible

- Los valores por defecto cambian: el resumen se acelera a ×1,25 y elimina las pausas. Para volver al
  comportamiento de la 0.1.0, pide `velocidad=1` y `pausas=no`.
- `render` exige aceptación: `--accept "frase literal del usuario"` o `--directo`. Un plan sin una de
  las dos se rechaza, y un aviso bloqueante detiene el montaje incluso con `--directo`.
- La salida ya no es `final/`, sino `vN/` (vídeo) o `documento-vN/` (audio), inmutables.
- `frames --out` pasa a ser la carpeta de fotogramas del trabajo, con una subcarpeta `bSSSSS/` por
  bloque; ya no falla si existe, sino que reanuda. Los planes de la 0.1 se importan con
  `plan --import`.

### Añadido

- Objetivo de compresión en porcentaje o duración (`10 %`, `12 min`, `0:12:00`), con banda de
  tolerancia, seis estados, alternativas, sugerencias y dieciocho avisos.
- Propuesta previa (`propuesta-vN.md`) y edición en lenguaje natural antes y después del montaje, con
  versiones inmutables e `historial.jsonl`.
- Entrada de solo audio: `plan --kind audio` publica un esquema y `doc` entrega
  `documento-vN/resumen.md` (+ DOCX si hay Pandoc o python-docx).
- Documento equivalente junto al MP4, con marcas de tiempo expandidas, timeline e informe de
  validación; `compare` mide la cobertura de palabras sin bloquear.
- Subcomandos `plan`, `doc`, `compare` y `search`; módulos `common.py`, `plan.py`, `render.py` y
  `doc.py`.
- `frames` barre por bloques en un proceso por bloque, con índice de cambios (`indice.gray`), hojas
  de contacto y reanudación; en las medidas hechas al desarrollarlo, 50 vistas pasaron de 21,1 s a
  0,68 s.
- `transcribe` trabaja por bloques reanudables cortados en el silencio, recupera sin VAD los huecos
  con sonido, marca los segmentos dudosos, admite `--device auto`, `--dll-dir`, `--block`, `--slack`
  y `--budget`, y normaliza subtítulos SRT o WebVTT con `--subtitles`.
- `render` monta por cortes cacheados, con presupuesto reanudable, un reintento ante falta de memoria
  y validación bloqueante de recuentos, imagen y envolvente antes de publicar; `render --dry-run`
  estima el coste del montaje (`{reused, new, eta_s}`) sin renderizar, frente a `plan --dry-run`, que
  muestra el plan propuesto sin escribirlo.
- `check` informa además de los filtros obligatorios, Pandoc, python-docx, Pillow y la memoria
  disponible, indicando qué se degrada si falta cada opcional.
- Referencias nuevas `compresion.md`, `revision.md` y `documento.md`.

### Cambiado

- `--device` de `transcribe` pasa de `cpu` a `auto`: prueba CUDA, avisa y vuelve a CPU.
  `--compute-type` deja de tener un valor fijo (`int8` en CPU, `float16` en CUDA).
- La identidad del medio pasa a ser una huella (tamaño, `mtime_ns` y sha256 de los primeros y últimos
  4 MiB): un plan sigue siendo válido si el archivo se mueve y la huella coincide.
- `prepare` clasifica el medio (`kind`), guarda la línea temporal y la cadencia, calcula
  `energia.f32` una sola vez, rechaza el material HDR con un mensaje explícito y deja en
  `metadata.avisos` lo que detecta el sondeo de paquetes (`fuente_vfr`, `huecos_pts`).
- La referencia de operación retira «el montaje no se reanuda» y «cada imagen es una búsqueda
  independiente»: ambas cosas han dejado de ser ciertas.

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
- Infraestructura de repositorio público: integración continua con las dos baterías en Ubuntu y Windows (Python 3.10 y 3.12), guía de contribución, política de seguridad, plantillas de incidencia y de pull request, e índice de documentación.
- Gráficos del README generados a partir de datos medidos (`scripts/generar_graficos.py`).
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
