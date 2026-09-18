# Especificación · resumir-video 0.2.0

Fecha: 2026-09-18. Estado: aprobada en diseño; pendiente de implementación.
Revisada con tres críticas adversariales (cobertura, ambigüedad y viabilidad); las correcciones están
incorporadas y las comprobaciones empíricas se indican con «(comprobado)».

Amplía la skill `resumir-video` con tres capacidades pedidas por el usuario: objetivo de compresión
parametrizable, revisión previa de los highlights en lenguaje natural y entrada de solo audio con
documento como entrega. Sustituye el criterio «no acelerar ni quitar pausas» de la 0.1.0.

## 1. Objetivo y alcance

| Incluye | No incluye |
| --- | --- |
| Objetivo de duración en porcentaje o minutos, con velocidad y pausas configurables | Narración sintética, música, subtítulos incrustados o transiciones |
| Propuesta previa de cortes y edición conversacional antes y después del montaje | Interfaz gráfica, servicio o API |
| Entrada de solo audio con documento (Markdown, y DOCX si hay conversor) como única entrega | Montaje de audio resumido (descartado por el usuario) |
| Documento equivalente junto al MP4 en entradas de vídeo | Vídeo sin pista de audio (grabación de pantalla muda) |
| Montaje reanudable con caché de cortes y validación del resultado | Traducción, doblaje o envío del medio a servicios externos |

Se mantienen las garantías de la 0.1.0: evidencia de audio e imagen en vídeo, orden cronológico, nada
publicado se sobrescribe, procesamiento local y separación entre el juicio del agente y las operaciones
deterministas del asistente.

## 2. Requisitos confirmados

| Id | Requisito | Origen |
| --- | --- | --- |
| R1 | Objetivo de compresión como porcentaje del original («10 %») o duración absoluta («12 min»). Por defecto se aplican selección, eliminación de pausas y velocidad ×1,25; velocidad y pausas configurables. Si el objetivo destruye contexto, se avisa | Usuario, 2026-09-17 |
| R2 | Antes de montar se muestran los cortes propuestos y se espera aceptación; el usuario acepta, quita, amplía o añade en lenguaje natural. También después del montaje, generando versiones nuevas | Usuario, 2026-09-17 |
| R3 | Entrada de solo audio: no se monta audio; se entrega documento con resumen, ideas clave y preguntas y respuestas, en Markdown y, si hay Pandoc o python-docx, también en DOCX. Su ausencia se avisa antes de empezar y se registra en las limitaciones | Usuario, 2026-09-17 |
| R4 | En vídeo se entrega siempre ese mismo documento junto al MP4, con tiempos del original y del resumen | Usuario, 2026-09-17 |
| R5 | Se conservan las garantías, dependencias, preferencia por subtítulos fiables y pruebas de la 0.1.0 | D-003, D-004, D-006 |

Decisiones tomadas en la sesión de diseño:

| Id | Decisión |
| --- | --- |
| A-1 | Sin objetivo indicado no hay porcentaje fijo: manda el criterio editorial y la propuesta informa del porcentaje resultante |
| A-2 | La revisión previa es obligatoria salvo `directo`; tras el montaje, «…y móntalo» equivale a aceptación solo si la edición no introduce ningún aviso que no estuviera en la versión aceptada anterior y no deja decisiones abiertas |
| A-3 | En modo audio también hay revisión previa: se presenta el esquema (ideas y preguntas con tiempos) y se acepta antes de redactar |
| A-4 | Un cambio que solo afecta al documento publica `vN/resumen-rM.md` y `vN/resumen-rM.docx` junto a los anteriores, sin volver a montar |
| A-5 | Banda del objetivo: `[max(0, T_obj − d), T_obj + d]` con `d = max(0,05 · T_obj, 10 s)`, medida sobre la duración de salida estimada |
| A-6 | La skill vive en `plugins/resumir-video/skills/resumir-video/` (D-004); la implementación se hace en un worktree aislado |

## 3. Arquitectura

Cinco archivos en `scripts/`, todos con biblioteca estándar y FFmpeg, para que ningún módulo crezca sin
control (la 0.1.0 tiene 581 líneas en `video.py` y 241 en `test_video.py`):

| Archivo | Contenido |
| --- | --- |
| `common.py` | Ejecución de FFmpeg, publicación atómica, cerrojo, identidad y huella, línea temporal, energía, interpretación del objetivo, historial, avisos |
| `video.py` | Punto de entrada y subcomandos `check`, `probe`, `prepare`, `frames`, `transcribe`, `search` |
| `plan.py` | `plan`: tramos, estimación, estados, sugerencias, versión y propuesta |
| `render.py` | `render`: caché, presupuesto, montaje, ensamblado y validación |
| `doc.py` | `doc` y `compare`: expansión de marcas, DOCX, timeline y cobertura |

`video.py` fija `sys.dont_write_bytecode = True` antes de importar los módulos hermanos, de modo que la
carpeta de la skill nunca recibe escrituras. Importaciones perezosas: `faster_whisper` en `transcribe`,
`docx` en `doc`, `PIL` solo para el PNG del timeline. Python admitido: 3.10–3.13 (no se usa `audioop`,
eliminado en 3.13).

| Subcomando | Estado | Propósito |
| --- | --- | --- |
| `check` | ampliado | Añade filtros obligatorios, Pandoc, python-docx, Pillow y memoria disponible, indicando qué se degrada si falta cada opcional (sin afectar al código de salida) |
| `probe` | igual | Pistas, formato e identidad |
| `prepare` | ampliado | Añade `kind` (video\|audio), huella, línea temporal y energía |
| `frames` | reescrito | Barrido secuencial por bloques con índice de cambios y hojas de contacto |
| `transcribe` | reescrito | Bloques reanudables, recuperación de huecos, dispositivo automático |
| `search` | nuevo | Búsqueda en la transcripción sin distinguir tildes ni mayúsculas |
| `plan` | nuevo | Tramos, estimación, avisos, sugerencias, versión y propuesta (vídeo y audio) |
| `render` | reescrito | Caché por corte, presupuesto de tiempo, ensamblado y validación |
| `doc` | nuevo | Expande marcas de tiempo y genera DOCX |
| `compare` | nuevo | Cobertura de palabras del resumen frente al original (informativo) |

Reparto de responsabilidades:

- **Agente:** interpreta la invocación y el lenguaje natural, reúne evidencia, construye el inventario
  con prioridades y reservas, escribe borradores y documento, revisa uniones y cobertura.
- **Script:** calcula bordes, tramos, estimaciones, avisos y sugerencias; monta, valida, expande marcas
  y convierte a DOCX. Nunca decide qué conocimiento importa.

**Símbolos.** `T_obj`: duración objetivo de salida. `T_orig`: duración del medio. `F`: cadencia fijada
una vez en `metadata.json` (`r_frame_rate` si es finita y no supera 120 fps; si no, `avg_frame_rate` con
el mismo tope; si no, 30 fps, como `output_rate()` de la 0.1.0). `SR`: frecuencia de muestreo de la
pista de audio elegida, que reutiliza el AAC final. `L`: suma de los tramos de un corte ya ajustados a
la rejilla. `N`: fotogramas del corte montado. `M`: muestras de su audio. `v`: velocidad. `ρ`: retención
de audio tras quitar pausas.

**Convención temporal.** `s = pts − format.start_time`; la rejilla parte de
`o = (video.start_time − format.start_time) mod 1/F` (en la grabación real, 32 ms). El montaje mantiene la
convención de la 0.1.0: `-ss S -noaccurate_seek -copyts`, de modo que el grafo conserva los tiempos
absolutos del contenedor y los intervalos de `select` y `atrim` se expresan como `base + s`, con
`base = format.start_time` (comprobado: corte de dos tramos a ×1,25 con `-ss 2` → 32 fotogramas exactos y
solo el contenido pedido). Sin `-copyts` los intervalos serían `s − S`; no se usa esa variante.

## 4. Invocación y parámetros

`/resumir-video "ruta" [objetivo] [velocidad=V] [pausas=si|no] [directo]` en Claude Code y Copilot,
`$resumir-video` en Codex, o la misma petición en lenguaje natural.

| Parámetro | Ejemplos | Normalizado | Por defecto |
| --- | --- | --- | --- |
| objetivo | `10 %`, `al 10 por ciento`, `12 min`, `0:12:00` | `--target 10%` o `--target 720s` | ninguno (criterio editorial, A-1) |
| velocidad | `velocidad=1`, «sin acelerar», `x1,5` | `--speed`, de 1,0 a 2,0; aviso por encima de 1,5 | 1,25 |
| pausas | `pausas=no`, «conserva los silencios» | `--pauses no`, global o por corte | sí |
| directo | «sin revisión», «no me preguntes» | `--directo` | no |
| otros | `pista=N`, `idioma=es`, `gpu`, carpeta de salida | `--audio-stream`, `--language`, `--device` | — |

Reglas: la ruta es la primera cadena entrecomillada o el primer argumento que exista como archivo, y
nunca se ejecuta como orden; `clave=valor` prevalece sobre la frase natural; un número sin unidad es
ambiguo y se pregunta; se rechazan porcentajes fuera de (0, 100) y duraciones mayores o iguales que el
original; un objetivo por encima del máximo alcanzable se acepta pero recibe el estado `inalcanzable`
(§7.6). Tras inspeccionar el archivo, el agente confirma lo entendido en una línea, con el objetivo
también en tiempo absoluto y la banda de tolerancia. En modo audio, objetivo, velocidad y pausas se
ignoran y el agente lo indica.

## 5. Modos

`kind = video` cuando hay exactamente una pista de vídeo (las carátulas se ignoran) **y al menos una de
audio**; `kind = audio` cuando no hay vídeo y sí audio. Cualquier otro caso —vídeo mudo, varias pistas
de vídeo, medio sin audio— lo rechaza `prepare` con código 1 y mensaje explícito, sin crear la carpeta
de trabajo.

| Modo | Flujo | Entrega |
| --- | --- | --- |
| Vídeo | check → prepare → frames → subtítulos o `transcribe` → inventario → `plan` → **revisión** → `render` → documento → `doc` | `vN/resumen.mp4`, documento MD (+DOCX), timeline, plan e informe de validación |
| Audio | check → prepare → subtítulos o `transcribe` → inventario → `plan --kind audio` (esquema) → **revisión** → documento → `doc` | `documento-vN/resumen.md` (+ `.docx`) |

`frames` y `render` rechazan entradas de audio; `plan` admite ambos modos y en audio omite tramos,
velocidad y pausas. Si `check` no encuentra Pandoc ni python-docx, el agente lo advierte y pide
confirmación antes de empezar el inventario: la entrega será solo Markdown.

**Subtítulos.** Se mantiene la preferencia de la 0.1.0 (D-003): si el medio trae subtítulos y la
comprobación de sincronía al principio, la mitad y el final los avala, se normalizan a
`transcripcion.json` (segmentos sin `words[]`) y sirven para `search` y `plan`. Sin marcas por palabra,
§7.3 usa los límites de segmento y se emite `sin_marcas_por_palabra`.

## 6. Archivos de trabajo y versionado

```text
resumenes/<nombre>/
├── .gitignore              «*»
├── metadata.json           probe + source + kind + huella + línea temporal + F
├── audio.wav               mono 16 kHz PCM 16 bits (solo análisis)
├── energia.f32             RMS de 10 ms en dBFS (se calcula una vez)
├── fotogramas/bSSSSS/      frame-NNNN.jpg, indice.gray, hoja-NNN.jpg, index.json
├── transcripcion.json      (+ transcripcion.parcial/ con bloques y huecos)
├── analisis.md             inventario del agente
├── borrador-vN.json        candidatos: incluidos y reservas
├── seleccion-vN.json       plan inmutable con tramos y estimación (vídeo)
├── esquema-vN.json         ideas y preguntas con tiempos (audio)
├── propuesta-vN.md         lo que se muestra al usuario
├── documento-vN.md         borrador del documento con marcas
├── historial.jsonl         init, edit, accept, render, verify, doc, deliver
├── cortes/<clave>.mkv      caché de cortes (+ .json al terminar)
├── vN/                     resumen.mp4, seleccion.json, validacion.json, montaje.md, cobertura.json,
│                           uniones/, resumen.md, resumen.docx, resumen-rM.*, revisiones.json, timeline.*
└── documento-vN/           entrega del modo audio: resumen.md (+ resumen.docx)
```

- **Borrador:** `{parent, request, settings, segments:[{id, start, end, title, phrase, reason,
  audio_evidence, visual_evidence, priority 1-3, included, pinned, depends_on, remove_pauses,
  visual_only}], excluded}`. Los identificadores son enteros estables (máximo + 1) y nunca se reutilizan.
- **Plan (`seleccion-vN.json`):** añade `version`, `parent`, `changes`, los tramos y la estimación de
  cada corte, `estimate`, `alternativas`, `sugerencias`, `warnings` y el sha256 canónico del plan.
- **Identidad y caché.** La identidad del medio es la huella: tamaño, `mtime_ns` y sha256 de los
  primeros y últimos 4 MiB. `render` acepta un plan cuyo `source.path` haya cambiado si la huella
  coincide: lo avisa y actualiza `source` en el plan publicado; una huella distinta sigue siendo error.
  La clave de caché es el sha256 de huella, pista de audio, tramos redondeados al milisegundo,
  velocidad, `F`, parámetros del codificador, índice y total de subcortes y versión de FFmpeg.
- **Versiones.** `N` se reserva creando en exclusiva `seleccion-vN.json` (o `borrador-vN.json`); si ya
  existe se reintenta con `N+1` hasta tres veces y después se devuelve código 1. `historial.jsonl` se
  escribe en modo añadir, con un registro por llamada menor de 4 KiB. «Vuelve a la v2» copia
  `seleccion-v2.json` a un borrador nuevo. Las revisiones del documento se publican como
  `vN/resumen-rM.md` y `.docx` (M ≥ 2), registradas en `vN/revisiones.json` con motivo, frase del
  usuario y fecha; la entrega apunta siempre a la M mayor.
- **Planes heredados.** `plan --import ruta` convierte un plan 0.1: cortes ordenados con `id` desde 1,
  `priority = 1`, `included = true`, `remove_pauses` y `visual_only` a falso, `depends_on` vacío, un
  tramo `[start, end)` y velocidad 1,0; la identidad se contrasta solo con tamaño y `mtime_ns` y se
  completa la huella desde el archivo actual con aviso `identidad_parcial`. El resultado es un borrador
  que sigue exigiendo revisión y aceptación.
- **Regla de sobrescritura (0.2.0).** Solo `prepare` crea `resumenes/<nombre>/`, y falla si existe.
  Dentro, `frames`, `transcribe` y `render` admiten carpetas existentes para reanudar: nunca reemplazan
  un archivo publicado y renombran a `*.parcial` lo incompleto. `vN/`, `documento-vN/` y los JSON
  publicados son inmutables.

## 7. Compresión

1. **Presupuesto.** `plan --dry-run` informa de la retención `ρ` —medida sobre los cortes candidatos
   (incluidos y reservas), con `ρ = 1` en los `visual_only` y en los que llevan `remove_pauses: false`,
   y recalculada en cada `plan`—, del presupuesto de fuente `B = T_obj · v / ρ`, del tiempo de salida
   que ocupan los cortes de prioridad 1 y del porcentaje mínimo alcanzable sin sacrificarlos.
2. **Selección (agente).** Primero prioridad 1, después 2 y 3 por valor editorial hasta entrar en la
   banda del objetivo. Nunca se rellena: si sobran segundos se recortan frases redundantes.
3. **Bordes (script).** Si la energía RMS de 10 ms supera −50 dBFS —el mismo umbral de silencio del
   punto 4, configurable con `--silence-db`— en alguno de los 80 ms siguientes al final del corte, este
   se lleva al primer silencio de al menos 0,1 s dentro de los 0,6 s posteriores, sin invadir la palabra
   siguiente (su inicio − 0,02 s); el inicio es simétrico. Sin silencio cercano se emite `borde_en_voz`.
   El ajuste se aplica en orden cronológico y nunca cruza al vecino; los cortes que queden contiguos o a
   menos de un fotograma se fusionan (identificador menor, prioridad mayor, unión de tramos y
   evidencias) y la fusión se anota en `changes`.
4. **Pausas.** Silencios de 0,30 s o más por debajo de −50 dBFS se sustituyen por un hueco conservando
   0,08 s a cada lado. Se descartan tramos menores de 0,12 s y, en los extremos, menores de 0,20 s. Los
   tramos se ajustan a la rejilla y se fusionan los separados por menos de un fotograma. Los cortes
   `visual_only` conservan sus pausas. Todo corte debe conservar al menos un tramo y `N ≥ 1`: si
   `L < v / F`, vuelve a reservas con aviso `corte_vacio` anotado en `changes`.
5. **Velocidad y estimación exacta.** Por corte, `N = round(L · F / v)` y `M = round(N / F · SR)`; la
   duración estimada es `Σ N / F`, con margen de 0,1 s por el relleno del códec. En cortes divididos en
   subcortes, `N` y `M` se calculan para el corte completo y se reparten (`N_k = round(L_k · F / v)`
   para los primeros y `N_n = N − Σ N_k` para el último).
6. **Estados:** `ok`, `por_encima`, `por_debajo`, `sin_objetivo`, `inviable` (los cortes de prioridad 1
   superan la banda) e `inalcanzable` (`T_obj > T_max + d`, con `T_max = T_orig · ρ / v`). Las
   `sugerencias` nunca se aplican solas: respetan prioridad 1, los cortes fijados por el usuario
   (`pinned`) y las dependencias. Si es inviable se ofrece la velocidad necesaria (hasta ×1,5), qué
   esenciales habría que sacrificar o el porcentaje mínimo razonable; si es inalcanzable, el objetivo
   máximo cumplible y las alternativas `velocidad=1` y `pausas=no`, sin alargar nunca el resumen con
   material prescindible. `alternativas` recoge las cuatro combinaciones de velocidad y pausas.
7. **Avisos.** Todos llevan `codigo`, `corte`, `mensaje` y `bloquea`.

| Aviso | Se emite cuando | Bloquea |
| --- | --- | --- |
| `esenciales_superan_objetivo` | La suma de prioridad 1 supera `T_obj + d` (estado `inviable`) | Sí |
| `objetivo_muy_bajo` | `T_obj < 0,05 · T_orig` | No |
| `objetivo_muy_alto` | `T_obj > T_max + d` (estado `inalcanzable`) | No |
| `dependencia_excluida` | Un corte incluido depende de otro excluido (pregunta, premisa o corrección) | Sí |
| `tema_sin_cubrir` | Un tema marcado como imprescindible en el inventario no tiene ningún corte incluido | Sí |
| `corte_vacio` | Los descartes dejan el corte sin tramos o con `L < v / F` | Sí |
| `corte_breve` | Corte con voz de menos de 3 s de salida | No |
| `visual_breve` | Corte `visual_only` de menos de 4 s de salida | No |
| `borde_en_voz` | No hay silencio en los 0,6 s posteriores al borde ajustado | No |
| `pausas_excesivas` | Las pausas eliminadas superan el 45 % del corte | No |
| `sin_pausas_detectadas` | El percentil 10 del nivel del corte queda por encima de −53 dBFS | No |
| `sin_marcas_por_palabra` | La transcripción procede de subtítulos sin palabras | No |
| `fuente_vfr` | `avg_frame_rate ≠ r_frame_rate` o el sondeo de paquetes detecta cadencia variable | No |
| `huecos_pts` | El sondeo de paquetes detecta saltos mayores de un fotograma | No |
| `identidad_parcial` | Plan importado de la 0.1 sin huella completa | No |
| `origen_reasignado` | El archivo cambió de ruta pero su huella coincide; `render` actualiza `source` | No |
| `cobertura_baja` | `compare` da media menor de 0,9 o algún corte por debajo de 0,85 | No |
| `velocidad_alta` | `v > 1,5` | No |

## 8. Montaje

Por corte, una sola pasada de FFmpeg (filtros verificados en FFmpeg 8.0.1):

- Entrada `-ss S -noaccurate_seek -copyts` con `S = max(0, inicio − seek_margin)`, el margen de búsqueda
  que ya usa la 0.1.0 (3 s, o 10 s en contenedores que solo buscan hacia delante). La lectura **no** se
  acota con `-t` ni con `-to`: junto a `-copyts` ambas dejan la cadena en cero fotogramas (comprobado);
  termina sola cuando `trim=end_frame=N` y `atrim=end_sample=M` cierran la salida. Los intervalos del
  grafo van en tiempo absoluto del contenedor (`base + s`).
- Vídeo: `fps=F` → `trim=end=<base + fin + 1/F>` (cierra la lectura al acabar el corte, ya que `-t` y
  `-to` no sirven con `-copyts`) → `select` (suma de intervalos) → `settb=AVTB` → `setpts=N/F/v/TB` →
  `fps=F` → `tpad=stop=-1:stop_mode=clone` → `trim=end_frame=N` → `setpts=N/F/TB` → relleno a
  dimensiones pares → `format=yuv420p`. El `fps=F` inicial aporta la robustez frente a cadencia variable y fotogramas
  perdidos; `tpad` necesita `stop=-1` para clonar hasta completar `N` (comprobado: con el valor por
  defecto se obtienen 125 fotogramas donde se piden 200). Sin el `fps` inicial, la pausa eliminada queda
  congelada en imagen y el corte pierde su final (comprobado con una fuente cuya luminancia codifica el
  instante de origen).
- Audio: `aresample=async=1:first_pts=0`, `asplit`, `atrim` + `asetpts` por tramo, `concat`,
  `atempo=v`, `apad=whole_len=M` y `atrim=end_sample=M`.
- No se usa `aselect`: en FFmpeg 8.0.1 no descarta muestras (comprobado).
- Máximo 40 tramos por pasada; los cortes con más se dividen en subcortes, cada uno con su entrada de
  caché. Antes de invocar FFmpeg se comprueba `N ≥ 1` y `M ≥ 1` por corte y subcorte.
- Salida intermedia MKV con H.264 (CRF 18, preset fast) y audio PCM de 24 bits; ese PCM no se lee nunca
  desde Python (§8, validación).

Ensamblado: concat demuxer con `-c:v copy` y el audio codificado una sola vez
(`aresample=async=1:min_hard_comp=0.01`, AAC 192 kbps, `+faststart`), lo que mantiene el invariante de
D-006 —audio codificado una sola vez, sin deriva acumulada en las uniones—.

**Validación bloqueante** (sin ella no se publica nada):

- decodificación completa con `-xerror`; fotogramas totales iguales a `Σ N`; diferencia entre audio y
  vídeo menor o igual a 0,1 s;
- colocación de cada corte **frente al original**, en ventanas de inicio y fin: imagen contra el índice
  del barrido (distancia media absoluta de luminancia reducida a 64×64 y normalizada: acepta por debajo
  de 0,08, marca entre 0,08 y 0,15, falla por encima) y envolvente de audio reescalada por la velocidad
  (desfase máximo 45 ms y correlación mínima 0,9 cuando hay voz). Toda envolvente que lea el script
  procede de una decodificación temporal a `-ac 1 -c:a pcm_s16le`, porque `wave` no abre PCM de 24 bits
  ni en coma flotante (comprobado);
- hojas de uniones para la revisión visual del agente.

**Validación informativa:** `compare` se ejecuta siempre que haya transcripción, escribe
`vN/cobertura.json`, no bloquea y devuelve código 0; por debajo de 0,9 de media o 0,85 en algún corte
emite `cobertura_baja`, que el agente resuelve o declara en las limitaciones antes de entregar.

## 9. Revisión en lenguaje natural

**Propuesta (`propuesta-vN.md`)**: cabecera con original, objetivo, banda de tolerancia, estimación,
porcentaje y estado; cadena de técnicas («38 cortes · 16:45 → sin pausas 15:09 → ×1,25 → 12:07»);
cambios respecto a la versión anterior; avisos redactados; tabla `# | Origen | Salida estimada |
Prioridad | Qué se dice`; reservas con lo que aportaría cada una; alternativas y sugerencias; timeline
de texto; ejemplos de respuesta. Con más de 40 filas se agrupa por bloques en el chat. **El agente
termina su turno y espera**, salvo `directo`.

| Petición | Efecto |
| --- | --- |
| «quita el 7 y el 9» | Pasan a reserva |
| «añade el 6» | Se incluye la reserva y queda fijada (`pinned`) |
| «añade la parte donde habla de ATEX» | `search` + contexto + fotogramas; se crea o recupera el corte. Varias coincidencias o ninguna: una pregunta |
| «alarga el 3» / «10 s más» | Se amplía hasta completar la frase o la unidad |
| «acorta el 12», «empieza el 5 cuando dice…» | Se recorta al núcleo o se mueven los límites |
| «parte el 4» / «une 4 y 5» | Identificadores nuevos; al unir se conserva el menor |
| «súbelo al 15 %», «déjalo en 8 min» | Objetivo nuevo y aplicación de las sugerencias mostradas |
| «sin acelerar», «no quites pausas en el 12» | Ajustes globales o por corte |
| «vuelve a la v1», «deshaz» | Se copia esa versión a un borrador nuevo |
| «¿qué has dejado fuera?» | Se muestran reservas y exclusiones sin crear versión |

Reglas: «el 7» es el número de la última propuesta mostrada; no se reordena el vídeo; ante ambigüedad,
una sola pregunta y no se aplica nada. `plan` rechaza sin escribir si hay identificadores inexistentes,
límites fuera del medio, evidencias vacías o solapes estrictos, evaluados sobre los límites entregados
por el usuario antes del ajuste de bordes (los cortes contiguos son legales, como en la 0.1.0).

Tras cada edición se muestra el diff (altas, bajas y cambios con título, segundos y frase), la nueva
estimación y el coste de montaje («reutiliza 36 de 38 · 2 cortes nuevos · ≈2 min»), y se vuelve a
esperar.

**Aceptación:** `render` exige `--accept "frase literal del usuario"` o `--directo`; sin uno de los dos
rechaza el plan. Queda registrado en `vN/seleccion.json` y en `historial.jsonl` junto al sha256 del
plan. `--directo` no anula la protección de dependencias: ante `dependencia_excluida` (o cualquier
aviso bloqueante) `render` termina con código 2 sin escribir nada y nombra los cortes afectados; la
confirmación del usuario se pasa entonces como `--accept`. En modo audio, `doc` exige la misma
aceptación contra el sha256 del esquema.

**Después del montaje:** mismo ciclo hacia `v(N+1)`, sin tocar `vN/`. Si la petición incluye «y
móntalo» y la edición no introduce ningún aviso que no estuviera en la versión aceptada anterior, se
monta sin esperar (A-2); los avisos informativos nunca bloquean y los marcados como bloqueantes en §7.7
siempre obligan a esperar.

## 10. Documento

Estructura: ficha (archivo, duraciones, porcentaje, técnicas y transcriptor); resumen de uno a tres
párrafos; ideas clave con su tiempo; preguntas y respuestas de la sesión más preguntas de repaso,
respondidas solo con contenido de la fuente y marcando «(pendiente de verificar)» lo dudoso; qué se ha
dejado fuera y limitaciones de la revisión. El índice de cortes, el timeline y el informe de validación
existen solo en vídeo: en audio, `[[indice]]`, `[[timeline]]` y `[[validacion]]` son marcas no válidas y
`doc` falla indicando la línea.

El agente escribe marcas y el script las expande: `[[t=752.3]]` → «12:32 (resumen 1:05)» o «12:32 (no
incluido en el resumen)»; `[[r=745-800]]` para intervalos; `[[ficha]]`, `[[indice]]`, `[[timeline]]` y
`[[validacion]]` para bloques generados. La salida se calcula con los tramos y la velocidad; si el
instante cae en una pausa eliminada se usa el inicio del tramo siguiente del mismo corte, y si esa pausa
es la última del corte, el instante de salida de su fin. `doc` falla indicando la línea si hay marcas
desconocidas, fuera de rango, rutas absolutas o textos pendientes de completar.

DOCX: Pandoc si está disponible; si no, python-docx con un subconjunto de Markdown (títulos, párrafos,
listas, tablas, negrita, cursiva, código e imagen). Sin ninguno de los dos se entrega solo Markdown, con
código 0, aviso e instrucciones de instalación; la falta se anticipa tras `check` (§5) y se registra en
las limitaciones del documento. Timeline: siempre en texto; PNG únicamente si Pillow está instalado.

## 11. Fiabilidad

- **Barrido:** un proceso por bloque de 600 s con `fps` y `split`, que produce JPEG de 1280 px, índice
  gris y hojas de contacto; máximo 600 imágenes por llamada. Los bloques terminados se saltan y los
  incompletos se renombran. Detalle a resolución original bajo demanda. Se comprueba el espacio libre
  (unos 900 MB por 2 h).
- **Energía:** lectura por bloques con `wave` y `array`, sin cargar el archivo entero, cacheada en
  `energia.f32`; coste medido de unos 8–11 s por cada 2 h de audio. No se usa `audioop`.
- **Transcripción:** bloques de unos 600 s cortados en la ventana más silenciosa, cada uno guardado por
  separado; el modelo se carga una vez y el idioma se fija con el primer bloque. `--device auto` con
  rutas de DLL configurables en Windows y regreso a CPU si CUDA falla. Los huecos con energía y sin
  palabras se repiten sin VAD; los segmentos dudosos se marcan, no se descartan.
- **Montaje:** cada corte se verifica (fotogramas y muestras) antes de entrar en la caché; `--budget`
  limita el tiempo por llamada y devuelve «pendiente»; el reintento (uno solo, con `-threads 1
  -filter_threads 1`) ocurre únicamente ante fallos de memoria reconocidos en la constante
  `MEMORY_PATTERNS`: `Cannot allocate memory`, `Out of memory`, `av_buffer_alloc() failed`, código 137
  y NTSTATUS 0xC0000017. Un `AVERROR` externo no se reintenta.
- **Protección:** todo se prepara en archivos temporales y se publica renombrando; cerrojo exclusivo
  para el montaje; JSON creados en exclusiva; FFmpeg con `-n`; el original solo se abre en lectura; no
  se escribe nada dentro de la carpeta de la skill.

## 12. Errores

| Código | Significado |
| --- | --- |
| 0 | Correcto (incluye «DOCX no disponible», con aviso) |
| 1 | Error controlado, mensaje `Error: …` |
| 2 | Argumentos inválidos o plan con aviso bloqueante |
| 3 | Pendiente y reanudable (presupuesto agotado), con `{done, total, pending}` |
| 4 | Validación fallida: no se publica; la evidencia queda aparte |
| 130 | Interrupción |

Casos explícitos: audio donde se espera vídeo, vídeo sin pista de audio, HDR, varias pistas de vídeo,
objetivo ambiguo, identificadores inexistentes o solapes, plan sin aceptación, plan con aviso
bloqueante incluso con `--directo`, huella del origen distinta, cerrojo activo, ajustes de transcripción
distintos al reanudar, caché dañada, falta de memoria, marcas inválidas, carpeta de trabajo ya existente
en `prepare` y `vN/` o `documento-vN/` ya publicadas.

## 13. Pruebas

Se conservan las 15 pruebas de la skill y las 23 de `tests/` (medidas el 2026-09-18), ampliadas con las
de abajo; las que solo ejercitaban el `render` de la 0.1.0 se reescriben para conservar su cobertura de
`prepare`, `frames` y `probe`. Comprobaciones
de `AGENTS.md`: `python -B -m unittest discover -s tests`,
`python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"`,
`claude plugin validate plugins/resumir-video --strict` y `claude plugin validate . --strict`.

- **Rápidas (sin FFmpeg):** interpretación del objetivo y banda de tolerancia (porcentaje, duración
  absoluta y el mínimo de 10 s); energía y su presupuesto de tiempo; construcción de tramos (margen,
  descartes, rejilla a 25 y a 29,97 fps, corte vacío); bordes que no invaden palabras ni al vecino y
  fusión de contiguos; conversión de intervalos con `S > 0`; estimación, los seis estados,
  alternativas, sugerencias y una prueba por código de aviso; identificadores y `changes`; `--dry-run`
  no escribe; reserva de versión bajo concurrencia; timeline de texto; expansión de marcas (dentro de un
  tramo, en una pausa intermedia, en la última pausa del corte y fuera de los cortes) con errores por
  línea; subconjunto de Markdown; `MEMORY_PATTERNS`; `search` sin tildes; normalización de subtítulos.
- **Con FFmpeg:** montaje exacto a ×1 y ×1,25 verificando **contenido** con una fuente cuya luminancia
  codifica el instante de origen, con fuente desfasada, con fotogramas perdidos y con un corte que
  termina en el último fotograma del medio, más un control negativo sin el `fps` inicial; pausas con
  tono y silencio alternos; subcortes que reparten `N` y `M`; caché, presupuesto y reanudación; versión
  nueva que reutiliza cortes; cerrojo; validación que detecta un mapa desplazado; plan importado de la
  0.1; barrido con colores de luminancia distinta; modo audio (wav, m4a, m4a con carátula y mp3 si hay
  codificador) y rechazo de vídeo mudo; `doc` con Pandoc, con python-docx y sin ninguno.
- **Transcripción:** con un `faster_whisper` simulado, comprobando límites en el silencio, reanudación,
  huecos sin VAD, idioma fijado y presupuesto.
- **Empaquetado:** versión 0.2.0 en todos los lugares que comprueba `tests/test_packaging.py`,
  referencias existentes, ausencia de rutas absolutas y límites de `SKILL.md`.
- **Aceptación manual antes de publicar:** grabación larga en 4K en un equipo con poca memoria,
  midiendo memoria máxima por corte (40 tramos, 4/2/1 hilos), tiempos de cada fase, cobertura de
  palabras y calibración de umbrales.

## 14. Cambios en la skill y el repositorio

- **`SKILL.md`:** versión 0.2.0; descripción que cubre vídeo y audio; secciones de invocación, modos y
  flujo en once pasos; sustitución de las reglas «no aceleres» y «sin porcentaje fijo»; se mantienen
  ambas modalidades, el orden original, la preferencia por subtítulos fiables, la exclusión de datos
  sensibles y el trabajo local.
- **Referencias:** `operacion.md` actualizada (se retiran «el montaje no se reanuda» y «una búsqueda por
  imagen»); nuevas `compresion.md`, `revision.md` y `documento.md`.
- **Versión 0.2.0** en: `CHANGELOG.md`, los tres `plugin.json`, `.claude-plugin/marketplace.json`
  (`metadata.version` y `plugins[0].version`), `SKILL.md` (`metadata.version`), `video.py`
  (`__version__`), `README.md` («Versión 0.2.0 ·»), primer párrafo de `docs/capacidades.md` y la línea
  «Estado: versión 0.2.0» de `docs/instalacion.md`. El CHANGELOG marca como incompatible los nuevos
  valores por defecto y la aceptación obligatoria.
- **Documentación del repositorio:** `docs/requisitos.md` (R1–R5, decisiones A-1…A-6 y umbrales
  provisionales), `docs/capacidades.md` (entradas, salidas, garantías, reasignación por huella y
  «Sincronía sin deriva»), `docs/arquitectura.md` (cinco módulos y montaje en una pasada),
  `docs/instalacion.md` (Pandoc, python-docx y Pillow opcionales), `docs/plan.md` y `README.md`.
- **Decisiones nuevas** en `docs/decisiones.md`: D-007 compresión por defecto; D-008 revisión previa con
  aceptación registrada y versiones inmutables; D-009 montaje por cortes en caché con recuento forzado
  de fotogramas y muestras, junto con una actualización fechada de D-006 (la pasada única produce vídeo
  y PCM en el mismo MKV, manteniendo el invariante de audio codificado una sola vez); D-010 modo audio y
  documento con motores opcionales; D-011 identidad por huella y reasignación de planes.

## 15. Umbrales provisionales y riesgos

Umbrales pendientes de calibrar con material real, documentados como provisionales: silencio a
−50 dBFS con 0,30 s y margen de 0,08 s; `sin_pausas_detectadas` a −53 dBFS; recuperación de huecos del
VAD; patrones de falta de memoria; umbral de imagen en la validación de colocación (0,08 y 0,15);
desfase máximo de la envolvente (40 ms) con guarda de modulación de 6 dB y bloqueo a 8 dB; presupuesto
de tiempo de la energía (medido: 11,9 s por 2 h de audio, alarma a 30 s).

| Riesgo | Mitigación |
| --- | --- |
| Tamaño del cambio: unas 1.900 líneas de código en cinco módulos y unas 900 de pruebas | Implementación por etapas verificables, cada una con sus pruebas; pruebas rápidas separadas de las que requieren FFmpeg |
| Otra sesión trabajando en el repositorio | Worktree aislado; integración cuando la 0.1.0 esté consolidada |
| Validación de colocación contra el índice del barrido no medida | Alternativa: decodificación secuencial única del original en los instantes de validación |
| Umbral de pausas dependiente de la grabación | Configurable, anunciado en la propuesta y sujeto a la aceptación manual |
| Dependencias opcionales ausentes | Degradación explícita y anticipada: solo Markdown, timeline de texto, CPU |
