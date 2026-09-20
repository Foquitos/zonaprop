"""Generador de Ficha de Visita Presencial (PDF, HTML y Markdown) y Mensajes para Inmobiliarias.
"""

from __future__ import annotations

import html
import urllib.parse
from pathlib import Path


from zp.comun import _plata


def generar_ficha_visita_html(run: str, top_avisos: list[dict]) -> str:
    """Genera una versión HTML estilizada y optimizada para impresión en PDF A4."""
    cards_html = []
    for idx, a in enumerate(top_avisos[:15], start=1):
        aid = a.get("id")
        score = a.get("score", 0.0)
        dir_txt = html.escape(a.get("direccion") or "Sin dirección")
        barrio = html.escape(a.get("barrio") or "")
        costo = _plata(a.get("costo_mensual"))
        caja = _plata(a.get("caja_inicial_total"))
        tipo = (a.get("tipo") or "departamento").upper()
        m2 = a.get("m2_total") or "?"
        cub = a.get("m2_cubierto") or "?"
        amb = a.get("ambientes") or "?"
        gar = html.escape(", ".join(a.get("garantias_aceptadas") or ["Consultar"]))
        url = a.get("url") or "#"

        preguntas = a.get("preguntas_visita") or []
        preguntas_li = "".join(f"<li><span class='check-box'></span> {html.escape(p)}</li>" for p in preguntas)

        score_badge_class = "score-high" if score >= 70 else ("score-mid" if score >= 50 else "score-low")

        cards_html.append(f"""
        <div class="prop-card">
          <div class="prop-header">
            <div class="prop-title-block">
              <span class="prop-idx">#{idx}</span>
              <span class="prop-dir">{dir_txt}</span>
              <span class="prop-type">({tipo})</span>
            </div>
            <div class="prop-score {score_badge_class}">{score:.1f} pts</div>
          </div>

          <div class="prop-meta-grid">
            <div class="meta-item"><strong>Costo Mensual:</strong> {costo}</div>
            <div class="meta-item"><strong>Caja Entrada:</strong> {caja}</div>
            <div class="meta-item"><strong>Superficie:</strong> {amb} amb · {m2} m² ({cub}m² cub)</div>
            <div class="meta-item"><strong>Garantías:</strong> {gar}</div>
            <div class="meta-item"><strong>Barrio / ID:</strong> {barrio} (ID: {aid})</div>
            <div class="meta-item"><strong>Link:</strong> <a href="{url}" target="_blank">Ver en Zonaprop</a></div>
          </div>

          <div class="prop-section">
            <div class="section-subtitle">🔍 Preguntas específicas para el martillero in situ:</div>
            <ul class="check-list">
              {preguntas_li}
            </ul>
          </div>

          <div class="notes-grid">
            <div class="note-box">
              <span class="note-label">Luz Natural:</span>
              <span class="stars">⭐ [ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]</span>
            </div>
            <div class="note-box">
              <span class="note-label">Silencio / Ruido:</span>
              <span class="stars">🔇 [ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ]</span>
            </div>
            <div class="note-field"><strong>Presión agua / desagües:</strong> ________________________________</div>
            <div class="note-field"><strong>¿Hacer contraoferta?:</strong> [ ] Sí  [ ] No  (Oferta: $____________)</div>
          </div>
        </div>
        """)

    cards_str = "\n".join(cards_html)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Planilla de Inspección Presencial · {html.escape(run)}</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 12mm 12mm 12mm 12mm;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      background: #ffffff;
      font-size: 11px;
      line-height: 1.35;
      padding: 10px;
    }}
    header {{
      border-bottom: 2px solid #0284c7;
      padding-bottom: 8px;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
    }}
    h1 {{ font-size: 18px; color: #0f172a; font-weight: 800; }}
    .subtitle {{ color: #64748b; font-size: 11px; }}

    /* Protocolo Forense */
    .protocol-box {{
      background: #f8fafc;
      border: 1.5px solid #cbd5e1;
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 14px;
      page-break-inside: avoid;
    }}
    .protocol-title {{
      font-size: 12px;
      font-weight: 700;
      color: #0369a1;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .protocol-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 14px;
    }}
    .protocol-item {{
      display: flex;
      align-items: flex-start;
      gap: 6px;
      font-size: 10.5px;
    }}

    /* Prop Cards */
    .prop-card {{
      background: #ffffff;
      border: 1px solid #94a3b8;
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 12px;
      page-break-inside: avoid;
    }}
    .prop-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 6px;
      margin-bottom: 6px;
    }}
    .prop-idx {{ font-weight: 800; color: #0284c7; font-size: 13px; margin-right: 4px; }}
    .prop-dir {{ font-weight: 700; font-size: 13px; color: #0f172a; }}
    .prop-type {{ color: #64748b; font-size: 11px; margin-left: 4px; }}
    .prop-score {{
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
    }}
    .score-high {{ background: #dcfce7; color: #166534; }}
    .score-mid {{ background: #fef3c7; color: #92400e; }}
    .score-low {{ background: #f1f5f9; color: #475569; }}

    .prop-meta-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr 1.2fr;
      gap: 4px 8px;
      background: #f8fafc;
      padding: 6px 8px;
      border-radius: 4px;
      margin-bottom: 6px;
      font-size: 10px;
    }}
    .meta-item strong {{ color: #334155; }}
    .meta-item a {{ color: #0284c7; text-decoration: none; }}

    .section-subtitle {{
      font-weight: 700;
      font-size: 10.5px;
      color: #0369a1;
      margin-top: 4px;
      margin-bottom: 3px;
    }}
    .check-list {{ list-style: none; padding-left: 0; }}
    .check-list li {{
      display: flex;
      align-items: flex-start;
      gap: 6px;
      margin-bottom: 3px;
      font-size: 10px;
    }}
    .check-box {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border: 1.2px solid #475569;
      border-radius: 2px;
      flex-shrink: 0;
      margin-top: 1px;
    }}

    .notes-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px 12px;
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px dashed #cbd5e1;
      font-size: 10px;
    }}
    .note-box {{ display: flex; align-items: center; justify-content: space-between; }}
    .stars {{ font-family: monospace; font-size: 9.5px; color: #475569; }}
    .note-field {{ grid-column: span 2; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>📋 Planilla de Inspección Presencial · {html.escape(run)}</h1>
      <div class="subtitle">Guía de campo y verificación forense in situ ({len(top_avisos[:15])} candidatos prioritarios)</div>
    </div>
  </header>

  <div class="protocol-box">
    <div class="protocol-title">🛠️ PROTOCOLO FORENSE DE INSPECCIÓN EN 5 PASOS</div>
    <div class="protocol-grid">
      <div class="protocol-item"><span class="check-box"></span> <strong>1. Agua y Presión:</strong> Abrir cocina y ducha simultáneamente. Mirar sifón bajo bacha.</div>
      <div class="protocol-item"><span class="check-box"></span> <strong>2. Tablero Eléctrico:</strong> Probar botón "T" (Test) del disyuntor. Contar tomas.</div>
      <div class="protocol-item"><span class="check-box"></span> <strong>3. Humedad y Muros:</strong> Alumbrar zócalos con linterna y esquinas de techo/baño.</div>
      <div class="protocol-item"><span class="check-box"></span> <strong>4. Aberturas y Ventilación:</strong> Subir/bajar persianas completas y verificar trabas.</div>
      <div class="protocol-item"><span class="check-box"></span> <strong>5. Gas y Calefacción:</strong> Verificar rejillas reglamentarias y tiraje estufa/calefón.</div>
      <div class="protocol-item"><span class="check-box"></span> <strong>6. Consorcio / Gastos:</strong> Verificar quién paga bomba de agua y arreglos comunes.</div>
    </div>
  </div>

  {cards_str}
</body>
</html>
"""


def generar_ficha_visita_pdf(run: str, top_avisos: list[dict], carpeta: Path) -> Path | None:
    """Genera un archivo PDF limpio y listo para imprimir usando Playwright."""
    html_str = generar_ficha_visita_html(run, top_avisos)
    html_path = carpeta / "ficha_visita.html"
    html_path.write_text(html_str, encoding="utf-8")

    pdf_path = carpeta / "ficha_visita.pdf"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_str, wait_until="load")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
            )
            browser.close()
        return pdf_path
    except Exception as e:
        print(f"  [Aviso] No se pudo generar PDF automáticamente ({e}). Se generó ficha_visita.html.")
        return None


def generar_ficha_visita(run: str, top_avisos: list[dict], carpeta: Path) -> Path:
    """Genera una guía/checklist imprimible y móvil para el día de las visitas presenciales."""
    lineas = [
        f"# 📋 Planilla de Inspección Presencial · {run}",
        "",
        "> Llevá esta planilla en el celular o impresa el día que salgas a recorrer propiedades.",
        "",
        "## 🛠️ PROTOCOLO FORENSE EN 5 PASOS (Chequear en TODAS las visitas)",
        "",
        "- [ ] **1. Agua y Desagüe**:",
        "  - Abrir la canilla de la cocina y la ducha del baño simultáneamente para verificar presión.",
        "  - Mirar abajo de la bacha de la cocina con la linterna del celular (verificar sifón sin pérdidas ni aglomerado podrido).",
        "- [ ] **2. Electricidad y Tablero**:",
        "  - Ubicar el tablero general: apretar el botón **T (Test)** del disyuntor diferencial (debe cortar de inmediato).",
        "  - Contar enchufes en cocina y dormitorio (¿alcanzan para microondas, pava, heladera, computadora?).",
        "- [ ] **3. Humedad y Muros**:",
        "  - Alumbrar zócalos de madera (¿hinchados o con pintura descascarada?).",
        "  - Mirar esquinas superiores del techo y cielorraso del baño (¿moho por vapor o filtración?).",
        "- [ ] **4. Aberturas y Ventilación**:",
        "  - Subir y bajar persianas completas (verificar que no estén trabadas ni deshilachadas).",
        "  - Probar trabas y cierre hermético de ventanas.",
        "- [ ] **5. Gas y Calefacción**:",
        "  - Verificar rejillas reglamentarias de ventilación (arriba y abajo).",
        "  - Comprobar funcionamiento de estufa tiro balanceado / calefón.",
        "",
        "---",
        "",
        "## 🏡 FICHAS INDIVIDUALES POR PROPIEDAD",
        "",
    ]

    for idx, a in enumerate(top_avisos[:15], start=1):
        aid = a.get("id")
        score = a.get("score")
        dir_txt = a.get("direccion") or "Sin dirección"
        barrio = a.get("barrio") or ""
        costo = _plata(a.get("costo_mensual"))
        caja = _plata(a.get("caja_inicial_total"))
        tipo = (a.get("tipo") or "departamento").upper()
        m2 = a.get("m2_total") or "?"
        amb = a.get("ambientes") or "?"
        gar = ", ".join(a.get("garantias_aceptadas") or ["Consultar"])
        url = a.get("url") or "#"

        lineas += [
            f"### #{idx} · {dir_txt} ({tipo} · Score {score})",
            f"- **ID**: `{aid}` | **Barrio**: {barrio}",
            f"- **Costo Mensual**: {costo} | **Caja de Entrada**: {caja} | **Ambientes**: {amb} amb ({m2} m²)",
            f"- **Garantías declaradas**: {gar}",
            f"- **Link**: [Ver en Zonaprop]({url})",
            "",
            "**🔍 Preguntas específicas para hacerle al martillero in situ:**",
        ]
        preguntas = a.get("preguntas_visita") or []
        for p in preguntas:
            lineas.append(f"- [ ] {p}")

        lineas += [
            "",
            "**📝 Anotaciones de la visita:**",
            "- Calidad de luz natural (1 al 5): ⭐ ____",
            "- Nivel de ruido de la calle (1 al 5): 🔇 ____",
            "- Presión de agua / cañerías: ________________________________________________",
            "- Impresión del propietario / inmobiliaria: _________________________________",
            "- ¿Vale la pena hacer contraoferta?: [ ] Sí  [ ] No  (Oferta: $____________)",
            "",
            "---",
            "",
        ]

    destino = carpeta / "ficha_visita.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")

    # También generamos el PDF/HTML automáticamente
    generar_ficha_visita_pdf(run, top_avisos, carpeta)

    return destino


def generar_mensajes_inmobiliarias(run: str, top_avisos: list[dict], carpeta: Path) -> Path:
    """Genera mensajes_inmobiliarias.txt con textos listos para consultar por WhatsApp / Email."""
    bloques = [
        f"MENSAJES PREARMADOS DE CONSULTA PARA INMOBILIARIAS · {run}",
        "=" * 70,
        "Instrucciones: Copiá y pegá el mensaje para consultar a cada inmobiliaria.",
        "=" * 70,
        "",
    ]

    for idx, a in enumerate(top_avisos[:20], start=1):
        aid = a.get("id")
        score = a.get("score")
        dir_txt = a.get("direccion") or "Sin dirección"
        costo = _plata(a.get("costo_mensual"))
        amb = a.get("ambientes") or "?"
        tipo = (a.get("tipo") or "departamento").capitalize()
        url = a.get("url") or ""

        msg = (
            f"Hola! Te consulto por el alquiler del {tipo} de {amb} ambientes en {dir_txt} "
            f"(Ref Zonaprop #{aid}). ¿Sigue disponible? Cuento con garantía y recibos de sueldo listos. "
            f"¿Qué días y horarios tienen disponibles para coordinar una visita? Muchas gracias!"
        )

        bloques += [
            f"#{idx} | ID: {aid} | Score: {score} | {dir_txt} ({costo}/mes)",
            f"Link: {url}",
            "Mensaje:",
            f'"{msg}"',
            "-" * 70,
            "",
        ]

    destino = carpeta / "mensajes_inmobiliarias.txt"
    destino.write_text("\n".join(bloques), encoding="utf-8")
    return destino
