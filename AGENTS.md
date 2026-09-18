# Mapa para agentes

Este repositorio contiene la skill portable `resumir-video`, distribuida como plugin para Claude Code, GitHub Copilot y Codex. No hay aplicación ni servicio.

## Dónde empezar

- `README.md`: entrada al proyecto y navegación.
- `docs/capacidades.md`: qué hace la skill, garantías y límites.
- `docs/instalacion.md`: instalación, actualización y publicación por cliente.
- `docs/requisitos.md`: alcance confirmado y preguntas abiertas.
- `docs/arquitectura.md`: estado técnico y restricciones conocidas.
- `docs/decisiones.md`: decisiones aceptadas y su motivo.
- `docs/plan.md`: estado del trabajo y próximos pasos.
- `plugins/resumir-video/skills/resumir-video/SKILL.md`: comportamiento y uso de la skill; su carpeta contiene todos sus recursos. Los detalles operativos (órdenes, formatos y procedimientos de revisión) están en `references/operacion.md`, para que `SKILL.md` siga siendo breve.

## Cómo trabajar

- Lee los documentos relevantes antes de cambiar el repositorio. La documentación versionada es la fuente de verdad; no dependas del historial del chat.
- No conviertas suposiciones en requisitos ni elijas tecnologías sin una necesidad confirmada. Registra lo pendiente en su documento correspondiente.
- Mantén cada dato en un único documento y enlázalo desde los demás. Actualiza la documentación afectada junto con el cambio.
- Haz cambios pequeños y revisables. Respeta el trabajo existente y limita las modificaciones a este repositorio.
- Añade código, dependencias y herramientas solo cuando la tarea lo requiera.
- Mantén la skill autocontenida: no debe depender de los documentos ni de otras carpetas de este repositorio, ni escribir dentro de su propia carpeta.
- `plugins/resumir-video/skills/resumir-video/` es la única copia de la skill. No crees copias en `.claude/skills`, `.agents/skills` ni `.github/skills`: ocultarían o duplicarían el plugin. Para probarla, usa `claude --plugin-dir plugins/resumir-video` o `scripts/install.py` hacia un proyecto temporal.
- Usa en la skill solo los campos portables de `SKILL.md` (`name`, `description`, `license`, `metadata`) y texto válido para cualquier agente.

## Comprobaciones

Ejecuta las pertinentes y comunica qué verificaste y qué no:

```text
python -B -m unittest discover -s tests
python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"   # requiere FFmpeg
claude plugin validate plugins/resumir-video --strict
claude plugin validate . --strict
```

Usa `-B` para no generar `__pycache__` dentro de la skill: Codex copia tal cual la carpeta de un catálogo local. Si Codex está instalado, sus validadores comprueban el manifiesto y la skill (ambos scripts requieren PyYAML: `python -m pip install pyyaml`). Sintaxis de Bash:

```text
PYTHONUTF8=1 python -B "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py" plugins/resumir-video
PYTHONUTF8=1 python -B "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" plugins/resumir-video/skills/resumir-video
```

La integración continua ([`.github/workflows/pruebas.yml`](.github/workflows/pruebas.yml)) ejecuta las dos baterías en Ubuntu y Windows con Python 3.10 y 3.12, más una comprobación de los manifiestos. Los validadores de los clientes solo existen en local: pásalos antes de publicar ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Versiones

Al publicar, sigue [docs/instalacion.md](docs/instalacion.md#7-publicar-una-versión-nueva): el mismo número en `CHANGELOG.md`, los tres `plugin.json`, `.claude-plugin/marketplace.json` (`metadata.version` y `plugins[0].version`), `SKILL.md`, `video.py`, `README.md`, el primer párrafo de `docs/capacidades.md` y la línea «Estado» de `docs/instalacion.md`. `tests/test_packaging.py` falla si no coinciden.

Registra en `docs/plan.md` qué se verificó, con qué versiones de cada cliente, y qué quedó pendiente.

## CodeGraph

Si existe `.codegraph/` en la raíz, consulta primero `codegraph_explore` o `codegraph explore` para localizar o entender código. Si no existe, omítelo; no indexes por iniciativa propia.
