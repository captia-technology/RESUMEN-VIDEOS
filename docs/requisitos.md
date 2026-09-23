# Requisitos

## Confirmado

- Skill portable y autocontenida `resumir-video`, invocable con la ruta de una grabación local.
- Crear un resumen de alta calidad con fragmentos originales y su audio, analizando conjuntamente
  explicaciones y material visual, y priorizando conceptos técnicos, normativa, requisitos,
  procedimientos, arquitectura, configuraciones, ejemplos, decisiones, conclusiones y advertencias.
- Eliminar contenido sin valor sin perder contexto ni información visual durante silencios.
- Priorizar simplicidad, rapidez, fiabilidad y consumo moderado de recursos.
- Distribuirla como plugin fácil de instalar en Claude Code, OpenAI Codex y GitHub Copilot, con
  licencia MIT a nombre de CAPTIA TECHNOLOGY S.L. en `captia-technology/RESUMEN-VIDEOS`.
- Mantener la documentación versionada como fuente de verdad. No se solicita aplicación, servidor ni
  interfaz propia.

| Id | Requisito (2026-09-17) | Decisión |
| --- | --- | --- |
| R1 | Objetivo de compresión en porcentaje o duración, con velocidad y pausas configurables y aviso si destruye contexto | [D-007](decisiones.md#d-007--compresión-por-defecto-con-objetivo-configurable) |
| R2 | Propuesta de cortes revisable en lenguaje natural antes y después del montaje | [D-008](decisiones.md#d-008--revisión-previa-con-aceptación-registrada-y-versiones-inmutables) |
| R3 | Entrada de solo audio: documento en Markdown y, si hay conversor, DOCX | [D-010](decisiones.md#d-010--modo-audio-y-documento-con-motores-opcionales) |
| R4 | En vídeo, el mismo documento acompaña siempre al MP4 | [D-010](decisiones.md#d-010--modo-audio-y-documento-con-motores-opcionales) |
| R5 | Se conservan garantías, dependencias, preferencia por subtítulos fiables y pruebas de la 0.1.0 | [D-003](decisiones.md#d-003--skill-autocontenida-con-montaje-local), [D-006](decisiones.md#d-006--audio-codificado-una-sola-vez-en-el-montaje) |

Decisiones de diseño tomadas en la sesión de especificación: A-1 sin objetivo manda el criterio
editorial; A-2 la revisión previa es obligatoria salvo `directo`; A-3 en modo audio se acepta el
esquema antes de redactar; A-4 un cambio que solo afecta al documento publica `resumen-rM.*`; A-5 la
banda de tolerancia es `max(0,05 · T_obj, 10 s)`; A-6 la skill vive en `plugins/…` y la
implementación se hace en un worktree aislado.

## Umbrales provisionales

Pendientes de calibrar con material real: silencio a −50 dBFS con 0,30 s y margen de 0,08 s;
`sin_pausas_detectadas` a −53 dBFS; recuperación de huecos del VAD; segmento dudoso con
`no_speech_prob > 0,6` o `avg_logprob < −1,0`; patrones de falta de memoria; umbrales de imagen de la
validación de colocación (0,08 y 0,15); desfase máximo de la envolvente de 40 ms, con guarda de
modulación de 6 dB y bloqueo a 8 dB; presupuesto de tiempo de la energía; 1 MB por vista del barrido;
2 GB de memoria disponible por debajo de los cuales `check` recomienda montar con un solo hilo.

## Criterios de aceptación

- La carpeta de la skill puede copiarse sin referencias absolutas ni dependencias de este repositorio, y funciona desde una caché de plugins de solo lectura.
- Las instrucciones exigen evidencia de ambas modalidades y revisión editorial de cobertura y uniones, y no dependen de un agente concreto.
- El asistente comprueba el entorno, extrae audio e imágenes, acepta un plan temporal y produce un MP4 decodificable con audio sincronizado, junto con su informe y plan.
- Los cortes inválidos se rechazan y los originales o salidas existentes no se sobrescriben.
- El plugin supera `claude plugin validate --strict` y el validador de plugins de Codex; el catálogo se registra e instala en cada cliente con las órdenes documentadas.
- La skill cumple los campos portables del estándar Agent Skills, y los manifiestos y versiones coinciden (`tests/test_packaging.py`).

## Pendiente

- Comprobar el flujo de instalación desde la interfaz de VS Code y la invocación dentro de una sesión; la instalación desde GitHub ya está verificada en los tres clientes ([plan](plan.md#validación-2026-09-17)).
- Precisión de transcripción de terminología y lectura de tablas en más grabaciones del usuario.
- Calidad editorial, legibilidad, reducción alcanzable y consumo en vídeos largos con la versión empaquetada.
- Calibrar los umbrales provisionales y la aceptación manual de §13 de la especificación con una
  grabación larga en 4K.

El objetivo de duración es opcional: sin él manda el criterio editorial (A-1). El idioma y la pista
de voz se resuelven por grabación cuando sea necesario.
