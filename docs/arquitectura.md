# Arquitectura

## Unidad distribuible

La unidad distribuible es `plugins/resumir-video/`, y dentro de ella la skill `skills/resumir-video/`:

- `SKILL.md`: instrucciones de selección audiovisual y validación editorial, válidas para cualquier agente.
- `agents/openai.yaml`: metadatos de interfaz de Codex; los demás clientes lo ignoran.
- `references/operacion.md`: órdenes, requisitos, formatos y límites del asistente.
- `scripts/video.py`: comprobación del entorno, extracción, transcripción opcional y montaje local con Python estándar y FFmpeg.
- `scripts/test_video.py`: pruebas reproducibles con vídeo sintético, sin descargas.
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

El agente analiza la evidencia y decide los cortes. El asistente ejecuta esas decisiones sin inferir importancia a partir del silencio o de palabras clave. Audio, imágenes y selección comparten la línea temporal del original. `render` recodifica cada corte de vídeo a frecuencia constante desde el fotograma en pantalla en su inicio, extrae su audio como PCM desde ese mismo inicio y con la duración del vídeo renderizado, y codifica el audio una sola vez. Así cada unión queda con un desfase máximo de medio fotograma, sin acumulación ([D-006](decisiones.md#d-006--audio-codificado-una-sola-vez-en-el-montaje)).

La skill resuelve sus recursos respecto a su propio `SKILL.md` y no escribe en su carpeta, que puede ser una caché de plugins de solo lectura. Los materiales de cada trabajo se guardan en una carpeta de trabajo nueva que elige el usuario (por defecto `resumenes/<nombre-del-archivo-sin-extensión>/`). `prepare` crea esa carpeta con su propio `.gitignore` (`*`); la carpeta padre `resumenes/` no recibe ninguno. El entorno virtual de transcripción se comparte en la caché del usuario (`video.py check` indica la ruta).

## Herramientas del repositorio

- `scripts/install.py`: copia la skill en las carpetas de skills personales o de proyecto de cada cliente, sin duplicar las compartidas por Codex y Copilot.
- `tests/test_packaging.py`: coherencia de manifiestos, catálogos, versiones, licencias y frontmatter; portabilidad del contenido distribuido; comportamiento del instalador.

No hay servicio, base de datos ni framework. Los pesos de transcripción y FFmpeg son requisitos externos y no se distribuyen. La [guía de instalación](instalacion.md) y la [referencia de operación](../plugins/resumir-video/skills/resumir-video/references/operacion.md) contienen los detalles operativos; este documento solo describe límites y responsabilidades.
