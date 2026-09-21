"""Generador de Dashboard HTML interactivo (resumen.html) con Mapa Leaflet, WhatsApp y Métricas.
"""

from __future__ import annotations

import html
import json
import urllib.parse
from pathlib import Path

from zp import geocodificador
from zp.comun import _plata

# --------------------------------------------------------------------------- #
# Tiles del mapa
# --------------------------------------------------------------------------- #
# NO usar https://{s}.tile.openstreetmap.org/... acá. Esos son los servidores de
# voluntarios de OpenStreetMap y su política de uso no permite que una app les
# pegue directo: devuelven un tile con "Access blocked / App is not following
# the tile usage policy", que es lo que se ve en el mapa en vez del plano.
# Encima el patrón de subdominios {s} (a./b./c.) está deprecado y OSM pide
# explícitamente dejar de usarlo.
#
# CARTO sirve tiles derivados de datos de OSM desde su propia CDN, pensada para
# esto. La atribución tiene que nombrar a los dos: los datos son de OSM, el
# render es de CARTO.
#
# Se puede cambiar por cualquier otro proveedor de tiles raster; sólo hay que
# actualizar la atribución junto con la URL. Para tema claro: 'light_all'.
# Otra alternativa sin API key es Esri (World_Street_Map).
TILES_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
TILES_ATRIBUCION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)
TILES_MAX_ZOOM = 20


def generar_dashboard_html(run: str, avisos: list[dict], carpeta: Path) -> Path:
    """Genera un archivo resumen.html con un dashboard visual responsivo y mapa interactivo."""
    vivos = [a for a in avisos if not a.get("descartado")]

    # Métricas clave
    top_score = vivos[0]["score"] if vivos else 0
    costos = [a["costo_mensual"] for a in vivos if a.get("costo_mensual")]
    mediana_costo = sorted(costos)[len(costos) // 2] if costos else 0
    m2_refs = [a["costo_m2"] for a in vivos if a.get("costo_m2")]
    mejor_m2 = min(m2_refs) if m2_refs else 0

    # Puntos para el mapa Leaflet
    map_points = []

    filas_html = []
    for idx, a in enumerate(vivos, start=1):
        aid = a.get("id")
        score = a.get("score", 0)
        tipo = (a.get("tipo") or "departamento").upper()
        direccion = html.escape(a.get("direccion") or "Sin dirección")
        barrio = html.escape(a.get("barrio") or "")
        costo = _plata(a.get("costo_mensual"))
        alquiler = f"{a.get('moneda', 'ARS')} {_plata(a.get('precio'))}"
        exp = _plata(a.get("expensas") or a.get("expensas_estimadas"))
        m2_tot = a.get("m2_total") or "?"
        m2_cub = a.get("m2_cubierto_estimado") or a.get("m2_cubierto") or m2_tot
        costo_m2 = _plata(a.get("costo_m2"))
        amb = a.get("ambientes") or "?"
        dorm = a.get("dormitorios") or "?"
        garantias = html.escape(", ".join(a.get("garantias_aceptadas") or ["Consultar"]))
        mascotas = html.escape(a.get("politica_mascotas") or "No especifica")
        caja_entrada = html.escape(a.get("caja_inicial_resumen") or "-")
        caja_total = _plata(a.get("caja_inicial_total"))
        entorno = html.escape(a.get("entorno_tipo") or "")
        proy_txt = html.escape(a.get("proyeccion_resumen") or "No calculada")
        dias = a.get("dias_publicado")
        dias_txt = f"{dias} días" if dias is not None else "Reciente"
        url = a.get("url") or "#"
        ruta_contacto = f"contactos/{aid}.jpg"

        lat_lng = geocodificador.obtener_coordenadas_reales(a)
        lat = lat_lng[0] if lat_lng else None
        lng = lat_lng[1] if lat_lng else None

        if lat is not None and lng is not None:
            map_points.append({
                "id": str(aid),
                "rank": idx,
                "score": score,
                "direccion": a.get("direccion") or "Sin dirección",
                "costo": costo,
                "m2": f"{m2_tot} m²",
                "url": url,
                "contacto": ruta_contacto,
                "lat": float(lat),
                "lng": float(lng),
            })

        # Mensaje de WhatsApp URL-encoded
        wa_msg = (
            f"Hola! Te consulto por el alquiler en {a.get('direccion', '')} (Ref Zonaprop #{aid}). "
            f"¿Sigue disponible? Cuento con garantía y recibos de sueldo listos para coordinar visita. Gracias!"
        )
        wa_link = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_msg)}"

        # Badges
        badges = []
        if tipo == "PH":
            badges.append('<span class="badge badge-blue">PH</span>')
        elif tipo == "CASA":
            badges.append('<span class="badge badge-purple">CASA</span>')
        else:
            badges.append('<span class="badge badge-gray">DEPTO</span>')

        if a.get("es_dueno_directo"):
            badges.append('<span class="badge badge-emerald">💎 DUEÑO DIRECTO</span>')
        if a.get("es_duplicado"):
            badges.append('<span class="badge badge-amber">⚠️ DUPLICADO</span>')
        if a.get("baja_precio"):
            badges.append(f'<span class="badge badge-green">📉 -{a.get("descuento_porcentaje")}%</span>')
        if not a.get("m2_confiable"):
            badges.append('<span class="badge badge-orange">TERRAZA</span>')

        preguntas_li = "".join(f"<li>{html.escape(p)}</li>" for p in (a.get("preguntas_visita") or []))

        onclick_attr = f"onclick=\"focusMap('{aid}', {lat}, {lng})\"" if lat is not None and lng is not None else ""

        filas_html.append(f"""
        <tr class="item-row" id="row-{aid}" {onclick_attr}>
          <td class="col-rank">#{idx}</td>
          <td class="col-score"><span class="score-pill">{score}</span></td>
          <td class="col-dir">
            <strong>{direccion}</strong>
            <div class="sub-text">{barrio}</div>
            <div class="badge-container">{' '.join(badges)}</div>
          </td>
          <td class="col-costo">
            <span class="costo-main">{costo}</span>
            <div class="sub-text">Alq: {alquiler} | Exp: {exp}</div>
          </td>
          <td class="col-sup">
            <span>{m2_tot} m² ({m2_cub} cub)</span>
            <div class="sub-text">{amb} amb · {dorm} dorm · {costo_m2}/m²</div>
          </td>
          <td class="col-caja">
            <span class="caja-main">{caja_total}</span>
            <div class="sub-text" title="{caja_entrada}">Caja de entrada est.</div>
          </td>
          <td class="col-contrato">
            <div><strong>Garantía:</strong> {garantias}</div>
            <div><strong>Mascotas:</strong> {mascotas}</div>
            <div class="sub-text"><strong>Mercado:</strong> {dias_txt}</div>
          </td>
          <td class="col-acciones">
            <a href="{url}" target="_blank" class="btn btn-outline">Zonaprop ↗</a>
            <a href="{ruta_contacto}" target="_blank" class="btn btn-primary">Fotos 🖼️</a>
            <a href="{wa_link}" target="_blank" class="btn btn-wa">WhatsApp 💬</a>
          </td>
        </tr>
        <tr class="details-row" id="details-{aid}">
          <td colspan="8">
            <div class="details-content">
              <div class="details-grid">
                <div>
                  <h4>📍 Micro-entorno y Conectividad</h4>
                  <p>{entorno}</p>
                  <h4>💰 Desglose Caja Inicial</h4>
                  <p>{caja_entrada}</p>
                  <h4>📈 Evolución Cuota a 24 Meses (IPC 3% proyectado)</h4>
                  <p>{proy_txt}</p>
                </div>
                <div>
                  <h4>🔍 Preguntas Clave para la Visita</h4>
                  <ul>{preguntas_li}</ul>
                </div>
              </div>
            </div>
          </td>
        </tr>
        """)

    filas_str = "\n".join(filas_html)
    points_json = json.dumps(map_points)
    map_section = '<div id="map"></div>' if map_points else (
        '<div class="map-hint">📍 <em>Las coordenadas en el mapa se cargarán automáticamente al ejecutar el paso <code>fotos</code>.</em></div>'
    )

    doc_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboard Candidatos · {html.escape(run)}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --accent: #f59e0b;
      --success: #10b981;
      --danger: #ef4444;
      --wa: #22c55e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; color: #fff; }}
    .subtitle {{ color: var(--text-muted); font-size: 15px; }}

    /* KPI Cards */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .kpi-title {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }}
    .kpi-value {{ font-size: 24px; font-weight: 700; color: #fff; margin-top: 4px; }}

    /* Map */
    #map {{
      height: 380px;
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--border);
      margin-bottom: 24px;
      z-index: 1;
    }}

    /* Table */
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }}
    th {{
      background: #0f172a;
      padding: 14px 16px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    td {{ padding: 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    tr.item-row:hover {{ background: rgba(56, 189, 248, 0.04); cursor: pointer; }}

    .score-pill {{
      display: inline-block;
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 15px;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .costo-main {{ font-size: 16px; font-weight: 700; color: #fff; }}
    .caja-main {{ font-size: 15px; font-weight: 600; color: #fbbf24; }}
    .sub-text {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; }}

    /* Badges */
    .badge-container {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }}
    .badge {{
      font-size: 11px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      text-transform: uppercase;
    }}
    .badge-blue {{ background: #1e3a8a; color: #93c5fd; }}
    .badge-purple {{ background: #4c1d95; color: #c4b5fd; }}
    .badge-gray {{ background: #334155; color: #cbd5e1; }}
    .badge-emerald {{ background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }}
    .badge-amber {{ background: #78350f; color: #fde68a; }}
    .badge-green {{ background: #065f46; color: #a7f3d0; }}
    .badge-orange {{ background: #7c2d12; color: #fed7aa; }}

    /* Buttons */
    .btn {{
      display: inline-block;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s ease;
      text-align: center;
      margin: 2px;
    }}
    .btn-primary {{ background: var(--primary); color: #0f172a; }}
    .btn-primary:hover {{ background: var(--primary-hover); }}
    .btn-outline {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
    .btn-outline:hover {{ background: var(--border); }}
    .btn-wa {{ background: #15803d; color: #f0fdf4; }}
    .btn-wa:hover {{ background: #16a34a; }}

    /* Expandable Details */
    .details-row {{ background: #131d31; }}
    .details-content {{ padding: 12px 16px; font-size: 13px; }}
    .details-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .details-grid h4 {{ font-size: 13px; color: var(--primary); margin-top: 8px; margin-bottom: 2px; text-transform: uppercase; }}
    .details-grid ul {{ margin-left: 18px; color: #cbd5e1; }}
    .details-grid li {{ margin-bottom: 4px; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Candidatos · {html.escape(run)}</h1>
      <div class="subtitle">Ranking, mapa satelital y análisis forense pre-inspección con LLM ({len(vivos)} propiedades)</div>
    </header>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">Propiedades Vivas</div>
        <div class="kpi-value">{len(vivos)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Score Más Alto</div>
        <div class="kpi-value">{top_score}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Mediana Costo Mensual</div>
        <div class="kpi-value">{_plata(mediana_costo)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Mejor $/m² Cubierto</div>
        <div class="kpi-value">{_plata(mejor_m2)}/m²</div>
      </div>
    </div>

    <!-- Mapa Interactivo Leaflet -->
    {map_section}
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Score</th>
            <th>Ubicación / Tipo</th>
            <th>Costo Mensual</th>
            <th>Superficie</th>
            <th>Caja Entrada</th>
            <th>Contrato / Requisitos</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {filas_str}
        </tbody>
      </table>
    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const points = {points_json};
    let map = null;
    let markers = {{}};

    if (points.length > 0) {{
      const first = points[0];
      map = L.map('map').setView([first.lat, first.lng], 14);

      L.tileLayer('{TILES_URL}', {{
        attribution: '{TILES_ATRIBUCION}',
        maxZoom: {TILES_MAX_ZOOM}
      }}).addTo(map);

      const bounds = [];
      points.forEach(p => {{
        bounds.push([p.lat, p.lng]);
        const color = p.score >= 70 ? '#10b981' : (p.score >= 50 ? '#f59e0b' : '#64748b');

        const marker = L.circleMarker([p.lat, p.lng], {{
          radius: 9,
          fillColor: color,
          color: '#fff',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.9
        }}).addTo(map);

        const popupContent = `
          <div style="font-family: sans-serif; font-size: 13px;">
            <strong style="color: #0f172a;">#${{p.rank}} · Score ${{p.score}}</strong><br>
            <b>${{p.direccion}}</b><br>
            <span>${{p.costo}} · ${{p.m2}}</span><br>
            <div style="margin-top: 6px;">
              <a href="${{p.url}}" target="_blank" style="color: #0284c7; font-weight: 600;">Zonaprop ↗</a> |
              <a href="${{p.contacto}}" target="_blank" style="color: #0284c7; font-weight: 600;">Fotos 🖼️</a>
            </div>
          </div>
        `;
        marker.bindPopup(popupContent);
        markers[p.id] = marker;
      }});

      if (bounds.length > 1) {{
        map.fitBounds(bounds, {{ padding: [30, 30] }});
      }}
    }}

    function focusMap(id, lat, lng) {{
      if (map && lat && lng && markers[id]) {{
        map.setView([lat, lng], 16, {{ animate: true }});
        markers[id].openPopup();
      }}
    }}
  </script>
</body>
</html>
"""
    destino = carpeta / "resumen.html"
    destino.write_text(doc_html.strip(), encoding="utf-8")
    return destino
