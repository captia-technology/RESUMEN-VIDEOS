# Contribuir

Este repositorio contiene la skill `resumir-video` y su empaquetado como plugin para Claude Code, GitHub Copilot y OpenAI Codex. No hay aplicación ni servicio. Antes de proponer un cambio, lee [AGENTS.md](AGENTS.md) (mapa del repositorio y reglas de mantenimiento) y el documento que sea fuente de verdad del área que vas a tocar.

## Requisitos

| Requisito | Para qué |
| --- | --- |
| Python 3.10+ | `video.py`, `install.py` y las pruebas; solo biblioteca estándar, nada que instalar |
| FFmpeg con libx264 y AAC | Pruebas de la skill y uso real; en Windows hacen falta `ffmpeg.exe` y `ffprobe.exe` en PATH, no un envoltorio `.cmd` o `.bat` |
| Git | Clonar y publicar |
| PyYAML (opcional) | Validadores de Codex: `python -m pip install pyyaml` |
| faster-whisper (opcional) | Solo para probar `transcribe`; se instala en el entorno virtual que indica `check`, fuera de la skill |

Comprueba el entorno antes de nada; debe terminar en `"ok": true`:

```text
python3 plugins/resumir-video/skills/resumir-video/scripts/video.py check
```

Las instrucciones por sistema operativo y la solución de problemas están en [docs/instalacion.md](docs/instalacion.md#1-requisitos-previos).

## Comprobaciones

Ejecuta las pertinentes y di en el pull request cuáles pasaste y cuáles no:

| Orden | Cubre | Necesita |
| --- | --- | --- |
| `python3 -B -m unittest discover -s tests` | Manifiestos, catálogos, versiones, licencias, frontmatter, portabilidad del contenido distribuido e instalador | Nada más |
| `python3 -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"` | Extracción, montaje, sincronía y validación del plan con vídeo sintético; no descarga nada | FFmpeg |
| `claude plugin validate plugins/resumir-video --strict` y `claude plugin validate . --strict` | Plugin y catálogo | Claude Code |
| `validate_plugin.py` y `quick_validate.py` de Codex ([órdenes en AGENTS.md](AGENTS.md#comprobaciones)) | Manifiesto de Codex y frontmatter de la skill | Codex y PyYAML |

Usa siempre `-B`: sin esa opción quedan carpetas `__pycache__` dentro de la skill, y Codex copia esa carpeta tal cual desde un catálogo local. En Windows, sustituye `python3` por `python` o `py -3`.

El flujo de integración continua ([`.github/workflows/pruebas.yml`](.github/workflows/pruebas.yml)) ejecuta las dos baterías en Ubuntu y Windows con Python 3.10 y 3.12, más una comprobación de los manifiestos. Los validadores de los clientes no están disponibles en los runners: ejecútalos en local antes de publicar.

## Reglas de la skill

- `plugins/resumir-video/skills/resumir-video/` es la **única copia** de la skill. No crees copias en `.claude/skills`, `.agents/skills` ni `.github/skills`: ocultarían o duplicarían el plugin, y las pruebas lo rechazan. Para probarla, usa `claude --plugin-dir plugins/resumir-video` o `scripts/install.py` contra un proyecto temporal.
- La skill debe seguir **autocontenida**: no puede depender de `docs/` ni de otras carpetas del repositorio, ni escribir dentro de su propia carpeta, que puede ser una caché de plugins de solo lectura.
- El texto debe ser **válido para cualquier agente**. Lo específico de un cliente vive en `agents/openai.yaml` y `.codex-plugin/plugin.json`; no lo mezcles con las instrucciones.
- El frontmatter de `SKILL.md` admite solo los campos portables del estándar Agent Skills: `name`, `description`, `license` y `metadata`. Cualquier otro campo hace fallar las pruebas.
- Nada de rutas locales, nombres de clientes ni datos de trabajos reales, ni en lo distribuido ni en la documentación. Las pruebas buscan letras de unidad, carpetas personales y rutas UNC.
- Añade código, dependencias o herramientas solo cuando la tarea lo exija. El asistente usa la biblioteca estándar y FFmpeg; mantenlo así.

## Dónde va cada cambio

Cada dato vive en un único documento y los demás enlazan a él. Actualiza la documentación afectada en el mismo cambio.

| Cambias… | Documenta en |
| --- | --- |
| Comportamiento o criterio editorial de la skill | `plugins/resumir-video/skills/resumir-video/SKILL.md` |
| Órdenes, opciones o formatos de `video.py` | `references/operacion.md` de la skill |
| Qué hace, garantiza o no hace la skill | [docs/capacidades.md](docs/capacidades.md) |
| Instalación, actualización o publicación | [docs/instalacion.md](docs/instalacion.md) |
| Un acuerdo con alternativas descartadas | [docs/decisiones.md](docs/decisiones.md) |
| Qué se ha verificado y qué queda pendiente | [docs/plan.md](docs/plan.md) |
| Cualquier cambio visible para quien la usa | [CHANGELOG.md](CHANGELOG.md) |

Escribe la documentación en español, con secciones cortas y tablas; el código y sus comentarios, en inglés. No marques como comprobado lo que no hayas ejecutado: señálalo como pendiente de evidencia.

## Publicar una versión

1. Usa el mismo número de versión en `CHANGELOG.md`, los tres `plugin.json` (`plugins/resumir-video/plugin.json`, `.claude-plugin/plugin.json` y `.codex-plugin/plugin.json`), `.claude-plugin/marketplace.json` (`metadata.version` y `plugins[0].version`), `SKILL.md` (`metadata.version`), `video.py` (`__version__`), `README.md` («Versión X.Y.Z ·»), el primer párrafo de [docs/capacidades.md](docs/capacidades.md) y la línea «Estado: versión X.Y.Z (fecha)» de [docs/instalacion.md](docs/instalacion.md). `tests/test_packaging.py` falla si alguno no coincide.
2. Ejecuta las pruebas y los validadores, y registra en [docs/plan.md](docs/plan.md) qué se verificó, con qué versiones de cada cliente y qué quedó pendiente.
3. Haz commit y crea la etiqueta con `claude plugin tag plugins/resumir-video` (prueba antes con `--dry-run`; `--push` la publica). El procedimiento completo está en [docs/instalacion.md](docs/instalacion.md#7-publicar-una-versión-nueva).

## Commits y pull requests

- Mensajes en inglés con [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/), como el historial actual: `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `refactor:`, `chore:`. Resumen en imperativo y cuerpo que explique el porqué, con viñetas si el cambio toca varios frentes.
- Un cambio lógico por commit y cambios pequeños y revisables. Respeta el trabajo existente y limita las modificaciones a este repositorio.
- Abre el pull request con la plantilla: qué cambia y por qué, pruebas ejecutadas, documentación actualizada, versión si procede y confirmación de que no se añaden rutas locales ni datos de clientes.

## Informar de un error

Usa la [plantilla de error](https://github.com/captia-technology/RESUMEN-VIDEOS/issues/new/choose) y revisa antes la tabla de [solución de problemas](docs/instalacion.md#8-solución-de-problemas). Incluye:

- Cliente y versión (Claude Code, Copilot CLI, VS Code, Codex u otro) y canal de instalación (plugin o skill independiente).
- Sistema operativo y versión.
- La salida completa de `video.py check`.
- La orden exacta que ejecutaste y el error literal.
- Si el fallo se reproduce con material sintético, como el que generan las pruebas de la skill.

No adjuntes el vídeo, los fotogramas ni la transcripción: contienen material confidencial. Las vulnerabilidades no se publican como incidencias; sigue [SECURITY.md](SECURITY.md).
