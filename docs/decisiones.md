# Decisiones

Registro de acuerdos aceptados. Las propuestas abiertas permanecen en requisitos o arquitectura; no se presentan como decisiones tomadas.

## D-001 — Base documental mínima

- Fecha: 2026-09-16.
- Estado: aceptada en la inicialización.
- Contexto: se necesita una base fácil de retomar sin requisitos de producto definidos.
- Decisión: usar Markdown versionado, un mapa breve en `AGENTS.md` y documentos separados por responsabilidad dentro de `docs/`.
- Motivo: facilitar la orientación y mantener una única fuente para cada tipo de información.
- Consecuencia: la estructura crecerá solo cuando el trabajo lo necesite; no se selecciona ninguna tecnología de producto.

## D-002 — Repositorio independiente

- Fecha: 2026-09-16.
- Estado: aceptada en la inicialización.
- Contexto: la carpeta estaba vacía y Git resolvía la raíz en un repositorio de una carpeta superior, ajeno al proyecto.
- Decisión: inicializar Git en esta carpeta para aislar el historial del proyecto.
- Consecuencia: los cambios de este proyecto se gestionan desde esta raíz; el repositorio padre no se modifica.

## D-003 — Skill autocontenida con montaje local

- Fecha: 2026-09-16.
- Estado: aceptada para el encargo de crear `resumir-video`; la ubicación y el reparto «Codex/asistente» quedan sustituidos por D-004 (cualquier agente realiza la selección).
- Contexto: el usuario solicita ahora una skill reutilizable que genere vídeo y analice tanto voz como pantalla.
- Decisión: alojar una única carpeta portable en `.agents/skills/`; Codex realiza la selección editorial y un asistente Python/FFmpeg extrae evidencia y monta los cortes. La transcripción local es opcional y se reutilizan subtítulos cuando son fiables.
- Motivo: separar el juicio audiovisual de las operaciones deterministas, evitando servicios y dependencias pesadas obligatorias.
- Consecuencia: requiere herramientas locales y capacidades multimodales del agente. El muestreo visual inicial se amplía donde haga falta; las pruebas técnicas no certifican la calidad editorial. Se recodifican solo los cortes seleccionados para obtener límites precisos.

## D-004 — Distribución como plugin multiplataforma

- Fecha: 2026-09-17.
- Estado: aceptada.
- Contexto: el usuario pide que la skill se instale fácilmente como plugin en Claude Code, Codex y GitHub Copilot. Había dos copias manuales idénticas en `.agents/skills` y `.claude/skills`.
- Decisión: una única copia en `plugins/resumir-video/skills/resumir-video/`, con manifiestos Agent Plugins 1.0 (`plugin.json`), Claude Code (`.claude-plugin/plugin.json`) y Codex (`.codex-plugin/plugin.json`), y la raíz del repositorio como catálogo `resumen-videos` (`.claude-plugin/marketplace.json` y `.agents/plugins/marketplace.json`). Se eliminan las copias de proyecto y se añade `scripts/install.py` para instalar la skill sin plugins. El texto de la skill pasa a ser válido para cualquier agente y su frontmatter se limita a los campos portables.
- Motivo: cada cliente lee un manifiesto distinto, pero todos aceptan la estructura `skills/<nombre>/SKILL.md`. Una sola copia evita desviaciones, y sin copias de proyecto Copilot no oculta el plugin ni Codex lo duplica. La subcarpeta evita que una instalación local arrastre material de trabajo.
- Consecuencia: los metadatos y la versión se repiten en varios archivos y `tests/test_packaging.py` comprueba que coinciden. En este repositorio la skill ya no aparece como skill de proyecto: se prueba con `--plugin-dir` o instalándola.

## D-005 — Licencia MIT y titularidad

- Fecha: 2026-09-17.
- Estado: aceptada por el usuario.
- Decisión: publicar con licencia MIT a nombre de CAPTIA TECHNOLOGY S.L. en el repositorio `captia-technology/RESUMEN-VIDEOS`.
- Consecuencia: `LICENSE` se copia en el plugin y en la skill porque algunos canales copian solo esas carpetas; los manifiestos declaran `MIT`.

## D-006 — Audio codificado una sola vez en el montaje

- Fecha: 2026-09-17.
- Estado: aceptada por el usuario junto con los arreglos de portabilidad.
- Contexto: concatenar cortes con AAC propio solapaba el audio en cada unión. En la ejecución real sobre una grabación de dos horas se midió un desfase que crecía unos 24 ms por unión; el material de esa ejecución no está versionado, así que la cifra no puede reproducirse desde el repositorio.
- Decisión: `render` recodifica cada corte solo con vídeo, extrae su audio como PCM con la duración exacta de ese vídeo, concatena ambos y codifica el audio una vez. Comprueba que las duraciones de vídeo y audio coinciden antes de publicar `resumen.mp4`.
- Consecuencia: más archivos intermedios (PCM) y ninguna deriva acumulada; la prueba con 20 uniones lo verifica. Se mantiene la tolerancia de un fotograma al inicio de cada corte.
- Actualización (2026-09-17, tras la verificación de la versión 0.1.0): el vídeo empezaba en el primer fotograma situado en el inicio del corte o después, y el audio exactamente en ese inicio, así que el audio llegaba hasta un fotograma tarde en cada unión, y las grabaciones de frecuencia variable perdían el fotograma en pantalla. Ahora cada corte se recodifica a frecuencia constante desde el fotograma en pantalla en su inicio, y su audio empieza exactamente en ese inicio y dura lo mismo que el vídeo renderizado. El desfase por unión queda en medio fotograma como máximo, sin acumulación, y sustituye a la tolerancia de un fotograma indicada arriba.

Para nuevas decisiones, registra un identificador consecutivo, fecha, estado, contexto, decisión, motivo y consecuencias. Conserva el historial cuando una decisión sea sustituida.
