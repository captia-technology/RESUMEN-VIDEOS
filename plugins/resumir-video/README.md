# Plugin `resumir-video`

Resume vídeos técnicos locales (ingeniería, formaciones, presentaciones y reuniones) en un MP4 compuesto por **fragmentos originales**. El agente analiza a la vez la voz y la pantalla, elige unidades de conocimiento completas y un asistente local con FFmpeg monta el resultado con su plan de cortes y un informe.

Funciona en Claude Code, GitHub Copilot (VS Code y Copilot CLI) y OpenAI Codex. La guía de instalación y el catálogo completo de capacidades están en el repositorio: [instalación](https://github.com/captia-technology/RESUMEN-VIDEOS/blob/main/docs/instalacion.md) · [capacidades](https://github.com/captia-technology/RESUMEN-VIDEOS/blob/main/docs/capacidades.md).

## Requisitos

- Python 3.10 o superior (`python3`, o `python`/`py -3` en Windows).
- `ffmpeg` y `ffprobe` en PATH, con los codificadores libx264 y AAC (en Windows, los ejecutables `.exe`; un envoltorio `.cmd` o `.bat` no sirve).
- Un agente capaz de inspeccionar imágenes.
- Opcional: `faster-whisper` para transcribir en local si el vídeo no tiene subtítulos.

Comprueba el entorno con `python3 skills/resumir-video/scripts/video.py check` desde la carpeta del plugin. Siempre imprime un JSON que termina en `"ok": true` si se cumplen los requisitos obligatorios.

## Uso

| Cliente | Invocación |
| --- | --- |
| Claude Code | `/resumir-video "ruta/video.mp4"` o `/resumir-video:resumir-video "ruta/video.mp4"` |
| GitHub Copilot | `/resumir-video "ruta/video.mp4"` |
| Codex | `$resumir-video:resumir-video "ruta/video.mp4"` |

También se activa cuando pides resumir un vídeo local. Tras la ruta puedes añadir indicaciones, como la duración objetivo.

## Resultado

En una carpeta de trabajo nueva que crea el propio asistente (por defecto `resumenes/<nombre>/`, excluida de Git):

- `final/resumen.mp4`: montaje de los fragmentos originales con audio sincronizado.
- `seleccion.json`: plan de cortes con motivo y evidencia de audio y pantalla; `render` guarda una copia en `final/`.
- `final/resumen.md`: índice de tiempos de origen y salida, reducción y revisión editorial.
- `analisis.md`, `metadata.json`, `audio.wav`, fotogramas y, si procede, `transcripcion.json`.

## Contenido

```text
plugin.json                 Manifiesto Agent Plugins 1.0 (Copilot, VS Code, Codex 0.146+)
.claude-plugin/plugin.json  Manifiesto de Claude Code
.codex-plugin/plugin.json   Interfaz de Codex (manifiesto completo en Codex 0.131–0.145)
skills/resumir-video/       La skill (SKILL.md, referencias y scripts)
```

Licencia MIT © 2026 CAPTIA TECHNOLOGY S.L.
