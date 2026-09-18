# RESUMEN-VIDEOS

Skill y plugin **`resumir-video`** para agentes de IA: resume vídeos técnicos locales (ingeniería, formaciones, presentaciones, reuniones) en un MP4 hecho con **fragmentos originales**, seleccionados analizando a la vez la voz y la pantalla. Funciona en **Claude Code**, **GitHub Copilot** (VS Code y Copilot CLI) y **OpenAI Codex**.

Versión 0.1.0 · Licencia MIT · © 2026 CAPTIA TECHNOLOGY S.L.

## Capacidades

- **Resumen audiovisual:** conserva las unidades de conocimiento completas (conceptos, normativa, requisitos, procedimientos, configuraciones, decisiones, advertencias) con su contexto, incluidas las demostraciones visuales sin voz.
- **Evidencia verificable:** cada corte de `seleccion.json` justifica su motivo con evidencia de audio y de pantalla; `resumen.md` relaciona los tiempos de origen y salida.
- **Montaje fiel:** fragmentos originales en su orden, a su resolución y velocidad, a frecuencia de fotogramas constante y con el audio sincronizado en cada unión (medio fotograma como máximo, sin acumulación); sin música, voz sintética ni transiciones.
- **Trabajo local:** Python (biblioteca estándar) y FFmpeg; transcripción opcional con faster-whisper en CPU o GPU. El vídeo no se sube a ningún servicio, pero el agente recibe los fotogramas y la transcripción que inspecciona; su tratamiento depende del proveedor del agente ([privacidad](docs/capacidades.md#privacidad-y-seguridad)).
- **Seguro por defecto:** no sobrescribe resultados, valida el plan contra el archivo exacto, comprueba duraciones y decodificación, y excluye de Git las carpetas de trabajo.

Detalle completo en [docs/capacidades.md](docs/capacidades.md).

## Instalación rápida

Requisitos: Python 3.10+, FFmpeg con libx264 y AAC y un agente capaz de ver imágenes. Guía completa, alternativas y solución de problemas en [docs/instalacion.md](docs/instalacion.md).

**Claude Code**

```text
claude plugin marketplace add captia-technology/RESUMEN-VIDEOS
claude plugin install resumir-video@resumen-videos
```

**GitHub Copilot CLI**

```text
copilot plugin marketplace add captia-technology/RESUMEN-VIDEOS
copilot plugin install resumir-video@resumen-videos
```

**VS Code (Copilot Chat) 1.133+:** paleta de comandos → **Chat: Install Plugin from Source** → `captia-technology/RESUMEN-VIDEOS`.

**Codex CLI 0.131+ o app**

```text
codex plugin marketplace add captia-technology/RESUMEN-VIDEOS
codex plugin add resumir-video@resumen-videos
```

**Sin sistema de plugins** (Codex en el IDE u otros clientes compatibles con Agent Skills):

```text
git clone https://github.com/captia-technology/RESUMEN-VIDEOS.git
python3 RESUMEN-VIDEOS/scripts/install.py
```

## Uso

| Cliente | Invocación |
| --- | --- |
| Claude Code | `/resumir-video "ruta/video.mp4"` |
| GitHub Copilot | `/resumir-video "ruta/video.mp4"` |
| Codex (plugin) | `$resumir-video:resumir-video "ruta/video.mp4"` |
| Codex (skill independiente) | `$resumir-video "ruta/video.mp4"` |

También basta con pedir «resume este vídeo: ruta/video.mp4». Tras la ruta puedes añadir indicaciones, por ejemplo `/resumir-video "ruta/video.mp4" en unos 10 minutos`. La invocación activa un flujo de trabajo del agente, no un ejecutable autónomo: el agente comprueba el entorno, extrae evidencia, analiza, selecciona los cortes con su evidencia, monta `resumen.mp4` y entrega el informe. El resultado queda por defecto en `resumenes/<nombre>/` del directorio de trabajo.

## Estructura

```text
.claude-plugin/marketplace.json   Catálogo para Claude Code y GitHub Copilot
.agents/plugins/marketplace.json  Catálogo nativo de Codex
plugins/resumir-video/            Plugin distribuible (única copia de la skill)
├── plugin.json                   Manifiesto Agent Plugins 1.0
├── .claude-plugin/plugin.json    Manifiesto de Claude Code
├── .codex-plugin/plugin.json     Manifiesto e interfaz de Codex
└── skills/resumir-video/         SKILL.md, agents/, references/, scripts/
scripts/install.py                Instalación como skill independiente
tests/test_packaging.py           Coherencia de manifiestos, skill e instalador
docs/                             Documentación del proyecto
```

## Documentación

Lee [AGENTS.md](AGENTS.md) para orientarte y consulta la documentación según la tarea:

| Documento | Fuente de verdad para |
| --- | --- |
| [Capacidades](docs/capacidades.md) | Qué hace la skill, entradas, salidas, garantías y límites |
| [Instalación](docs/instalacion.md) | Instalación, actualización y publicación por cliente |
| [Referencia de operación](plugins/resumir-video/skills/resumir-video/references/operacion.md) | Órdenes de `video.py` y formato del plan |
| [Requisitos](docs/requisitos.md) | Objetivo, alcance y preguntas de producto |
| [Arquitectura](docs/arquitectura.md) | Estado técnico y restricciones |
| [Decisiones](docs/decisiones.md) | Acuerdos aceptados y su justificación |
| [Plan](docs/plan.md) | Avance, verificaciones y próximos pasos |
| [Cambios](CHANGELOG.md) | Historial de versiones |

## Desarrollo

```text
python3 -B -m unittest discover -s tests
python3 -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
claude plugin validate plugins/resumir-video --strict
claude plugin validate . --strict
```

Las pruebas de la skill requieren FFmpeg y no descargan nada. [AGENTS.md](AGENTS.md) describe las reglas de mantenimiento y publicación.
