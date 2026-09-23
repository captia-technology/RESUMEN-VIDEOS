# Arquitectura

## Unidad distribuible

La unidad distribuible es `plugins/resumir-video/`, y dentro de ella la skill `skills/resumir-video/`:

- `SKILL.md`: instrucciones de selección audiovisual y validación editorial, válidas para cualquier agente.
- `agents/openai.yaml`: metadatos de interfaz de Codex; los demás clientes lo ignoran.
- `references/operacion.md`: órdenes, requisitos, formatos y límites del asistente.
- `scripts/common.py`: ejecución de FFmpeg, publicación atómica, cerrojo, identidad y huella, línea
  temporal, energía, interpretación del objetivo, historial y avisos.
- `scripts/video.py`: punto de entrada y subcomandos `check`, `probe`, `prepare`, `frames`,
  `transcribe` y `search`.
- `scripts/plan.py`: tramos, estimación, estados, sugerencias, versión y propuesta.
- `scripts/render.py`: caché de cortes, presupuesto, montaje, ensamblado y validación.
- `scripts/doc.py`: expansión de marcas, DOCX, timeline y cobertura.
- `scripts/test_*.py`: pruebas reproducibles con medios sintéticos y un `faster_whisper` simulado,
  sin descargas.
- `references/operacion.md`, `compresion.md`, `revision.md` y `documento.md`: órdenes, formatos,
  límites y procedimientos.
- `LICENSE.txt`: licencia MIT, para los canales que copian solo la skill.

El plugin añade tres manifiestos con los mismos metadatos, porque cada cliente elige uno:

| Archivo | Leído por |
| --- | --- |
| `plugin.json` (Agent Plugins 1.0) | GitHub Copilot CLI, VS Code y Codex 0.146 o posterior (nombre, versión y descripción) |
| `.claude-plugin/plugin.json` | Claude Code (y, como alternativa, Copilot y Codex) |
| `.codex-plugin/plugin.json` | Codex: interfaz de la app (combinada con `plugin.json` desde la 0.146), manifiesto completo en Codex 0.131–0.145 y validador `validate_plugin.py` |

## Catálogos

La raíz del repositorio es un catálogo llamado `resumen-videos`:

- `.claude-plugin/marketplace.json`: Claude Code, Copilot CLI y VS Code (Codex lo acepta como alternativa).
- `.agents/plugins/marketplace.json`: formato nativo de Codex, con `policy` y `category`.

Ambos apuntan a `./plugins/resumir-video`. El plugin está en una subcarpeta para que una instalación desde una copia local no arrastre `resumenes/`, `input/` ni la documentación del repositorio.

## Responsabilidades

El agente analiza la evidencia, decide los cortes y espera la aceptación del usuario; el asistente
ejecuta esas decisiones sin inferir importancia a partir del silencio o de palabras clave. `frames`
barre la imagen en un proceso por bloque y deja un índice de cambios reutilizable; `transcribe`
trabaja por bloques reanudables cortados en el silencio. `render` monta cada corte en una pasada de
vídeo y una de audio, los cachea verificados por recuento exacto de fotogramas y muestras, y
concatena copiando el vídeo y codificando el audio una sola vez, de modo que las uniones no acumulan
desfase ([D-006](decisiones.md#d-006--audio-codificado-una-sola-vez-en-el-montaje),
[D-009](decisiones.md#d-009--montaje-por-cortes-en-caché-con-recuento-forzado)). Nada se publica sin
superar la validación bloqueante, y `vN/` y `documento-vN/` son inmutables.

**Desviaciones respecto a la especificación.** Tanto el montaje como el barrido buscan desde
`S = max(0, inicio − seek_margin(data))` —3 s, o 10 s en contenedores que solo buscan hacia
delante—, no desde `inicio − 1`; y, al leer con `-ss S -noaccurate_seek -copyts`, los intervalos del
grafo van en tiempo absoluto del contenedor (`base + s`) en lugar de `s − S`. De ahí que la lectura
no se acote con `-t` ni con `-to`, que con `-copyts` dejan la cadena en cero fotogramas. En el
barrido la cierran los recuentos de cada salida; en el montaje hace falta además una guarda
`trim=end=<base + fin + 1/F>` detrás del `fps` inicial, porque `select` descarta fotogramas en vez de
cerrar la cadena y sin ella se decodifica el medio entero en cada corte (medido: 1 000 fotogramas
leídos frente a 153, con la misma salida)
([D-009](decisiones.md#d-009--montaje-por-cortes-en-caché-con-recuento-forzado)).

La skill resuelve sus recursos respecto a su propio `SKILL.md` y no escribe en su carpeta, que puede ser una caché de plugins de solo lectura. Los materiales de cada trabajo se guardan en una carpeta de trabajo nueva que elige el usuario (por defecto `resumenes/<nombre-del-archivo-sin-extensión>/`). `prepare` crea esa carpeta con su propio `.gitignore` (`*`); la carpeta padre `resumenes/` no recibe ninguno. El entorno virtual de transcripción se comparte en la caché del usuario (`video.py check` indica la ruta).

## Herramientas del repositorio

- `scripts/install.py`: copia la skill en las carpetas de skills personales o de proyecto de cada cliente, sin duplicar las compartidas por Codex y Copilot.
- `tests/test_packaging.py`: coherencia de manifiestos, catálogos, versiones, licencias y frontmatter; portabilidad del contenido distribuido; comportamiento del instalador.

No hay servicio, base de datos ni framework. Los pesos de transcripción y FFmpeg son requisitos externos y no se distribuyen. La [guía de instalación](instalacion.md) y la [referencia de operación](../plugins/resumir-video/skills/resumir-video/references/operacion.md) contienen los detalles operativos; este documento solo describe límites y responsabilidades.
