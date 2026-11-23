#!/usr/bin/env python3
"""Scraper y ranking de alquileres de Zonaprop.

Subcomandos:
    buscar    recorre el listado y guarda todos los avisos de la búsqueda
    rankear   puntúa lo scrapeado por precio, m², expensas y señales del texto
    fotos     baja el detalle + las fotos del top N y arma las hojas de contacto
    auditar   le pasa fotos y texto de cada aviso a Claude y guarda el veredicto
    dossier   arma el dashboard, la ficha de visita y los mensajes
    diff      qué cambió desde la búsqueda anterior (o contra otra corrida)
    seguir    marca un aviso como favorito, contactado, visita, descartado...
    tablero   un solo dashboard con todas las búsquedas

Ejemplo completo:
    python zp.py buscar  --zona vicente-lopez --ambientes 1 2
    python zp.py rankear --run vicente-lopez-1-2amb-alquiler --presupuesto 900000
    python zp.py fotos   --run vicente-lopez-1-2amb-alquiler --top 20
    python zp.py auditar --run vicente-lopez-1-2amb-alquiler
    python zp.py auditar --run vicente-lopez-1-2amb-alquiler --segunda
    python zp.py dossier --run vicente-lopez-1-2amb-alquiler
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from zp import bloques, corrida, geocodificador, parseo, scoring, urls, zonas
from zp import fotos as mod_fotos
from zp.comun import _plata

# Playwright se importa recién cuando hace falta un navegador, y `anthropic`
# recién cuando se audita. `rankear`, `dossier`, `zonas` y `menu` trabajan
# sobre archivos ya bajados y tienen que poder correr sin ninguno de los dos.


def _navegador():
    from zp.navegador import DesafioError, navegador
    return DesafioError, navegador

RAIZ = Path(__file__).parent
SALIDA = RAIZ / "salida"
PERFIL = RAIZ / ".perfil-chrome"

# Códigos de salida de `buscar`, para que el menú corte el pipeline y diga por qué.
SALIDA_OK = 0
SALIDA_DESAFIO = 1
SALIDA_ZONA_INCORRECTA = 2
SALIDA_INCOMPLETA = 3

CAMPOS_CSV = [
    "score", "id", "tipo", "precio", "moneda",
    "expensas", "expensas_estimadas", "expensas_imputadas",
    "costo_mensual", "costo_m2", "costo_m2_ranking",
    "m2_total", "m2_cubierto", "m2_cubierto_estimado", "m2_confiable",
    "datos_sospechosos", "mediana_usada", "mediana_origen",
    "vs_zpindex", "nota_zpindex",
    "ambientes", "dormitorios", "banos", "cocheras",
    "antiguedad_anios", "antiguedad_label", "estado_unidad",
    "orientacion", "disposicion", "luminosidad", "direccion", "barrio",
    "latitude", "longitude", "entorno_tipo", "avenidas_cercanas", "estaciones_cercanas",
    "garantias_aceptadas", "garantia_compatible", "politica_mascotas", "ajuste_frecuencia", "ajuste_indice", "deposito_monto", "plazo_contrato", "costos_adicionales",
    "es_dueno_directo", "caja_inicial_total", "caja_inicial_resumen", "proyeccion_resumen",
    "baja_precio", "descuento_porcentaje", "nota_historial", "alerta_gran_angular",
    "publicador", "dias_publicado", "es_duplicado", "disparidad_precio", "nota_negociacion",
    "riesgo_humedad", "motivos_riesgo",
    "barrio_popular", "barrio_popular_distancia_m", "barrio_popular_nombre",
    "fotos_totales", "descartado", "url",
]

# Campos que se controlan al terminar `buscar`. Si uno cae a 0% de cobertura,
# casi seguro Zonaprop cambió un data-qa y el parser lo está perdiendo en
# silencio (ya pasó con `publicador`).
CAMPOS_COBERTURA = ("precio", "expensas", "m2_total", "ambientes", "direccion",
                    "descripcion", "publicador")


class _CorteBusqueda(Exception):
    pass


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
    estado = {"completo": True, "codigo": SALIDA_OK, "motivo": None}
    recortadas: list[tuple[str, int]] = []
    DesafioError, navegador = _navegador()

    def cortar(codigo: int, motivo: str):
        estado.update(completo=False, codigo=codigo, motivo=motivo)
        raise _CorteBusqueda()

    try:
        with navegador(PERFIL, headless=args.headless, lento=not args.rapido,
                       espera_desafio=args.espera_captcha,
                       canal=None if args.canal == "chromium" else args.canal) as ses:
            print(f"Navegador: {ses.canal}")
            try:
                ses.calentar()
            except DesafioError as e:
                print(f"\n  {e}")
                print(_ayuda_captcha(args.headless))
                cortar(SALIDA_DESAFIO, "verificación de seguridad sin resolver")
            for zona_item in zonas_list:
                if len(zonas_list) > 1:
                    print(f"\n--- [ZONA] Buscando en {zona_item} ({zonas_list.index(zona_item)+1}/{len(zonas_list)}) ---")
                for amb in tandas:
                    total = None
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
                            cortar(SALIDA_DESAFIO, "verificación de seguridad sin resolver")
                        except RuntimeError as e:
                            print(f"  [{etiqueta}] {e}")
                            estado.update(completo=False, codigo=SALIDA_INCOMPLETA,
                                          motivo=f"no cargó {etiqueta}")
                            break

                        h1 = parseo.titulo_busqueda(html) or ""
                        if not h1.strip():
                            # Sin <h1> no hay con qué validar la zona: casi
                            # siempre es una página de bloqueo que quedó después
                            # del desafío, no un slug equivocado. Antes esto se
                            # informaba como "ZONA INCORRECTA".
                            print(f"\n  [{etiqueta}] La página volvió sin título ni avisos: "
                                  "parece un bloqueo de Zonaprop, no una zona incorrecta.")
                            cortar(SALIDA_INCOMPLETA, "página sin contenido (posible bloqueo)")

                        # Zonaprop no tira 404 con un slug inválido: devuelve otra zona
                        # o el país entero. Se verifica contra el h1 antes de guardar nada.
                        ok, mensaje = zonas.validar_h1(zona_item, h1)
                        if not ok:
                            print(f"\n  ZONA INCORRECTA. {mensaje}")
                            print("  Corté la corrida para no guardarte avisos de otro lado.")
                            print("  Mirá `python zp.py zonas` para los slugs verificados.")
                            cortar(SALIDA_ZONA_INCORRECTA, "zona incorrecta")
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
                    else:
                        # Se agotaron las páginas permitidas sin llegar al final.
                        if total and total > args.paginas * 30:
                            recortadas.append((f"{zona_item} · {amb[0] if amb else 'todos'} amb", total))
    except _CorteBusqueda:
        pass
    except Exception as e:
        # Ventana cerrada a mano, red caída a mitad de página, etc. Lo bajado
        # hasta acá se guarda igual (abajo); el error no se esconde.
        print(f"\n  La búsqueda se cortó: {type(e).__name__}: {e}")
        estado.update(completo=False, codigo=SALIDA_INCOMPLETA, motivo=f"{type(e).__name__}")

    return _guardar_listado(carpeta, encontrados, estado, recortadas, args, zonas_list)


def _guardar_listado(carpeta: Path, encontrados: dict[str, dict], estado: dict,
                     recortadas: list[tuple[str, int]], args, zonas_list: list[str]) -> int:
    """Guarda lo que se haya bajado, aunque la búsqueda se haya cortado.

    Antes, un captcha sin resolver en la página 4 tiraba las tres anteriores:
    el único guardado estaba después del bucle y los `return` salían antes.
    Si la búsqueda quedó incompleta, los avisos de la búsqueda anterior que
    esta vez no se llegaron a ver se conservan (no se sabe si se retiraron).
    """
    hoy = datetime.date.today().isoformat()
    fecha_previa = corrida.fecha_busqueda(carpeta) if (carpeta / "listado.json").exists() else None

    if not encontrados:
        print("\nNo se bajó ningún aviso; dejo el listado anterior como estaba.")
        return estado["codigo"] or SALIDA_INCOMPLETA

    for a in encontrados.values():
        a["visto_en"] = hoy
    datos = list(encontrados.values())

    conservados = 0
    if not estado["completo"] and (carpeta / "listado.json").exists():
        for viejo in corrida.leer_json(carpeta / "listado.json", []):
            if viejo.get("id") not in encontrados:
                viejo.setdefault("visto_en", fecha_previa)
                datos.append(viejo)
                conservados += 1

    params = corrida.cargar_parametros(carpeta)
    busquedas = params.get("busquedas", [])
    if not busquedas and fecha_previa and fecha_previa < hoy:
        # Corrida de antes de que se registraran las búsquedas: el listado
        # que está en disco cuenta como la búsqueda anterior, así esta misma
        # corrida ya muestra qué es nuevo y qué se fue.
        from zp import historial
        previos = corrida.leer_json(carpeta / "listado.json", [])
        historial.registrar(carpeta, previos, fecha=fecha_previa)
        busquedas = [{"fecha": fecha_previa, "completo": True, "avisos": len(previos)}]

    corrida.escribir_json(carpeta / "listado.json", datos)
    busquedas.append({"fecha": hoy, "completo": estado["completo"], "avisos": len(encontrados)})
    corrida.guardar_parametros(carpeta, fecha_busqueda=hoy, ambientes=args.ambientes,
                               zonas=zonas_list, busquedas=busquedas)

    print(f"\n{len(encontrados)} avisos únicos bajados -> {carpeta / 'listado.json'}")
    if conservados:
        print(f"  (+{conservados} de la búsqueda anterior que esta vez no se llegaron a ver)")
    if not estado["completo"]:
        print(f"  ⚠ BÚSQUEDA INCOMPLETA: {estado['motivo']}. Lo bajado quedó guardado; "
              "volvé a correr `buscar` para completarla.")
    for etiqueta, total in recortadas:
        print(f"  ⚠ {etiqueta}: la búsqueda tiene {total} avisos y se vieron "
              f"{args.paginas * 30}. Subí --paginas (o el campo 'Páginas' del menú) "
              "para no perderte los que quedan afuera.")
    _informar_cobertura(list(encontrados.values()))
    return estado["codigo"]


def _informar_cobertura(avisos: list[dict]) -> None:
    if not avisos:
        return
    faltantes = []
    for campo in CAMPOS_COBERTURA:
        con_dato = sum(1 for a in avisos if a.get(campo) not in (None, "", [], 0))
        pct = con_dato / len(avisos)
        if pct == 0:
            faltantes.append(f"{campo} (0%: ¿cambió el sitio?)")
        elif pct < 0.5:
            faltantes.append(f"{campo} ({pct:.0%})")
    if faltantes:
        print("  Campos con poca cobertura: " + ", ".join(faltantes))


# --------------------------------------------------------------------------- #
def _resolver_dolar(args, params: dict) -> float:
    if getattr(args, "dolar", None):
        return args.dolar
    if params.get("dolar"):
        return params["dolar"]
    from zp.cotizacion import obtener_dolar
    dolar, origen = obtener_dolar()
    print(f"Dólar: {_plata(dolar)} ({origen})\n")
    return dolar


def _escribir_ranking(carpeta: Path, ordenados: list[dict]) -> None:
    corrida.escribir_json(carpeta / "ranking.json", ordenados)
    with (carpeta / "ranking.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        w.writeheader()
        for a in ordenados:
            fila = {
                k: "; ".join(str(item) for item in v) if isinstance(v, (list, tuple)) else v
                for k, v in a.items()
            }
            w.writerow(fila)


def cmd_rankear(args):
    carpeta = SALIDA / args.run
    datos = json.loads((carpeta / "listado.json").read_text(encoding="utf-8"))

    # El detalle de cada aviso (antigüedad, orientación, descripción completa,
    # días publicado) vive en detalles/<id>.json desde `fotos`. Antes sólo se
    # rescataba una lista fija de campos del ranking anterior, y `dias_publicado`
    # no estaba: se perdía en el 100% de los avisos.
    con_detalle = corrida.fusionar_detalles(carpeta, datos)
    if con_detalle:
        print(f"Detalle conservado de {con_detalle} avisos.")

    params = corrida.cargar_parametros(carpeta)
    presupuesto = args.presupuesto if args.presupuesto is not None else params.get("presupuesto")
    dolar = args.dolar
    if dolar is None:
        from zp.cotizacion import obtener_dolar
        dolar, origen = obtener_dolar()
        print(f"Dólar: {_plata(dolar)} ({origen})\n")
    # Se guardan para que `fotos` y `auditar` puntúen con los mismos números.
    corrida.guardar_parametros(carpeta, presupuesto=presupuesto, dolar=dolar)

    ordenados = corrida.puntuar_corrida(carpeta, datos, presupuesto, dolar)

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

        # Recién ahora hay coordenadas, así que se vuelve a puntuar: la
        # cercanía a barrios populares del RENABAP depende de la ubicación y en
        # la primera pasada todavía no existía. Es sólo CPU, no vuelve a pegarle
        # a la red ni a geocodificar nada (las coordenadas ya están en el aviso).
        ordenados = corrida.puntuar_corrida(carpeta, ordenados, presupuesto, dolar)
        cerca = [a for a in ordenados
                 if not a.get("descartado")
                 and (a.get("barrio_popular_distancia_m") or 99999) <= 500]
        if cerca:
            print(f"  {len(cerca)} de los avisos vivos están a menos de 500 m "
                  "de un barrio popular del RENABAP\n")

    _escribir_ranking(carpeta, ordenados)

    vivos = [a for a in ordenados if not a["descartado"]]
    print(f"{len(ordenados)} avisos · {len(vivos)} pasan los filtros duros\n")
    print(f"{'#':>2} {'score':>5} {'costo':>12} {'$/m²':>8} {'m²':>4}  aviso")
    for i, a in enumerate(vivos[:args.top], 1):
        print(f"{i:>2} {a['score']:>5.1f} {_plata(a['costo_mensual']):>12} "
              f"{_plata(a['costo_m2']):>8} {a.get('m2_total') or '-':>4}  "
              f"{(a.get('direccion') or a.get('barrio') or '')[:44]}")

    ratios_zp = [a["vs_zpindex"] for a in vivos if a.get("vs_zpindex") is not None]
    # Con menos de 10 avisos la mediana no dice nada sobre "la búsqueda": mejor
    # no imprimir la línea que imprimir un número que se lee como un hallazgo.
    if len(ratios_zp) >= 10:
        med_ratio = statistics.median(ratios_zp)
        diff_pct = round((med_ratio - 1.0) * 100)
        regiones = [a.get("region_zpindex") for a in vivos if a.get("region_zpindex")]
        es_gba = (regiones.count("gba_norte") > regiones.count("caba")) if regiones else False
        reg_txt = "GBA Norte" if es_gba else "CABA"
        fecha_txt = "agosto 2026"

        if diff_pct > 0:
            print(f"\nEsta búsqueda está {diff_pct}% por encima de la referencia ZPIndex ({reg_txt}, {fecha_txt})")
        elif diff_pct < 0:
            print(f"\nEsta búsqueda está {abs(diff_pct)}% por debajo de la referencia ZPIndex ({reg_txt}, {fecha_txt})")
        else:
            print(f"\nEsta búsqueda está en línea con la referencia ZPIndex ({reg_txt}, {fecha_txt})")

    print(f"\n-> {carpeta / 'ranking.csv'}")
    return 0


# --------------------------------------------------------------------------- #
def cmd_fotos(args):
    carpeta = SALIDA / args.run
    ordenados = json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))
    params = corrida.cargar_parametros(carpeta)
    presupuesto = args.presupuesto if args.presupuesto is not None else params.get("presupuesto")
    dolar = _resolver_dolar(args, params)

    objetivo = [a for a in ordenados if not a["descartado"]][:args.top]
    detalles = corrida.cargar_detalles(carpeta)
    pendientes = [
        a for a in objetivo
        if args.refrescar
        or not corrida.detalle_fresco(detalles.get(str(a["id"])))
        or not (carpeta / "contactos" / f"{a['id']}.jpg").exists()
    ]
    if len(pendientes) < len(objetivo):
        print(f"{len(objetivo) - len(pendientes)} avisos ya tienen detalle de los últimos "
              f"{corrida.DIAS_DETALLE_FRESCO} días; los salteo (--refrescar para bajarlos igual).")
    print(f"Bajando detalle y fotos de {len(pendientes)} avisos...\n")

    codigo = 0
    if pendientes:
        DesafioError, navegador = _navegador()
        try:
            with navegador(PERFIL, headless=args.headless, lento=not args.rapido,
                           espera_desafio=args.espera_captcha,
                           canal=None if args.canal == "chromium" else args.canal) as ses:
                ses.calentar()
                for i, a in enumerate(pendientes, 1):
                    print(f"[{i}/{len(pendientes)}] {a['id']} · {(a.get('direccion') or '')[:50]}")
                    try:
                        html = ses.ir(a["url"])
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
                    # Se guarda apenas se parsea: si la corrida se corta en el
                    # aviso 12, los 11 anteriores no se vuelven a bajar.
                    corrida.guardar_detalle(carpeta, str(a["id"]), {
                        **detalle,
                        "fotos_totales": a["fotos_totales"],
                        "fotos_final_galeria": a["fotos_final_galeria"],
                    })
                    titulo = (f"{a['id']} · {a.get('direccion') or a.get('barrio')} · "
                              f"{_plata(a.get('costo_mensual'))}/mes · {a.get('m2_total') or '?'} m² · "
                              f"{a.get('antiguedad') or '?'} años · {a.get('orientacion') or '?'}")
                    mod_fotos.hoja_contacto(imgs, carpeta / "contactos" / f"{a['id']}.jpg", titulo,
                                            marcadas=marcadas)
                    print(f"  {len(imgs)} fotos · antigüedad {a.get('antiguedad') or '?'} · "
                          f"orientación {a.get('orientacion') or '?'} · "
                          f"disposición {a.get('disposicion') or '?'}")
                    ses.esperar()
        except DesafioError as e:
            print(f"\n  {e}")
            print(_ayuda_captcha(args.headless))
            codigo = SALIDA_DESAFIO
        except Exception as e:
            # Ventana cerrada a mano (TargetClosedError), red caída, etc.
            print(f"\n  La descarga se cortó: {type(e).__name__}: {e}")
            print("  Lo bajado hasta acá quedó en detalles/ y no se vuelve a bajar.")
            codigo = SALIDA_INCOMPLETA

    # Volvemos a puntuar, ahora con antigüedad y orientación reales, y con los
    # MISMOS parámetros e historial que `rankear`.
    corrida.fusionar_detalles(carpeta, ordenados)
    ordenados = corrida.puntuar_corrida(carpeta, ordenados, presupuesto, dolar)
    _escribir_ranking(carpeta, ordenados)
    print(f"\nHojas de contacto -> {carpeta / 'contactos'}")
    return codigo


# --------------------------------------------------------------------------- #
def cmd_auditar(args):
    from zp import auditor

    carpeta = SALIDA / args.run
    if not (carpeta / "ranking.json").exists():
        print(f"No hay ranking en {carpeta}: corré `rankear` y `fotos` primero.")
        return 1
    ranking = json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))
    etapa = "segunda" if args.segunda else "primera"
    resumen = auditor.auditar_corrida(
        carpeta, ranking, etapa=etapa, modelo_corto=args.modelo, top=args.top,
        ids=args.ids, forzar=args.forzar, tope_usd=args.tope_usd,
    )
    if resumen["auditados"] and not args.sin_dossier:
        print("\nActualizo el dashboard y la ficha de visita con los veredictos...")
        cmd_dossier(argparse.Namespace(run=args.run, top=args.top, max_descripcion=0))
    if resumen["cortado"] and not resumen["auditados"]:
        return 1
    return 0


# --------------------------------------------------------------------------- #
def cmd_dossier(args):
    """Arma el markdown, el dashboard, la ficha de visita y los mensajes."""
    from zp import auditor, historial, seguimiento

    carpeta = SALIDA / args.run
    ordenados = json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))
    auditor.anotar_avisos(carpeta, ordenados)
    seguimiento.anotar_avisos(SALIDA, ordenados)

    def descartado_por_mi(a):
        return seguimiento.estado(a) == "descartado"

    con_fotos = [a for a in ordenados
                 if (carpeta / "contactos" / f"{a['id']}.jpg").exists() and not descartado_por_mi(a)]
    if not con_fotos:
        print("(no hay hojas de contacto todavía; corré `fotos` primero. "
              "Armo el dossier con el top del ranking, sin imágenes.)")
        con_fotos = [a for a in ordenados
                     if not a["descartado"] and not descartado_por_mi(a)][:args.top]

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
        "| # | Score | IA | ID | Dirección | Tipo | Costo/mes | $/m² cub | Amb | Mascotas | Garantías | Caja Entrada Est. | Negociación | Barrio pop. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
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
        bp_dist = a.get("barrio_popular_distancia_m")
        bp_lbl = f"{bp_dist} m" if bp_dist is not None else "—"
        ia_lbl = (a.get("auditoria") or {}).get("veredicto", "—").replace("_", " ")
        lineas.append(
            f"| {idx} | **{a['score']}** | {ia_lbl} | [{a['id']}](#{a['id']}--score-{str(a['score']).replace('.', '')}) | {dir_lbl} | {tipo_lbl} | {costo_lbl} | {m2_lbl} | {amb_lbl} | {masc_lbl} | {gar_lbl} | {caja_lbl} | {neg_lbl} | {bp_lbl} |"
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
        exp_txt = bloques.texto_expensas(a)

        item_lineas = [
            f"## {a['id']} — score {a['score']}",
            "",
        ] + bloques.bloque_yaml(a) + [
            f"- **Costo**: {_plata(a.get('costo_mensual'))}/mes "
            f"(alquiler {a.get('moneda')} {_plata(a.get('precio'))} + expensas {_plata(a.get('expensas'))})",
            f"- **Caja Inicial al firmar**: {a.get('caja_inicial_resumen') or 'Consultar'}",
            linea_sup,
            f"- **Edificio**: {a.get('antiguedad') or '?'} años · disposición "
            f"{a.get('disposicion') or '?'} · orientación {a.get('orientacion') or '?'} · "
            f"{a.get('luminosidad') or '?'}",
            f"- **Dónde**: {a.get('direccion') or '?'} — {a.get('barrio') or '?'}",
            f"- **Barrio popular más cercano**: {a.get('barrio_popular') or 'sin dato (falta geocodificar)'}",
            f"- **A favor**: {', '.join(a.get('motivos_a_favor') or []) or '—'}",
            f"- **En contra**: {', '.join(a.get('motivos_en_contra') or []) or '—'}",
            f"- **Riesgo de humedad a priori**: {a.get('riesgo_humedad', 0)} "
            f"({', '.join(a.get('motivos_riesgo') or []) or 'sin señales'})",
            f"- **Expensas**: {exp_txt}",
        ]
        aud = a.get("auditoria")
        if aud:
            item_lineas.append(
                f"- **🤖 Auditoría ({aud.get('modelo')})**: {aud['veredicto'].replace('_', ' ')} · "
                f"visual {aud.get('score_visual')} — {aud.get('resumen')}"
            )
        if a.get("nota_negociacion"):
            item_lineas.append(f"- **⚠️ Negociación / Duplicado**: {a.get('nota_negociacion')}")

        if a.get("preguntas_visita"):
            item_lineas.append("- **🔍 Preguntas clave para la visita presencial / LLM**:")
            for p in a["preguntas_visita"]:
                item_lineas.append(f"  - {p}")

        item_lineas += [
            bloques.linea_fotos(a),
            f"- **Link**: {a.get('url')}",
            "",
        ] + bloques.bloque_descripcion(a, args.max_descripcion) + [""]

        lineas += item_lineas

    destino = carpeta / "dossier.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")

    # La ficha de visita es para el día que se sale a recorrer: si ya hay
    # visitas agendadas, sólo esas, en orden. Si no, el top como antes.
    agendadas = [a for a in ordenados if seguimiento.estado(a) == "visita"]
    para_ficha = sorted(agendadas, key=lambda a: (a.get("seguimiento") or {}).get("visita") or "") or con_fotos

    params = corrida.cargar_parametros(carpeta)
    novedades = historial.novedades(historial.cargar(carpeta), params.get("busquedas", []))

    from zp import dashboard, mapa, prompt, visita
    prompt_file = prompt.generar_prompt_diagnostico(args.run, con_fotos, carpeta)
    dash_file = dashboard.generar_dashboard_html(
        args.run, ordenados, carpeta, novedades=novedades,
        seguimiento_inicial=seguimiento.cargar(SALIDA),
    )
    ficha_file = visita.generar_ficha_visita(args.run, para_ficha, carpeta)
    pdf_file = carpeta / "ficha_visita.pdf"
    msg_file = visita.generar_mensajes_inmobiliarias(args.run, con_fotos, carpeta)
    mapa.exportar_geojson(args.run, ordenados, carpeta)
    kml_file = mapa.exportar_kml(args.run, ordenados, carpeta)

    print(f"-> {dash_file} (Dashboard: abrilo primero)")
    print(f"-> {destino}")
    if pdf_file.exists():
        print(f"-> {pdf_file} (PDF listo para imprimir / llevar en celular)")
    print(f"-> {ficha_file} (Ficha de visita{': ' + str(len(agendadas)) + ' visitas agendadas' if agendadas else ''})")
    print(f"-> {msg_file} (Mensajes prearmados para WhatsApp)")
    print(f"-> {kml_file} (Recorrido para Google Maps / Earth)")
    if not any(a.get("auditoria") for a in con_fotos):
        print(f"Para el análisis de fotos: `python zp.py auditar --run {args.run}` "
              f"(o pegá {prompt_file.name} + dossier.md + contactos/ en un chat).")
    return 0


def _bloque_descripcion(a: dict, tope: int = 0) -> list[str]:
    # Se mudó a zp/bloques.py para que el auditor use el mismo texto.
    return bloques.bloque_descripcion(a, tope)


# --------------------------------------------------------------------------- #
def cmd_diff(args):
    """Qué cambió desde la búsqueda anterior, o contra otra corrida con --vs."""
    from zp import historial, seguimiento

    carpeta_a = SALIDA / args.run
    if not (carpeta_a / "ranking.json").exists():
        print(f"No existe ranking en {carpeta_a}")
        return 1
    avisos_a = {a["id"]: a for a in json.loads((carpeta_a / "ranking.json").read_text(encoding="utf-8"))}

    if not args.vs:
        # Antes comparaba ranking.json contra el listado.json de la MISMA
        # corrida: como uno sale del otro, daba siempre 0 nuevos y 0 retirados.
        params = corrida.cargar_parametros(carpeta_a)
        nov = historial.novedades(historial.cargar(carpeta_a), params.get("busquedas", []))
        if not nov:
            print("Todavía hay una sola búsqueda registrada para esta corrida: "
                  "volvé a correr `buscar` otro día y acá vas a ver qué cambió.")
            return 0
        seguidos = set(seguimiento.cargar(SALIDA))
        print(f"\n--- Novedades: búsqueda del {nov['actual']} contra la del {nov['anterior']} ---")
        print(f"Nuevos: {len(nov['nuevos'])} · bajaron: {len(nov['bajas'])} · "
              f"subieron: {len(nov['subas'])} · ya no están: {len(nov['retirados'])}")
        if nov["bajas"]:
            print("\n[-] Bajaron de precio:")
            for b in sorted(nov["bajas"], key=lambda b: b["pct"]):
                d = (avisos_a.get(b["id"]) or {}).get("direccion", "?")
                print(f"  * {b['id']} ({d}): {b['moneda']} {_plata(b['antes'])} -> {_plata(b['ahora'])} ({b['pct']}%)")
        if nov["nuevos"]:
            print("\n[NEW] Nuevos (por score):")
            nuevos = sorted((avisos_a[i] for i in nov["nuevos"] if i in avisos_a),
                            key=lambda a: -(a.get("score") or 0))
            for a in nuevos[:10]:
                print(f"  * {a['id']}: {a.get('direccion', '?')} ({_plata(a.get('costo_mensual'))}/mes · score {a.get('score')})")
        if nov["retirados"]:
            print("\n[OUT] Ya no están publicados:")
            for r in nov["retirados"][:10]:
                marca = "  <- lo estabas siguiendo" if r["id"] in seguidos else ""
                print(f"  * {r['id']}: {r.get('direccion') or '?'}{marca}")
        elif not nov["completa"]:
            print("\nLa última búsqueda no terminó completa: no se puede saber qué se retiró.")
        print("")
        return 0

    carpeta_b = SALIDA / args.vs
    if not (carpeta_b / "ranking.json").exists():
        print(f"No existe ranking en {carpeta_b}")
        return 1
    avisos_b = {a["id"]: a for a in json.loads((carpeta_b / "ranking.json").read_text(encoding="utf-8"))}

    ids_a, ids_b = set(avisos_a), set(avisos_b)
    solo_a, solo_b, comunes = ids_a - ids_b, ids_b - ids_a, ids_a & ids_b
    print(f"\n--- [DIFF] {args.run} contra {args.vs} ---")
    print(f"Sólo en {args.run}: {len(solo_a)} · sólo en {args.vs}: {len(solo_b)} · en las dos: {len(comunes)}")

    for aid in sorted(comunes):
        a, b = avisos_a[aid], avisos_b[aid]
        if (a.get("moneda") or "ARS") != (b.get("moneda") or "ARS"):
            continue
        pa, pb = a.get("precio"), b.get("precio")
        if pa and pb and pa != pb:
            pct = round((pa - pb) / pb * 100)
            print(f"  * {aid} ({a.get('direccion', '?')}): {_plata(pb)} -> {_plata(pa)} ({pct:+d}%)")
    for titulo, ids, fuente in ((f"Sólo en {args.run}", solo_a, avisos_a),
                                (f"Sólo en {args.vs}", solo_b, avisos_b)):
        if ids:
            print(f"\n{titulo}:")
            for aid in list(ids)[:10]:
                x = fuente[aid]
                print(f"  * {aid}: {x.get('direccion', '?')} ({_plata(x.get('costo_mensual'))}/mes)")
    print("")
    return 0


# --------------------------------------------------------------------------- #
def cmd_seguir(args):
    from zp import seguimiento

    if args.importar:
        try:
            actualizados, ignorados = seguimiento.importar(SALIDA, Path(args.importar))
        except ValueError as e:
            print(e)
            return 1
        print(f"Seguimiento importado: {actualizados} cambios, {ignorados} sin cambios o más viejos.")
        print("Corré `dossier` (o `tablero`) para verlo reflejado.")
        return 0
    if args.listar or not args.id:
        datos = seguimiento.cargar(SALIDA)
        if not datos:
            print("Todavía no marcaste ningún aviso.")
            return 0
        for estado in seguimiento.ESTADOS:
            items = [(i, e) for i, e in datos.items() if e.get("estado") == estado]
            if items:
                print(f"\n{seguimiento.ETIQUETAS[estado]} ({len(items)}):")
                for i, e in items:
                    extra = " — ".join(x for x in (e.get("visita"), e.get("motivo"), e.get("nota")) if x)
                    print(f"  {i}{'  ' + extra if extra else ''}")
        return 0
    if not args.estado:
        print(f"Falta el estado: {', '.join(seguimiento.ESTADOS)} o borrar")
        return 1
    try:
        seguimiento.marcar(SALIDA, args.id, args.estado, motivo=args.motivo,
                           nota=args.nota, visita=args.visita)
    except ValueError as e:
        print(e)
        return 1
    print(f"{args.id}: {args.estado}")
    return 0


def cmd_tablero(args):
    """Un solo dashboard con todas las búsquedas, sin avisos repetidos."""
    from zp import auditor, dashboard, seguimiento

    por_id: dict[str, dict] = {}
    corridas = sorted(p for p in SALIDA.iterdir() if p.is_dir() and (p / "ranking.json").exists()) \
        if SALIDA.exists() else []
    if not corridas:
        print("No hay corridas con ranking en salida/.")
        return 1
    for carpeta in corridas:
        avisos = corrida.leer_json(carpeta / "ranking.json", [])
        auditor.anotar_avisos(carpeta, avisos)
        for a in avisos:
            a["_run"] = carpeta.name
            aid = str(a["id"])
            previo = por_id.get(aid)
            # Si está en varias búsquedas se queda la versión viva y con más score.
            clave = (not a.get("descartado"), a.get("score") or 0)
            if previo is None or clave > (not previo.get("descartado"), previo.get("score") or 0):
                if previo:
                    a["_tambien_en"] = sorted(set(previo.get("_tambien_en", [])) | {previo["_run"]})
                por_id[aid] = a
            else:
                previo.setdefault("_tambien_en", [])
                if carpeta.name not in previo["_tambien_en"]:
                    previo["_tambien_en"].append(carpeta.name)

    avisos = sorted(por_id.values(), key=lambda a: (bool(a.get("descartado")), -(a.get("score") or 0)))
    seguimiento.anotar_avisos(SALIDA, avisos)
    destino = dashboard.generar_dashboard_html(
        f"{len(corridas)} búsquedas", avisos, SALIDA,
        seguimiento_inicial=seguimiento.cargar(SALIDA),
        nombre_archivo="tablero.html", multi=True,
    )
    repetidos = sum(1 for a in avisos if a.get("_tambien_en"))
    print(f"{len(avisos)} avisos de {len(corridas)} búsquedas ({repetidos} aparecían en más de una).")
    print(f"-> {destino}")
    return 0


# --------------------------------------------------------------------------- #
def _ayuda_captcha(headless: bool) -> str:
    if headless:
        return ("  Estás corriendo en modo headless: la ventana no se ve, así que no hay\n"
                "  forma de tildar el casillero. Destildá 'Sin ventana del navegador' en\n"
                "  el menú (o sacá --headless) y resolvelo una vez a mano: la cookie queda\n"
                "  guardada en .perfil-chrome y después podés volver a headless.")
    return ("  Si no llegaste a tildarlo, volvé a correr el paso: la ventana se abre de\n"
            "  nuevo y la espera arranca otra vez. Si te pasa seguido, subí el margen con\n"
            "  --espera-captcha 600 y bajá --paginas.")


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


# --------------------------------------------------------------------------- #
def _preparar_consola() -> None:
    """En Windows la consola (y el pipe que lee el menú) usa cp1252, que no
    tiene "⚠" ni "✓": un print con esos caracteres tiraba UnicodeEncodeError
    y cortaba el comando a mitad. Por pipe (el menú, que decodifica UTF-8) se
    escribe en UTF-8; en una consola, lo que no entra se reemplaza por "?"."""
    for flujo in (sys.stdout, sys.stderr):
        if not hasattr(flujo, "reconfigure"):
            continue
        if flujo.isatty():
            flujo.reconfigure(errors="replace")
        else:
            flujo.reconfigure(encoding="utf-8", errors="replace")


def main():
    _preparar_consola()
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
    r.add_argument("--presupuesto", type=float, default=None,
                   help="tope de alquiler + expensas (default: el de la última vez)")
    r.add_argument("--dolar", type=float, default=None, help="cotización para pasar USD a ARS (default: consulta con caché)")
    r.add_argument("--top", type=int, default=20)
    r.set_defaults(func=cmd_rankear)

    f = sub.add_parser("fotos", help="detalle + fotos del top N")
    f.add_argument("--run", required=True)
    f.add_argument("--top", type=int, default=20)
    f.add_argument("--max-fotos", type=int, default=16)
    f.add_argument("--presupuesto", type=float, default=None,
                   help="default: el que se usó en rankear")
    f.add_argument("--dolar", type=float, default=None, help="default: el que se usó en rankear")
    f.add_argument("--refrescar", action="store_true",
                   help="volver a bajar también los avisos con detalle reciente")
    comunes(f)
    f.set_defaults(func=cmd_fotos)

    au = sub.add_parser("auditar", help="análisis de fotos y texto con la API de Claude")
    au.add_argument("--run", required=True)
    au.add_argument("--segunda", action="store_true",
                    help="segunda revisión con Opus de los que la primera no descartó, "
                         "con las fotos sueltas en resolución completa")
    au.add_argument("--modelo", choices=["sonnet", "opus"], default=None,
                    help="default: sonnet en la primera revisión, opus en la segunda")
    au.add_argument("--top", type=int, default=20, help="cuántos avisos del ranking auditar")
    au.add_argument("--ids", nargs="+", default=None, help="auditar sólo estos avisos")
    au.add_argument("--forzar", action="store_true", help="repetir aunque el aviso no haya cambiado")
    au.add_argument("--tope-usd", type=float, default=None, help="cortar al llegar a este gasto estimado")
    au.add_argument("--sin-dossier", action="store_true", help="no regenerar el dashboard al terminar")
    au.set_defaults(func=cmd_auditar)

    d = sub.add_parser("dossier", help="arma el dashboard, la ficha y los mensajes")
    d.add_argument("--run", required=True)
    d.add_argument("--top", type=int, default=20)
    d.add_argument("--max-descripcion", type=int, default=0, metavar="CHARS",
                   help="recortar la descripción a N caracteres (default 0 = entera)")
    d.set_defaults(func=cmd_dossier)

    z = sub.add_parser("zonas", help="lista las zonas verificadas y sus slugs")
    z.add_argument("--buscar", default=None, help="filtra por nombre")
    z.set_defaults(func=cmd_zonas)

    df = sub.add_parser("diff", help="qué cambió desde la búsqueda anterior")
    df.add_argument("--run", required=True, help="nombre de la corrida")
    df.add_argument("--vs", default=None, help="comparar contra otra corrida en vez de contra la búsqueda anterior")
    df.set_defaults(func=cmd_diff)

    sg = sub.add_parser("seguir", help="marcar un aviso: favorito, contactado, visita, visitado, descartado")
    sg.add_argument("id", nargs="?", help="id del aviso")
    sg.add_argument("estado", nargs="?", help="favorito | contactado | visita | visitado | descartado | borrar")
    sg.add_argument("--motivo", default=None, help="por qué (sobre todo al descartar)")
    sg.add_argument("--nota", default=None, help="notas de la visita")
    sg.add_argument("--visita", default=None, help="cuándo es la visita (ej: 'jueves 18 hs')")
    sg.add_argument("--importar", default=None, metavar="ARCHIVO",
                    help="mezclar el seguimiento exportado desde el dashboard")
    sg.add_argument("--listar", action="store_true", help="mostrar todo lo marcado")
    sg.set_defaults(func=cmd_seguir)

    tb = sub.add_parser("tablero", help="un dashboard con todas las búsquedas")
    tb.set_defaults(func=cmd_tablero)

    m = sub.add_parser("menu", help="abre el menú visual")
    m.set_defaults(func=cmd_menu)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
