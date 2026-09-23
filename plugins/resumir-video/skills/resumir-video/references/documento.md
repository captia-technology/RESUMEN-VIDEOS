# Documento, búsqueda y cobertura

`doc` expande las marcas que escribe el agente y convierte a DOCX. El texto es del agente; los
tiempos, las tablas generadas y el formato son del script. Sustituye `SKILL_DIR` por la carpeta que
contiene `SKILL.md` y `TRABAJO` por la carpeta de trabajo; las rutas van entre comillas simples.

## Estructura

1. Ficha: archivo, duraciones de original y resumen, porcentaje, técnicas aplicadas y transcriptor.
2. Resumen de uno a tres párrafos.
3. Ideas clave con su tiempo.
4. Preguntas y respuestas de la sesión, más preguntas de repaso, respondidas solo con contenido de la
   fuente y marcando «(pendiente de verificar)» lo dudoso.
5. Qué se ha dejado fuera y limitaciones de la revisión.

El índice de cortes, el timeline y el informe de validación existen solo en vídeo.

## Buscar en la transcripción

```text
python3 'SKILL_DIR/scripts/video.py' search 'TRABAJO/transcripcion.json' 'ATEX' --context 2
```

Compara en minúsculas y sin tildes, pero **conserva la eñe**: «año» y «ano» son palabras distintas y
no se confunden. Devuelve, por coincidencia, el segmento, el instante de la **palabra** cuando la
transcripción trae marcas por palabra, el del segmento cuando no, el texto y el contexto. `--max`
limita el número de coincidencias (20 por defecto).

## Marcas del documento

El agente escribe `TRABAJO/documento-vN.md` con marcas y el asistente las expande:

| Marca | Se convierte en |
| --- | --- |
| `[[t=752.3]]` | `12:32 (resumen 1:05)` o `12:32 (no incluido en el resumen)` |
| `[[r=745-800]]` | `12:25–13:20 (resumen 1:02–1:15)`, `(no incluido…)` o `(incluido en parte…)` |
| `[[ficha]]` | Tabla con archivo, duraciones, porcentaje, técnicas, transcriptor y versión |
| `[[indice]]` | Tabla `# / Origen / Salida / Tema` (solo vídeo) |
| `[[timeline]]` | Línea temporal de texto y, con Pillow, `timeline.png` (solo vídeo) |
| `[[validacion]]` | Resumen de `vN/validacion.json` (solo vídeo) |

Reglas: las marcas de bloque ocupan una línea entera; los tiempos van en segundos; en modo audio,
`[[t]]` y `[[r]]` solo dan el tiempo del original y `[[indice]]`, `[[timeline]]` y `[[validacion]]` no
existen. `doc` se detiene citando la línea si encuentra una marca desconocida, un tiempo fuera del
medio, una ruta absoluta o un texto pendiente de completar (`TBD`, `TODO`, `FIXME`, `XXX`,
`(pendiente de completar)`); «(pendiente de verificar)» sí es válido y un enlace `https://…` no se
confunde con una ruta.

La salida se calcula con los tramos y la velocidad del plan publicado. Si el instante cae en una pausa
eliminada se usa el inicio del tramo siguiente del mismo corte, y si esa pausa es la última del corte,
el instante de salida de su fin.

## Publicar el documento

```text
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1 --accept 'adelante, redáctalo'
python3 'SKILL_DIR/scripts/video.py' doc --work 'TRABAJO' --version 1 --source 'TRABAJO/documento-v1-r2.md' --revision 'corrige la cifra' --accept 'la cifra correcta es 12'
```

En vídeo publica `vN/resumen.md` y `vN/resumen.docx`; en audio crea `documento-vN/` con `resumen.md`,
`resumen.docx` y una copia inmutable del esquema aceptado. En audio, `--accept` con la frase literal
del usuario es obligatorio y se comprueba contra el sha256 del esquema. Una revisión publica
`resumen-rM` (M ≥ 2) junto a la anterior y la registra en `revisiones.json`; la entrega apunta siempre
a la M mayor. Nada publicado se sobrescribe —`vN/montaje.md`, el informe técnico que escribe `render`,
tampoco se toca—.

DOCX: Pandoc si está en PATH; si no, `python-docx` con un subconjunto de Markdown (títulos, párrafos,
listas, tablas, negrita, cursiva, código e imagen). Sin ninguno de los dos la entrega es solo Markdown,
con código 0, aviso en el informe e instrucciones de instalación; `check` lo anticipa en `degraded` y
la falta se anota en las limitaciones del documento. `--no-docx` fuerza esa entrega. El timeline es
siempre de texto; el PNG requiere Pillow.

## Cobertura (informativa)

```text
python3 'SKILL_DIR/scripts/video.py' compare --work 'TRABAJO' --version 1
```

Escribe `vN/cobertura.json` y devuelve 0 siempre. Mide, por corte, qué proporción de las palabras de la
transcripción comprendidas en el corte sobrevive entera dentro de sus tramos (holgura de 20 ms). Por
debajo de 0,90 de media o de 0,85 en algún corte emite `cobertura_baja`, que no bloquea: el agente lo
resuelve moviendo bordes o lo declara en las limitaciones antes de entregar. Los dos umbrales son
provisionales hasta la calibración con material real. Repetir la orden sobre una versión que ya tiene
su `cobertura.json` no la reescribe: avisa y devuelve 0.
