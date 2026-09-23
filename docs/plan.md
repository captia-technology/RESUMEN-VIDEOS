# Plan y estado

## Completado

- Publicación en `captia-technology/RESUMEN-VIDEOS` (público, MIT) el 2026-09-18: versión 0.1.0 etiquetada, integración continua en verde, guía de contribución, política de seguridad y README con demostración y gráficos.

- Inicialización del repositorio independiente y documentación mínima.
- Skill portable con selección audiovisual, guía operativa y asistente local de extracción y montaje.
- Ejecución real sobre una grabación de dos horas en 4K (material excluido del repositorio). Sus lecciones se documentan como límites y posibles ampliaciones en [capacidades](capacidades.md).
- Versión 0.1.0 empaquetada como plugin para Claude Code, GitHub Copilot y Codex ([D-004](decisiones.md#d-004--distribución-como-plugin-multiplataforma)), con instalador, guía de instalación y catálogo de capacidades.
- Arreglos de portabilidad y de sincronía de audio en `video.py` ([D-006](decisiones.md#d-006--audio-codificado-una-sola-vez-en-el-montaje)).
- Verificación de la versión 0.1.0 por cliente (sección siguiente), con los arreglos derivados en `video.py`, `install.py` y la documentación ([cambios](../CHANGELOG.md)).
- Versión 0.2.0: compresión con objetivo, revisión previa con aceptación registrada, modo audio y
  documento, montaje reanudable y validado, barrido y transcripción por bloques
  ([especificación](especificaciones/2026-09-18-resumir-video-0.2.0.md), planes 1 a 4 en
  [docs/planes/](planes/)).

## Validación (2026-09-17)

Entorno: Windows 11, Python 3.11.9 y FFmpeg 8.0.1 (compilación completa con libx264 y AAC). Cada cliente se ejecutó con sus carpetas de usuario y de configuración redirigidas a una carpeta temporal, sin iniciar sesión ni llamar a modelos. Como `captia-technology/RESUMEN-VIDEOS` aún no está publicado, los flujos Git usaron una copia bare local: servida por HTTP local en Claude Code y sustituyendo la URL de GitHub con `git url.insteadOf` en Codex y Copilot.

| Ámbito | Versión | Comprobado | Resultado |
| --- | --- | --- | --- |
| Claude Code | 2.1.274 | `plugin validate --strict` (plugin y catálogo). Catálogo por ruta local y por Git: `marketplace add`, `install` (ámbito por defecto y `--scope user`), `list`, `details`, `update` (0.1.0 → 0.1.1), `uninstall`, `marketplace remove`. `--plugin-dir` y `plugin tag` (`--dry-run`, `--push`). | Correcto. La caché contiene solo el plugin y `video.py check` funciona desde ella. |
| GitHub Copilot CLI | 1.0.85 (`npx`) | Catálogo por ruta local y por Git: `marketplace add`, `install`, `update` (0.1.0 → 0.1.1), `disable`, `enable`, `uninstall`, `marketplace remove`. Instalación directa, `--plugin-dir`, `skill list`, catálogo declarado en `.claude/settings.json` y skill independiente (personal, `COPILOT_HOME` y proyecto). | Correcto. Con ruta local, el plugin se carga en vivo desde la copia ([detalle](instalacion.md#copilot-cli)). |
| OpenAI Codex CLI | 0.154.0 y 0.131.0 (`npx`); binario de la app de escritorio 0.154.0-alpha.6.2 | Catálogo por ruta local y por Git (`owner/repo`, `@main`, `--ref`, URL HTTPS): `marketplace add`, `plugin list`, `plugin add`, `marketplace upgrade`, `plugin remove`, `marketplace remove`. `enabled = false`, manifiesto leído en cada versión, skill visible en `debug prompt-input` y en el app-server, `validate_plugin.py` y `quick_validate.py`. | Correcto. `marketplace upgrade` no admite catálogos locales. La 0.130.0 no tiene `plugin add` y la 0.104.0 no tiene órdenes de plugins. |
| VS Code con Copilot Chat | 1.137.0 | Solo lectura de los archivos instalados: orden **Chat: Install Plugin from Source**, valores por defecto de `chat.plugins.enabled` y `chat.plugins.marketplaces`, filtro `@agentPlugins` y reconocimiento de `plugin.json`. | Coincide con la guía. El mínimo 1.133 procede de las notas de esa versión. |
| Vercel skills | 1.5.18 y 1.6.0 (`npx`) | Detección e instalación desde la copia local (proyecto, `-a`, `-g`). | Correcto. Desde la 1.5.19 requiere Node 22.20+. |
| GitHub CLI (`gh skill`) | 2.101.0 (portable) | `gh skill install --from-local` con `--scope user` y `--agent`. | Correcto. Sin `--agent` instala para Copilot y reescribe el frontmatter de `SKILL.md`. La 2.83.2 no tiene `gh skill`. |
| Codex `$skill-installer` | Script incluido en Codex | Simulación sin red de `install-skill-from-github.py` con la URL documentada. | Copia idéntica; una segunda ejecución se detiene porque la carpeta existe. |
| Copias manuales | Bash y Windows PowerShell 5.1 | Órdenes de la sección 5 de la guía, dos veces seguidas. | Bash correcto; PowerShell necesitaba `-Force` para repetirla (corregido en la guía). |
| `scripts/install.py` | Python 3.11 | Ámbitos personal y de proyecto, `--status`, `--dry-run`, `--force`, `--uninstall`, enlaces y uniones, `CLAUDE_CONFIG_DIR` y `COPILOT_HOME`. | Correcto salvo archivos de solo lectura, uniones rotas y `--project-dir` inexistente, que se corrigen en esta entrega. |
| Uso de extremo a extremo | — | Skill instalada con `install.py`, siguiendo `SKILL.md` y la referencia de operación sobre un vídeo de formación sintético de 91,88 s con subtítulos SRT (sin transcripción). | `resumen.mp4` de 67,40 s con 3 cortes (reducción del 26,6 %), uniones limpias en imagen y en silencio, y voz alineada con el original con 12 ms de diferencia como máximo. El índice de 15 s no mostró una diapositiva de 8,5 s, localizada gracias a los subtítulos. Los procedimientos que faltaban se añadieron a la referencia. |
| Revisión del código | Python 3.10 y 3.11 (Windows); Python 3.12 (WSL Ubuntu) | Revisión adversarial de `video.py` e `install.py` con medios sintéticos: pistas y formatos, frecuencias de fotogramas y de muestreo, nombres de archivo, interrupciones y permisos. | Las pruebas pasaron en Windows; en WSL, sin FFmpeg, se omitieron las de vídeo. Los fallos encontrados se corrigen en esta entrega; con el prototipo de los arreglos, el desfase por unión quedó centrado en unos ±19 ms a 25 fps (medio fotograma). |

- Sincronía (20 uniones, vídeo sintético de 12 s): con el montaje de la primera versión, 7,16 s de vídeo frente a 7,25 s de audio decodificado; con el audio codificado una vez, 6,80 s frente a 6,81 s; con la versión final (frecuencia constante), 6,40 s frente a 6,40 s. La prueba automática admite 50 ms.
- Instalación desde GitHub (2026-09-18, repositorio ya publicado): `marketplace add captia-technology/RESUMEN-VIDEOS` e instalación del plugin correctas en Claude Code 2.1.274, Copilot CLI 1.0.85 y Codex 0.154.0, con las carpetas de configuración redirigidas a carpetas temporales.
- Integración continua (2026-09-18): el flujo `Pruebas` ejecuta las dos baterías en `ubuntu-latest` y `windows-latest` con Python 3.10 y 3.12, más la comprobación de manifiestos; todas las combinaciones correctas. Es la primera ejecución verificada en Linux.
- Pruebas automáticas (Windows 11, FFmpeg 8.0.1): las 23 de `tests/` y las 15 de la skill pasan con Python 3.10.18 y 3.11.9; también pasan `claude plugin validate --strict` (plugin y catálogo), `validate_plugin.py` y `quick_validate.py`.
- Segunda ronda sobre la versión corregida: las instalaciones y el uso de extremo a extremo se repitieron con éxito, y una revisión adversarial del montaje (fuentes marcadas fotograma a fotograma a 25, 29,97 y 5 fps, de frecuencia variable y MPEG-TS) encontró tres fallos que se corrigen en esta entrega: truncamiento de cortes cortos al concatenar, imagen congelada en contenedores sin índice y una tolerancia mal calculada. Tras el arreglo, el audio de cada unión cae a menos de 1 ms de su sitio y no acumula desfase.

No verificado (pendiente de evidencia):

- Invocación dentro de una sesión (`/resumir-video`, `$resumir-video`, `$resumir-video:resumir-video`, `/skills`, `/plugin`, `/plugins`), aviso de carpetas de confianza y propuesta del bloque de equipo: requieren iniciar sesión y llamar a modelos.
- Flujo de instalación de VS Code (**Chat: Install Plugin from Source**) y agente en la nube de Copilot.
- Instaladores de terceros contra GitHub.
- macOS: no se ha ejecutado `video.py` ni las pruebas automáticas, ni se han comprobado las órdenes de `brew` de la [guía de instalación](instalacion.md#1-requisitos-previos). Linux sí queda cubierto por la integración continua.

## Validación (2026-09-18)

Aceptación manual de la versión 0.2.0 sobre una grabación real, con los umbrales provisionales de
[requisitos.md](requisitos.md#umbrales-provisionales) recorridos al menos una vez. Pendiente de
completar antes de publicar.

| Fecha | Grabación | Objetivo pedido | Frase de aceptación | Resultado |
| --- | --- | --- | --- | --- |
| | | | | |

Comprobaciones exigidas por la especificación §13 antes de publicar, sobre la grabación larga en 4K:

| Comprobación | Cómo | Resultado |
| --- | --- | --- |
| Memoria máxima por corte | Corte de 40 tramos montado con `--threads 4`, `2` y `1`, midiendo el pico del proceso de FFmpeg | (pendiente de evidencia) |
| Tiempo por fase | Segundos de `prepare`, `frames` completo, `transcribe` completo, `plan` y `render` sobre la grabación de 4K | (pendiente de evidencia) |
| Cobertura de palabras | `vN/cobertura.json`: media y mínimo por corte | (pendiente de evidencia) |
| Calibración de umbrales | Silencio, `sin_pausas_detectadas`, recuperación de huecos y umbrales de imagen, contrastados con el material real | (pendiente de evidencia) |
| Barrido de 2 h | Espacio ocupado por `fotogramas/` y tiempo por bloque | (pendiente de evidencia) |
| Revisión en lenguaje natural | Las diez peticiones de la tabla de `revision.md`, una por una | (pendiente de evidencia) |
| Modo audio | Una grabación de solo audio de extremo a extremo, con y sin Pandoc | (pendiente de evidencia) |

Ejecutado en esta entrega (tarea 13), sin la grabación real anterior: Windows 11 (build 26200),
Python 3.11.9, FFmpeg 8.0.1 (compilación completa con libx264 y AAC), Claude Code 2.1.280 y Codex
CLI 0.104.0 (solo para los validadores independientes de más abajo; esa versión no tiene órdenes de
plugin, como ya registra la validación del 2026-09-17).

- `python -B -m unittest discover -s tests`: 27 pruebas, correcto.
- `python -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"`:
  278 pruebas, correcto (2 omitidas: sin CUDA y sin `faster-whisper` en esta máquina).
- `claude plugin validate plugins/resumir-video --strict` y `claude plugin validate . --strict`:
  correcto en los dos.
- `validate_plugin.py` (`skills/.system/plugin-creator`) y `quick_validate.py`
  (`skills/.system/skill-creator`) de Codex: correcto en los dos.
- `scripts/install.py --dry-run`, `--agent codex` y `--uninstall` contra el `HOME` real: instalación
  y desinstalación limpias; `video.py check` de la copia instalada devuelve `"version": "0.2.0"` y
  los cinco módulos se importan desde ella; sin `__pycache__` en la copia.
- `claude plugin tag plugins/resumir-video --dry-run`: simulación correcta (etiqueta
  `resumir-video--v0.2.0`, sin crearla). No se ha ejecutado `--push` ni se ha creado la etiqueta real:
  la tabla de aceptación manual sigue con filas «(pendiente de evidencia)».

Omitido en esta entrega: la aceptación manual con la grabación larga en 4K (las dos tablas
anteriores) y las diez peticiones de `revision.md`. La regla del repositorio prohíbe inventar esos
datos, así que quedan marcados y no se ha publicado ninguna versión.

## Siguiente paso

- Completar la aceptación manual de las dos tablas anteriores con una grabación real en 4K,
  incluidas las diez peticiones de `revision.md`.
- Publicar la versión 0.2.0 (`claude plugin tag plugins/resumir-video --push`) solo cuando esas
  tablas queden sin filas «(pendiente de evidencia)».
- Comprobar el flujo de instalación desde la interfaz de VS Code y la invocación dentro de una sesión en Claude Code, Copilot y Codex.
- Comprobar macOS: `video.py check`, las pruebas automáticas y las órdenes de `brew` de la guía.
- Evaluar la versión empaquetada con nuevos vídeos técnicos: cobertura, precisión, legibilidad, uniones y consumo.

No hay desarrollo de una aplicación en curso.
