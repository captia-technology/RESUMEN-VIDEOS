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
- Actualización (2026-09-18, versión 0.2.0): el montaje pasa a hacerse por cortes cacheados y cada
  corte se produce en dos pasadas de FFmpeg —vídeo H.264 y audio PCM de 24 bits— que se remultiplexan
  en el mismo MKV sin recodificar. El invariante se mantiene: el audio se codifica una sola vez, en
  el ensamblado final, así que las uniones siguen sin acumular desfase. Se añade la comprobación de
  recuento exacto de fotogramas y muestras por corte antes de entrar en la caché.

## D-007 — Compresión por defecto con objetivo configurable

- Fecha: 2026-09-18.
- Estado: aceptada por el usuario (2026-09-17) e incorporada a la 0.2.0.
- Contexto: la 0.1.0 no aceleraba ni quitaba pausas y rechazaba imponer un porcentaje de reducción.
  El usuario pide poder fijar «el 10 %» o «12 minutos».
- Decisión: admitir un objetivo en porcentaje o duración absoluta y aplicar por defecto selección,
  eliminación de pausas y velocidad ×1,25, ambas configurables. La banda de tolerancia es
  `[max(0, T_obj − d), T_obj + d]` con `d = max(0,05 · T_obj, 10 s)`. Sin objetivo manda el criterio
  editorial y la propuesta informa del porcentaje resultante.
- Motivo: la duración es una restricción real de uso; convertirla en un cálculo explícito y auditable
  evita que el agente improvise recortes.
- Consecuencia: cambio incompatible en los valores por defecto; el resumen ya no es material
  íntegramente «tal cual», y la propuesta debe declarar las técnicas aplicadas. Los umbrales de
  silencio y pausa quedan como provisionales hasta la calibración con material real.

## D-008 — Revisión previa con aceptación registrada y versiones inmutables

- Fecha: 2026-09-18.
- Estado: aceptada por el usuario (2026-09-17).
- Contexto: montar sin acuerdo previo desperdicia tiempo de cómputo y obliga a repetir el trabajo.
- Decisión: `plan` publica `propuesta-vN.md` y el agente termina su turno; `render` exige
  `--accept "frase literal del usuario"` o `--directo`, que queda registrada en `vN/seleccion.json` y
  en `historial.jsonl` junto al sha256 canónico del plan. `vN/` y `documento-vN/` son inmutables: una
  edición posterior produce `v(N+1)`.
- Motivo: separar el juicio editorial del trabajo determinista y dejar trazabilidad de quién aceptó
  qué.
- Consecuencia: el flujo deja de ser de una sola pasada. `--directo` no anula la protección de
  dependencias ni ningún aviso bloqueante.

## D-009 — Montaje por cortes en caché con recuento forzado

- Fecha: 2026-09-18.
- Estado: aceptada.
- Contexto: un montaje de dos horas no cabe en una sola orden y un fallo obligaba a repetirlo entero.
- Decisión: cada corte se monta por separado, se verifica por recuento exacto de fotogramas y
  muestras y se guarda en `cortes/<clave>.mkv`, con la clave derivada de la huella, la pista, los
  tramos, la velocidad, la cadencia, los parámetros del codificador y la versión de FFmpeg.
  `--budget` limita el tiempo por llamada y devuelve 3; un cerrojo exclusivo impide dos montajes
  simultáneos. No se publica `vN/` sin superar la validación bloqueante.
- Motivo: reanudar sin repetir trabajo y no publicar nada que no se haya comprobado.
- Consecuencia: más espacio en disco (la caché) y una clave que hay que invalidar cuando cambia
  cualquiera de sus componentes.
- Nota sobre el código 3: su payload amplía el `{done, total, pending}` de §12 con un campo `bloques`
  adicional (la lista con los nombres de los bloques pendientes), para que el agente que reanude sepa
  exactamente qué falta sin tener que releer la especificación pensando que es un error.
- Desviaciones respecto a la especificación, medidas al implementar; las dos primeras se adoptan en
  todo el montaje y también en el barrido de `frames`, y la tercera solo en el montaje:
  1. La búsqueda de cada corte empieza en `S = max(0, inicio − seek_margin(data))` —el margen de la
     0.1.0: 3 s, o 10 s en los contenedores que solo buscan hacia delante— y no en `inicio − 1`. Con
     un segundo no basta para garantizar un fotograma clave anterior en contenedores sin índice.
  2. Con `-ss S -noaccurate_seek -copyts`, los intervalos de `select`, `atrim` y `fps=…:start_time`
     se expresan en **tiempo absoluto del contenedor** (`base + s`) y no en `s − S`. Como
     consecuencia, la lectura no se puede acotar con `-t` ni con `-to` (medido: con `-copyts` dejan
     la cadena en cero fotogramas).
  3. La cadena de vídeo del montaje lleva una guarda de lectura `trim=end=<base + fin + 1/F>` justo
     detrás del `fps` inicial. En el barrido de `frames` basta con los `-frames:v` de cada salida;
     en el montaje no, porque `select` descarta fotogramas en lugar de cerrar la cadena y
     `trim=end_frame=N` nunca recibe el que la cerraría: sin la guarda, FFmpeg decodifica el medio
     entero en cada corte (medido: 1 000 de 1 000 fotogramas leídos, frente a 153 con la guarda y la
     misma salida exacta). La salida de audio la cierra `atrim=end_sample=M`. Esta medida se
     incorporó después a §8 de la especificación.

## D-010 — Modo audio y documento con motores opcionales

- Fecha: 2026-09-18.
- Estado: aceptada por el usuario (2026-09-17).
- Contexto: el usuario pide poder resumir grabaciones de solo audio y recibir siempre un documento.
- Decisión: con solo audio no se monta nada; se acepta un esquema y se entrega
  `documento-vN/resumen.md`. En vídeo, el mismo documento acompaña siempre al MP4. El DOCX se genera
  con Pandoc y, si no está, con python-docx; sin ninguno de los dos se entrega solo Markdown, con
  código 0, aviso y la limitación anotada.
- Motivo: el valor del resumen no es solo el vídeo, y las dependencias de conversión no pueden ser
  obligatorias.
- Consecuencia: `check` debe anticipar la degradación antes de empezar el inventario; el timeline en
  PNG queda condicionado a Pillow.

## D-011 — Identidad por huella y reasignación de planes

- Fecha: 2026-09-18.
- Estado: aceptada.
- Contexto: en la 0.1.0 un plan dejaba de ser válido si el vídeo se movía o cambiaba su fecha de
  modificación, aunque fuera el mismo archivo.
- Decisión: la identidad pasa a ser la huella —tamaño, `mtime_ns` y sha256 de los primeros y últimos
  4 MiB—. En los archivos de 8 MiB o menos, el sha256 se calcula sobre el archivo completo y no solo
  sobre los extremos, que es como lo hace realmente `common.fingerprint`, para no saltarse el
  contenido intermedio de un archivo pequeño. `render` acepta un plan cuyo `source.path` haya
  cambiado si la huella coincide: lo avisa y actualiza `source` en el plan publicado. Una huella
  distinta sigue siendo un error. Los planes de la 0.1 se importan con `plan --import` y reciben el
  aviso `identidad_parcial`.
- Motivo: los trabajos largos sobreviven a copias y movimientos del material.
- Consecuencia: `prepare` calcula la huella una vez y la guarda en `metadata.json`; leer 8 MiB por
  archivo es despreciable frente al resto del trabajo.

Para nuevas decisiones, registra un identificador consecutivo, fecha, estado, contexto, decisión, motivo y consecuencias. Conserva el historial cuando una decisión sea sustituida.
