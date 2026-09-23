# Compresión

Objetivo, retención, bordes, pausas y estados que calcula `plan`. El agente decide **qué** se
conserva; el script calcula **cuánto** dura y qué avisa.

## Objetivo

`--target` admite porcentaje del original (`10%`) o duración absoluta (`720s`, `12min`, `0:12:00`).
Sin objetivo manda el criterio editorial y la propuesta informa del porcentaje resultante. Se
rechazan los porcentajes fuera de (0, 100) y las duraciones mayores o iguales que el original; un
número sin unidad es ambiguo y se pregunta.

Banda de tolerancia: `[max(0, T_obj − d), T_obj + d]` con `d = max(0,05 · T_obj, 10 s)`.

## Presupuesto

`plan --dry-run` no escribe nada e informa de la retención `ρ` tras quitar pausas (medida sobre los
cortes candidatos; `ρ = 1` en los `visual_only` y en los que llevan `remove_pauses: false`), del
presupuesto de fuente `B = T_obj · v / ρ`, del tiempo que ocupan los cortes de prioridad 1 y del
porcentaje mínimo alcanzable sin sacrificarlos.

## Bordes y pausas

- Un borde que cae sobre voz se lleva al primer silencio de al menos 0,1 s dentro de los 0,6 s
  siguientes, sin invadir la palabra siguiente (su inicio − 0,02 s); el inicio es simétrico. Sin
  silencio cercano (una llamada con ruido de fondo constante) se usan las marcas por palabra: si el
  borde parte una palabra, se conserva entera cuando la mitad o más cae dentro del corte y se deja
  fuera en caso contrario, y el borde pasa al hueco contiguo, a 0,15 s como mucho de la palabra y a
  1 s como mucho del borde original. Solo si tampoco eso es posible (sin marcas, o una palabra
  demasiado larga) se emite `borde_en_voz`. El ajuste va en orden cronológico y nunca cruza al vecino.
- Los cortes que quedan contiguos o a menos de un fotograma se fusionan: se conserva el
  identificador menor y la prioridad mayor, y la fusión se anota en `changes`.
- Pausas: los silencios de 0,30 s o más por debajo de −50 dBFS se sustituyen por un hueco
  conservando 0,08 s a cada lado. Se descartan los tramos menores de 0,12 s y, en los extremos,
  los menores de 0,20 s. Los tramos se ajustan a la rejilla de fotogramas. Los cortes `visual_only`
  conservan sus pausas.
- Todo corte debe conservar al menos un tramo y `N ≥ 1`: si `L < v / F` vuelve a reservas con el
  aviso `corte_vacio`.

Umbral configurable con `--silence-db`. Los valores de arriba son **provisionales** hasta la
calibración con material real.

## Velocidad y estimación

Por corte, `N = round(L · F / v)` y `M = round(N / F · SR)`; la duración estimada es `Σ N / F`, con
un margen de 0,1 s por el relleno del códec. En cortes divididos en subcortes, `N` y `M` se calculan
para el corte completo y se reparten. Velocidad por defecto 1,25; de 1,0 a 2,0, con aviso
`velocidad_alta` por encima de 1,5.

## Estados

| Estado | Significado |
| --- | --- |
| `ok` | La estimación cae dentro de la banda |
| `por_encima` / `por_debajo` | Fuera de la banda, con sugerencias que la recuperan |
| `sin_objetivo` | No se pidió duración: manda el criterio editorial |
| `inviable` | Los cortes de prioridad 1 ya superan la banda |
| `inalcanzable` | `T_obj > T_max + d`, con `T_max = T_orig · ρ / v` |

Las sugerencias nunca se aplican solas: respetan la prioridad 1, los cortes fijados (`pinned`) y las
dependencias. `alternativas` recoge las cuatro combinaciones de velocidad y pausas.

## Avisos

Son dieciocho y todos llevan `codigo`, `corte`, `mensaje` y `bloquea`. Bloquean el montaje cuatro
—`esenciales_superan_objetivo`, `dependencia_excluida`, `tema_sin_cubrir` y `corte_vacio`—; los otros
catorce (`objetivo_muy_bajo`, `objetivo_muy_alto`, `corte_breve`, `visual_breve`, `borde_en_voz`,
`pausas_excesivas`, `sin_pausas_detectadas`, `sin_marcas_por_palabra`, `fuente_vfr`, `huecos_pts`,
`identidad_parcial`, `origen_reasignado`, `cobertura_baja`, `velocidad_alta`) informan sin detener
nada. `--directo` no anula los bloqueantes: `render` termina con código 2 y nombra los cortes
afectados.

`origen_reasignado` es el aviso de la identidad por huella: el archivo ya no está donde lo dejó el
plan, pero su huella —tamaño, `mtime_ns` y sha256 de los primeros y últimos 4 MiB— coincide, así que
`render` sigue adelante y actualiza `source` en el plan publicado. Una huella distinta no es un
aviso, sino un error.
