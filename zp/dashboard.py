"""Dashboard HTML (resumen.html y tablero.html): la pantalla para decidir.

Una tarjeta por aviso, pensada para leerse en el celular yendo a una visita:
lo que decide arriba (costo, veredicto del auditor, garantía, novedades) y el
resto plegado. Además:

  - El estado de seguimiento (★, contactado, visita, descartado) se marca con
    botones y queda guardado en el navegador; "Exportar seguimiento" baja el
    archivo para pasárselo al programa con `python zp.py seguir --importar`.
  - Los descartados a mano y las publicaciones más caras de una propiedad
    duplicada se ocultan por defecto (un clic los vuelve a mostrar).
  - Arriba de todo, qué cambió desde la búsqueda anterior.

Es HTML estático: no hay servidor, por eso el seguimiento vive en
localStorage hasta que se exporta.
"""

from __future__ import annotations

import html
import json
import urllib.parse
from pathlib import Path

from zp import perfil
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
# Después se usó CARTO (dark_all), y en noviembre de 2026 empezó a devolver
# tiles con "API KEY REQUIRED" sobre todo el mapa. Esri World Street Map anda
# sin clave (verificado abriendo el dashboard en Chrome) y trae nombres de
# calles, que es lo que sirve para ubicar un aviso.
#
# Se puede cambiar por cualquier otro proveedor de tiles raster; sólo hay que
# actualizar la atribución junto con la URL.
TILES_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
             "World_Street_Map/MapServer/tile/{z}/{y}/{x}")
TILES_ATRIBUCION = (
    'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, USGS, '
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
)
TILES_MAX_ZOOM = 19

CLASE_VEREDICTO = {
    "APROBADO": "v-ok",
    "CON_RESERVAS": "v-reserva",
    "DESCARTADO": "v-mal",
}
TEXTO_VEREDICTO = {
    "APROBADO": "✔ Aprobado",
    "CON_RESERVAS": "⚠ Con reservas",
    "DESCARTADO": "✖ Descartado por IA",
}


def _coords(a: dict) -> tuple[float, float] | None:
    """Sólo las coordenadas ya guardadas: el dashboard no sale a la red.

    Antes llamaba al geocodificador, que podía consultar Nominatim por cada
    aviso sin coordenadas mientras se armaba el HTML.
    """
    crudo_lat, crudo_lng = a.get("latitude"), a.get("longitude")
    if crudo_lat is None or crudo_lng is None:
        return None
    try:
        lat, lng = float(crudo_lat), float(crudo_lng)
    except (TypeError, ValueError):
        return None
    if lat and lng and -90 <= lat <= 90 and -180 <= lng <= 180:
        return round(lat, 6), round(lng, 6)
    return None


def _mensaje_whatsapp(a: dict) -> str:
    tipo = (a.get("tipo") or "departamento")
    amb = a.get("ambientes")
    desc = f"el {tipo} de {amb} ambientes" if amb else f"el {tipo}"
    msg = (f"Hola! Te consulto por {desc} en {a.get('direccion') or ''} "
           f"(Ref Zonaprop #{a.get('id')}). ¿Sigue disponible? "
           f"Cuento con {perfil.describir_garantias()} y recibos de sueldo.")
    pregunta = (a.get("auditoria") or {}).get("pregunta_para_inmobiliaria")
    if pregunta:
        msg += f" Una consulta: {pregunta}"
    msg += " ¿Qué días y horarios tienen para coordinar una visita? Gracias!"
    return msg


def _ocultar_duplicados_caros(vivos: list[dict]) -> set[str]:
    """Ids de las publicaciones más caras de una propiedad que está publicada
    más barata en otra tarjeta de la misma lista."""
    por_id = {str(a["id"]): a for a in vivos}
    ocultos = set()
    for a in vivos:
        if not a.get("es_duplicado") or a.get("costo_mensual") is None:
            continue
        hermanos = [por_id[str(i)] for i in a.get("duplicados_ids") or [] if str(i) in por_id]
        for h in hermanos:
            ch = h.get("costo_mensual")
            if ch is None:
                continue
            # Más caro, o igual de caro pero con id mayor (para no ocultar los dos).
            if ch < a["costo_mensual"] or (ch == a["costo_mensual"] and str(h["id"]) < str(a["id"])):
                ocultos.add(str(a["id"]))
                break
    return ocultos


def _bloque_novedades(nov: dict | None, por_id: dict[str, dict], seguidos: set[str]) -> str:
    if not nov:
        return ""
    partes = [f"<strong>Desde la búsqueda del {nov['anterior']}</strong> (última: {nov['actual']}):"]
    items = []
    if nov["nuevos"]:
        items.append(f"<li><span class='badge badge-nuevo'>NUEVO</span> {len(nov['nuevos'])} avisos nuevos</li>")
    if nov["bajas"]:
        detalle = ", ".join(
            f"{html.escape((por_id.get(b['id']) or {}).get('direccion') or b['id'])} ({b['pct']}%)"
            for b in sorted(nov["bajas"], key=lambda b: b["pct"])[:6]
        )
        items.append(f"<li><span class='badge badge-green'>BAJÓ</span> {len(nov['bajas'])} bajaron de precio: {detalle}</li>")
    if nov["subas"]:
        items.append(f"<li>{len(nov['subas'])} subieron de precio</li>")
    if nov["retirados"]:
        seg = [r for r in nov["retirados"] if r["id"] in seguidos]
        txt = f"{len(nov['retirados'])} ya no están publicados"
        if seg:
            nombres = ", ".join(html.escape(r.get("direccion") or r["id"]) for r in seg[:5])
            txt += f" — <strong>incluye {len(seg)} que seguías: {nombres}</strong>"
        items.append(f"<li><span class='badge badge-gray'>RETIRADO</span> {txt}</li>")
    elif not nov.get("completa"):
        items.append("<li>La última búsqueda no terminó completa: no se puede saber qué se retiró.</li>")
    if not items:
        items.append("<li>Sin cambios.</li>")
    return f"<section class='novedades'>{partes[0]}<ul>{''.join(items)}</ul></section>"


def _tarjeta(a: dict, rank: int, carpeta: Path, multi: bool, ocultos: set[str],
             nuevos: set[str]) -> tuple[str, dict | None]:
    aid = str(a.get("id"))
    prefijo = f"{a['_run']}/" if multi and a.get("_run") else ""
    tipo = (a.get("tipo") or "departamento").upper()
    direccion = html.escape(a.get("direccion") or "Sin dirección")
    barrio = html.escape(a.get("barrio") or "")
    score = a.get("score", 0)
    costo = _plata(a.get("costo_mensual"))
    alquiler = f"{a.get('moneda', 'ARS')} {_plata(a.get('precio'))}"
    exp = _plata(a.get("expensas") or a.get("expensas_estimadas"))
    m2_tot = a.get("m2_total") or "?"
    amb = a.get("ambientes") or "?"
    dorm = a.get("dormitorios") or "?"
    costo_m2 = _plata(a.get("costo_m2"))
    url = a.get("url") or "#"
    ruta_contacto = f"{prefijo}contactos/{aid}.jpg"
    hay_hoja = (carpeta / ruta_contacto).exists()

    # ---- badges
    badges = []
    aud = a.get("auditoria")
    if aud:
        cls = CLASE_VEREDICTO.get(aud.get("veredicto"), "v-reserva")
        quien = "Opus" if aud.get("etapa") == "segunda" else "Sonnet"
        badges.append(f'<span class="badge {cls}" title="{quien}, {html.escape(aud.get("fecha") or "")[:10]}">'
                      f'{TEXTO_VEREDICTO.get(aud.get("veredicto"), aud.get("veredicto"))} · visual {aud.get("score_visual")}</span>')
    if aid in nuevos:
        badges.append('<span class="badge badge-nuevo">NUEVO</span>')
    if a.get("baja_precio"):
        badges.append(f'<span class="badge badge-green">📉 -{a.get("descuento_porcentaje")}%</span>')
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
    if not a.get("m2_confiable", True):
        badges.append('<span class="badge badge-orange">TERRAZA</span>')
    bp_dist = a.get("barrio_popular_distancia_m")
    if bp_dist is not None and bp_dist <= 600:
        badges.append(f'<span class="badge badge-renabap">barrio popular a {bp_dist} m</span>')

    # ---- contrato
    garantias = a.get("garantias_aceptadas") or ["Consultar"]
    gar_txt = html.escape(", ".join(garantias))
    if a.get("garantia_compatible") is True:
        gar_txt += ' <span class="ok">✓ la tenés</span>'
    mascotas = html.escape(a.get("politica_mascotas") or "No especifica")
    dias = a.get("dias_publicado")
    dias_html = f" · publicado hace {dias} días" if dias is not None else ""

    # ---- auditoría
    aud_html = ""
    aud_detalle = ""
    if aud:
        vicio = (f"<div class='vicio'>Vicio crítico: {html.escape(aud['vicio_critico'])}</div>"
                 if aud.get("vicio_critico") else "")
        aud_html = f"<div class='ia'>🤖 {html.escape(aud.get('resumen') or '')}{vicio}</div>"
        hall = "".join(
            f"<li><a href='{prefijo}fotos/{aid}/{h['foto']:02d}.jpg' target='_blank'>Foto {h['foto']}</a> "
            f"({html.escape(h['tipo'])}, {html.escape(h['gravedad'])}): {html.escape(h['observacion'])}</li>"
            for h in aud.get("hallazgos") or []
        )
        contra = "".join(f"<li>{html.escape(c)}</li>" for c in aud.get("contradicciones") or [])
        neg = f"<h4>Negociación</h4><p>{html.escape(aud['negociacion'])}</p>" if aud.get("negociacion") else ""
        aud_detalle = (
            "<h4>🤖 Auditoría de fotos</h4>"
            + (f"<ul>{hall}</ul>" if hall else "<p>Sin hallazgos en las fotos.</p>")
            + (f"<h4>Contradicciones texto / fotos</h4><ul>{contra}</ul>" if contra else "")
            + neg
        )

    preguntas = list(a.get("preguntas_visita") or [])
    if aud:
        preguntas = list(aud.get("preguntas_visita") or []) + preguntas
    preguntas_li = "".join(f"<li>{html.escape(p)}</li>" for p in preguntas)
    favor = "".join(f"<li>{html.escape(m)}</li>" for m in a.get("motivos_a_favor") or [])
    contra_txt = "".join(f"<li>{html.escape(m)}</li>" for m in a.get("motivos_en_contra") or [])
    bp_html = (f"<h4>🏘️ Barrio popular (RENABAP)</h4><p>{html.escape(a['barrio_popular'])}</p>"
               if a.get("barrio_popular") else "")

    nota_dup = ""
    if a.get("es_duplicado") and a.get("disparidad_precio") and aid not in ocultos:
        nota_dup = f"<div class='sub-text'>{html.escape(a.get('nota_negociacion') or '')}</div>"

    wa_link = f"https://api.whatsapp.com/send?text={urllib.parse.quote(_mensaje_whatsapp(a))}"
    btn_fotos = (f'<a href="{ruta_contacto}" target="_blank" class="btn btn-primary">Fotos 🖼️</a>'
                 if hay_hoja else "")
    zona_html = f"<div class='sub-text'>Búsqueda: {html.escape(a['_run'])}</div>" if multi and a.get("_run") else ""

    coords = _coords(a)
    clases = ["card"]
    if aid in ocultos:
        clases.append("dup-caro")
    if aud and aud.get("veredicto"):
        clases.append("ia-" + aud["veredicto"].lower())
    if aid in nuevos:
        clases.append("es-nuevo")
    if a.get("baja_precio"):
        clases.append("es-baja")

    tarjeta = f"""
<article class="{' '.join(clases)}" id="card-{aid}" data-id="{aid}" data-rank="{rank}"
  {f'data-lat="{coords[0]}" data-lng="{coords[1]}"' if coords else ''}>
  <header class="card-head">
    <span class="rank">#{rank}</span>
    <span class="score-pill" title="score del ranking">{score}</span>
    <span class="estado" data-estado-de="{aid}"></span>
    <div class="titulo"><strong>{direccion}</strong><div class="sub-text">{barrio}</div>{zona_html}</div>
  </header>
  <div class="badge-container">{' '.join(badges)}</div>
  {aud_html}
  <div class="datos">
    <div><span class="costo-main">{costo}</span><div class="sub-text">Alq {alquiler} · Exp {exp}</div></div>
    <div><span>{m2_tot} m² · {amb} amb · {dorm} dorm</span><div class="sub-text">{costo_m2}/m²</div></div>
    <div><span class="caja-main">{_plata(a.get('caja_inicial_total'))}</span><div class="sub-text">caja de entrada est.</div></div>
  </div>
  <div class="contrato"><strong>Garantía:</strong> {gar_txt}<br><strong>Mascotas:</strong> {mascotas}{dias_html}</div>
  {nota_dup}
  <div class="acciones">
    <a href="{url}" target="_blank" class="btn btn-outline">Zonaprop ↗</a>
    {btn_fotos}
    <a href="{wa_link}" target="_blank" class="btn btn-wa">WhatsApp 💬</a>
    <button class="btn btn-seg" data-accion="favorito" data-id="{aid}">★</button>
    <button class="btn btn-seg" data-accion="contactado" data-id="{aid}">Contacté</button>
    <button class="btn btn-seg" data-accion="visita" data-id="{aid}">Visita</button>
    <button class="btn btn-seg" data-accion="visitado" data-id="{aid}">Visité</button>
    <button class="btn btn-seg btn-x" data-accion="descartado" data-id="{aid}">✕</button>
    {f'<button class="btn btn-outline" data-mapa="{aid}">Mapa</button>' if coords else ''}
  </div>
  <details>
    <summary>Más detalle</summary>
    <div class="details-grid">
      <div>
        {aud_detalle}
        <h4>A favor</h4><ul>{favor or '<li>—</li>'}</ul>
        <h4>En contra</h4><ul>{contra_txt or '<li>—</li>'}</ul>
      </div>
      <div>
        <h4>🔍 Para preguntar en la visita</h4><ul>{preguntas_li or '<li>—</li>'}</ul>
        <h4>💰 Caja inicial</h4><p>{html.escape(a.get('caja_inicial_resumen') or '-')}</p>
        <h4>📈 Cuota a 24 meses (IPC 3% proyectado)</h4><p>{html.escape(a.get('proyeccion_resumen') or 'No calculada')}</p>
        <h4>📍 Entorno</h4><p>{html.escape(a.get('entorno_tipo') or '')}</p>
        {bp_html}
        <p class="nota-seg" data-nota-de="{aid}"></p>
      </div>
    </div>
  </details>
</article>"""

    punto = None
    if coords:
        punto = {
            "id": aid, "rank": rank, "score": score,
            "direccion": a.get("direccion") or "Sin dirección",
            "costo": costo, "m2": f"{m2_tot} m²", "url": url,
            "contacto": ruta_contacto if hay_hoja else None,
            "lat": coords[0], "lng": coords[1],
            "bp_dist_txt": f"Barrio popular a {bp_dist} m (RENABAP)" if bp_dist is not None else "",
            "veredicto": (aud or {}).get("veredicto"),
        }
    return tarjeta, punto


def generar_dashboard_html(run: str, avisos: list[dict], carpeta: Path,
                           novedades: dict | None = None,
                           seguimiento_inicial: dict | None = None,
                           nombre_archivo: str = "resumen.html",
                           multi: bool = False) -> Path:
    """Genera el dashboard. `multi=True` es el tablero de todas las zonas:
    cada aviso trae `_run` y los links a fotos se arman relativos a salida/."""
    vivos = [a for a in avisos if not a.get("descartado")]
    por_id = {str(a.get("id")): a for a in avisos}
    ocultos = _ocultar_duplicados_caros(vivos)
    nuevos = set((novedades or {}).get("nuevos") or [])
    seguimiento_inicial = seguimiento_inicial or {}

    tarjetas, puntos = [], []
    for idx, a in enumerate(vivos, start=1):
        t, p = _tarjeta(a, idx, carpeta, multi, ocultos, nuevos)
        tarjetas.append(t)
        if p:
            puntos.append(p)

    auditados = sum(1 for a in vivos if a.get("auditoria"))
    aprobados = sum(1 for a in vivos if (a.get("auditoria") or {}).get("veredicto") == "APROBADO")
    subtitulo = (f"{len(vivos)} avisos que pasan los filtros · {len(ocultos)} duplicados más caros ocultos"
                 + (f" · {auditados} auditados con IA ({aprobados} aprobados)" if auditados else ""))
    if multi:
        subtitulo += (" · Los scores de búsquedas distintas no son comparables entre sí: "
                      "cada uno se mide contra la mediana de su propia búsqueda.")

    mapa = '<div id="map"></div>' if puntos else (
        '<div class="map-hint">📍 Sin coordenadas todavía: se cargan al correr <code>rankear</code>.</div>'
    )

    def _json_en_script(datos) -> str:
        # Un motivo de descarte o una dirección con "</script>" cerraría el
        # bloque de JS antes de tiempo. "<\/" es equivalente dentro del JSON.
        return json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")

    doc = (_PLANTILLA
           .replace("__TITULO__", html.escape(("Tablero · " if multi else "Candidatos · ") + run))
           .replace("__SUBTITULO__", html.escape(subtitulo))
           .replace("__NOVEDADES__", _bloque_novedades(novedades, por_id, set(seguimiento_inicial)))
           .replace("__MAPA__", mapa)
           .replace("__TARJETAS__", "\n".join(tarjetas))
           .replace("__CSS__", _CSS)
           .replace("__JS__", _JS
                    .replace("__PUNTOS__", _json_en_script(puntos))
                    .replace("__SEGUIMIENTO__", _json_en_script(seguimiento_inicial))
                    .replace("__TILES_URL__", TILES_URL)
                    .replace("__TILES_ATRIB__", TILES_ATRIBUCION.replace("'", "\\'"))
                    .replace("__TILES_ZOOM__", str(TILES_MAX_ZOOM))))

    # Igual que fotos.py, historial.py y el caché del geocodificador: el que
    # escribe se asegura de que la carpeta exista, en vez de depender de que el
    # que llama la haya creado antes.
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombre_archivo
    destino.write_text(doc.strip(), encoding="utf-8")
    return destino


_PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>__TITULO__</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
  <style>__CSS__</style>
</head>
<body>
  <div class="container">
    <header class="top">
      <h1>__TITULO__</h1>
      <div class="subtitle">__SUBTITULO__</div>
    </header>
    __NOVEDADES__
    <nav class="filtros">
      <button class="chip activo" data-filtro="todos">Todos</button>
      <button class="chip" data-filtro="favorito">★ Favoritos</button>
      <button class="chip" data-filtro="aprobado">✔ Aprobados IA</button>
      <button class="chip" data-filtro="nuevo">Nuevos</button>
      <button class="chip" data-filtro="baja">Bajaron</button>
      <label class="toggle"><input type="checkbox" id="ver-descartados"> ver descartados por mí</label>
      <label class="toggle"><input type="checkbox" id="ver-duplicados"> ver duplicados más caros</label>
      <button class="chip" id="exportar">⬇ Exportar seguimiento</button>
    </nav>
    __MAPA__
    <main id="lista">
__TARJETAS__
    </main>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>__JS__</script>
</body>
</html>
"""

_CSS = """
:root {
  --bg: #0f172a; --card-bg: #1e293b; --border: #334155; --text: #f8fafc;
  --text-muted: #94a3b8; --primary: #38bdf8; --primary-hover: #0284c7;
  --accent: #f59e0b; --success: #10b981; --danger: #ef4444;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       background: var(--bg); color: var(--text); padding: 16px; line-height: 1.45; }
.container { max-width: 1100px; margin: 0 auto; }
header.top { margin-bottom: 12px; }
h1 { font-size: 24px; font-weight: 700; color: #fff; }
.subtitle { color: var(--text-muted); font-size: 13px; }
.novedades { background: #172554; border: 1px solid #1e40af; border-radius: 10px; padding: 10px 14px;
             margin-bottom: 12px; font-size: 14px; }
.novedades ul { margin: 6px 0 0 18px; }
.filtros { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 12px; }
.chip { background: var(--card-bg); color: var(--text); border: 1px solid var(--border); border-radius: 999px;
        padding: 5px 12px; font-size: 13px; cursor: pointer; }
.chip.activo { background: var(--primary); color: #0f172a; border-color: var(--primary); font-weight: 700; }
.toggle { font-size: 13px; color: var(--text-muted); }
#map { height: 340px; width: 100%; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 12px; z-index: 1; }
.map-hint { color: var(--text-muted); margin-bottom: 12px; font-size: 13px; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; margin-bottom: 10px; }
.card.seg-favorito { border-color: #facc15; box-shadow: 0 0 0 1px #facc15 inset; }
.card.seg-descartado { opacity: .55; }
.card.oculto { display: none; }
.card-head { display: flex; align-items: flex-start; gap: 8px; }
.titulo { flex: 1; }
.rank { color: var(--text-muted); font-weight: 700; font-size: 14px; padding-top: 2px; }
.score-pill { background: rgba(56,189,248,.15); color: var(--primary); font-weight: 700; padding: 2px 9px;
              border-radius: 999px; font-size: 14px; border: 1px solid rgba(56,189,248,.3); }
.estado:not(:empty) { background: #422006; color: #fde68a; font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
.sub-text { font-size: 12px; color: var(--text-muted); }
.badge-container { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; }
.badge { font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
.badge-blue { background: #1e3a8a; color: #93c5fd; } .badge-purple { background: #4c1d95; color: #c4b5fd; }
.badge-gray { background: #334155; color: #cbd5e1; }
.badge-emerald { background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }
.badge-amber { background: #78350f; color: #fde68a; }
/* Cercanía a un barrio popular del RENABAP. Clase propia y no badge-amber,
   que ya la usa DUPLICADO: son dos cosas distintas y con el mismo color no
   se distinguen de un vistazo. */
.badge-renabap { background: #422006; color: #fcd34d; border: 1px solid #a16207; }
.badge-green { background: #065f46; color: #a7f3d0; } .badge-orange { background: #7c2d12; color: #fed7aa; }
.badge-nuevo { background: #1d4ed8; color: #dbeafe; }
.v-ok { background: #14532d; color: #bbf7d0; border: 1px solid #22c55e; }
.v-reserva { background: #713f12; color: #fef08a; border: 1px solid #eab308; }
.v-mal { background: #7f1d1d; color: #fecaca; border: 1px solid #ef4444; }
.ia { background: #0b1324; border-left: 3px solid var(--primary); padding: 6px 10px; font-size: 13px; margin: 6px 0; border-radius: 4px; }
.vicio { color: #fca5a5; font-weight: 600; margin-top: 2px; }
.datos { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 6px 0; font-size: 14px; }
.costo-main { font-size: 17px; font-weight: 700; color: #fff; }
.caja-main { font-weight: 600; color: #fbbf24; }
.contrato { font-size: 13px; color: #cbd5e1; }
.ok { color: #4ade80; font-weight: 700; }
.acciones { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.btn { display: inline-block; padding: 6px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;
       text-decoration: none; text-align: center; border: 1px solid transparent; cursor: pointer; font-family: inherit; }
.btn-primary { background: var(--primary); color: #0f172a; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text); }
.btn-wa { background: #15803d; color: #f0fdf4; }
.btn-seg { background: #0b1324; color: var(--text); border-color: var(--border); }
.btn-seg.marcado { background: #facc15; color: #0f172a; }
.btn-x.marcado { background: var(--danger); color: #fff; }
details { margin-top: 8px; font-size: 13px; }
summary { cursor: pointer; color: var(--primary); }
.details-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 6px; }
.details-grid h4 { font-size: 12px; color: var(--primary); margin-top: 8px; text-transform: uppercase; }
.details-grid ul { margin-left: 18px; color: #cbd5e1; }
.details-grid a { color: var(--primary); }
.nota-seg:not(:empty) { margin-top: 8px; color: #fde68a; }
@media (max-width: 700px) {
  body { padding: 10px; }
  h1 { font-size: 19px; }
  #map { height: 240px; }
  .datos { grid-template-columns: 1fr 1fr; }
  .details-grid { grid-template-columns: 1fr; }
  .btn { padding: 8px 10px; }
}
"""

_JS = """
const PUNTOS = __PUNTOS__;
const SEG_ARCHIVO = __SEGUIMIENTO__;
const CLAVE = 'zp-seguimiento';
const ETIQUETAS = {favorito: '★ Favorito', contactado: 'Contactado', visita: 'Visita agendada',
                   visitado: 'Visitado', descartado: 'Descartado'};

function leerLocal() {
  try { return JSON.parse(localStorage.getItem(CLAVE) || '{}'); } catch (e) { return {}; }
}
function guardarLocal(d) {
  try { localStorage.setItem(CLAVE, JSON.stringify(d)); } catch (e) { console.warn('no se pudo guardar', e); }
}
// Gana lo más nuevo entre el archivo (lo que ya sabe el programa) y el navegador.
function seguimiento() {
  const local = leerLocal(), todo = Object.assign({}, SEG_ARCHIVO);
  for (const [id, e] of Object.entries(local)) {
    if (!todo[id] || (e.fecha || '') > (todo[id].fecha || '')) todo[id] = e;
  }
  return todo;
}

let filtro = 'todos';
function aplicar() {
  const seg = seguimiento();
  const verDesc = document.getElementById('ver-descartados').checked;
  const verDup = document.getElementById('ver-duplicados').checked;
  const cards = Array.from(document.querySelectorAll('.card'));
  for (const c of cards) {
    const id = c.dataset.id, e = seg[id] || {}, est = e.estado;
    c.classList.remove('seg-favorito', 'seg-descartado');
    if (est) c.classList.add('seg-' + est);
    const etq = c.querySelector('[data-estado-de]');
    etq.textContent = est ? (ETIQUETAS[est] || est) + (e.visita ? ' · ' + e.visita : '') : '';
    const nota = c.querySelector('[data-nota-de]');
    if (nota) nota.textContent = [e.motivo, e.nota].filter(Boolean).join(' — ');
    c.querySelectorAll('.btn-seg').forEach(b => b.classList.toggle('marcado', b.dataset.accion === est));
    let ver = true;
    if (est === 'descartado' && !verDesc) ver = false;
    if (c.classList.contains('dup-caro') && !verDup) ver = false;
    if (filtro === 'favorito' && est !== 'favorito') ver = false;
    if (filtro === 'aprobado' && !c.classList.contains('ia-aprobado')) ver = false;
    if (filtro === 'nuevo' && !c.classList.contains('es-nuevo')) ver = false;
    if (filtro === 'baja' && !c.classList.contains('es-baja')) ver = false;
    c.classList.toggle('oculto', !ver);
  }
  // Favoritos primero; el resto en el orden del ranking.
  const lista = document.getElementById('lista');
  cards.sort((a, b) => {
    const fa = (seg[a.dataset.id] || {}).estado === 'favorito' ? 0 : 1;
    const fb = (seg[b.dataset.id] || {}).estado === 'favorito' ? 0 : 1;
    return fa - fb || (+a.dataset.rank) - (+b.dataset.rank);
  }).forEach(c => lista.appendChild(c));
}

function marcar(id, estado) {
  const local = leerLocal(), actual = seguimiento()[id] || {};
  if (actual.estado === estado) {
    // Tocar de nuevo el mismo botón lo desmarca.
    local[id] = {estado: null, fecha: new Date().toISOString().slice(0, 19)};
  } else {
    const e = {estado: estado, fecha: new Date().toISOString().slice(0, 19)};
    if (estado === 'descartado') {
      const m = window.prompt('¿Por qué lo descartás? (queda anotado)', actual.motivo || '');
      if (m === null) return;
      e.motivo = m;
    }
    if (estado === 'visita') {
      const v = window.prompt('¿Cuándo es la visita? (ej: jueves 18 hs)', actual.visita || '');
      if (v === null) return;
      e.visita = v;
    }
    if (estado === 'visitado') {
      const n = window.prompt('Notas de la visita (luz, ruido, humedad, impresión)', actual.nota || '');
      if (n === null) return;
      e.nota = n;
    }
    local[id] = Object.assign({}, actual, e);
  }
  guardarLocal(local);
  aplicar();
}

document.addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (!b) return;
  if (b.dataset.accion) marcar(b.dataset.id, b.dataset.accion);
  if (b.dataset.filtro) {
    filtro = b.dataset.filtro;
    document.querySelectorAll('.chip[data-filtro]').forEach(x => x.classList.toggle('activo', x === b));
    aplicar();
  }
  if (b.dataset.mapa) enfocar(b.dataset.mapa);
  if (b.id === 'exportar') {
    // Los desmarcados viajan con estado null para que el programa también los borre.
    const datos = seguimiento();
    const blob = new Blob([JSON.stringify(datos, null, 2)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'seguimiento.json';
    a.click();
  }
});
document.getElementById('ver-descartados').addEventListener('change', aplicar);
document.getElementById('ver-duplicados').addEventListener('change', aplicar);

let map = null; const markers = {};
if (PUNTOS.length > 0 && window.L) {
  map = L.map('map').setView([PUNTOS[0].lat, PUNTOS[0].lng], 14);
  L.tileLayer('__TILES_URL__', {attribution: '__TILES_ATRIB__', maxZoom: __TILES_ZOOM__}).addTo(map);
  const bounds = [];
  PUNTOS.forEach(p => {
    bounds.push([p.lat, p.lng]);
    const color = p.veredicto === 'APROBADO' ? '#22c55e' : p.veredicto === 'DESCARTADO' ? '#ef4444'
                : p.veredicto === 'CON_RESERVAS' ? '#eab308'
                : (p.score >= 70 ? '#10b981' : (p.score >= 50 ? '#f59e0b' : '#64748b'));
    const m = L.circleMarker([p.lat, p.lng], {radius: 9, fillColor: color, color: '#fff', weight: 2, opacity: 1, fillOpacity: .9}).addTo(map);
    const fotos = p.contacto ? ` | <a href="${p.contacto}" target="_blank">Fotos</a>` : '';
    const bp = p.bp_dist_txt ? `<br><span style="color:#64748b;font-size:11px">${p.bp_dist_txt}</span>` : '';
    m.bindPopup(`<div style="font-size:13px"><strong>#${p.rank} · Score ${p.score}</strong><br><b>${p.direccion}</b><br>${p.costo} · ${p.m2}${bp}<br><a href="${p.url}" target="_blank">Zonaprop</a>${fotos} | <a href="#card-${p.id}">Ver tarjeta</a></div>`);
    markers[p.id] = m;
  });
  if (bounds.length > 1) map.fitBounds(bounds, {padding: [30, 30]});
}
function enfocar(id) {
  if (map && markers[id]) {
    map.setView(markers[id].getLatLng(), 16, {animate: true});
    markers[id].openPopup();
    document.getElementById('map').scrollIntoView({behavior: 'smooth'});
  }
}
aplicar();
"""
