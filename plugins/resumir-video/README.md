# Plugin `resumir-video`

Resume vídeos técnicos locales (ingeniería, formaciones, presentaciones y reuniones) en un MP4 compuesto por **fragmentos originales**. El agente analiza a la vez la voz y la pantalla, elige unidades de conocimiento completas y un asistente local con FFmpeg monta el resultado con su plan de cortes y un informe.

Funciona en Claude Code, GitHub Copilot (VS Code y Copilot CLI) y OpenAI Codex. La guía de instalación y el catálogo completo de capacidades están en el repositorio: [instalación](https://github.com/captia-technology/RESUMEN-VIDEOS/blob/main/docs/instalacion.md) · [capacidades](https://github.com/captia-technology/RESUMEN-VIDEOS/blob/main/docs/capacidades.md).

## Requisitos

- Python 3.10 o superior (`python3`, o `python`/`py -3` en Windows).
- `ffmpeg` y `ffprobe` en PATH, con los codificadores libx264 y AAC (en Windows, los ejecutables `.exe`; un envoltorio `.cmd` o `.bat` no sirve).
- Un agente capaz de inspeccionar imágenes.
- Opcional: `faster-whisper` para transcribir en local si el vídeo no tiene subtítulos; Pandoc o `python-docx` para el DOCX del informe (sin ninguno de los dos, se entrega solo Markdown); Pillow para la línea temporal en PNG.

Comprueba el entorno con `python3 skills/resumir-video/scripts/video.py check` desde la carpeta del plugin. Siempre imprime un JSON que termina en `"ok": true` si se cumplen los requisitos obligatorios.

## Uso

| Cliente | Invocación |
| --- | --- |
| Claude Code | `/resumir-video "ruta/video.mp4"` o `/resumir-video:resumir-video "ruta/video.mp4"` |
| GitHub Copilot | `/resumir-video "ruta/video.mp4"` |
| Codex | `$resumir-video:resumir-video "ruta/video.mp4"` |

También se activa cuando pides resumir un vídeo local. Tras la ruta puedes añadir indicaciones, como el objetivo de compresión (porcentaje o duración) o la velocidad. Antes de montar nada, la skill publica una propuesta en lenguaje natural y espera tu aceptación, salvo que pidas `--directo`; con solo audio no monta vídeo y entrega el documento equivalente.

## Resultado

En una carpeta de trabajo nueva que crea el propio asistente (por defecto `resumenes/<nombre>/`, excluida de Git), la entrega aceptada queda en versiones `vN/` inmutables:

- `vN/resumen.mp4`: montaje de los fragmentos originales con audio sincronizado.
- `vN/seleccion.json`: plan de cortes aceptado, con la frase de aceptación del usuario.
- `vN/montaje.md`: informe técnico del montaje — versión, cortes, velocidad, cadencia, duración de salida, desfase vídeo-audio y tabla origen → salida con la distancia de imagen y envolvente de cada corte.
- `vN/resumen.md` (y `resumen.docx` si hay Pandoc o `python-docx`): documento editorial — ficha, resumen, ideas clave con su tiempo, preguntas y respuestas y qué se ha dejado fuera.
- `vN/validacion.json`, `vN/cobertura.json` y `vN/timeline.*`: comprobaciones bloqueantes, cobertura de palabras y línea temporal del resumen.
- Con solo audio no hay montaje: se entrega `documento-vN/resumen.md` (y `.docx`), el mismo documento que en vídeo acompaña siempre al MP4.
- En la carpeta de trabajo, antes de aceptar: `propuesta-vN.md`, `seleccion-vN.json` (o `esquema-vN.json` en audio) e `historial.jsonl`, junto a `analisis.md`, `metadata.json`, `audio.wav` y, si procede, `transcripcion.json`.

## Contenido

```text
plugin.json                 Manifiesto Agent Plugins 1.0 (Copilot, VS Code, Codex 0.146+)
.claude-plugin/plugin.json  Manifiesto de Claude Code
.codex-plugin/plugin.json   Interfaz de Codex (manifiesto completo en Codex 0.131–0.145)
skills/resumir-video/       La skill (SKILL.md, referencias y scripts)
```

Licencia MIT © 2026 CAPTIA TECHNOLOGY S.L.
