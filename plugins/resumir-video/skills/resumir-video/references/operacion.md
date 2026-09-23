# Operación del asistente

`video.py` usa solo la biblioteca estándar de Python 3.10+ y FFmpeg. Solo `transcribe` importa `faster-whisper`. En los ejemplos, sustituye:

- `SKILL_DIR` por la ruta absoluta de la carpeta que contiene `SKILL.md`.
- `TRABAJO` por la carpeta de trabajo (por defecto, `resumenes/<nombre-del-archivo-sin-extensión>/` bajo el directorio actual).
- `VENV` por la carpeta del entorno de transcripción (véase [Transcripción opcional](#transcripción-opcional)).
- `python3` por el intérprete disponible (`python` o `py -3` en Windows).

Usa rutas absolutas entre comillas simples: en Bash y PowerShell, las comillas dobles no impiden que se ejecute un `$(…)` contenido en un nombre de archivo. Si el nombre contiene una comilla simple, escríbela como `'\''` en Bash o duplícala (`''`) en PowerShell. Si automatizas, pasa los argumentos como lista, sin construir órdenes de shell a partir de nombres de archivo. `python3 'SKILL_DIR/scripts/video.py' <subcomando> --help` muestra cada opción con su valor por defecto.

## Reglas comunes

- Nada publicado se sobrescribe. Solo `prepare --work` exige una carpeta **nueva**: si ya existe, se detiene con `La carpeta ya existe y no se sobrescribe; indica una carpeta nueva (p. ej., con el sufijo -2): <ruta>`. Dentro de ella, `frames`, `transcribe` y `render` **reanudan**: saltan lo terminado, apartan lo incompleto con el sufijo `.parcial` y publican por renombrado atómico. Las carpetas `vN/` y `documento-vN/` y los JSON publicados son inmutables.
- Un trabajo que se queda a medias por presupuesto termina con código 3 e imprime `{"done", "total", "pending", "bloques"}`, con `pending` entero y `bloques` con los nombres que faltan: repite la misma orden para continuar. En `frames`, `done` y `total` son acumulados de todo el intervalo pedido, incluidas llamadas anteriores: es el criterio natural de un barrido reanudable sobre un rango fijo. En `render`, que reanuda desde una caché de cortes, cuentan solo lo que esa llamada concreta monta, no lo ya cacheado: es una diferencia intencional entre ambos, no un error.
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

Si el medio trae subtítulos, usa `transcribe --subtitles` para normalizarlos a `transcripcion.json` en vez de transcribir con un modelo: es más rápido y preserva el texto original. No vuelvas a transcribir sin necesidad. La transcripción es evidencia del audio, nunca evidencia visual.

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

El agente escribe un borrador con los cortes propuestos y `plan` calcula tramos, estimación, avisos y
alternativas a partir de él (detalle en [Compresión](compresion.md)); tras la revisión en lenguaje
natural (detalle en [Revisión](revision.md)), `render` monta y publica la versión aceptada. Ningún
paso admite editar a mano los JSON publicados.

Escribe `TRABAJO/borrador.json` con `segments` en orden cronológico, sin solaparse (los contiguos son
legales) y dentro de la pista de vídeo:

```json
{
  "segments": [
    {
      "id": 1,
      "start": 12.3,
      "end": 45.8,
      "title": "Requisito y excepción",
      "phrase": "Cita representativa de lo que se dice en el tramo.",
      "reason": "Conserva el requisito, su ámbito y la excepción que condiciona su aplicación.",
      "audio_evidence": "12.3–45.8: explicación del requisito y su excepción; transcripción contrastada.",
      "visual_evidence": "18 y 32 s: tabla inspeccionada con los límites y su nota al pie.",
      "priority": 1,
      "included": true,
      "pinned": false,
      "remove_pauses": true,
      "visual_only": false,
      "depends_on": []
    }
  ]
}
```

Los valores son ilustrativos. Por corte: `id` es un entero estable desde 1; `start` y `end`, segundos
numéricos; `title`, `phrase`, `reason` y `audio_evidence` son textos no vacíos (`phrase` es la cita que
aparece en la tabla de la propuesta); `visual_evidence` es obligatorio solo con `--kind video`.
`priority` es 1, 2 o 3. `included`, `pinned`, `visual_only` (por defecto `false`) y `remove_pauses`
(por defecto `true`) son booleanos; `depends_on` lista identificadores de otros cortes de los que
depende. Un corte con `included: false` queda en reserva. El borrador se admite en UTF-8 con o sin
BOM; `plan` rechaza sin escribir nada si hay identificadores repetidos o inexistentes, límites fuera
del medio, solapes estrictos o texto vacío. Registra evidencia real; en un tramo visual silencioso,
indícalo en `audio_evidence`, y en una toma sin material gráfico técnico, describe lo observado en
`visual_evidence`. El script valida estructura y tiempos; no puede verificar la veracidad de estas
observaciones.

```text
python3 'SKILL_DIR/scripts/video.py' plan --work 'TRABAJO' --draft 'TRABAJO/borrador.json' --target '12min' --speed 1.25 --pauses si
```

`--target`, `--speed`, `--pauses`, `--silence-db` y `--kind video|audio` ajustan lo que calcula `plan`
([Compresión](compresion.md)); sin `--kind`, usa el modo que fijó `prepare`. `plan --dry-run` calcula e
imprime el plan sin publicar nada; sin `--dry-run`, publica a la vez `propuesta-vN.md` (para tu
revisión) y `seleccion-vN.json` (el plan que citarás en `render --plan`). Muestra la propuesta y
espera, salvo `--directo`; aplica las peticiones del usuario según [Revisión](revision.md) volviendo a
ejecutar `plan` sobre un borrador derivado. Una vez aceptada:

```text
python3 'SKILL_DIR/scripts/video.py' render 'video.mp4' --work 'TRABAJO' --plan 'TRABAJO/seleccion-vN.json' --accept 'frase literal del usuario'
```

(o `--directo`, que no anula los avisos bloqueantes). `render` no admite `--out`: monta siempre dentro
de `--work` y publica la versión en `TRABAJO/vN/`.

Antes de montar, `render` comprueba que el archivo indicado conserva la huella (tamaño, `mtime_ns` y
sha256) que registró el plan —si solo cambió de ruta, avisa y actualiza `source`; si la huella no
coincide, rechaza el plan y pide volver a planificar sobre el medio actual—, que ningún aviso
bloqueante sigue pendiente (o que hay `--accept`/`--directo`) y que están los codificadores `libx264` y
`aac`. La rotación a SDR y el número de pistas de vídeo ya los exigió `prepare`; `render` no los repite.
Después:

1. Por cada corte —y cada subcorte, si `plan` lo dividió por tener demasiados tramos tras quitar
   pausas—, dos pasadas de FFmpeg sobre los mismos tramos (`spans`) que fijó el plan: una de vídeo a
   frecuencia constante (la base de la fuente, `r_frame_rate`, si es válida y no supera 120 fps; si no,
   `avg_frame_rate` con la misma condición, y 30 fps si ninguna la cumple, de modo que una grabación de
   144 o 240 fps se monta a 30 fps) con H.264 CRF 18, preset fast, 8 bits yuv420p y sin fotogramas B
   (para que la concatenación sea exacta), decodificando desde antes del corte y recortada exactamente
   a los `N` fotogramas que calculó el plan, con un píxel de relleno si una dimensión es impar; y otra
   de audio, PCM sobre la pista elegida, recortada a las `M` muestras que calculó el plan. Ambas pasadas
   se remuxan sin recodificar en un único corte.
2. Si el corte no produce exactamente esos `N` fotogramas y `M` muestras, se detiene sin publicar nada
   con `El corte N subcorte i/total produjo X fotogramas y Y muestras; se esperaban A y B.`
3. Cada corte verificado se cachea en `cortes/<clave>.mkv`, dentro de `--work` (véase más abajo).
4. Concatena los cortes con dos pasadas del demuxor `concat`: la de vídeo copiando sin recodificar y la
   de audio codificándolo una sola vez en AAC 192 kbps.
5. Decodifica el montaje completo, comprueba que el total de fotogramas coincide exactamente con la
   suma de los que fija el plan (si no, `El montaje tiene X fotogramas y el plan suma Y.`), que el
   desfase entre vídeo y audio no supera 0,1 s (`Vídeo y audio difieren D s (máximo 0,1 s): vídeo A s,
   audio B s.`) y compara cada corte contra el original en sus bordes (imagen y envolvente de audio).
6. Publica `vN/resumen.mp4`, `vN/seleccion.json` (el plan con la frase de aceptación), `vN/validacion.json`
   y `vN/montaje.md` —versión, cortes, velocidad, cadencia, duración de salida, desfase vídeo-audio y una
   tabla por corte con origen, salida, colocación de imagen y de audio, y tema—, además de `vN/uniones/`
   con las hojas de contacto de cada unión. Ninguno se sobrescribe después: el nombre del archivo de
   origen, la duración comparada y el porcentaje de reducción los recoge el documento (`vN/resumen.md`)
   que publica `doc` a continuación, no `render` ([Documento](documento.md)).

`resumen.mp4` solo contiene la pista de vídeo y la pista de audio elegida: se descartan los subtítulos
incrustados, las demás pistas de audio, los capítulos y los metadatos del contenedor. El montaje no
recorta la imagen ni añade rótulos o transiciones más allá de la velocidad y las pausas que fija el
plan; no apliques esos cambios con FFmpeg fuera de `render`.

No utiliza copia directa para cortar: los límites entre fotogramas clave no serían precisos. `cortes/`,
dentro de `--work`, es una caché **persistente**: no es una carpeta temporal y no se borra sola ni al
terminar ni al fallar; un corte ya cacheado con los mismos fotogramas y muestras no se vuelve a
renderizar. No se borra el vídeo ni el material de análisis. `--threads` limita los hilos de
codificación (por defecto, el mínimo entre 4 y los núcleos disponibles); redúcelo si falta memoria con
fuentes 4K. Prevé espacio para la caché de cortes y el MP4 final. CRF 18 puede producir un archivo con
más bitrate que una grabación de pantalla muy comprimida.

El montaje se reanuda: `--budget` limita el tiempo por llamada y, si se agota, devuelve 3 con
`{"done", "total", "pending", "bloques"}` —contando solo lo que esa llamada concreta monta, no lo ya
cacheado— para repetir la misma orden. Un cerrojo exclusivo impide dos montajes a la vez sobre el mismo
trabajo. `render --dry-run` estima el coste sin montar nada, imprimiendo `{reused, new, eta_s}` —cortes
reutilizables, cortes nuevos y segundos—; no lo confundas con `plan --dry-run`, que muestra el plan
propuesto sin escribirlo. En vídeos largos con muchos cortes, ejecútalo en segundo plano si el cliente
lo permite. No se admiten fuentes con varias pistas de vídeo (se rechazan al preparar el trabajo):
normalízalas antes. Las discontinuidades de tiempo y los desfases de inicio inusuales entre pistas
requieren revisión específica; no garantices fidelidad con la ruta estándar si los metadatos los
indican. En contenedores sin índice (MPEG-TS, M2TS), donde la búsqueda solo avanza, `render` decodifica
desde más lejos antes de cada corte (10 s en vez de 3) para reducir el riesgo de aterrizar después del
punto pedido; si aun así no se puede situar, lo revela el mismo aviso de fotogramas y muestras del
punto 2. Convertir esas fuentes a MP4 o MKV antes de montar reduce ese riesgo. En fuentes de 10 bits o
4:4:4, revisa la legibilidad del texto fino tras la conversión; en fuentes de frecuencia variable,
revisa con especial atención las uniones.

## Revisión del resultado

Las uniones son los finales de la columna «Salida» de `vN/montaje.md`, salvo el último. Para cada unión `U`, extrae fotogramas de la salida en una carpeta nueva:

```text
python3 'SKILL_DIR/scripts/video.py' frames 'TRABAJO/vN/resumen.mp4' --out 'TRABAJO/revision/union-01' --start U-0.2 --end U+0.2 --step 0.04
```

Usa como `--step` la duración de un fotograma de la salida, que tiene frecuencia constante (0,04 s a 25 fps). Cada imagen es un proceso de FFmpeg: acota el intervalo a las uniones y no barras el vídeo entero con ese paso. Antes de `U` solo debe verse el corte anterior y, desde `U`, el siguiente, sin fotogramas ajenos. Revisa igual el principio (`--start 0 --end 0.4`) y el final (`--start <final − 0,4>`, omitiendo `--end` para usar la duración exacta).

Para el audio, escucha cada unión si puedes. Si no, detecta los silencios de la salida con el método de [Sincronización y huecos sin escuchar](#sincronización-y-huecos-sin-escuchar), usando `-i 'TRABAJO/vN/resumen.mp4' -map 0:a:0`. Convierte cada límite al tiempo de origen (origen = salida − inicio de salida del corte que lo contiene + inicio de origen) y compáralo con el límite detectado en `audio.wav`: la diferencia no debe superar medio fotograma más la imprecisión de la detección. Un silencio que atraviesa una unión se detecta una sola vez: convierte su inicio con el corte anterior y su final con el siguiente. Los límites en 0, al final de la salida (el último `silence_end` puede superar un poco su duración) o sobre una unión los crea el propio corte y no tienen equivalente en `audio.wav`: en ellos, comprueba solo que el instante de origen del lado silencioso cae dentro de un silencio de `audio.wav`. Comprueba con las marcas por palabra o con los subtítulos que ninguna unión corta una frase, y anota en las limitaciones lo que no pudiste escuchar.

El `resumen.md` que entregarás no se completa a mano después de montar: «qué se ha dejado fuera y las limitaciones de la revisión» y el resto de la estructura los escribe el agente en `documento-vN.md` y `doc` los publica ya expandidos en `vN/resumen.md` ([Documento](documento.md)). `vN/montaje.md`, el informe técnico que escribe `render`, tampoco se toca después de publicado. Si la revisión de uniones o de cobertura descubre un problema, no edites ningún archivo publicado: vuelve a `plan` y publica `v(N+1)` con la corrección; `vN/` queda intacto.

Si un comando falla, no repitas descargas o renderizados sin diagnosticar el error. Si no existe capacidad de inspeccionar imágenes o audio/texto temporal fiable, deja el análisis como incompleto y explica qué falta.

Referencias de implementación: [FFmpeg](https://ffmpeg.org/ffmpeg.html) y [faster-whisper](https://github.com/SYSTRAN/faster-whisper). La selección editorial corresponde al agente; el asistente no decide qué conocimiento importa.
