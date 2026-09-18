# Documentación

Índice de la documentación de **resumir-video**. Cada dato vive en un único documento; los demás enlazan a él.

## Para usar la skill

| Documento | Responde a |
| --- | --- |
| [Instalación](instalacion.md) | Cómo instalarla, actualizarla y desinstalarla en Claude Code, GitHub Copilot y Codex; requisitos por sistema operativo; solución de problemas |
| [Capacidades](capacidades.md) | Qué hace y qué no hace, entradas admitidas, archivos que produce, garantías medidas, rendimiento, privacidad y límites conocidos |
| [Referencia de operación](../plugins/resumir-video/skills/resumir-video/references/operacion.md) | Órdenes exactas de `video.py`, formato de `seleccion.json` y procedimientos de revisión |
| [Instrucciones de la skill](../plugins/resumir-video/skills/resumir-video/SKILL.md) | El flujo de trabajo que sigue el agente |

## Para entender el proyecto

| Documento | Responde a |
| --- | --- |
| [Arquitectura](arquitectura.md) | Qué se distribuye, qué manifiesto lee cada cliente y cómo se reparten las responsabilidades |
| [Decisiones](decisiones.md) | Por qué el proyecto es así, con su contexto y sus consecuencias |
| [Requisitos](requisitos.md) | Alcance confirmado, criterios de aceptación y lo que queda pendiente |
| [Plan y estado](plan.md) | Qué se ha verificado, con qué versiones de cada cliente y qué falta por comprobar |
| [Cambios](../CHANGELOG.md) | Historial de versiones |

## Para contribuir

| Documento | Responde a |
| --- | --- |
| [Guía de contribución](../CONTRIBUTING.md) | Cómo preparar el entorno, ejecutar las pruebas y publicar una versión |
| [Política de seguridad](../SECURITY.md) | Qué garantiza la skill y cómo informar de una vulnerabilidad |
| [Mapa para agentes](../AGENTS.md) | Reglas de trabajo en este repositorio para agentes de IA |

## Gráficos

Las figuras del README están en [`img/`](img) y se generan con [`scripts/generar_graficos.py`](../scripts/generar_graficos.py) a partir de [`img/datos.json`](img/datos.json), que recoge medidas reales de la ejecución de demostración y de la verificación.
