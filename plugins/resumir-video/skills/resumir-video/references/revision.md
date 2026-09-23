# Revisión en lenguaje natural

Antes de montar, la skill muestra `propuesta-vN.md` y **espera**. Solo `directo` salta esa espera.

## Qué contiene la propuesta

Cabecera con original, objetivo, banda de tolerancia, estimación, porcentaje y estado; la cadena de
técnicas («38 cortes · 16:45 → sin pausas 15:09 → ×1,25 → 12:07»); los cambios respecto a la versión
anterior; los avisos redactados; una tabla `# | Origen | Salida estimada | Prioridad | Qué se dice`;
las reservas con lo que aportaría cada una; alternativas y sugerencias; el timeline de texto y
ejemplos de respuesta. Con más de 40 filas se agrupa por bloques en el chat.

## Qué se puede pedir

| Petición | Efecto |
| --- | --- |
| «quita el 7 y el 9» | Pasan a reserva |
| «añade el 6» | Se incluye la reserva y queda fijada (`pinned`) |
| «añade la parte donde habla de ATEX» | `search` + contexto + fotogramas; se crea o recupera el corte |
| «alarga el 3» / «10 s más» | Se amplía hasta completar la frase o la unidad |
| «acorta el 12», «empieza el 5 cuando dice…» | Se recorta al núcleo o se mueven los límites |
| «parte el 4» / «une 4 y 5» | Identificadores nuevos; al unir se conserva el menor |
| «súbelo al 15 %», «déjalo en 8 min» | Objetivo nuevo y aplicación de las sugerencias mostradas |
| «sin acelerar», «no quites pausas en el 12» | Ajustes globales o por corte |
| «vuelve a la v1», «deshaz» | Se copia esa versión a un borrador nuevo |
| «¿qué has dejado fuera?» | Se muestran reservas y exclusiones sin crear versión |

«El 7» es el número de la última propuesta mostrada. No se reordena el vídeo. Ante una ambigüedad se
hace **una** pregunta y no se aplica nada. `plan` rechaza sin escribir si hay identificadores
inexistentes, límites fuera del medio, evidencias vacías o solapes estrictos (los cortes contiguos
son legales).

Tras cada edición se muestra el diff (altas, bajas y cambios con título, segundos y frase), la nueva
estimación y el coste de montaje («reutiliza 36 de 38 · 2 cortes nuevos · ≈2 min»): el dato lo da
`render --dry-run`, que imprime `{reused, new, eta_s}` sin montar nada. Después se vuelve a esperar.

## Aceptación y versiones

`render` exige `--accept "frase literal del usuario"` o `--directo`; sin uno de los dos rechaza el
plan. La frase queda en `vN/seleccion.json` y en `historial.jsonl` junto al sha256 canónico del plan.
En modo audio, `doc` exige la misma aceptación contra el sha256 del esquema.

Cada versión reserva su número creando en exclusiva `seleccion-vN.json` (o `esquema-vN.json` en
audio); si ya existe se reintenta con `N+1` hasta tres veces. `vN/` y `documento-vN/` son inmutables: una edición posterior produce
`v(N+1)` sin tocar la anterior. Un cambio que solo afecta al documento publica `vN/resumen-rM.md` (y
`.docx`) junto a los anteriores, registrado en `vN/revisiones.json`; la entrega apunta siempre a la M
mayor.

Después del montaje, si la petición incluye «y móntalo» y la edición no introduce ningún aviso que no
estuviera en la versión aceptada anterior, se monta sin esperar; los avisos bloqueantes siempre
obligan a esperar.

## Eventos de `historial.jsonl`

El historial es un diario: una línea JSON por evento, con `cuando` (UTC, segundos) y `evento` más los
campos propios de cada uno.

| Evento | Quién lo escribe |
| --- | --- |
| `init` | `plan`, al publicar la primera versión o al importar un plan de la 0.1 |
| `edit` | `plan`, en cada versión derivada o al regresar a una anterior |
| `accept` | `render`, con la frase literal aceptada |
| `render` | `render`, al publicar `vN/` |
| `verify` | `render` y `compare`, con la validación y la cobertura |
| `doc` | `doc`, en cada publicación del documento o de una revisión |
| `deliver` | **Lo escribe el agente al entregar; no lo emite ningún script** |

El evento `verify` tiene dos formas distintas según quién lo escriba: la de `render` lleva `ok`,
`codigo` (solo si `ok` es `false`) y, si `ok` es `true`, `fotogramas` y `desfase_s`, **sin** el campo
`tipo`; la de `compare` lleva `tipo: "cobertura"` junto con `media` y `minimo`. Un agente que filtre
`historial.jsonl` por `evento == "verify"` debe mirar la presencia o ausencia de `tipo` para saber
cuál de las dos está leyendo.

Cuando entregues el resultado al usuario, añade tú esa línea al final de `historial.jsonl`, con el
mismo formato que el resto de eventos:

```text
{"cuando": "2026-09-18T12:40:05+00:00", "evento": "deliver", "version": 1}
```
