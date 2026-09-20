"""Tests del parser y el scoring contra el fixture.

    python -m pytest tests/ -q
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import fixture_listado as fx
from zp import dashboard, fotos, parseo, prompt, scoring, urls, zonas


def test_urls():
    assert urls.construir_url("Vicente López", ambientes=[2]) == (
        "https://www.zonaprop.com.ar/departamentos-ph-alquiler-vicente-lopez-2-ambientes.html"
    )
    assert urls.construir_url("nunez", tipos=["departamentos"], ambientes=[1], pagina=3) == (
        "https://www.zonaprop.com.ar/departamentos-alquiler-nunez-1-ambiente-pagina-3.html"
    )
    assert urls.construir_url("caballito", ambientes=[2], precio_max=900000) == (
        "https://www.zonaprop.com.ar/departamentos-ph-alquiler-caballito-2-ambientes-menos-900000-pesos.html"
    )
    assert urls.nombre_run(["nunez", "belgrano"], ambientes=[2, 3]) == "nunez-belgrano-2-3amb-alquiler"
    assert urls.nombre_run(["nunez", "belgrano", "colegiales", "villa-urquiza"], ambientes=[2]) == "nunez-y-3-zonas-2amb-alquiler"


def test_listado_campos():
    avisos = {a.id: a for a in parseo.parsear_listado(fx.html())}
    assert len(avisos) == 8
    a = avisos["59553528"]
    assert (a.precio, a.moneda, a.expensas) == (700000.0, "ARS", 70000.0)
    assert (a.m2_total, a.m2_cubierto, a.ambientes, a.dormitorios) == (40.0, 40.0, 2, 1)
    assert a.direccion == "Perú al 1200"
    assert a.url.endswith("-59553528.html") and a.url.startswith("https://")
    assert len(a.fotos) == 2

    usd = avisos["59052566"]
    assert usd.moneda == "USD" and usd.precio == 2500.0 and usd.cocheras == 1


def test_total_resultados():
    assert parseo.total_resultados(fx.html()) == 357


def test_detalle():
    d = parseo.parsear_detalle(fx.DETALLE)
    assert d["antiguedad"] == "20"
    assert d["orientacion"] == "N"
    assert d["disposicion"] == "Frente"
    assert d["luminosidad"] == "Muy luminoso"
    assert len(d["fotos"]) == 3
    assert "1200x1200" in d["fotos"][0]
    assert "muy luminoso" in d["descripcion_completa"].lower()


def test_costo_incluye_expensas_y_convierte_dolares():
    ars = {"precio": 700000, "expensas": 70000, "moneda": "ARS", "expensas_informadas": True}
    usd = {"precio": 1000, "expensas": 100000, "moneda": "USD", "expensas_informadas": True}
    assert scoring.costo_mensual(ars, 1450) == 770000
    assert scoring.costo_mensual(usd, 1450) == 1550000


# --------------------------------------------------------------------------- #
# Bug 1: las expensas ausentes se cargaban como cero
# --------------------------------------------------------------------------- #

def test_expensas_ausentes_no_son_cero():
    """El aviso que no informa expensas queda en None, no en 0."""
    avisos = {a.id: a for a in parseo.parsear_listado(fx.html())}
    sin_dato = avisos["60010001"]
    assert sin_dato.expensas is None
    assert sin_dato.expensas_informadas is False


def test_sin_expensas_declarado_si_es_cero():
    """Cuando el aviso dice 'no paga expensas', el 0 es un 0 de verdad."""
    avisos = {a.id: a for a in parseo.parsear_listado(fx.html())}
    declarado = avisos["59855694"]
    assert declarado.expensas == 0.0
    assert declarado.expensas_informadas is True


def test_expensas_faltantes_se_estiman_y_penalizan():
    avisos = [a.dict() for a in parseo.parsear_listado(fx.html())]
    r = {a["id"]: a for a in scoring.puntuar(avisos, presupuesto=2_000_000, dolar=1450)}
    sin_dato = r["60010001"]

    assert sin_dato["expensas_imputadas"] is True
    assert sin_dato["expensas_estimadas"] > 0
    # El costo mensual ya no es solo el alquiler.
    assert sin_dato["costo_mensual"] > sin_dato["precio"]
    assert any("no informa expensas" in m for m in sin_dato["motivos_en_contra"])


def test_ocultar_expensas_no_conviene():
    """Dos avisos idénticos: el que oculta las expensas no puede puntuar mejor."""
    base = dict(id="x", precio=700000, moneda="ARS", m2_total=45, ambientes=2,
                descripcion="Departamento de 2 ambientes con balcón.")
    declara = {**base, "id": "declara", "expensas": 150000, "expensas_informadas": True}
    oculta = {**base, "id": "oculta", "expensas": None, "expensas_informadas": False}
    # Contexto para que haya mediana con la que estimar.
    contexto = [
        {**base, "id": f"c{i}", "expensas": 140000 + i * 1000, "expensas_informadas": True}
        for i in range(6)
    ]
    r = {a["id"]: a for a in scoring.puntuar([declara, oculta] + contexto, dolar=1450)}
    assert r["oculta"]["score"] <= r["declara"]["score"]


def test_expensas_de_ph_sin_consorcio_no_arrastran_la_estimacion():
    """Los 0 declarados quedan fuera de la mediana: no son expensas bajas,
    es que no hay consorcio."""
    avisos = [
        {"id": "ph", "precio": 600000, "moneda": "ARS", "expensas": 0.0,
         "expensas_informadas": True},
        *[{"id": f"d{i}", "precio": 700000, "moneda": "ARS", "expensas": 200000,
           "expensas_informadas": True} for i in range(6)],
        {"id": "sin", "precio": 700000, "moneda": "ARS", "expensas": None,
         "expensas_informadas": False},
    ]
    ratio = scoring.imputar_expensas(avisos, 1450)
    assert ratio == pytest.approx(200000 / 700000)


# --------------------------------------------------------------------------- #
# Bug 2: la antigüedad se leía mal con 'a estrenar' y con reciclados
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("crudo, esperado", [
    ("20", 20), ("  38 ", 38), ("0", 0),
    ("A estrenar", 0), ("a estrenar", 0), ("En pozo", 0), ("En construcción", 0),
    (None, None), ("", None), ("sin datos", None),
])
def test_parseo_de_antiguedad(crudo, esperado):
    assert scoring.parsear_antiguedad(crudo)[0] == esperado


def test_ausente_no_se_confunde_con_cero():
    assert scoring.parsear_antiguedad(None)[0] is None
    assert scoring.parsear_antiguedad("0")[0] == 0


def test_a_estrenar_no_arrastra_riesgo():
    r, _ = scoring.riesgo_humedad({"antiguedad": "A estrenar"}, "monoambiente a estrenar al frente")
    assert r == 0


def test_reciclado_amortigua_la_antiguedad_pero_no_la_borra():
    viejo, _ = scoring.riesgo_humedad({"antiguedad": "60"}, "piso 3 al frente")
    recic, _ = scoring.riesgo_humedad({"antiguedad": "60"}, "reciclado a nuevo, piso 3 al frente")
    nuevo, _ = scoring.riesgo_humedad({"antiguedad": "5"}, "piso 3 al frente")
    # Reciclar la unidad no arregla la terraza ni la fachada: baja, no desaparece.
    assert nuevo < recic < viejo


def test_antiguedad_se_saca_del_texto_cuando_no_hay_ficha():
    a = {"antiguedad": ""}
    scoring.riesgo_humedad(a, "El edificio, de 38 años de antigüedad, dispone de 2 ascensores")
    assert a["antiguedad_anios"] == 38


def test_recien_pintado_sube_el_riesgo_no_lo_baja():
    con, _ = scoring.riesgo_humedad({"antiguedad": "30"}, "departamento recién pintado")
    sin, _ = scoring.riesgo_humedad({"antiguedad": "30"}, "departamento en buen estado")
    assert con > sin


# --------------------------------------------------------------------------- #
# Bug 3: el recorte de fotos se comía la fachada
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("total, tope", [(20, 16), (30, 16), (17, 16), (60, 12)])
def test_la_ultima_foto_nunca_se_corta(total, tope):
    urls_fotos = [f"f{i:02d}" for i in range(1, total + 1)]
    elegidas, marcadas = fotos.muestrear(urls_fotos, tope)
    assert len(elegidas) == tope
    # Las últimas de la galería son fachada, palier y plano: tienen que estar.
    assert urls_fotos[-fotos.COLA:] == elegidas[-fotos.COLA:]
    assert marcadas == set(range(tope - fotos.COLA + 1, tope + 1))


def test_galeria_corta_entra_entera():
    urls_fotos = [f"f{i}" for i in range(1, 8)]
    elegidas, marcadas = fotos.muestrear(urls_fotos, 16)
    assert elegidas == urls_fotos
    assert max(marcadas) == len(urls_fotos)


# --------------------------------------------------------------------------- #
# Zonas
# --------------------------------------------------------------------------- #

def test_zona_correcta_pasa():
    ok, _ = zonas.validar_h1("villa-martelli",
                             "37 Departamentos en alquiler en Villa Martelli, Vicente López")
    assert ok


def test_slug_inexistente_devuelve_todo_el_pais_y_se_detecta():
    ok, msg = zonas.validar_h1("nunez", "45.738 Departamentos en alquiler en Argentina")
    assert not ok and "todo el país" in msg


def test_zona_homonima_de_otra_provincia_se_detecta():
    ok, msg = zonas.validar_h1("general-san-martin",
                               "4 Departamentos en alquiler en San Martín, Mendoza")
    assert not ok and "Mendoza" in msg


def test_partido_y_localidad_son_slugs_distintos():
    assert zonas.TODAS["vicente-lopez"].nivel == "partido"
    assert zonas.TODAS["vicente-lopez-vicente-lopez"].nivel == "localidad"


# --------------------------------------------------------------------------- #
# El dossier: la descripción va entera
# --------------------------------------------------------------------------- #
# zp.py no se puede importar con `import zp` porque el paquete zp/ le gana el
# nombre, así que se carga por ruta.
import importlib.util as _il  # noqa: E402

_spec = _il.spec_from_file_location(
    "cli_zp", Path(__file__).resolve().parents[1] / "zp.py")
cli = _il.module_from_spec(_spec)
_spec.loader.exec_module(cli)


AVISO_LARGO = {
    "descripcion_completa": (
        "Departamento de 2 ambientes en Florida. " + "Living comedor amplio y luminoso. " * 30
        + "Requisitos para ingresar: garantía propietaria de CABA, 1 mes de adelanto, "
          "1 mes de depósito, no acepta mascotas."
    )
}


def test_la_descripcion_va_entera():
    """El recorte a 900 caracteres se comía el final del aviso."""
    bloque = "\n".join(cli._bloque_descripcion(AVISO_LARGO))
    assert len(AVISO_LARGO["descripcion_completa"]) > 900
    assert "…recortado" not in bloque


def test_los_requisitos_del_final_sobreviven():
    """En Zonaprop los requisitos van al final, y son los que definen si el
    departamento es viable: garantía, jurisdicción, mascotas, adelanto."""
    bloque = "\n".join(cli._bloque_descripcion(AVISO_LARGO))
    for dato in ("garantía propietaria de CABA", "1 mes de adelanto",
                 "no acepta mascotas"):
        assert dato in bloque


def test_el_tope_explicito_recorta_y_lo_avisa():
    bloque = "\n".join(cli._bloque_descripcion(AVISO_LARGO, tope=200))
    assert "…recortado" in bloque


def test_el_copete_de_la_tarjeta_se_marca_como_tal():
    """Sin la ficha de detalle solo tenemos el copete, que corta Zonaprop.
    Hay que decirlo para que no se lea como el aviso completo."""
    bloque = "\n".join(cli._bloque_descripcion(
        {"descripcion": "Depto 2 ambientes con balcón en Olivos, cocina integrada"}))
    assert "cortado por Zonaprop" in bloque


def test_aviso_sin_descripcion_no_rompe():
    assert "no trae descripción" in "\n".join(cli._bloque_descripcion({}))


# --------------------------------------------------------------------------- #
# El desafío anti-bot
# --------------------------------------------------------------------------- #
# navegador.py importa playwright, que no hace falta para probar la detección.
detectar = pytest.importorskip("zp.navegador", reason="requiere playwright").detectar_desafio


def test_detecta_cloudflare():
    assert detectar(fx.DESAFIO_CLOUDFLARE, "Un momento...") == "Cloudflare"


def test_detecta_datadome():
    assert detectar(fx.DESAFIO_DATADOME, "zonaprop.com.ar") == "DataDome"


def test_detecta_por_titulo_aunque_cambien_las_marcas():
    """Si mañana cambian el HTML, el título sigue delatando el interstitial."""
    assert detectar("<html><body>algo distinto</body></html>", "Just a moment...")


def test_una_pagina_con_avisos_no_es_un_desafio():
    """El listado real trae scripts de Cloudflare dando vueltas; mientras haya
    tarjetas, el contenido llegó y no hay que frenar nada."""
    html = fx.html().replace(
        "<body>", "<body><script src='/cdn-cgi/challenge-platform/h/g/x.js'></script>")
    assert detectar(html, "357 Departamentos en alquiler en Vicente López - Zonaprop") is None


def test_listado_normal_no_es_un_desafio():
    assert detectar(fx.html(), "357 Departamentos en alquiler en Vicente López") is None


def test_temporal_se_descarta():
    avisos = [a.dict() for a in parseo.parsear_listado(fx.html())]
    r = {a["id"]: a for a in scoring.puntuar(avisos, presupuesto=900000, dolar=1450)}
    assert "alquiler temporal" in r["58506752"]["motivos_descarte"]
    assert r["58506752"]["descartado"]


def test_no_acepta_mascotas_no_suma_bono():
    """'No acepta mascotas' no puede contar como bono de 'acepta mascotas'."""
    _, pos, neg = scoring.señales("No acepta mascotas sin excepción perros y gatos.")
    assert "acepta mascotas" not in pos
    assert "no acepta mascotas" in neg


def test_contrafrente_no_dispara_bono_de_frente():
    _, pos, _ = scoring.señales("Primer piso al contrafrente con balcón.")
    assert "al frente" not in pos


def test_riesgo_humedad_sube_en_pb_y_edificio_viejo():
    alto, _ = scoring.riesgo_humedad({"antiguedad": "60"}, "planta baja al contrafrente")
    bajo, _ = scoring.riesgo_humedad({"antiguedad": "5"}, "piso 12 al frente, a estrenar")
    assert alto > bajo


def test_ranking_prefiere_lo_mas_barato_por_m2():
    avisos = [a.dict() for a in parseo.parsear_listado(fx.html())]
    r = scoring.puntuar(avisos, presupuesto=900000, dolar=1450)
    vivos = [a for a in r if not a["descartado"]]
    assert vivos[0]["id"] == "59855694"  # $620k sin expensas, 45 m²


# --------------------------------------------------------------------------- #
# Nuevas mejoras: los 5 patrones detectados
# --------------------------------------------------------------------------- #

def test_ph_o_casa_sin_expensas_estima_cero():
    """Un PH o chalet sin consorcio / sin expensas no recibe la mediana de deptos."""
    avisos = [
        {"id": f"d{i}", "tipo": "departamento", "precio": 700000, "moneda": "ARS",
         "expensas": 200000, "expensas_informadas": True}
        for i in range(6)
    ]
    ph_sin_dato = {
        "id": "ph_brasil", "tipo": "ph", "precio": 900000, "moneda": "ARS",
        "expensas": None, "expensas_informadas": False, "m2_total": 55, "ambientes": 3,
        "descripcion": "PH de 3 ambientes con terraza propia y entrada independiente."
    }
    r = {a["id"]: a for a in scoring.puntuar(avisos + [ph_sin_dato], dolar=1450)}
    # Debe estimar $0 y costo mensual = $900.000 (no $1.080.000)
    assert r["ph_brasil"]["expensas_estimadas"] == 0.0
    assert r["ph_brasil"]["costo_mensual"] == 900000.0
    assert not any("no informa expensas" in m for m in r["ph_brasil"]["motivos_en_contra"])


def test_superficie_terraza_marca_m2_no_confiable():
    """Laprida 4500: declara 118 m² pero tiene terraza de 74 m² y ~52 m² cubiertos."""
    desc = (
        "Excelente Ph 3 ambientes sobre Av. Laprida con balcon al frente, patio y terraza. "
        "Living comedor: 5.60 x 3.10. Balcón 7,00 x 1,00. Distribuidor: 3.60 x 0.90. "
        "Dormitorio al frente 3,60 x 2,70 con placar. Dormitorio al frente 2,60 x 2.50 con placar. "
        "Baño: 1.50 x 1.90. Cocina: 2.45 x 2.35. Patio c/ Lavadero 2.4x2.60. "
        "Terraza: 8.66x8.50 solo se permite tendido de ropa."
    )
    aviso = {
        "id": "59658007", "precio": 1000000, "moneda": "ARS", "expensas": 0.0,
        "expensas_informadas": True, "m2_total": 118.0, "ambientes": 3,
        "descripcion": desc, "descripcion_completa": desc
    }
    scoring.analizar_superficies(aviso, desc)
    assert aviso["m2_confiable"] is False
    assert aviso["m2_cubierto_estimado"] < 60
    assert aviso["m2_descubierto_estimado"] > 70


def test_artefacto_a_estrenar_no_baja_riesgo_edificio_viejo():
    """Adolfo Alsina 4200: 'artefacto a estrenar' en edificio de 58 años no es riesgo 0."""
    desc = (
        "Ubicado en Villa Martelli, este encantador PH ofrece un espacio de 66 m2 sin expensas. "
        "La cocina cuenta con un artefacto a estrenar."
    )
    aviso = {"id": "60007637", "antiguedad": "58", "tipo": "ph"}
    r, motivos = scoring.riesgo_humedad(aviso, desc)
    pts, pos, _ = scoring.señales(desc, aviso)
    assert "a estrenar" not in pos
    assert aviso["estado_unidad"] != "a_estrenar"
    assert r > 0  # No puede ser riesgo 0 en edificio de 58 años


def test_antiguedad_sospechosa_en_ph_o_chalet():
    """Zufriategui 4900 declara '1 año' sobre un chalet antiguo."""
    desc = "EN ALQUILER CHALET 3 AMBIENTES 2 DORMITORIOS BAÑO COMPLETO COCINA COMEDOR"
    aviso = {"id": "58554433", "antiguedad": "1", "tipo": "casa"}
    r, motivos = scoring.riesgo_humedad(aviso, desc)
    assert aviso.get("antiguedad_sospechosa") is True
    assert any("antigüedad sospechosa" in m for m in motivos)
    # No debe recibir el bono de riesgo -2 de edificio nuevo
    assert r >= 0


def test_sin_contradiccion_frente_contrafrente():
    """No debe haber 'al frente' y 'contrafrente' a la vez."""
    # Caso 1: Ficha oficial Contrafrente con 'Dormitorio al frente'
    aviso_cf = {"id": "cf", "disposicion": "Contrafrente"}
    desc_cf = "Dormitorio al frente con placard, living con salida al contrafrente."
    _, pos, neg = scoring.señales(desc_cf, aviso_cf)
    assert "al frente" not in pos

    # Caso 2: Falso frente ('Tipo de frente: Cemento')
    aviso_cemento = {"id": "cem", "disposicion": "Contrafrente"}
    desc_cemento = "Tipo de frente: Cemento. Disposición contrafrente."
    _, pos, neg = scoring.señales(desc_cemento, aviso_cemento)
    assert "al frente" not in pos

    # Caso 3: Ventilación cruzada (frente y contrafrente en la unidad)
    aviso_cruz = {"id": "cruz", "disposicion": ""}
    desc_cruz = "Dormitorio al frente y dormitorio al contrafrente."
    _, pos, neg = scoring.señales(desc_cruz, aviso_cruz)
    assert "ventilación cruzada (frente y contrafrente)" in pos
    assert "al frente" not in pos
    assert "contrafrente" not in neg


def test_contrafrente_piso_alto_no_penaliza():
    """Venezuela 3100: 5.º piso contrafrente con balcón y luz no se penaliza."""
    desc = "Departamento de 2 ambientes ubicado en quinto piso contrafrente, excelente ventilación e iluminación."
    aviso = {"id": "59426994", "disposicion": "Contrafrente"}
    _, pos, neg = scoring.señales(desc, aviso)
    assert "contrafrente" not in neg
    assert any("tranquilo y luminoso" in p for p in pos)

    r, motivos = scoring.riesgo_humedad(aviso, desc)
    assert "poco sol / poca ventilación" not in motivos


def test_deteccion_duplicados_por_direccion_y_negociacion():
    """Zufriategui 4900 publicado por dos inmobiliarias a distinto precio."""
    a1 = {
        "id": "58969332", "direccion": "Zufriategui al 4900", "ambientes": 3,
        "costo_mensual": 1050000.0, "publicador": "Alejandro Ale"
    }
    a2 = {
        "id": "58554433", "direccion": "Zufriategui 4900", "ambientes": 3,
        "costo_mensual": 1000000.0, "publicador": "De Paola"
    }
    scoring.identificar_duplicados([a1, a2])
    assert a1.get("es_duplicado") and a2.get("es_duplicado")
    assert a1["disparidad_precio"] == 50000.0
    assert a2["disparidad_precio"] == 50000.0
    assert "ahorro de $50.000" in a2.get("nota_negociacion", "")
    assert "diferencia de $50.000 para negociar" in a1.get("nota_negociacion", "")


def test_parsear_contrato_requisitos():
    """Extrae de forma estructurada garantías, ajuste, mascotas, depósito y costos."""
    texto = (
        "Requisitos: 1 mes de adelanto + 1 mes de depósito en U$S 900. "
        "Garantía propietaria o FINAER seguro de caución. "
        "Ajuste trimestral por IPC. Plazo de locación 24 meses. "
        "No se aceptan mascotas. ABL y seguro de incendio a cargo del locatario."
    )
    c = scoring.parsear_contrato(texto)
    assert any("FINAER" in g for g in c["garantias_aceptadas"])
    assert any("Propietaria" in g for g in c["garantias_aceptadas"])
    assert c["politica_mascotas"] == "No acepta mascotas"
    assert "Trimestral" in c["ajuste_frecuencia"]
    assert c["ajuste_indice"] == "IPC"
    assert "U$S 900" in c["deposito_monto"] or "USD 900" in c["deposito_monto"]
    assert "2 años" in c["plazo_contrato"]
    assert any("ABL" in cost for cost in c["costos_adicionales"])


def test_calcular_dias_mercado():
    """Calcula los días en mercado desde fecha ISO."""
    ayer = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    dias = scoring.calcular_dias_mercado(ayer)
    assert dias == 10


def test_analizar_entorno_y_conectividad():
    """Detecta avenidas principales, trenes y clasificación de micro-entorno."""
    aviso = {"direccion": "Av. Laprida al 4500", "barrio": "Villa Martelli", "latitude": -34.54, "longitude": -58.48}
    desc = "Excelente ubicación a metros de Av. Mitre y próximo a estación Padilla."
    ent = scoring.analizar_entorno(aviso, desc)
    assert any("Laprida" in av for av in ent["avenidas_cercanas"])
    assert any("Mitre" in av for av in ent["avenidas_cercanas"])
    assert any("Padilla" in tr for tr in ent["estaciones_cercanas"])
    assert "Sobre/próximo a" in ent["entorno_tipo"]


def test_generar_preguntas_visita():
    """Genera preguntas técnicas personalizadas para la inspección y visita."""
    aviso_viejo_ph = {
        "id": "1", "tipo": "ph", "antiguedad_anios": 45,
        "expensas": 0.0, "expensas_informadas": True,
        "m2_confiable": False, "m2_usado": 110, "m2_cubierto_estimado": 55,
        "ajuste_indice": "No especifica",
    }
    preguntas = scoring.generar_preguntas_visita(aviso_viejo_ph)
    assert any("cañerías" in p for p in preguntas)
    assert any("bomba" in p or "tanque" in p for p in preguntas)
    assert any("terraza" in p or "cubiertos" in p for p in preguntas)
    assert any("IPC" in p or "ICL" in p for p in preguntas)


def test_calculo_caja_inicial_entrada():
    """Calcula el desembolso total de entrada con depósito en USD y honorarios PBA."""
    aviso_pba = {
        "precio": 1000000, "moneda": "ARS", "barrio": "Villa Martelli, Vicente López",
        "deposito_monto": "U$S 900", "es_dueno_directo": False,
    }
    total, resumen, desglose = scoring.calcular_caja_inicial(aviso_pba, dolar=1450.0)
    assert desglose["adelanto"] == 1000000.0
    assert desglose["deposito"] == 900.0 * 1450.0  # 1.305.000
    assert desglose["honorarios"] == 24 * 1000000.0 * 0.0415  # 996.000
    assert desglose["sellado"] == 24 * 1000000.0 * 0.005  # 120.000
    assert total > 3400000.0
    assert "USD 900" in resumen or "Depósito" in resumen


def test_deteccion_dueno_directo_sin_comision():
    """Detecta dueño directo, aplica bono en puntuar y calcula honorarios en $0."""
    aviso = {
        "id": "dd1", "precio": 800000, "moneda": "ARS", "m2_total": 50,
        "descripcion": "Dueño directo alquila 2 ambientes sin comisión inmobiliaria.",
        "barrio": "Villa Martelli",
    }
    r = scoring.puntuar([aviso], dolar=1450.0)[0]
    assert r["es_dueno_directo"] is True
    assert any("dueño directo" in m for m in r["motivos_a_favor"])
    assert r["caja_inicial_desglose"]["honorarios"] == 0.0


def test_tracker_bajas_precio():
    """Detecta bajas de precio comparando contra un historial previo."""
    actual = {"id": "1", "precio": 900000, "moneda": "ARS", "m2_total": 50, "descripcion": "depto"}
    previo = {"id": "1", "precio": 1000000, "moneda": "ARS"}
    r = scoring.puntuar([actual], dolar=1450.0, historial={"1": previo})[0]
    assert r.get("baja_precio") is True
    assert r["descuento_porcentaje"] == 10
    assert any("BAJA DE PRECIO" in m for m in r["motivos_a_favor"])


def test_alerta_gran_angular():
    """Genera alerta visual cuando las medidas son estrechas."""
    aviso = {"m2_cubierto_estimado": 40, "ambientes": 3}
    desc = "Gran living comedor con dormitorio principal de 2.20 x 2.40."
    alerta = scoring.detectar_alerta_gran_angular(aviso, desc)
    assert alerta is not None
    assert "gran angular" in alerta


def test_generador_prompt_llm(tmp_path):
    """Verifica que el generador del prompt maestro escriba PROMPT_LLM.md."""
    from zp import prompt
    avisos = [{"id": "123", "score": 85.0}]
    p = prompt.generar_prompt_diagnostico("test-run", avisos, tmp_path)
    assert p.exists()
    texto = p.read_text(encoding="utf-8")
    assert "INSTRUCCIONES DE AUDITORÍA FORENSE" in texto
    assert "Perito Arquitecto" in texto


def test_simular_evolucion_alquiler():
    """Calcula la evolución de la cuota con saltos trimestrales y suma total."""
    aviso = {"precio": 1000000, "moneda": "ARS", "ajuste_frecuencia": "Trimestral"}
    sim = scoring.simular_evolucion_alquiler(aviso, inflacion_mensual=0.03)
    assert sim["mes_1"] == 1000000.0
    assert sim["mes_6"] > 1000000.0
    assert sim["mes_24"] > sim["mes_12"] > sim["mes_1"]
    assert sim["total_2_anios"] > 24000000.0


def test_generar_ficha_visita_y_mensajes(tmp_path):
    """Verifica que se generen ficha_visita.md y mensajes_inmobiliarias.txt."""
    from zp import visita
    avisos = [{
        "id": "59658007", "score": 85.0, "tipo": "ph", "costo_mensual": 800000,
        "direccion": "Laprida 4500", "ambientes": 3, "preguntas_visita": ["¿Presión de agua?"]
    }]
    fv = visita.generar_ficha_visita("test-run", avisos, tmp_path)
    msg = visita.generar_mensajes_inmobiliarias("test-run", avisos, tmp_path)
    assert fv.exists()
    assert msg.exists()
    assert "PROTOCOLO FORENSE" in fv.read_text(encoding="utf-8")
    assert "59658007" in msg.read_text(encoding="utf-8")


def test_exportar_mapas_geojson_kml(tmp_path):
    """Verifica la exportación de candidatos.geojson y recorrido_visitas.kml."""
    from zp import mapa
    avisos = [{
        "id": "1", "score": 80.0, "latitude": -34.54, "longitude": -58.48,
        "costo_mensual": 800000, "direccion": "Laprida 1000", "descartado": False
    }]
    gj = mapa.exportar_geojson("test-run", avisos, tmp_path)
    kml = mapa.exportar_kml("test-run", avisos, tmp_path)
    assert gj.exists()
    assert kml.exists()
    assert "FeatureCollection" in gj.read_text(encoding="utf-8")
    assert "<kml" in kml.read_text(encoding="utf-8")


def test_geocodificador_real():
    """Verifica el normalizador y geocodificador real con caché."""
    from zp import geocodificador
    assert geocodificador.normalizar_direccion("Av. La Plata al 1400 3° B") == "Av. La Plata 1400"
    assert geocodificador.normalizar_direccion("Pasaje Faraday al 1560") == "Pasaje Faraday 1560"
    assert geocodificador.tiene_altura_o_calle("Beauchef 1300") is True
    assert geocodificador.tiene_altura_o_calle("Parque Chacabuco") is False

    aviso_con_gps = {"latitude": -34.614, "longitude": -58.445, "direccion": "Sin dir"}
    assert geocodificador.obtener_coordenadas_reales(aviso_con_gps) == (-34.614, -58.445)


def test_fallo_de_red_no_envenena_la_cache(monkeypatch):
    """Un corte de red NO debe quedar cacheado como 'no geocodificable'.

    Si se cachea el None de un timeout, esa dirección no se reintenta nunca más:
    la corrida siguiente encuentra la clave y devuelve None sin consultar. El
    negativo legítimo (Nominatim contestó y no encontró nada) sí se cachea.
    """
    from zp import geocodificador

    geocodificador._cargar_cache()
    calles = dict(geocodificador._CACHE)  # restaurar al final
    try:
        geocodificador._CACHE.clear()

        # 1) La red falla: no se cachea nada, se puede reintentar.
        def _explota(*a, **k):
            raise TimeoutError("connection timed out")

        monkeypatch.setattr(geocodificador.urllib.request, "urlopen", _explota)
        monkeypatch.setattr(geocodificador.time, "sleep", lambda s: None)
        assert geocodificador.geocodificar_direccion("Beauchef 1300", "Caballito") is None
        assert geocodificador._CACHE == {}, "un fallo de red no se debe cachear"

        # 2) Nominatim contesta y no encuentra nada: eso sí se cachea.
        class _RespuestaVacia:
            def read(self):
                return b"[]"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        monkeypatch.setattr(geocodificador.urllib.request, "urlopen",
                            lambda *a, **k: _RespuestaVacia())
        assert geocodificador.geocodificar_direccion("Beauchef 1300", "Caballito") is None
        assert geocodificador._CACHE == {"beauchef 1300|caballito": None}
    finally:
        geocodificador._CACHE.clear()
        geocodificador._CACHE.update(calles)
        geocodificador._CAMBIOS_PENDIENTES = 0


def test_parsear_detalle_coordenadas_invertidas():
    """Verifica que si el JSON trae longitude antes de latitude, no queden invertidas."""
    html_inv = '<html><script>{"longitude": -58.456789, "latitude": -34.567890}</script></html>'
    d = parseo.parsear_detalle(html_inv)
    assert d.get("latitude") == -34.567890
    assert d.get("longitude") == -58.456789


def test_exportar_geojson_con_geocodificacion_fallback(tmp_path, monkeypatch):
    """Verifica que un aviso sin latitude/longitude use el geocodificador y termine en el GeoJSON."""
    import json
    from zp import mapa

    monkeypatch.setattr(
        "zp.geocodificador.geocodificar_direccion",
        lambda direccion, barrio="": (-34.5678, -58.4567)
    )

    aviso_sin_coords = {
        "id": "59999999",
        "score": 85.0,
        "direccion": "Av. Cabildo 2000",
        "barrio": "Belgrano",
        "costo_mensual": 900000,
        "descartado": False,
    }

    gj = mapa.exportar_geojson("test-geocoding", [aviso_sin_coords], tmp_path)
    assert gj.exists()
    datos = json.loads(gj.read_text(encoding="utf-8"))
    assert len(datos["features"]) == 1
    feat = datos["features"][0]
    # En GeoJSON las coordenadas van [longitud, latitud]
    assert feat["geometry"]["coordinates"] == [-58.4567, -34.5678]
    assert feat["properties"]["id"] == "59999999"
    assert feat["properties"]["direccion"] == "Av. Cabildo 2000"


def test_rankear_geocodifica_avisos_vivos(tmp_path, monkeypatch):
    """Verifica que el comando rankear geocodifique los candidatos vivos y persista coords."""
    import json

    monkeypatch.setattr(
        "zp.geocodificador.geocodificar_direccion",
        lambda direccion, barrio="": (-34.5800, -58.4200)
    )

    aviso = {
        "id": "101",
        "direccion": "Güemes 3500",
        "barrio": "Palermo",
        "precio": 800000,
        "moneda": "ARS",
        "expensas": 80000,
        "expensas_informadas": True,
        "m2_total": 45,
        "ambientes": 2,
    }
    carpeta_run = tmp_path / "test-run"
    carpeta_run.mkdir(parents=True, exist_ok=True)
    (carpeta_run / "listado.json").write_text(json.dumps([aviso]), encoding="utf-8")

    class Args:
        run = "test-run"
        presupuesto = 1000000
        dolar = 1450
        top = 10

    monkeypatch.setattr(cli, "SALIDA", tmp_path)

    ret = cli.cmd_rankear(Args)
    assert ret == 0

    ranking = json.loads((carpeta_run / "ranking.json").read_text(encoding="utf-8"))
    assert len(ranking) == 1
    assert ranking[0]["latitude"] == -34.5800
    assert ranking[0]["longitude"] == -58.4200


# --------------------------------------------------------------------------- #
# Cotización del dólar (zp/cotizacion.py)
# --------------------------------------------------------------------------- #

def test_cotizacion_cache_de_hoy_sin_red(tmp_path, monkeypatch):
    """Si existe caché con fecha de hoy, se utiliza de inmediato sin consultar la red."""
    import json
    from unittest.mock import MagicMock
    from zp import cotizacion

    hoy = datetime.date.today().isoformat()
    cache_file = tmp_path / ".cotizacion.json"
    cache_file.write_text(
        json.dumps({"fecha": hoy, "valor": 1520.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(cotizacion, "CACHE_FILE", cache_file)

    mock_urlopen = MagicMock(side_effect=AssertionError("No debería conectar a la red si hay caché de hoy"))
    monkeypatch.setattr(cotizacion.urllib.request, "urlopen", mock_urlopen)

    valor, origen = cotizacion.obtener_dolar()
    assert valor == 1520.0
    assert origen == "caché de hoy"
    mock_urlopen.assert_not_called()


def test_cotizacion_fallback_cuando_red_falla(tmp_path, monkeypatch):
    """Si la red falla y no hay caché de hoy, devuelve silenciosamente DOLAR_FALLBACK."""
    from unittest.mock import MagicMock
    from zp import cotizacion

    cache_file = tmp_path / ".cotizacion.json"
    monkeypatch.setattr(cotizacion, "CACHE_FILE", cache_file)

    mock_urlopen = MagicMock(side_effect=cotizacion.urllib.error.URLError("Sin conexión"))
    monkeypatch.setattr(cotizacion.urllib.request, "urlopen", mock_urlopen)

    valor, origen = cotizacion.obtener_dolar()
    assert valor == cotizacion.DOLAR_FALLBACK
    assert origen == "fallback"


def test_cotizacion_valor_implausible_cae_a_fallback(tmp_path, monkeypatch):
    """Si la API devuelve un valor absurdo o datos basura, se descarta y cae al fallback."""
    from unittest.mock import MagicMock
    from zp import cotizacion

    cache_file = tmp_path / ".cotizacion.json"
    monkeypatch.setattr(cotizacion, "CACHE_FILE", cache_file)

    def _mock_respuesta(cuerpo: bytes):
        mock_resp = MagicMock()
        mock_resp.read.return_value = cuerpo
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp

    # Caso 1: valor excesivamente alto (> 100000)
    monkeypatch.setattr(
        cotizacion.urllib.request, "urlopen",
        MagicMock(return_value=_mock_respuesta(b'{"venta": 999999999}'))
    )
    v1, o1 = cotizacion.obtener_dolar()
    assert v1 == cotizacion.DOLAR_FALLBACK
    assert o1 == "fallback"

    # Caso 2: valor por debajo del límite plausible (< 100)
    monkeypatch.setattr(
        cotizacion.urllib.request, "urlopen",
        MagicMock(return_value=_mock_respuesta(b'{"venta": 50}'))
    )
    v2, o2 = cotizacion.obtener_dolar()
    assert v2 == cotizacion.DOLAR_FALLBACK
    assert o2 == "fallback"

    # Caso 3: respuesta sin campo 'venta' o con basura
    monkeypatch.setattr(
        cotizacion.urllib.request, "urlopen",
        MagicMock(return_value=_mock_respuesta(b'{"moneda": "USD", "casa": "blue"}'))
    )
    v3, o3 = cotizacion.obtener_dolar()
    assert v3 == cotizacion.DOLAR_FALLBACK
    assert o3 == "fallback"


def test_cotizacion_api_exitosa_guarda_cache(tmp_path, monkeypatch):
    """Si la API responde correctamente con un valor plausible, se persiste en caché de hoy."""
    import json
    from unittest.mock import MagicMock
    from zp import cotizacion

    cache_file = tmp_path / ".cotizacion.json"
    monkeypatch.setattr(cotizacion, "CACHE_FILE", cache_file)

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"venta": 1490.0}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    monkeypatch.setattr(
        cotizacion.urllib.request, "urlopen",
        MagicMock(return_value=mock_resp)
    )

    valor, origen = cotizacion.obtener_dolar()
    assert valor == 1490.0
    assert origen == "api"
    assert cache_file.exists()

    guardado = json.loads(cache_file.read_text(encoding="utf-8"))
    assert guardado["valor"] == 1490.0
    assert guardado["fecha"] == datetime.date.today().isoformat()


# --------------------------------------------------------------------------- #
# Historial de precios (zp/historial.py)
# --------------------------------------------------------------------------- #

def test_historial_detecta_baja_precio_entre_snapshots(tmp_path):
    """Una baja entre dos corridas se detecta vía detectar_bajas_precio.

    Respeta el orden real de cmd_rankear: cargar -> puntuar -> registrar. O sea
    que al puntuar, el historial TODAVÍA NO tiene el precio de hoy.
    """
    from zp import historial as mod_historial

    # Corrida 1: el aviso se publica a $900.000 y se registra.
    mod_historial.registrar(tmp_path, [{"id": "av1", "precio": 900000, "expensas": 70000}])

    # Corrida 2: hoy sale $800.000. Se carga el historial ANTES de registrar.
    h = mod_historial.cargar(tmp_path)
    ult = mod_historial.ultimo_precio(h)
    assert ult["av1"]["precio"] == 900000

    aviso_actual = [{"id": "av1", "precio": 800000, "moneda": "ARS"}]
    scoring.detectar_bajas_precio(aviso_actual, ult)

    assert aviso_actual[0].get("baja_precio") is True
    assert aviso_actual[0]["descuento_porcentaje"] == 11
    assert aviso_actual[0]["precio_anterior"] == 900000
    assert "Bajó un 11%" in aviso_actual[0]["nota_baja_precio"]

    # Y recién ahora se registra la corrida de hoy.
    mod_historial.registrar(tmp_path, aviso_actual)
    assert len(mod_historial.cargar(tmp_path)["av1"]["snapshots"]) == 2


def test_historial_compara_contra_la_corrida_anterior_no_contra_la_primera(tmp_path):
    """Con tres corridas, la referencia es la ÚLTIMA conocida, no la penúltima.

    Regresión: tomar snapshots[-2] compara contra dos corridas atrás e infla el
    descuento. Con 1000 -> 900 -> hoy 800, la baja reportable es del 11% contra
    los 900 de la corrida pasada, no del 20% contra los 1000 del principio.
    """
    from zp import historial as mod_historial

    mod_historial.registrar(tmp_path, [{"id": "av1", "precio": 1000000}])   # corrida 1
    mod_historial.registrar(tmp_path, [{"id": "av1", "precio": 900000}])    # corrida 2

    ult = mod_historial.ultimo_precio(mod_historial.cargar(tmp_path))
    assert ult["av1"]["precio"] == 900000, "debe comparar contra la corrida anterior"

    actual = [{"id": "av1", "precio": 800000, "moneda": "ARS"}]
    scoring.detectar_bajas_precio(actual, ult)
    assert actual[0]["descuento_porcentaje"] == 11


def test_historial_no_duplica_snapshots_mismo_precio(tmp_path):
    """Verifica que registrar dos veces el mismo precio no duplica snapshots."""
    from zp import historial as mod_historial

    aviso = [{"id": "av1", "precio": 800000, "expensas": 50000}]
    mod_historial.registrar(tmp_path, aviso)
    mod_historial.registrar(tmp_path, aviso)
    mod_historial.registrar(tmp_path, aviso)

    h = mod_historial.cargar(tmp_path)
    assert len(h["av1"]["snapshots"]) == 1


def test_historial_resumen_bajas():
    """resumen_bajas devuelve el texto de bajas sucesivas solo si hubo más de una baja; si no, None."""
    from zp import historial as mod_historial

    # Caso 1: solo 1 baja registrada en el tiempo -> None
    h_una_baja = {
        "av1": {
            "snapshots": [
                {"fecha": "2026-08-01", "precio": 900000},
                {"fecha": "2026-08-20", "precio": 800000},
            ]
        }
    }
    assert mod_historial.resumen_bajas(h_una_baja, "av1") is None

    # Caso 2: 2 bajas sucesivas en 40 días -> formato descriptivo para negociación
    h_dos_bajas = {
        "av1": {
            "snapshots": [
                {"fecha": "2026-08-01", "precio": 850000},
                {"fecha": "2026-08-20", "precio": 800000},
                {"fecha": "2026-09-10", "precio": 700000},
            ]
        }
    }
    res = mod_historial.resumen_bajas(h_dos_bajas, "av1")
    assert res is not None
    assert res == "bajó 2 veces en 40 días: $850.000 -> $700.000 (-18%)"


def test_rankear_con_dolar_automatico_e_historial(tmp_path, monkeypatch):
    """Verifica que cmd_rankear sin --dolar consulte la cotización, registre historial y agregue nota_historial."""
    import json
    from unittest.mock import MagicMock
    from zp import cotizacion, historial as mod_historial

    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    monkeypatch.setattr(
        "zp.geocodificador.geocodificar_direccion",
        lambda direccion, barrio="": (-34.5800, -58.4200)
    )

    # Mock de cotización automática
    monkeypatch.setattr(
        "zp.cotizacion.obtener_dolar",
        lambda forzar=False: (1500.0, "api")
    )

    carpeta_run = tmp_path / "run-historial"
    carpeta_run.mkdir(parents=True, exist_ok=True)

    # Pre-cargamos un historial previo donde el aviso bajó dos veces
    historial_previo = {
        "201": {
            "snapshots": [
                {"fecha": "2026-08-01", "precio": 1000000, "expensas": 50000},
                {"fecha": "2026-08-20", "precio": 900000, "expensas": 50000},
            ]
        }
    }
    (carpeta_run / "historial.json").write_text(
        json.dumps(historial_previo, ensure_ascii=False), encoding="utf-8"
    )

    # Aviso actual a $800.000 (3ra baja)
    aviso = {
        "id": "201",
        "direccion": "Av. Santa Fe 3000",
        "barrio": "Palermo",
        "precio": 800000,
        "moneda": "ARS",
        "expensas": 50000,
        "expensas_informadas": True,
        "m2_total": 50,
        "ambientes": 2,
    }
    (carpeta_run / "listado.json").write_text(json.dumps([aviso]), encoding="utf-8")

    class Args:
        run = "run-historial"
        presupuesto = 1200000
        dolar = None
        top = 10

    ret = cli.cmd_rankear(Args)
    assert ret == 0

    ranking = json.loads((carpeta_run / "ranking.json").read_text(encoding="utf-8"))
    assert len(ranking) == 1
    a = ranking[0]
    # Se detectó baja respecto al precio anterior
    assert a.get("baja_precio") is True
    # Contiene la nota_historial calculada con resumen_bajas
    assert "nota_historial" in a
    assert "bajó 2 veces" in a["nota_historial"]

    # El historial guardado en disco ahora tiene 3 snapshots
    hist_disco = mod_historial.cargar(carpeta_run)
    assert len(hist_disco["201"]["snapshots"]) == 3

