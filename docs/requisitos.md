# Requisitos

## Confirmado

- Skill portable y autocontenida `resumir-video`, invocable con una ruta de vídeo local.
- Crear un vídeo resumen de alta calidad usando fragmentos originales y su audio.
- Analizar conjuntamente explicaciones y material visual: diapositivas, esquemas, tablas y documentación.
- Priorizar conceptos técnicos, normativa, requisitos, procedimientos, arquitectura, configuraciones, ejemplos, decisiones, conclusiones y advertencias.
- Eliminar contenido sin valor sin perder contexto ni información visual durante silencios.
- Priorizar simplicidad, rapidez, fiabilidad y consumo moderado de recursos.
- Distribuir la skill como plugin fácil de instalar en Claude Code, OpenAI Codex y GitHub Copilot, con instrucciones por cliente y una documentación detallada de sus capacidades (solicitado el 2026-09-17).
- Publicar en `captia-technology/RESUMEN-VIDEOS` con licencia MIT a nombre de CAPTIA TECHNOLOGY S.L.
- Mantener la documentación versionada como fuente de verdad. No se solicita aplicación, servidor ni interfaz propia.

## Criterios de aceptación

- La carpeta de la skill puede copiarse sin referencias absolutas ni dependencias de este repositorio, y funciona desde una caché de plugins de solo lectura.
- Las instrucciones exigen evidencia de ambas modalidades y revisión editorial de cobertura y uniones, y no dependen de un agente concreto.
- El asistente comprueba el entorno, extrae audio e imágenes, acepta un plan temporal y produce un MP4 decodificable con audio sincronizado, junto con su informe y plan.
- Los cortes inválidos se rechazan y los originales o salidas existentes no se sobrescriben.
- El plugin supera `claude plugin validate --strict` y el validador de plugins de Codex; el catálogo se registra e instala en cada cliente con las órdenes documentadas.
- La skill cumple los campos portables del estándar Agent Skills, y los manifiestos y versiones coinciden (`tests/test_packaging.py`).

## Pendiente

- Crear y publicar el repositorio `captia-technology/RESUMEN-VIDEOS` (y decidir si es público o privado, lo que afecta a la autenticación de los usuarios).
- Comprobar, una vez publicado, la instalación desde GitHub en cada cliente, el flujo de VS Code y la invocación dentro de una sesión; lo verificado hasta ahora está en el [plan](plan.md#validación-2026-09-17).
- Precisión de transcripción de terminología y lectura de tablas en más grabaciones del usuario.
- Calidad editorial, legibilidad, reducción alcanzable y consumo en vídeos largos con la versión empaquetada.
- Prioridad de las posibles ampliaciones de [capacidades](capacidades.md#posibles-ampliaciones).

La duración objetivo, el idioma y la pista de voz se resuelven por vídeo cuando sea necesario; no hay porcentaje de reducción obligatorio.
