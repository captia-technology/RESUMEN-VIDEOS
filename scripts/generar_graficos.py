"""Generate the README graphics as SVG from measured data (docs/img/datos.json).

Every figure is data-driven: the timeline comes from a real run of the skill on the synthetic
demo video, and the synchronisation chart from the measurements recorded in docs/plan.md.
Run it after updating docs/img/datos.json:  python -B scripts/generar_graficos.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"

FONDO = "#0B1220"
PANEL = "#111C30"
BORDE = "#1E293B"
TEXTO = "#E2E8F0"
SUAVE = "#94A3B8"
TENUE = "#475569"
AMBAR = "#FBBF24"
CIAN = "#38BDF8"
VERDE = "#34D399"
ROJO = "#F87171"
FUENTE = "Segoe UI, Inter, Helvetica, Arial, sans-serif"
MONO = "Cascadia Mono, Consolas, monospace"


def texto(x, y, contenido, tamano=14, color=TEXTO, peso=400, anclaje="start", fuente=FUENTE, extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{fuente}" font-size="{tamano}" fill="{color}" '
            f'font-weight="{peso}" text-anchor="{anclaje}"{extra}>{contenido}</text>')


def caja(x, y, ancho, alto, radio=10, relleno=PANEL, borde=BORDE, extra=""):
    return (f'<rect x="{x}" y="{y}" width="{ancho}" height="{alto}" rx="{radio}" fill="{relleno}" '
            f'stroke="{borde}" stroke-width="1"{extra}/>')


def documento(ancho, alto, cuerpo, titulo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" '
            f'height="{alto}" role="img" aria-label="{titulo}">\n<title>{titulo}</title>\n'
            f'<rect width="{ancho}" height="{alto}" fill="{FONDO}"/>\n{cuerpo}\n</svg>\n')


def reloj(segundos):
    return f"{int(segundos // 60)}:{segundos % 60:04.1f}".replace(".", ",")


def banner(datos):
    """Animated header: the original timeline collapses into the summary, loop every 9 s."""
    ancho, alto = 1200, 352
    total = datos["original_segundos"]
    izquierda, util = 80, 1040
    partes = []
    partes.append(f'<defs><linearGradient id="fondo" x1="0" y1="0" x2="1" y2="1">'
                  f'<stop offset="0%" stop-color="#0B1220"/><stop offset="55%" stop-color="#0F1E38"/>'
                  f'<stop offset="100%" stop-color="#0B1220"/></linearGradient>'
                  f'<linearGradient id="barra" x1="0" y1="0" x2="1" y2="0">'
                  f'<stop offset="0%" stop-color="{CIAN}"/><stop offset="100%" stop-color="{VERDE}"/>'
                  f'</linearGradient></defs>')
    partes.append(f'<rect width="{ancho}" height="{alto}" fill="url(#fondo)"/>')
    partes.append(f'<rect x="0" y="0" width="{ancho}" height="3" fill="url(#barra)"/>')
    partes.append(texto(izquierda, 96, "resumir-video", 52, TEXTO, 700))
    partes.append(texto(izquierda + 352, 96, "v" + datos["version"], 18, AMBAR, 600))
    partes.append(texto(izquierda, 130,
                        "Resúmenes de vídeo técnico con fragmentos originales, para agentes de IA",
                        19, SUAVE))
    for i, nombre in enumerate(("Claude Code", "GitHub Copilot", "OpenAI Codex")):
        x = izquierda + i * 190
        partes.append(caja(x, 152, 174, 32, 16, "#0F1B2E", BORDE))
        partes.append(texto(x + 87, 173, nombre, 14, SUAVE, 600, "middle"))

    fila, altura = 222, 26
    partes.append(texto(izquierda, fila - 14, "ORIGINAL", 11, TENUE, 700, extra=' letter-spacing="2"'))
    partes.append(texto(izquierda + util, fila - 14, reloj(total), 11, TENUE, 700, "end"))
    partes.append(f'<rect x="{izquierda}" y="{fila}" width="{util}" height="{altura}" rx="6" '
                  f'fill="#152238" stroke="{BORDE}"/>')
    # Kept fragments: they fade in place and then slide together into the summary bar below.
    acumulado = 0.0
    for corte in datos["cortes"]:
        x = izquierda + util * corte["start"] / total
        w = max(6.0, util * (corte["end"] - corte["start"]) / total)
        destino = izquierda + util * acumulado / total
        acumulado += corte["end"] - corte["start"]
        partes.append(
            f'<rect x="{x:.1f}" y="{fila}" width="{w:.1f}" height="{altura}" rx="5" fill="{AMBAR}" '
            f'opacity=".92">'
            f'<animate attributeName="y" values="{fila};{fila};{fila + 62};{fila + 62};{fila}" '
            f'keyTimes="0;0.34;0.52;0.88;1" dur="9s" repeatCount="indefinite"/>'
            f'<animate attributeName="x" values="{x:.1f};{x:.1f};{destino:.1f};{destino:.1f};{x:.1f}" '
            f'keyTimes="0;0.34;0.52;0.88;1" dur="9s" repeatCount="indefinite"/>'
            f'</rect>')
    partes.append(texto(izquierda, fila + 62 - 12, "RESUMEN", 11, TENUE, 700,
                        extra=' letter-spacing="2"'))
    partes.append(texto(izquierda + util * acumulado / total + 12, fila + 62 + 18,
                        f'{reloj(datos["resumen_segundos"])}  ·  −{datos["reduccion_porcentaje"]:.0f} %'
                        .replace(".", ","), 13, VERDE, 700))
    partes.append(f'<rect x="{izquierda}" y="{fila + 62}" width="{util * acumulado / total:.1f}" '
                  f'height="{altura}" rx="6" fill="none" stroke="{VERDE}" stroke-width="1.5" '
                  f'stroke-dasharray="4 4" opacity=".55"/>')
    return documento(ancho, alto, "\n".join(partes),
                     "resumir-video: la línea de tiempo original se condensa en el resumen")


def linea_tiempo(datos):
    """Where the summary comes from: kept fragments over the original timeline."""
    ancho, alto = 1200, 340
    total = datos["original_segundos"]
    izquierda, util, fila, altura = 60, 1080, 120, 44
    partes = [caja(20, 20, ancho - 40, alto - 40, 14, "#0D1626")]
    partes.append(texto(izquierda, 58, "De dónde sale el resumen", 20, TEXTO, 700))
    partes.append(texto(izquierda, 82,
                        f'{datos["cortes"].__len__()} fragmentos conservados · '
                        f'{reloj(total)} → {reloj(datos["resumen_segundos"])} '
                        f'(−{datos["reduccion_porcentaje"]:.0f} %)'.replace(".", ","), 14, SUAVE))
    partes.append(f'<rect x="{izquierda}" y="{fila}" width="{util}" height="{altura}" rx="8" '
                  f'fill="#152238" stroke="{BORDE}"/>')
    for corte in datos["cortes"]:
        x = izquierda + util * corte["start"] / total
        w = max(8.0, util * (corte["end"] - corte["start"]) / total)
        partes.append(f'<rect x="{x:.1f}" y="{fila}" width="{w:.1f}" height="{altura}" rx="7" '
                      f'fill="{AMBAR}" opacity=".92"/>')
        # Alterna la altura de los rótulos para que no se solapen en fragmentos próximos.
        desplazado = 22 if datos["cortes"].index(corte) % 2 == 0 else 62
        partes.append(texto(x + w / 2, fila + altura + desplazado, corte["titulo"], 12, TEXTO, 600,
                            "middle"))
        partes.append(texto(x + w / 2, fila + altura + desplazado + 17, reloj(corte["start"]), 11,
                            TENUE, 400, "middle", MONO))
        partes.append(f'<line x1="{x + w / 2:.1f}" y1="{fila + altura}" x2="{x + w / 2:.1f}" '
                      f'y2="{fila + altura + desplazado - 12}" stroke="{BORDE}" stroke-width="1"/>')
    for etiqueta, x, anclaje in (("0:00", izquierda, "start"), (reloj(total), izquierda + util, "end")):
        partes.append(texto(x, fila - 12, etiqueta, 11, TENUE, 600, anclaje, MONO))
    partes.append(f'<rect x="{izquierda}" y="{fila + 136}" width="{util}" height="10" rx="5" '
                  f'fill="#152238"/>')
    partes.append(f'<rect x="{izquierda}" y="{fila + 136}" '
                  f'width="{util * datos["resumen_segundos"] / total:.1f}" height="10" rx="5" '
                  f'fill="{VERDE}"/>')
    partes.append(texto(izquierda, fila + 172, "Descartado: saludos, repeticiones, despedida y "
                        "lecturas literales de diapositivas visibles", 12, TENUE))
    partes.append(texto(izquierda + util, fila + 172, "Conservado", 12, AMBAR, 600, "end"))
    return documento(ancho, alto, "\n".join(partes), "Fragmentos conservados sobre el vídeo original")


def sincronia(datos):
    """Audio drift at the joins, measured on the same 20-join render."""
    ancho, alto = 620, 300
    izquierda, base, escala = 210, 240, 1.6
    partes = [caja(20, 20, ancho - 40, alto - 40, 14, "#0D1626")]
    partes.append(texto(40, 58, "Desfase de audio acumulado", 18, TEXTO, 700))
    partes.append(texto(40, 80, "20 uniones, vídeo sintético de 12 s", 13, SUAVE))
    for i, medida in enumerate(datos["sincronia"]):
        y = 110 + i * 46
        largo = max(3.0, medida["ms"] * escala)
        color = ROJO if medida["ms"] > 20 else (AMBAR if medida["ms"] > 1 else VERDE)
        partes.append(texto(izquierda - 14, y + 15, medida["etapa"], 13, SUAVE, 500, "end"))
        partes.append(f'<rect x="{izquierda}" y="{y}" width="{largo:.1f}" height="22" rx="6" '
                      f'fill="{color}" opacity=".9"/>')
        valor = f'{medida["ms"]:.0f} ms'.replace(".", ",") if medida["ms"] else "0 ms"
        partes.append(texto(izquierda + largo + 10, y + 16, valor, 13, color, 700, fuente=MONO))
    partes.append(texto(40, base + 28, "Medido como diferencia entre la duración del vídeo y la del "
                        "audio decodificado.", 11, TENUE))
    return documento(ancho, alto, "\n".join(partes), "Desfase de audio antes y después de los arreglos")


def pipeline():
    """How the work is split between the agent and the local assistant."""
    ancho, alto = 1200, 380
    partes = [caja(20, 20, ancho - 40, alto - 40, 14, "#0D1626")]
    partes.append(texto(60, 58, "Cómo trabaja la skill", 20, TEXTO, 700))
    partes.append(texto(60, 82, "El agente decide qué conocimiento se conserva; el asistente local "
                        "extrae la evidencia y monta el vídeo.", 14, SUAVE))
    columnas = [
        ("1 · Entrada", CIAN, ["vídeo local", "check · probe", "pistas, HDR, fps"]),
        ("2 · Evidencia", CIAN, ["prepare → audio.wav", "frames por bloques", "subtítulos o transcribe"]),
        ("3 · Análisis", AMBAR, ["el agente mira y escucha", "analisis.md", "inventario y decisiones"]),
        ("4 · Selección", AMBAR, ["seleccion.json", "cortes con evidencia", "audio + pantalla"]),
        ("5 · Montaje", VERDE, ["render", "cortes originales", "audio sin deriva"]),
        ("6 · Entrega", VERDE, ["resumen.mp4", "resumen.md", "revisión editorial"]),
    ]
    x, y, w, h, hueco = 60, 130, 168, 150, 22
    for i, (titulo, color, lineas) in enumerate(columnas):
        cx = x + i * (w + hueco)
        partes.append(caja(cx, y, w, h, 12, PANEL, BORDE))
        partes.append(f'<rect x="{cx}" y="{y}" width="{w}" height="4" rx="2" fill="{color}"/>')
        partes.append(texto(cx + 16, y + 34, titulo, 13, color, 700))
        for j, linea in enumerate(lineas):
            partes.append(texto(cx + 16, y + 62 + j * 24, linea, 13, TEXTO if j == 0 else SUAVE))
        if i < len(columnas) - 1:
            flecha = cx + w + hueco / 2
            partes.append(f'<path d="M{flecha - 7} {y + h / 2 - 6} l7 6 l-7 6" fill="none" '
                          f'stroke="{TENUE}" stroke-width="2" stroke-linecap="round"/>')
    partes.append(caja(60, 300, 1080, 44, 10, "#101B2E", BORDE))
    partes.append(texto(80, 328, "Todo se ejecuta en local: Python de la biblioteca estándar y FFmpeg. "
                        "El vídeo no se sube a ningún servicio.", 13, SUAVE))
    partes.append(texto(1120, 328, "MIT", 13, TENUE, 700, "end"))
    return documento(ancho, alto, "\n".join(partes), "Flujo de trabajo de la skill resumir-video")


def main():
    datos = json.loads((IMG / "datos.json").read_text(encoding="utf-8"))
    figuras = {"banner.svg": banner(datos), "linea-tiempo.svg": linea_tiempo(datos),
               "sincronia.svg": sincronia(datos), "pipeline.svg": pipeline()}
    for nombre, contenido in figuras.items():
        (IMG / nombre).write_text(contenido, encoding="utf-8", newline="\n")
        print(nombre, len(contenido), "bytes")


if __name__ == "__main__":
    main()
