#!/usr/bin/env python3
"""Scraper y ranking de alquileres de Zonaprop.

Subcomandos:
    buscar    recorre el listado y guarda todos los avisos de la búsqueda
    rankear   puntúa lo scrapeado por precio, m², expensas y señales del texto
    fotos     baja el detalle + las fotos del top N y arma las hojas de contacto
    dossier   arma la carpeta que le pasás a Claude para el análisis visual

Ejemplo completo:
    python zp.py buscar  --zona vicente-lopez --ambientes 1 2 --precio-max 900000
    python zp.py rankear --run vicente-lopez-1-2amb-alquiler --presupuesto 900000
    python zp.py fotos   --run vicente-lopez-1-2amb-alquiler --top 20
    python zp.py dossier --run vicente-lopez-1-2amb-alquiler
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from zp import fotos as mod_fotos
from zp import geocodificador, parseo, scoring, urls, zonas

# Playwright se importa recién cuando hace falta un navegador. `rankear`,
# `dossier`, `zonas` y `menu` trabajan sobre archivos ya bajados y tienen que
# poder correr aunque Playwright no esté instalado.


def _navegador():
    from zp.navegador import DesafioError, navegador
    return DesafioError, navegador

RAIZ = Path(__file__).parent
SALIDA = RAIZ / "salida"
PERFIL = RAIZ / ".perfil-chrome"

CAMPOS_CSV = [
    "score", "id", "tipo", "precio", "moneda",
    "expensas", "expensas_estimadas", "expensas_imputadas",
    "costo_mensual", "costo_m2", "costo_m2_ranking",
    "m2_total", "m2_cubierto", "m2_cubierto_estimado", "m2_confiable",
    "ambientes", "dormitorios", "banos", "cocheras",
    "antiguedad_anios", "antiguedad_label", "estado_unidad",
    "orientacion", "disposicion", "luminosidad", "direccion", "barrio",
    "latitude", "longitude", "entorno_tipo",
    "politica_mascotas", "ajuste_frecuencia", "ajuste_indice", "deposito_monto", "plazo_contrato",
    "es_dueno_directo", "caja_inicial_total", "caja_inicial_resumen",
    "baja_precio", "descuento_porcentaje", "alerta_gran_angular",
    "publicador", "dias_publicado", "es_duplicado", "disparidad_precio", "nota_negociacion",
    "riesgo_humedad", "fotos_totales", "descartado", "url",
]


# --------------------------------------------------------------------------- #
def cmd_buscar(args):
    zonas_list = args.zona if isinstance(args.zona, list) else [args.zona]
    run = args.run or urls.nombre_run(zonas_list, args.ambientes, args.operacion)
    carpeta = SALIDA / run
    carpeta.mkdir(parents=True, exist_ok=True)

    # Zonaprop a veces normaliza los rangos de ambientes, así que hacemos una
    # búsqueda por cada valor y unimos deduplicando por id.
    tandas = [[a] for a in args.ambientes] if args.ambientes else [None]
    encontrados: dict[str, dict] = {}
    DesafioError, navegador = _navegador()

    with navegador(PERFIL, headless=args.headless, lento=not args.rapido,
                   espera_desafio=args.espera_captcha,
                   canal=None if args.canal == "chromium" else args.canal) as ses:
        print(f"Navegador: {ses.canal}")
        ses.calentar()
        for zona_item in zonas_list:
            if len(zonas_list) > 1:
                print(f"\n--- [ZONA] Buscando en {zona_item} ({zonas_list.index(zona_item)+1}/{len(zonas_list)}) ---")
            for amb in tandas:
                for pagina in range(1, args.paginas + 1):
                    url = urls.construir_url(
                        zona_item, tipos=args.tipos, operacion=args.operacion,
                        ambientes=amb, pagina=pagina, precio_max=args.precio_max,
                    )
                    etiqueta = f"{zona_item} · {amb[0] if amb else 'todos'} amb · pág {pagina}"
                    try:
                        html = ses.ir(url, espera_selector='[data-qa="posting PROPERTY"]')
                    except DesafioError as e:
                        print(f"\n  {e}")
                        print(_ayuda_captcha(args.headless))
                        return 1
                    except RuntimeError as e:
                        print(f"  [{etiqueta}] {e}")
                        break

                    # Zonaprop no tira 404 con un slug inválido: devuelve otra zona
                    # o el país entero. Se verifica contra el h1 antes de guardar nada.
                    h1 = parseo.titulo_busqueda(html) or ""
                    ok, mensaje = zonas.validar_h1(zona_item, h1)
                    if not ok:
                        print(f"\n  ZONA INCORRECTA. {mensaje}")
                        print("  Corté la corrida para no guardarte avisos de otro lado.")
                        print("  Mirá `python zp.py zonas` para los slugs verificados.")
                        return 2
                    if mensaje:
                        print(f"  aviso: {mensaje}")

                    ses.scrollear()
                    html = ses.pagina.content()
                    avisos = parseo.parsear_listado(html)
                    if not avisos:
                        print(f"  [{etiqueta}] sin resultados, corto la paginación.")
                        break

                    nuevos = 0
                    for a in avisos:
                        if a.id not in encontrados:
                            encontrados[a.id] = a.dict()
                            nuevos += 1
                    total = parseo.total_resultados(html)
                    print(f"  [{etiqueta}] {len(avisos)} avisos ({nuevos} nuevos) · "
                          f"total de la búsqueda: {total}")
                    ses.esperar()

                    if total and pagina * 30 >= total:
                        break

    datos = list(encontrados.values())
    (carpeta / "listado.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(datos)} avisos únicos consolidados -> {carpeta / 'listado.json'}")
    return 0


# --------------------------------------------------------------------------- #
def cmd_rankear(args):
    carpeta = SALIDA / args.run
    datos = json.loads((carpeta / "listado.json").read_text(encoding="utf-8"))

    # Si ya existía un ranking con datos de detalle (antigüedad, orientación, disposición, descripción completa),
    # preservamos esos datos enriquecidos al re-rankear.
    if (carpeta / "ranking.json").exists():
        try:
            previos = {a["id"]: a for a in json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))}
            for d in datos:
                prev = previos.get(d["id"])
                if prev:
                    for k in ("antiguedad", "orientacion", "disposicion", "luminosidad",
                              "descripcion_completa", "fotos_totales", "fotos_final_galeria",
                              "amenities", "fecha_publicacion", "latitude", "longitude"):
                        if prev.get(k):
                            d[k] = prev[k]
        except Exception:
            pass

    ordenados = scoring.puntuar(datos, presupuesto=args.presupuesto, dolar=args.dolar)

    # Geocodificar avisos vivos (no descartados) que aún no tengan coordenadas
    vivos_sin_coords = [
        a for a in ordenados
        if not a.get("descartado") and (a.get("latitude") is None or a.get("longitude") is None)
    ]
    if vivos_sin_coords:
        total = len(vivos_sin_coords)
        resueltos = 0
        fallidos = 0
        hits_cache = 0
        try:
            for i, a in enumerate(vivos_sin_coords, 1):
                dir_txt = a.get("direccion") or ""
                barrio_txt = a.get("barrio") or ""
                en_cache = geocodificador.esta_en_cache(dir_txt, barrio_txt)
                if en_cache:
                    hits_cache += 1

                # Feedback de progreso: segundo a segundo si consulta Nominatim, o cada 10 si viene de caché
                if i == 1 or i == total or not en_cache or i % 10 == 0:
                    print(f"  Geocodificando {i}/{total}... (cache: {hits_cache})", flush=True)

                coords = geocodificador.obtener_coordenadas_reales(a)
                if coords:
                    a["latitude"] = coords[0]
                    a["longitude"] = coords[1]
                    resueltos += 1
                else:
                    fallidos += 1
        finally:
            geocodificador.guardar_cache()

        print(f"  Geocodificación: {resueltos} resueltos, {fallidos} fallaron ({hits_cache} desde caché)\n", flush=True)

    (carpeta / "ranking.json").write_text(
        json.dumps(ordenados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (carpeta / "ranking.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        w.writeheader()
        for a in ordenados:
            w.writerow(a)

    vivos = [a for a in ordenados if not a["descartado"]]
    print(f"{len(ordenados)} avisos · {len(vivos)} pasan los filtros duros\n")
    print(f"{'#':>2} {'score':>5} {'costo':>12} {'$/m²':>8} {'m²':>4}  aviso")
    for i, a in enumerate(vivos[:args.top], 1):
        print(f"{i:>2} {a['score']:>5.1f} {_plata(a['costo_mensual']):>12} "
              f"{_plata(a['costo_m2']):>8} {a.get('m2_total') or '-':>4}  "
              f"{(a.get('direccion') or a.get('barrio') or '')[:44]}")
    print(f"\n-> {carpeta / 'ranking.csv'}")
    return 0


# --------------------------------------------------------------------------- #
def cmd_fotos(args):
    carpeta = SALIDA / args.run
    ordenados = json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))
    objetivo = [a for a in ordenados if not a["descartado"]][:args.top]
    DesafioError, navegador = _navegador()
    print(f"Bajando detalle y fotos de {len(objetivo)} avisos...\n")

    with navegador(PERFIL, headless=args.headless, lento=not args.rapido,
                   espera_desafio=args.espera_captcha,
                   canal=None if args.canal == "chromium" else args.canal) as ses:
        ses.calentar()
        for i, a in enumerate(objetivo, 1):
            print(f"[{i}/{len(objetivo)}] {a['id']} · {(a.get('direccion') or '')[:50]}")
            try:
                html = ses.ir(a["url"])
            except DesafioError as e:
                print(f"\n  {e}")
                print(_ayuda_captcha(args.headless))
                break
            except RuntimeError as e:
                print(f"  ! {e}")
                continue

            detalle = parseo.parsear_detalle(html)
            a.update(detalle)

            todas = detalle.get("fotos", [])
            _, marcadas = mod_fotos.muestrear(todas, args.max_fotos)
            imgs = mod_fotos.descargar(todas, carpeta / "fotos" / a["id"],
                                       maximo=args.max_fotos)
            a["fotos_totales"] = len(todas)
            a["fotos_final_galeria"] = sorted(marcadas)
            titulo = (f"{a['id']} · {a.get('direccion') or a.get('barrio')} · "
                      f"{_plata(a.get('costo_mensual'))}/mes · {a.get('m2_total') or '?'} m² · "
                      f"{a.get('antiguedad') or '?'} años · {a.get('orientacion') or '?'}")
            mod_fotos.hoja_contacto(imgs, carpeta / "contactos" / f"{a['id']}.jpg", titulo,
                                    marcadas=marcadas)
            print(f"  {len(imgs)} fotos · antigüedad {a.get('antiguedad') or '?'} · "
                  f"orientación {a.get('orientacion') or '?'} · "
                  f"disposición {a.get('disposicion') or '?'}")
            ses.esperar()

    # Volvemos a puntuar: ahora tenemos antigüedad y orientación reales.
    ordenados = scoring.puntuar(ordenados, presupuesto=args.presupuesto, dolar=args.dolar)
    (carpeta / "ranking.json").write_text(
        json.dumps(ordenados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nHojas de contacto -> {carpeta / 'contactos'}")
    return 0


# --------------------------------------------------------------------------- #
def cmd_dossier(args):
    """Arma el markdown que acompaña a las fotos cuando se lo pasás a Claude."""
    carpeta = SALIDA / args.run
    ordenados = json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))
    con_fotos = [a for a in ordenados
                 if (carpeta / "contactos" / f"{a['id']}.jpg").exists()]
    if not con_fotos:
        print("(no hay hojas de contacto todavía; corré `fotos` primero. "
              "Armo el dossier con el top del ranking, sin imágenes.)")
        con_fotos = [a for a in ordenados if not a["descartado"]][:args.top]

    hay_fotos = (carpeta / "contactos").exists()
    lineas = [
        f"# Candidatos · {args.run}",
        "",
        f"{len(con_fotos)} avisos. Cada uno tiene una hoja de contacto en "
        "`contactos/<id>.jpg` con las fotos numeradas, y las fotos sueltas en "
        "`fotos/<id>/`."
        if hay_fotos else
        f"{len(con_fotos)} avisos, todavía sin fotos descargadas.",
        "",
        "## 📊 Matriz Resumen de Candidatos",
        "",
        "| # | Score | ID | Dirección | Tipo | Costo/mes | $/m² cub | Amb | Mascotas | Garantías | Caja Entrada Est. | Negociación |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for idx, a in enumerate(con_fotos, start=1):
        tipo_lbl = (a.get("tipo") or "dep").upper()
        dir_lbl = a.get("direccion") or "?"
        costo_lbl = _plata(a.get("costo_mensual"))
        m2_lbl = f"{_plata(a.get('costo_m2_ranking') or a.get('costo_m2'))}/m²"
        amb_lbl = str(a.get("ambientes") or "?")
        masc_lbl = "No" if "no acepta" in (a.get("politica_mascotas") or "").lower() else ("Sí" if "acepta" in (a.get("politica_mascotas") or "").lower() else "—")
        gar_lbl = "/".join(a.get("garantias_aceptadas") or ["Consultar"])[:22]
        caja_lbl = _plata(a.get("caja_inicial_total"))
        neg_lbl = "Duplicado" if a.get("es_duplicado") else ("Baja precio" if a.get("baja_precio") else ("Dueño dir." if a.get("es_dueno_directo") else "—"))
        lineas.append(
            f"| {idx} | **{a['score']}** | [{a['id']}](#{a['id']}--score-{str(a['score']).replace('.', '')}) | {dir_lbl} | {tipo_lbl} | {costo_lbl} | {m2_lbl} | {amb_lbl} | {masc_lbl} | {gar_lbl} | {caja_lbl} | {neg_lbl} |"
        )

    lineas += ["", "---", ""]

    for a in con_fotos:
        if not a.get("m2_confiable") and a.get("m2_cubierto_estimado"):
            linea_sup = (
                f"- **Superficie**: {a.get('m2_total') or '?'} m² tot "
                f"(~{a.get('m2_cubierto_estimado')} m² cubiertos, $/m² NO confiable por incluir terraza/patio) · "
                f"{a.get('ambientes') or '?'} amb · {a.get('dormitorios') or '?'} dorm · "
                f"{_plata(a.get('costo_m2'))}/m² (sobre cubierta: {_plata(a.get('costo_m2_ranking'))}/m²)"
            )
        else:
            linea_sup = (
                f"- **Superficie**: {a.get('m2_total') or '?'} m² · {a.get('ambientes') or '?'} amb · "
                f"{a.get('dormitorios') or '?'} dorm · {_plata(a.get('costo_m2'))}/m²"
            )

        if a.get("tipo") in ("ph", "casa") and not a.get("expensas_informadas"):
            exp_txt = "$0 (PH/casa sin expensas declaradas ni consorcio)"
        elif not a.get("expensas_imputadas"):
            exp_txt = f"declaradas por el aviso ({_plata(a.get('expensas'))})"
        else:
            exp_txt = f"NO declaradas, estimadas con la mediana de la búsqueda ({_plata(a.get('expensas_estimadas'))})"

        # Bloque estructurado YAML para ingesta determinística del LLM
        yaml_bloque = [
            "```yaml",
            f"id: \"{a['id']}\"",
            f"score: {a['score']}",
            f"tipo: \"{a.get('tipo', 'departamento')}\"",
            f"es_dueno_directo: {'true' if a.get('es_dueno_directo') else 'false'}",
            f"costo_mensual: {_plata(a.get('costo_mensual'))}",
            f"alquiler: \"{a.get('moneda', 'ARS')} {_plata(a.get('precio'))}\"",
            f"expensas: \"{exp_txt}\"",
            "superficie:",
            f"  total_declarada: {a.get('m2_total') or 'null'}",
            f"  cubierta_estimada: {a.get('m2_cubierto_estimado') or a.get('m2_total') or 'null'}",
            f"  confiable: {'true' if a.get('m2_confiable', True) else 'false'}",
            "caja_inicial_entrada:",
            f"  total_estimado: {_plata(a.get('caja_inicial_total'))}",
            f"  detalle: \"{a.get('caja_inicial_resumen', '')}\"",
            "contrato:",
            f"  garantias: \"{', '.join(a.get('garantias_aceptadas') or ['Consultar'])}\"",
            f"  mascotas: \"{a.get('politica_mascotas') or 'No especifica'}\"",
            f"  ajuste: \"{a.get('ajuste_frecuencia', 'No especifica')} ({a.get('ajuste_indice', 'No especifica')})\"",
            f"  deposito: \"{a.get('deposito_monto', 'No especifica')}\"",
            f"  plazo: \"{a.get('plazo_contrato', 'No especifica')}\"",
            f"  costos_extras: \"{', '.join(a.get('costos_adicionales') or ['Ninguno informado'])}\"",
            "ubicacion:",
            f"  direccion: \"{a.get('direccion') or '?'}\"",
            f"  barrio: \"{a.get('barrio') or '?'}\"",
            f"  entorno: \"{a.get('entorno_tipo') or 'Residencial'}\"",
            "mercado:",
            f"  dias_publicado: {a.get('dias_publicado') if a.get('dias_publicado') is not None else 'null'}",
            f"  baja_precio: {'true' if a.get('baja_precio') else 'false'}",
            f"  duplicados: {json.dumps(a.get('duplicados_ids') or [])}",
            "```",
            "",
        ]

        item_lineas = [
            f"## {a['id']} — score {a['score']}",
            "",
        ] + yaml_bloque + [
            f"- **Costo**: {_plata(a.get('costo_mensual'))}/mes "
            f"(alquiler {a.get('moneda')} {_plata(a.get('precio'))} + expensas {_plata(a.get('expensas'))})",
            f"- **Caja Inicial al firmar**: {a.get('caja_inicial_resumen') or 'Consultar'}",
            linea_sup,
            f"- **Edificio**: {a.get('antiguedad') or '?'} años · disposición "
            f"{a.get('disposicion') or '?'} · orientación {a.get('orientacion') or '?'} · "
            f"{a.get('luminosidad') or '?'}",
            f"- **Dónde**: {a.get('direccion') or '?'} — {a.get('barrio') or '?'}",
            f"- **A favor**: {', '.join(a.get('motivos_a_favor') or []) or '—'}",
            f"- **En contra**: {', '.join(a.get('motivos_en_contra') or []) or '—'}",
            f"- **Riesgo de humedad a priori**: {a.get('riesgo_humedad', 0)} "
            f"({', '.join(a.get('motivos_riesgo') or []) or 'sin señales'})",
            f"- **Expensas**: {exp_txt}",
        ]
        if a.get("nota_negociacion"):
            item_lineas.append(f"- **⚠️ Negociación / Duplicado**: {a.get('nota_negociacion')}")

        if a.get("preguntas_visita"):
            item_lineas.append("- **🔍 Preguntas clave para la visita presencial / LLM**:")
            for p in a["preguntas_visita"]:
                item_lineas.append(f"  - {p}")

        item_lineas += [
            _linea_fotos(a),
            f"- **Link**: {a.get('url')}",
            "",
        ] + _bloque_descripcion(a, args.max_descripcion) + [""]

        lineas += item_lineas

    destino = carpeta / "dossier.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")

    from zp import dashboard, mapa, prompt, visita
    prompt_file = prompt.generar_prompt_diagnostico(args.run, con_fotos, carpeta)
    dash_file = dashboard.generar_dashboard_html(args.run, ordenados, carpeta)
    ficha_file = visita.generar_ficha_visita(args.run, con_fotos, carpeta)
    pdf_file = carpeta / "ficha_visita.pdf"
    msg_file = visita.generar_mensajes_inmobiliarias(args.run, con_fotos, carpeta)
    geojson_file = mapa.exportar_geojson(args.run, ordenados, carpeta)
    kml_file = mapa.exportar_kml(args.run, ordenados, carpeta)

    print(f"-> {destino}")
    print(f"-> {prompt_file} (Prompt maestro para Claude/Gemini)")
    print(f"-> {dash_file} (Dashboard interactivo web con mapa Leaflet)")
    if pdf_file.exists():
        print(f"-> {pdf_file} (PDF listo para imprimir / llevar en celular)")
    print(f"-> {ficha_file} (Ficha forense imprimible para visitas)")
    print(f"-> {msg_file} (Mensajes prearmados para WhatsApp)")
    print(f"-> {kml_file} (Recorrido para Google Maps / Earth)")
    print(f"Pasale a Claude: {prompt_file} + {destino} + la carpeta {carpeta / 'contactos'}")
    return 0


def _bloque_descripcion(a: dict, tope: int = 0) -> list[str]:
    """El texto del aviso, entero.

    Acá había un `[:900]` que venía de cuando el dossier se pegaba a mano en un
    chat. Era el mismo error que cometía con las fotos: cortar la cola. En los
    avisos de Zonaprop el final es justo donde están los requisitos —garantía
    propietaria y de qué jurisdicción, mascotas, meses de adelanto y depósito,
    ajuste, honorarios—, que es lo que decide si un departamento es viable
    antes de ir a verlo. El score nunca se vio afectado (se calcula sobre el
    texto completo del ranking.json), pero al que lee el dossier le faltaba
    justo esa parte.

    El tope quedó como opción por si algún día hace falta, en 0 = sin límite.
    """
    completa = (a.get("descripcion_completa") or "").strip()
    texto = completa or (a.get("descripcion") or "").strip()
    if not texto:
        return ["> _(el aviso no trae descripción)_"]

    if tope and len(texto) > tope:
        texto = texto[:tope].rstrip() + " […recortado]"

    lineas = ["> " + l if l.strip() else ">"
              for l in texto.splitlines()]
    if not completa:
        # Zonaprop ya viene cortando el copete de la tarjeta; que quede claro
        # que lo que falta no lo cortamos nosotros.
        lineas.append(">")
        lineas.append("> _(copete de la tarjeta, cortado por Zonaprop. "
                      "El texto completo sale al correr `fotos`.)_")
    return lineas


def cmd_diff(args):
    """Compara dos corridas o la corrida actual contra una versión previa."""
    carpeta_a = SALIDA / args.run
    if not (carpeta_a / "ranking.json").exists():
        print(f"No existe ranking en {carpeta_a}")
        return 1

    avisos_a = {a["id"]: a for a in json.loads((carpeta_a / "ranking.json").read_text(encoding="utf-8"))}

    if args.vs:
        carpeta_b = SALIDA / args.vs
        if not (carpeta_b / "ranking.json").exists():
            print(f"No existe ranking en {carpeta_b}")
            return 1
        avisos_b = {a["id"]: a for a in json.loads((carpeta_b / "ranking.json").read_text(encoding="utf-8"))}
        nombre_b = args.vs
    else:
        # Si no hay otro run, comparar con listado.json
        if not (carpeta_a / "listado.json").exists():
            print("No hay historial para comparar.")
            return 1
        avisos_b = {a["id"]: a for a in json.loads((carpeta_a / "listado.json").read_text(encoding="utf-8"))}
        nombre_b = "listado base"

    ids_a = set(avisos_a.keys())
    ids_b = set(avisos_b.keys())

    nuevos = ids_a - ids_b
    salieron = ids_b - ids_a
    comunes = ids_a & ids_b

    print(f"\n--- [DIFF] Comparativa: {args.run} vs {nombre_b} ---")
    print(f"Avisos analizados: {len(ids_a)} (Nuevos: {len(nuevos)}, Salieron/Alquilados: {len(salieron)})")

    bajas = []
    subas = []
    for aid in comunes:
        pa = avisos_a[aid].get("precio")
        pb = avisos_b[aid].get("precio")
        if pa and pb and pa < pb:
            bajas.append((aid, pb, pa, pb - pa))
        elif pa and pb and pa > pb:
            subas.append((aid, pb, pa, pa - pb))

    if bajas:
        print(f"\n[-] {len(bajas)} Avisos con BAJA DE PRECIO:")
        for aid, pb, pa, diff in bajas:
            pct = round((diff / pb) * 100)
            print(f"  * ID {aid} ({avisos_a[aid].get('direccion', '?')}): {_plata(pb)} -> {_plata(pa)} (-{pct}%, ahorro {_plata(diff)})")

    if subas:
        print(f"\n[+] {len(subas)} Avisos con SUBAS de precio:")
        for aid, pb, pa, diff in subas:
            pct = round((diff / pb) * 100)
            print(f"  * ID {aid} ({avisos_a[aid].get('direccion', '?')}): {_plata(pb)} -> {_plata(pa)} (+{pct}%)")

    if nuevos:
        print(f"\n[NEW] {len(nuevos)} Nuevos avisos ingresados recientemente:")
        for aid in list(nuevos)[:5]:
            a = avisos_a[aid]
            print(f"  * ID {aid}: {a.get('direccion', '?')} ({_plata(a.get('costo_mensual'))}/mes · score {a.get('score')})")

    if salieron:
        print(f"\n[OUT] {len(salieron)} Avisos retirados / posiblemente alquilados:")
        for aid in list(salieron)[:5]:
            print(f"  * ID {aid}: {avisos_b[aid].get('direccion', '?')}")

    print("")
    return 0


def _ayuda_captcha(headless: bool) -> str:
    if headless:
        return ("  Estás corriendo en modo headless: la ventana no se ve, así que no hay\n"
                "  forma de tildar el casillero. Destildá 'Sin ventana del navegador' en\n"
                "  el menú (o sacá --headless) y resolvelo una vez a mano: la cookie queda\n"
                "  guardada en .perfil-chrome y después podés volver a headless.")
    return ("  Si no llegaste a tildarlo, volvé a correr el paso: la ventana se abre de\n"
            "  nuevo y la espera arranca otra vez. Si te pasa seguido, subí el margen con\n"
            "  --espera-captcha 600 y bajá --paginas.")


def _linea_fotos(a: dict) -> str:
    total = a.get("fotos_totales")
    if not total:
        return "- **Fotos**: todavía no descargadas (falta correr `fotos`)"
    finales = ", ".join(str(n) for n in a.get("fotos_final_galeria") or [])
    return (f"- **Fotos**: {total} en la galería. Mirar sí o sí las {finales}: "
            "son el final de la galería, donde suelen estar la fachada, el "
            "palier y el plano")


def cmd_zonas(args):
    if args.buscar:
        halladas = zonas.buscar(args.buscar)
        if not halladas:
            print(f"No encontré ninguna zona que coincida con '{args.buscar}'.")
            return 1
        for z in halladas:
            print(f"  {z.slug:<30} {z.nombre}  [{z.nivel}]")
            if z.nota:
                print(f"  {'':<30} └ {z.nota}")
    else:
        print(zonas.resumen())
        print("\nUsalos así:  python zp.py buscar --zona villa-martelli --ambientes 1 2")
    return 0


def cmd_menu(args):
    from zp.menu import abrir
    return abrir()


def _plata(v) -> str:
    if v is None:
        return "-"
    if v == 0:
        return "$0"
    return f"${v:,.0f}".replace(",", ".")


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def comunes(sp):
        sp.add_argument("--headless", action="store_true",
                        help="sin ventana (más rápido, pero Zonaprop lo detecta más)")
        sp.add_argument("--rapido", action="store_true",
                        help="sin pausas entre páginas (más riesgo de bloqueo)")
        sp.add_argument("--espera-captcha", type=int, default=240, metavar="SEG",
                        help="cuánto esperar a que resuelvas la verificación (default 240)")
        sp.add_argument("--canal", default="chrome",
                        help="navegador a usar: 'chrome' (el instalado, recibe menos "
                             "verificaciones) o 'chromium' (el de Playwright)")

    b = sub.add_parser("buscar", help="recorre el listado")
    b.add_argument("--zona", nargs="+", required=True,
                   help="una o varias zonas a rastrear (ej: --zona nunez belgrano colegiales)")
    b.add_argument("--ambientes", nargs="*", type=int, default=[2])
    b.add_argument("--tipos", nargs="*", default=["departamentos", "ph"])
    b.add_argument("--operacion", default="alquiler")
    b.add_argument("--paginas", type=int, default=5, help="máximo de páginas por búsqueda")
    b.add_argument("--precio-max", type=float, default=None, help="informativo; el filtro se aplica en rankear")
    b.add_argument("--run", default=None, help="nombre de la carpeta de salida")
    comunes(b)
    b.set_defaults(func=cmd_buscar)

    r = sub.add_parser("rankear", help="puntúa lo scrapeado")
    r.add_argument("--run", required=True)
    r.add_argument("--presupuesto", type=float, default=None, help="tope de alquiler + expensas")
    r.add_argument("--dolar", type=float, default=1450.0, help="cotización para pasar USD a ARS")
    r.add_argument("--top", type=int, default=20)
    r.set_defaults(func=cmd_rankear)

    f = sub.add_parser("fotos", help="detalle + fotos del top N")
    f.add_argument("--run", required=True)
    f.add_argument("--top", type=int, default=20)
    f.add_argument("--max-fotos", type=int, default=16)
    f.add_argument("--presupuesto", type=float, default=None)
    f.add_argument("--dolar", type=float, default=1450.0)
    comunes(f)
    f.set_defaults(func=cmd_fotos)

    d = sub.add_parser("dossier", help="arma el markdown para el análisis visual")
    d.add_argument("--run", required=True)
    d.add_argument("--top", type=int, default=20)
    d.add_argument("--max-descripcion", type=int, default=0, metavar="CHARS",
                   help="recortar la descripción a N caracteres (default 0 = entera)")
    d.set_defaults(func=cmd_dossier)

    z = sub.add_parser("zonas", help="lista las zonas verificadas y sus slugs")
    z.add_argument("--buscar", default=None, help="filtra por nombre")
    z.set_defaults(func=cmd_zonas)

    df = sub.add_parser("diff", help="compara dos corridas o busca bajas de precio")
    df.add_argument("--run", required=True, help="nombre de la corrida actual")
    df.add_argument("--vs", default=None, help="nombre de otra corrida con la cual comparar")
    df.set_defaults(func=cmd_diff)

    m = sub.add_parser("menu", help="abre el menú visual")
    m.set_defaults(func=cmd_menu)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
