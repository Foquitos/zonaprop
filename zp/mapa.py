"""Exportador de candidatos a formatos geoespaciales (GeoJSON y KML para Google Maps).
"""

from __future__ import annotations

import html
import json
from pathlib import Path


from zp import zonas


def _plata(v) -> str:
    if v is None:
        return "-"
    if v == 0:
        return "$0"
    return f"${v:,.0f}".replace(",", ".")


def exportar_geojson(run: str, avisos: list[dict], carpeta: Path) -> Path:
    """Genera candidatos.geojson con las coordenadas de cada propiedad."""
    features = []
    for idx, a in enumerate(avisos, start=1):
        if a.get("descartado"):
            continue
        lat_lng = zonas.obtener_coordenadas(a)
        if not lat_lng:
            continue
        lat, lng = lat_lng

        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lng), float(lat)],
            },
            "properties": {
                "rank": idx,
                "id": a.get("id"),
                "score": a.get("score"),
                "tipo": a.get("tipo"),
                "direccion": a.get("direccion"),
                "barrio": a.get("barrio"),
                "costo_mensual": a.get("costo_mensual"),
                "alquiler": f"{a.get('moneda', 'ARS')} {_plata(a.get('precio'))}",
                "expensas": _plata(a.get("expensas") or a.get("expensas_estimadas")),
                "m2": a.get("m2_total"),
                "ambientes": a.get("ambientes"),
                "dormitorios": a.get("dormitorios"),
                "caja_inicial": a.get("caja_inicial_total"),
                "url": a.get("url"),
            },
        }
        features.append(feat)

    geojson_data = {
        "type": "FeatureCollection",
        "name": f"Candidatos - {run}",
        "features": features,
    }

    destino = carpeta / "candidatos.geojson"
    destino.write_text(json.dumps(geojson_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def exportar_kml(run: str, avisos: list[dict], carpeta: Path) -> Path:
    """Genera recorrido_visitas.kml para importar en Google Maps o Google Earth."""
    placemarks = []
    for idx, a in enumerate(avisos, start=1):
        if a.get("descartado"):
            continue
        lat_lng = zonas.obtener_coordenadas(a)
        if not lat_lng:
            continue
        lat, lng = lat_lng

        aid = a.get("id")
        score = a.get("score")
        dir_txt = html.escape(a.get("direccion") or "Sin dirección")
        barrio = html.escape(a.get("barrio") or "")
        costo = _plata(a.get("costo_mensual"))
        caja = _plata(a.get("caja_inicial_total"))
        m2 = a.get("m2_total") or "?"
        amb = a.get("ambientes") or "?"
        url = a.get("url") or "#"

        desc = (
            f"<![CDATA["
            f"<h3>#{idx} · Score {score} — {dir_txt}</h3>"
            f"<p><b>Costo mensual:</b> {costo} (Alquiler + Expensas)<br>"
            f"<b>Superficie:</b> {m2} m² · {amb} amb<br>"
            f"<b>Caja de entrada est.:</b> {caja}<br>"
            f"<b>Ubicación:</b> {barrio}<br>"
            f"<a href='{url}' target='_blank'>Ver en Zonaprop</a></p>"
            f"]]>"
        )

        pm = f"""
    <Placemark>
      <name>#{idx} [{score} pts] {dir_txt}</name>
      <description>{desc}</description>
      <Point>
        <coordinates>{lng},{lat},0</coordinates>
      </Point>
    </Placemark>"""
        placemarks.append(pm)

    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Candidatos - {html.escape(run)}</name>
    <description>Recorrido de propiedades candidatas para visitas presenciales.</description>
    {''.join(placemarks)}
  </Document>
</kml>
"""
    destino = carpeta / "recorrido_visitas.kml"
    destino.write_text(kml_content.strip(), encoding="utf-8")
    return destino

