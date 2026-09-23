# Operación del asistente

`video.py` usa solo la biblioteca estándar de Python 3.10+ y FFmpeg. Solo `transcribe` importa `faster-whisper`. En los ejemplos, sustituye:

- `SKILL_DIR` por la ruta absoluta de la carpeta que contiene `SKILL.md`.
- `TRABAJO` por la carpeta de trabajo (por defecto, `resumenes/<nombre-del-archivo-sin-extensión>/` bajo el directorio actual).
- `VENV` por la carpeta del entorno de transcripción (véase [Transcripción opcional](#transcripción-opcional)).
- `python3` por el intérprete disponible (`python` o `py -3` en Windows).

Usa rutas absolutas entre comillas simples: en Bash y PowerShell, las comillas dobles no impiden que se ejecute un `$(…)` contenido en un nombre de archivo. Si el nombre contiene una comilla simple, escríbela como `'\''` en Bash o duplícala (`''`) en PowerShell. Si automatizas, pasa los argumentos como lista, sin construir órdenes de shell a partir de nombres de archivo. `python3 'SKILL_DIR/scripts/video.py' <subcomando> --help` muestra cada opción con su valor por defecto.

## Reglas comunes

- Nada publicado se sobrescribe. Solo `prepare --work` exige una carpeta **nueva**: si ya existe, se detiene con `La carpeta ya existe y no se sobrescribe; indica una carpeta nueva (p. ej., con el sufijo -2): <ruta>`. Dentro de ella, `frames`, `transcribe` y `render` **reanudan**: saltan lo terminado, apartan lo incompleto con el sufijo `.parcial` y publican por renombrado atómico. Las carpetas `vN/` y `documento-vN/` y los JSON publicados son inmutables.
- Un trabajo que se queda a medias por presupuesto termina con código 3 e imprime `{"done", "total", "pending", "bloques"}`, con `pending` entero y `bloques` con los nombres que faltan: repite la misma orden para continuar.
- En `transcribe`, `--out` es un archivo JSON que no debe existir, dentro de una carpeta que ya exista. Ningún JSON se reemplaza.
- Tras un fallo, conserva la evidencia, corrige el motivo y usa una carpeta nueva. Si falla `transcribe`, no se escribe ningún archivo.
- Los errores controlados se imprimen como `Error: …` en stderr con código de salida 1; los errores de argumentos devuelven 2. Una interrupción (Ctrl+C) imprime `Interrumpido; revisa las carpetas de salida incompletas.` y devuelve 130: la carpeta de salida queda incompleta y no debe reutilizarse. La salida se emite siempre en UTF-8.
- `probe`, `prepare`, `frames` y `render` exigen `ffmpeg` y `ffprobe` en PATH (en Windows, `ffmpeg.exe` y `ffprobe.exe`; un envoltorio `.cmd` o `.bat` no sirve). `render` exige además los codificadores `libx264` y `aac`.

## Comprobar el entorno

```text
python3 'SKILL_DIR/scripts/video.py' check
```

Imprime siempre un JSON, también con Python 3.7–3.9 o con FFmpeg ausente o averiado. Claves, en este orden:

| Clave | Significado |
| --- | --- |
| `version`, `python`, `python_ok`, `platform` | Versión de la skill, versión de Python, si es 3.10 o posterior, y plataforma. |
| `ffmpeg`, `ffprobe` | Ruta del ejecutable encontrado, o `null`. |
| `ffmpeg_version`, `libx264`, `aac` | Primera línea de `ffmpeg -version` y disponibilidad de cada codificador. |
| `filters_ok`, `missing_filters` | Si están los diecinueve filtros que usan el barrido y el montaje, y la lista de los que falten. |
| `faster_whisper` | Si **el intérprete que ejecuta `check`** puede importar `faster_whisper.WhisperModel`. |
| `pandoc`, `python_docx`, `docx_engine` | Conversores encontrados y cuál se usará (`pandoc`, `python-docx` o `null`). |
| `pillow` | Si hay Pillow para el PNG del timeline. |
| `transcription_venv` | Carpeta recomendada para el entorno de transcripción (`VENV`). |
| `disk_free_gb` | Espacio libre, en GB, de la unidad del directorio actual (o `null`). |
| `memory_free_gb` | Memoria disponible, en GB, o `null` donde no puede leerse sin dependencias. |
| `degraded` | Qué se pierde por cada opcional que falta, redactado. |
| `error` | `null`, o el diagnóstico de FFmpeg si falla al ejecutarse. |
| `ok` | `true` si Python 3.10+, `ffmpeg`, `ffprobe`, libx264, AAC y los filtros obligatorios están disponibles y no hay `error`. |

Termina con código 0 solo si `ok` es `true`, y en `ok` solo entran Python, FFmpeg, `ffprobe`, los codificadores y los filtros obligatorios: **ningún opcional cambia el código de salida**. Lee `degraded` antes de empezar el inventario y anuncia lo que se degrada (sin conversor, la entrega es solo Markdown; sin Pillow, el timeline solo en texto; sin faster-whisper, hacen falta subtítulos del medio; con poca memoria, monta con un solo hilo). Para saber si `faster-whisper` está instalado en `VENV`, ejecuta `check` con el Python de ese entorno. Si la carpeta de trabajo está en otra unidad, comprueba allí el espacio libre (`df -h` o `Get-PSDrive`). Como orden de magnitud, reserva 115 MB por hora de audio de análisis, entre 0,1 y 1 MB por fotograma extraído y, para el montaje, unas tres veces el tamaño previsto del resumen (cortes intermedios, PCM y MP4 final).

## Preparar evidencia

```text
python3 'SKILL_DIR/scripts/video.py' probe 'video.mp4'
python3 'SKILL_DIR/scripts/video.py' prepare 'video.mp4' --work 'TRABAJO'
```

`probe` muestra la salida completa de `ffprobe` (formato y todas las pistas) y la identidad del archivo (`source`: ruta absoluta, tamaño y `mtime_ns`). No resume nada ni escribe archivos.

### Claves de `probe`

| Qué revisar | Dónde |
| --- | --- |
| Duración | `format.duration`; en MKV/WebM, la de cada pista está en `tags.DURATION` |
| Pistas e índices globales | `streams[].index` y `codec_type` |
| Resolución | `width` y `height` de la pista de vídeo |
| Rotación | `side_data_list[].rotation` o, en compilaciones antiguas de FFmpeg, `tags.rotate` |
| HDR | `color_transfer` igual a `smpte2084` o `arib-std-b67`: `render` lo rechaza |
| Profundidad y croma | `pix_fmt` (por ejemplo, con `10` o `444`): el montaje convierte a 8 bits 4:2:0 |
| Frecuencia variable | `r_frame_rate` distinto de `avg_frame_rate` |
| Desfases de inicio | `start_time` distinto de 0 en el formato o en una pista |

Una clave ausente suele significar que no aplica (por ejemplo, sin `side_data_list` no hay rotación y sin `color_transfer` la fuente no declara HDR); compruébalo en las imágenes si el resultado no cuadra.

`prepare` crea `TRABAJO` (y sus carpetas padre) con `.gitignore` (`*`), `metadata.json` (salida de `probe` más `audio_stream`) y `audio.wav` mono a 16 kHz sin eliminar silencios. Por defecto usa la primera pista de audio; `--audio-stream N` elige el índice **global** mostrado por `probe`. El WAV solo sirve para análisis: el montaje utiliza el audio original. Un vídeo sin audio produce un error explícito antes de crear la carpeta; puede estudiarse con `frames`, pero no satisface por sí solo el análisis del ponente.

```text
python3 'SKILL_DIR/scripts/video.py' frames 'video.mp4' --out 'TRABAJO/fotogramas' --step 15
python3 'SKILL_DIR/scripts/video.py' frames 'video.mp4' --out 'TRABAJO/fotogramas' --start 120 --end 135 --step 1 --width 0
```

`frames` barre el intervalo semiabierto [`--start`, `--end`) por **bloques** de `--block` segundos
(600 por defecto), con un proceso de FFmpeg por bloque:

- Cada bloque produce su carpeta `bSSSSS/` (los segundos de su inicio) con `frame-NNNN.jpg`,
  `indice.gray`, `hoja-NNN.jpg` e `index.json`. `indice.gray` es el índice de cambios: 64×64 píxeles
  en gris por imagen, sin cabecera, `N × 4096` bytes. Las hojas de contacto agrupan 25 vistas cada una.
- `index.json` lleva `start`, `end`, `step` y, por imagen, `time` (segundos desde el inicio del
  contenedor) y `file`. Cada imagen es el fotograma **en pantalla** en ese instante, también en
  grabaciones de frecuencia variable que mantienen un fotograma durante segundos.
- Se reanuda: los bloques con `index.json` se saltan y los incompletos pasan a `bSSSSS.parcial`
  (no se borra nada). Repite la misma orden hasta que no queden pendientes.
- Como máximo 600 imágenes por llamada. Al agotarse, imprime `{"done", "total", "pending", "bloques"}`
  y devuelve 3. Antes de empezar comprueba el espacio libre: reserva unos 2 MB por vista.
- `--width 0` conserva la resolución original; el valor por defecto 1280 es un máximo. Para el
  detalle, repite el barrido sobre un intervalo corto con `--step` de 1–3 s y `--width 0`.
- Un medio de solo audio se rechaza con un mensaje explícito.

## Registro del análisis

El agente escribe `TRABAJO/analisis.md`; ningún subcomando lo lee ni lo modifica. Guárdalo solo en la carpeta de trabajo, protegida por su `.gitignore`, nunca en el directorio actual ni en `SKILL_DIR`. Debe permitir retomar el trabajo en otra sesión y contener:

- La evidencia de audio usada (subtítulos o transcripción) y el resultado de su comprobación de sincronía.
- Una tabla de tiempos con lo visto en pantalla y lo dicho en cada tramo revisado.
- El inventario de conceptos, normativa, requisitos, procedimientos, advertencias y correcciones, con sus tiempos.
- Las decisiones de selección y las exclusiones deliberadas, con su motivo.
- Los bloques terminados y las limitaciones de la revisión.

## Transcripción opcional

Si no hay subtítulos ni transcriptor disponible, instala `faster-whisper` en un entorno virtual compartido fuera de la skill y del trabajo. `VENV` es la carpeta `transcription_venv` que indica `check`: `%LOCALAPPDATA%\resumir-video\venv` en Windows, `~/Library/Caches/resumir-video/venv` en macOS y `$XDG_CACHE_HOME/resumir-video/venv` o `~/.cache/resumir-video/venv` en Linux. Reutilízala entre trabajos: si ya existe, ejecuta `check` con su Python y reinstala solo si allí `faster_whisper` es `false`. No modifiques el Python global.

```text
python3 -m venv 'VENV'
```

En Debian/Ubuntu, si la orden falla con `ensurepip is not available`, falta el paquete `python3-venv`: pide al usuario que ejecute `sudo apt install python3-venv` (no lo instales tú) y repite la orden sobre la misma carpeta.

Usa después `VENV/Scripts/python.exe` en Windows o `VENV/bin/python` en macOS/Linux. La primera vez que uses un modelo, añade `--allow-download`: descarga los pesos a la caché de Hugging Face (requiere red y espacio; el vídeo no se sube). Después puedes omitir la opción.

```text
<python-del-entorno> -m pip install faster-whisper
<python-del-entorno> 'SKILL_DIR/scripts/video.py' transcribe 'TRABAJO/audio.wav' --out 'TRABAJO/transcripcion.json' --model small --language es --allow-download
```

Sin `--allow-download`, un modelo que no está en caché termina con un error que pide repetir la orden con esa opción o indicar en `--model` una carpeta CTranslate2 local, y no se crea la salida. Si `faster-whisper` no puede importarse, por cualquier motivo, el error es `Falta faster-whisper…`.

La salida es `{"language", "settings", "segments": [{"start", "end", "text", "words": [{"start", "end", "text"}]}]}`; `settings` registra modelo, dispositivo, tipo de cálculo, haz y VAD. Las marcas no garantizan límites fonéticos exactos. Usa `base` si los recursos son muy limitados y la revisión confirma precisión suficiente; usa un modelo mayor solo si los errores técnicos lo justifican. El VAD puede omitir habla real: repite con `--no-vad` los huecos que la detección de silencios muestra con sonido (véase [Sincronización y huecos sin escuchar](#sincronización-y-huecos-sin-escuchar)) y suma el desplazamiento del extracto.

```text
<python-del-entorno> 'SKILL_DIR/scripts/video.py' transcribe 'TRABAJO/audio.wav' --out 'TRABAJO/transcripcion.json' --model small --language es --allow-download
<python-del-entorno> 'SKILL_DIR/scripts/video.py' transcribe 'TRABAJO/audio.wav' --out 'TRABAJO/transcripcion.json' --subtitles 'clase.srt' --language es
```

La transcripción se hace por **bloques** de `--block` segundos (600 por defecto), cortados en la
ventana más silenciosa que hay dentro de `--slack` segundos (60 por defecto) del corte teórico. Cada
bloque se guarda en `transcripcion.parcial/bloque-NNN.json` nada más terminar, así que una llamada
interrumpida no pierde trabajo: repite la misma orden. El modelo se carga una vez por llamada y el
idioma queda fijado con el primer bloque. Al final, los tramos que tienen sonido y ninguna palabra se
vuelven a transcribir sin VAD y se publican marcados con `"recuperado": true`; los segmentos dudosos
se marcan con `"dudoso": true`, no se descartan. `transcripcion.json` se publica por renombrado
atómico y la carpeta parcial desaparece.

Opciones: `--model`, `--language`, `--allow-download`, `--device cpu|cuda|auto` (por defecto `auto`:
prueba CUDA y avisa antes de volver a CPU), `--dll-dir` (carpeta de DLL de CUDA/cuDNN en Windows,
repetible), `--compute-type` (por defecto `int8` en CPU y `float16` en CUDA), `--beam-size`,
`--no-vad`, `--threads`, `--block`, `--slack`, `--budget` (segundos como máximo por llamada: al
agotarse devuelve 3) y `--subtitles`.

Con `--subtitles` no se carga ningún modelo: se normaliza un SRT o WebVTT del propio medio a
`transcripcion.json`, con `settings.origen = "subtitulos"`, segmentos sin `words[]` y el aviso
`sin_marcas_por_palabra`. Comprueba antes su sincronía con el método de
[Sincronización y huecos sin escuchar](#sincronización-y-huecos-sin-escuchar).

El asistente no importa SRT/VTT: el agente puede leerlos directamente y usarlos para decidir los cortes. No vuelvas a transcribir sin necesidad. La transcripción es evidencia del audio, nunca evidencia visual.

### Sincronización y huecos sin escuchar

Detecta los tramos con sonido del WAV de análisis (el resultado sale por stderr):

```text
ffmpeg -hide_banner -nostats -i 'TRABAJO/audio.wav' -af silencedetect=noise=-40dB:d=0.35 -f null -
```

Cada `silence_end` marca dónde empieza el sonido y cada `silence_start`, dónde termina. Si no aparece ningún silencio, o solo unos pocos en una charla con pausas, el ruido de fondo supera el umbral. Mide el pico de ese ruido en un tramo sin voz:

```text
ffmpeg -hide_banner -nostats -ss INICIO -t 10 -i 'TRABAJO/audio.wav' -af astats=measure_overall=none:measure_perchannel=Peak_level -f null -
```

Repite la detección con `noise` unos 3 dB por encima de ese pico (por ejemplo, `-30dB` si el pico es -33 dB). Con una salida vacía no se puede sacar ninguna conclusión.

- **Sincronización.** Al principio, a la mitad y al final, elige varias entradas de los subtítulos o de la transcripción que vayan tras un hueco claro (1 s o más sin texto). Compara el inicio de cada una con el `silence_end` más próximo.
  - Si están sincronizadas, las diferencias son pequeñas (normalmente menos de 0,5 s) y no siguen ninguna tendencia.
  - Si la diferencia es parecida en todos los puntos, hay un desfase constante: súmalo a los tiempos o transcribe.
  - Si la diferencia crece a lo largo del vídeo, hay deriva (por ejemplo, subtítulos hechos para otra frecuencia de fotogramas): transcribe.
  - No uses entradas que empiecen en medio de habla continua, porque no tienen un silencio delante. Una coincidencia aislada no prueba nada.
- **Huecos.** Un hueco largo entre entradas que coincide con un silencio detectado es un silencio real. Si en el hueco hay sonido, hay audio sin texto (habla omitida, música o ruido).
  - Extrae ese tramo con un nombre nuevo: `ffmpeg -hide_banner -n -ss INICIO -to FIN -i 'TRABAJO/audio.wav' 'TRABAJO/hueco-INICIO.wav'`.
  - Transcríbelo con `--no-vad` y suma `INICIO` a sus tiempos.
  - Si no hay transcriptor, revisa el tramo con `frames` y anótalo como limitación en `analisis.md`.

`silencedetect` distingue sonido de silencio, pero no voz de música: usa sus tiempos como referencia, nunca como evidencia del contenido.

## Selección y montaje

Crea `TRABAJO/seleccion.json` copiando `source` y `audio_stream` de `metadata.json`. La ruta es específica de cada trabajo y de cada máquina: si el vídeo se mueve, se copia o cambia su fecha de modificación, el plan deja de ser válido y hay que volver a copiar `source` de un `probe` nuevo. Los segmentos deben estar en orden cronológico, no solaparse (pueden ser contiguos) y quedar dentro de la pista de vídeo:

```json
{
  "source": {"path": "RUTA_ABSOLUTA_VIDEO", "size": 123456, "mtime_ns": 123456789},
  "audio_stream": 1,
  "segments": [
    {
      "start": 12.3,
      "end": 45.8,
      "title": "Requisito y excepción",
      "reason": "Conserva el requisito, su ámbito y la excepción que condiciona su aplicación.",
      "audio_evidence": "12.3–45.8: explicación del requisito y su excepción; transcripción contrastada.",
      "visual_evidence": "18 y 32 s: tabla inspeccionada con los límites y su nota al pie."
    }
  ]
}
```

Los valores son ilustrativos. `start` y `end` son segundos numéricos; `title`, `reason`, `audio_evidence` y `visual_evidence` son textos no vacíos y se ignoran las claves adicionales. El plan se admite en UTF-8 con o sin BOM. Registra evidencia real; en un tramo visual silencioso, indícalo en `audio_evidence`. En una toma sin material gráfico técnico, describe lo observado en `visual_evidence`. El script valida estructura y tiempos; no puede verificar la veracidad de estas observaciones.

```text
python3 'SKILL_DIR/scripts/video.py' render 'video.mp4' --plan 'TRABAJO/seleccion.json' --out 'TRABAJO/final'
```

Antes de crear la salida, `render` valida el plan contra el final de la pista de vídeo (que tiene en cuenta su `start_time` y, en MKV/WebM, su etiqueta `DURATION`) y rechaza las fuentes HDR (PQ/HLG) y un FFmpeg sin libx264 o AAC. Después:

1. Guarda el plan validado como `seleccion.json` en la carpeta de `--out`. Es el mismo contenido reescrito como JSON con sangría, no una copia byte a byte.
2. Recodifica cada corte, solo con vídeo, a frecuencia constante: la base de la fuente (`r_frame_rate`) si es válida y no supera 120 fps; si no, `avg_frame_rate` con la misma condición, y 30 fps si ninguna la cumple (una grabación de 144 o 240 fps se monta a 30 fps). Empieza por el fotograma más próximo a `start` (a lo sumo medio fotograma de diferencia) y decodifica desde antes del corte, así que las fuentes de frecuencia variable con fotogramas retenidos quedan a frecuencia constante sin perder la imagen en pantalla. Usa H.264 CRF 18, preset fast, 8 bits yuv420p y sin fotogramas B (para que la concatenación sea exacta; el archivo crece en torno a un 6 %), con la resolución original y un píxel de relleno si una dimensión es impar.
3. Comprueba que el corte produjo al menos su duración menos dos fotogramas; si no, se detiene con `El corte N (a–b s) solo produjo X s de vídeo.`
4. Extrae como PCM el audio de la pista elegida, desde exactamente `start` y con la duración exacta del vídeo renderizado. Cada unión queda con un desfase máximo de medio fotograma y el desfase no se acumula.
5. Concatena el vídeo sin recodificar y codifica el audio concatenado una sola vez en AAC 192 kbps. La concatenación se ejecuta dentro de la carpeta temporal con nombres relativos, por lo que las rutas de salida con `#` o `?` funcionan (Windows no admite `?` en nombres de archivo).
6. Verifica la duración del vídeo frente a la suma de los cortes (±0,25 s) y frente al audio (±0,1 s), y decodifica el archivo completo.
7. Escribe `resumen.mp4` y `resumen.md` (nombre del archivo de origen, duraciones, reducción, número de cortes y tabla de correspondencias). No incluye la ruta completa.

Con contenedores sin índice (MPEG-TS, M2TS) la búsqueda solo avanza: el asistente decodifica desde 10 s antes del corte y, si aun así el contenedor entrega el primer fotograma después del corte, se detiene con `El corte N … no se puede situar`. Convierte esas fuentes a MP4 o MKV antes de montar.

`resumen.mp4` solo contiene la pista de vídeo y la pista de audio elegida: se descartan los subtítulos incrustados, las demás pistas de audio, los capítulos y los metadatos del contenedor. El montaje no acelera, no recorta la imagen y no añade rótulos ni transiciones; no apliques esos cambios con FFmpeg fuera de `render`.

No utiliza copia directa para cortar: los límites entre fotogramas clave no serían precisos. Los intermedios se guardan en una carpeta temporal `cortes-*` dentro de la carpeta de `--out` y se eliminan al terminar o fallar; tras una interrupción puede quedar y debe borrarse a mano. No se borra el vídeo ni el material de análisis. `--threads` limita los hilos de codificación (por defecto, el mínimo entre 4 y los núcleos disponibles); redúcelo si falta memoria con fuentes 4K. Prevé espacio para los cortes intermedios y el MP4 final. CRF 18 puede producir un archivo con más bitrate que una grabación de pantalla muy comprimida.

El montaje se reanuda: cada corte verificado queda en `cortes/<clave>.mkv` y `--budget` limita el tiempo por llamada, que devuelve 3 con lo que falta. Un cerrojo exclusivo impide dos montajes a la vez sobre el mismo trabajo.
Órdenes de `render`: `--accept 'frase literal del usuario'` o `--directo` autorizan el montaje, `--budget` lo acota por llamada y `--dry-run` estima el coste imprimiendo `{reused, new, eta_s}` —cortes reutilizables, cortes nuevos y segundos— sin montar nada. No lo confundas con `plan --dry-run`: `plan --dry-run` muestra el plan propuesto sin escribirlo; `render --dry-run` estima el coste del montaje sin renderizar. En vídeos largos con muchos cortes, ejecútalo en segundo plano si el cliente lo permite. Las fuentes con varias pistas de vídeo se rechazan: normalízalas antes. Las discontinuidades de tiempo y los desfases de inicio inusuales entre pistas requieren revisión específica; no garantices fidelidad con la ruta estándar si los metadatos los indican. En fuentes de 10 bits o 4:4:4, revisa la legibilidad del texto fino tras la conversión; en fuentes de frecuencia variable, revisa con especial atención las uniones.

## Revisión del resultado

Las uniones son los finales de la columna «Salida» de `resumen.md`, salvo el último. Para cada unión `U`, extrae fotogramas de la salida en una carpeta nueva:

```text
python3 'SKILL_DIR/scripts/video.py' frames 'TRABAJO/final/resumen.mp4' --out 'TRABAJO/revision/union-01' --start U-0.2 --end U+0.2 --step 0.04
```

Usa como `--step` la duración de un fotograma de la salida, que tiene frecuencia constante (0,04 s a 25 fps). Cada imagen es un proceso de FFmpeg: acota el intervalo a las uniones y no barras el vídeo entero con ese paso. Antes de `U` solo debe verse el corte anterior y, desde `U`, el siguiente, sin fotogramas ajenos. Revisa igual el principio (`--start 0 --end 0.4`) y el final (`--start <final − 0,4>`, omitiendo `--end` para usar la duración exacta).

Para el audio, escucha cada unión si puedes. Si no, detecta los silencios de la salida con el método de [Sincronización y huecos sin escuchar](#sincronización-y-huecos-sin-escuchar), usando `-i 'TRABAJO/final/resumen.mp4' -map 0:a:0`. Convierte cada límite al tiempo de origen (origen = salida − inicio de salida del corte que lo contiene + inicio de origen) y compáralo con el límite detectado en `audio.wav`: la diferencia no debe superar medio fotograma más la imprecisión de la detección. Un silencio que atraviesa una unión se detecta una sola vez: convierte su inicio con el corte anterior y su final con el siguiente. Los límites en 0, al final de la salida (el último `silence_end` puede superar un poco su duración) o sobre una unión los crea el propio corte y no tienen equivalente en `audio.wav`: en ellos, comprueba solo que el instante de origen del lado silencioso cae dentro de un silencio de `audio.wav`. Comprueba con las marcas por palabra o con los subtítulos que ninguna unión corta una frase, y anota en las limitaciones lo que no pudiste escuchar.

Completa el `resumen.md` de la carpeta que vayas a entregar (si montaste varias versiones, solo esa): sustituye sus dos últimas líneas («Revisión editorial pendiente…» e «Indicar aquí…») por las secciones «Temas conservados», «Exclusiones deliberadas» (con tiempos de origen) y «Revisión y limitaciones» (qué se vio, qué se oyó o midió y qué no se pudo comprobar). Si corriges la selección, monta en otra carpeta (`final-2`, `final-3`…).

Si un comando falla, no repitas descargas o renderizados sin diagnosticar el error. Si no existe capacidad de inspeccionar imágenes o audio/texto temporal fiable, deja el análisis como incompleto y explica qué falta.

Referencias de implementación: [FFmpeg](https://ffmpeg.org/ffmpeg.html) y [faster-whisper](https://github.com/SYSTRAN/faster-whisper). La selección editorial corresponde al agente; el asistente no decide qué conocimiento importa.
