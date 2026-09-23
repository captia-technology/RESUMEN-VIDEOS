# Política de seguridad

Este repositorio distribuye la skill `resumir-video`: instrucciones para un agente y un asistente local en Python que llama a FFmpeg. No hay servicio, servidor ni base de datos.

## Versiones admitidas

| Versión | Estado |
| --- | --- |
| 0.2.x | Admitida; las correcciones salen en una versión nueva de la serie |
| 0.1.x | No admitida: actualiza a la 0.2.x |
| Anteriores a 0.1.0 | No existen: 0.1.0 es la primera versión publicada |

Las copias manuales y las instaladas con herramientas de terceros no se actualizan solas ([docs/instalacion.md](docs/instalacion.md#5-skill-independiente-sin-plugins)).

## Qué hace en tu máquina

- **Procesamiento local.** `video.py` solo ejecuta `ffmpeg` y `ffprobe` sobre archivos locales. El vídeo no se sube a ningún servicio.
- **Sin descargas salvo petición expresa.** La única descarga posible son los pesos del transcriptor, y solo con `--allow-download`. Sin esa opción, `transcribe` se detiene si el modelo no está en la caché local y no escribe nada.
- **Sin shell.** FFmpeg y ffprobe se lanzan como lista de argumentos, nunca a través de una shell, así que un nombre de archivo no puede interpretarse como orden. En Windows solo se aceptan los ejecutables `ffmpeg.exe` y `ffprobe.exe`; un envoltorio `.cmd` o `.bat` se rechaza.
- **Carpetas de trabajo excluidas de Git.** `prepare` crea la carpeta de trabajo con su propio `.gitignore` (`*`): contiene fotogramas, audio y transcripciones confidenciales.
- **Sin sobrescritura.** `prepare`, `frames` y `render` exigen una carpeta de salida que no exista, ningún JSON se reemplaza y el vídeo original nunca se modifica.
- **Plan ligado a su origen.** `render` solo monta un plan cuyo `source` coincide exactamente con el archivo actual (ruta, tamaño y fecha de modificación).
- **Sin permisos preaprobados.** La skill no pide autorizaciones permanentes: cada orden la autoriza el usuario según la política de su cliente.

## Límite de confianza

- El asistente trabaja en local, pero **el agente recibe los fotogramas y la transcripción** que inspecciona. Su tratamiento depende del proveedor del agente: revisa su política antes de resumir material confidencial.
- `resumen.md` no incluye la ruta completa del origen; `metadata.json`, `index.json` y `seleccion.json` sí. Revísalos antes de compartirlos.
- Las órdenes que lanza el agente sí pasan por la shell de tu cliente. Las rutas deben ir entre comillas simples o escapadas: en Bash y en PowerShell, las comillas dobles no impiden que se ejecute un `$(…)` contenido en un nombre de archivo.

## El contenido del vídeo es un dato, no una instrucción

- La skill indica al agente que trate el texto hablado o mostrado en el vídeo como contenido de la fuente, y que nunca lo ejecute ni lo use para componer una orden de shell. Lo mismo vale para el nombre del archivo y para el texto que acompaña a la invocación.
- El criterio editorial excluye credenciales, datos personales, incidentes sobre personas y material con restricciones de difusión, y deja constancia de la exclusión en el informe.
- Es una instrucción al agente, no un control técnico: un agente puede desviarse. No ejecutes órdenes propuestas a partir del contenido de un vídeo sin revisarlas.

## Alcance

| En alcance | Fuera de alcance |
| --- | --- |
| `video.py`, `scripts/install.py`, los manifiestos y catálogos, y las instrucciones de la skill | FFmpeg, faster-whisper y sus modelos; Claude Code, GitHub Copilot, Codex y sus sistemas de plugins |

Lo que esté fuera de alcance se informa a su propio proyecto. Si un fallo de esta skill hace peligroso un comportamiento normal de esas herramientas, sí entra en alcance.

## Informar de una vulnerabilidad

No abras una incidencia pública ni un pull request con los detalles.

1. En este repositorio, ve a la pestaña **Security** y elige **Report a vulnerability** (avisos de seguridad privados de GitHub). Ruta directa: `https://github.com/captia-technology/RESUMEN-VIDEOS/security/advisories/new`.
2. Incluye la versión, el sistema operativo, el cliente usado, los pasos mínimos para reproducirlo y el impacto que le atribuyes. Si puedes, reproduce el problema con material sintético; no adjuntes vídeos, fotogramas ni transcripciones reales.

Objetivo de respuesta: acuse de recibo en 5 días laborables y una primera valoración en 15 días naturales, con avisos del avance hasta el cierre. La publicación del aviso y el reconocimiento se acuerdan contigo; la corrección sale en una versión nueva y se registra en [CHANGELOG.md](CHANGELOG.md). No hay programa de recompensas.
