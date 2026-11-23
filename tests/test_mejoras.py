"""Tests de la auditoría con la API, el seguimiento, las novedades y los
arreglos del ranking que salieron de mirar las corridas reales.

Ningún test llama a la API de Claude: el cliente se reemplaza por uno falso
que devuelve respuestas con la misma forma que el SDK.

    python -m pytest tests/ -q
"""

from __future__ import annotations

import argparse
import importlib.util as _il
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from PIL import Image

import fixture_listado as fx
from zp import auditor, corrida, dashboard, fotos, historial, scoring, seguimiento, visita

_spec = _il.spec_from_file_location("cli_zp_mejoras", Path(__file__).resolve().parents[1] / "zp.py")
cli = _il.module_from_spec(_spec)
_spec.loader.exec_module(cli)


# --------------------------------------------------------------------------- #
# Auditor
# --------------------------------------------------------------------------- #

def _veredicto(**cambios) -> dict:
    base = {
        "veredicto": "CON_RESERVAS", "score_visual": 70, "confianza": "media",
        "resumen": "Cocina reformada, mancha en el baño.", "vicio_critico": None,
        "hallazgos": [{"foto": 2, "tipo": "humedad", "gravedad": "media", "observacion": "mancha"}],
        "contradicciones": [], "fotos_a_revisar_en_visita": [2],
        "preguntas_visita": ["¿La mancha viene de arriba?"],
        "pregunta_para_inmobiliaria": "¿Se arregló la filtración?",
        "negociacion": None, "diferencias_con_revision_previa": None,
    }
    base.update(cambios)
    return base


def _respuesta(datos: dict, modelo: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(datos))],
        stop_reason=stop_reason, model=modelo,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500,
                              cache_creation_input_tokens=0, cache_read_input_tokens=3000),
    )


class ClienteFalso:
    def __init__(self, fabrica):
        self.pedidos = []
        self.fabrica = fabrica
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._crear))

    def _crear(self, **kw):
        self.pedidos.append(kw)
        return self.fabrica(kw)


def _corrida_con_fotos(tmp_path: Path, ids: list[str], numeros=(1, 2, 3)) -> tuple[Path, list[dict]]:
    carpeta = tmp_path / "run"
    ranking = []
    for i, aid in enumerate(ids):
        dir_fotos = carpeta / "fotos" / aid
        dir_fotos.mkdir(parents=True)
        rutas = []
        for n in numeros:
            ruta = dir_fotos / f"{n:02d}.jpg"
            Image.new("RGB", (60, 40), (120 + n, 90, 80)).save(ruta, "JPEG")
            rutas.append(ruta)
        fotos.hoja_contacto(rutas, carpeta / "contactos" / f"{aid}.jpg", f"aviso {aid}")
        ranking.append({"id": aid, "score": 80 - i, "descartado": False, "precio": 800000,
                        "moneda": "ARS", "direccion": f"Calle {aid}", "descripcion": "Luminoso."})
    return carpeta, ranking


def test_auditor_guarda_saltea_lo_que_no_cambio_y_valida_fotos(tmp_path, capsys):
    carpeta, ranking = _corrida_con_fotos(tmp_path, ["a1", "a2"])
    cliente = ClienteFalso(lambda kw: _respuesta(
        _veredicto(hallazgos=[
            {"foto": 2, "tipo": "humedad", "gravedad": "media", "observacion": "mancha real"},
            {"foto": 9, "tipo": "otro", "gravedad": "leve", "observacion": "foto inventada"},
        ], fotos_a_revisar_en_visita=[2, 9]), kw["model"]))

    r = auditor.auditar_corrida(carpeta, ranking, top=5, cliente=cliente)
    assert r["auditados"] == 2 and r["errores"] == 0

    datos = json.loads((carpeta / "auditoria.json").read_text(encoding="utf-8"))
    v = datos["avisos"]["a1"]["primera"]["veredicto"]
    # La foto 9 no existe: el hallazgo se descarta en vez de mostrarse como hecho.
    assert [h["foto"] for h in v["hallazgos"]] == [2]
    assert v["fotos_a_revisar_en_visita"] == [2]
    assert "foto 9" in capsys.readouterr().out

    # La primera revisión es Sonnet y manda la hoja de contacto.
    pedido = cliente.pedidos[0]
    assert pedido["model"] == "claude-sonnet-5-5"
    assert [b["type"] for b in pedido["messages"][0]["content"]].count("image") == 1
    assert pedido["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert pedido["output_config"]["format"]["type"] == "json_schema"

    # Segunda corrida sin cambios: no se vuelve a pagar.
    r2 = auditor.auditar_corrida(carpeta, ranking, top=5, cliente=cliente)
    assert r2["salteados"] == 2 and len(cliente.pedidos) == 2

    # Si cambia la descripción, se vuelve a auditar ese aviso.
    ranking[0]["descripcion"] = "Ahora dice otra cosa."
    auditor.auditar_corrida(carpeta, ranking, top=5, cliente=cliente)
    assert len(cliente.pedidos) == 3
    assert (carpeta / "auditoria.md").exists()


def test_segunda_revision_usa_opus_fotos_sueltas_y_la_revision_previa(tmp_path):
    carpeta, ranking = _corrida_con_fotos(tmp_path, ["a1", "a2"])
    veredictos = iter(["APROBADO", "DESCARTADO"])
    cliente = ClienteFalso(lambda kw: _respuesta(_veredicto(veredicto=next(veredictos)), kw["model"]))
    auditor.auditar_corrida(carpeta, ranking, top=5, cliente=cliente)

    segundo = ClienteFalso(lambda kw: _respuesta(
        _veredicto(veredicto="CON_RESERVAS", diferencias_con_revision_previa="corrijo"), kw["model"]))
    r = auditor.auditar_corrida(carpeta, ranking, etapa="segunda", top=5, cliente=segundo)

    # Sólo el que Sonnet no descartó.
    assert r["auditados"] == 1 and len(segundo.pedidos) == 1
    pedido = segundo.pedidos[0]
    assert pedido["model"] == "claude-opus-5-5"
    contenido = pedido["messages"][0]["content"]
    assert sum(1 for b in contenido if b["type"] == "image") == 3   # las tres fotos sueltas
    assert any("Foto 2" == b.get("text") for b in contenido)
    assert any("Revisión previa" in b.get("text", "") for b in contenido)

    # El vigente es el de Opus.
    avisos = [dict(a) for a in ranking]
    auditor.anotar_avisos(carpeta, avisos)
    assert avisos[0]["auditoria"]["etapa"] == "segunda"
    assert avisos[0]["auditoria"]["veredicto"] == "CON_RESERVAS"
    assert avisos[1]["auditoria"]["etapa"] == "primera"


def test_sin_credenciales_corta_sin_romper_ni_guardar_basura(tmp_path, capsys):
    carpeta, ranking = _corrida_con_fotos(tmp_path, ["a1", "a2"])

    def sin_clave(_kw):
        raise TypeError("Could not resolve authentication method. Expected one of api_key...")

    r = auditor.auditar_corrida(carpeta, ranking, top=5, cliente=ClienteFalso(sin_clave))
    assert r["cortado"] and r["auditados"] == 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out
    assert not (carpeta / "auditoria.json").exists()


def test_refusal_queda_como_error_y_se_reintenta(tmp_path):
    carpeta, ranking = _corrida_con_fotos(tmp_path, ["a1"])
    cliente = ClienteFalso(lambda kw: _respuesta(_veredicto(), kw["model"], stop_reason="refusal"))
    r = auditor.auditar_corrida(carpeta, ranking, top=5, cliente=cliente)
    assert r["errores"] == 1
    entrada = json.loads((carpeta / "auditoria.json").read_text(encoding="utf-8"))["avisos"]["a1"]["primera"]
    assert "error" in entrada and "huella" not in entrada

    bien = ClienteFalso(lambda kw: _respuesta(_veredicto(), kw["model"]))
    assert auditor.auditar_corrida(carpeta, ranking, top=5, cliente=bien)["auditados"] == 1


def test_el_prompt_dice_las_garantias_reales():
    texto = auditor.prompt_sistema()
    assert "CABA" in texto and "Vicente López" in texto
    assert "No descartes un aviso por pedir garantía propietaria" in texto


# --------------------------------------------------------------------------- #
# Fotos: numeración estable
# --------------------------------------------------------------------------- #

def test_una_foto_rota_no_corre_la_numeracion(tmp_path, monkeypatch):
    import io

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 10, 10)).save(buf, "JPEG")
    bytes_ok = buf.getvalue()

    def get(url, **_kw):
        if "rota" in url:
            raise OSError("se cortó")
        return SimpleNamespace(content=bytes_ok, raise_for_status=lambda: None)

    monkeypatch.setattr(fotos.requests, "get", get)
    urls_ = ["https://x/1.jpg", "https://x/rota.jpg", "https://x/3.jpg"]
    rutas = fotos.descargar(urls_, tmp_path / "f", maximo=16)
    assert [r.name for r in rutas] == ["01.jpg", "03.jpg"]
    assert [fotos.numero_de_foto(r, i + 1) for i, r in enumerate(rutas)] == [1, 3]

    # Si la galería cambia, el slot con URL distinta se vuelve a bajar.
    llamadas = []
    monkeypatch.setattr(fotos.requests, "get",
                        lambda url, **kw: llamadas.append(url) or get(url))
    fotos.descargar(["https://x/1.jpg", "https://x/nueva.jpg", "https://x/3.jpg"], tmp_path / "f")
    assert llamadas == ["https://x/nueva.jpg"]


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #

def test_cochera_en_subsuelo_no_es_un_departamento_en_subsuelo():
    _, _, neg = scoring.señales("Sexto piso al frente. Cochera doble en primer subsuelo.")
    assert "subsuelo" not in neg
    _, _, neg = scoring.señales("Departamento en semisubsuelo con patio.")
    assert "subsuelo" in neg


def test_planta_baja_de_amenities_o_de_edificio_no_penaliza():
    for texto in ("Hall de acceso en planta baja. Piso 7.",
                  "Edificio de PB + 8 pisos, unidad en el 5to piso.",
                  "Amenities: sum, pileta y laundry en planta baja."):
        _, _, neg = scoring.señales(texto)
        assert "planta baja (más riesgo de humedad)" not in neg, texto
    _, _, neg = scoring.señales("Departamento en planta baja, con cochera opcional.")
    assert "planta baja (más riesgo de humedad)" in neg


def test_mascotas_una_sola_fuente():
    for texto in ("No apto mascotas.", "No se permiten animales.", "Mascotas: no"):
        assert scoring.politica_mascotas(texto) == "No acepta mascotas", texto
        assert scoring.parsear_contrato(texto)["politica_mascotas"] == "No acepta mascotas"
        _, pos, neg = scoring.señales(texto)
        assert "acepta mascotas" not in pos and "no acepta mascotas" in neg
    assert scoring.politica_mascotas("Apto mascotas.") == "Acepta mascotas"


def test_regex_que_sumaban_al_reves():
    _, pos, _ = scoring.señales("Departamento sin cochera.")
    assert "cochera" not in pos
    _, pos, _ = scoring.señales("Living con balcón francés.")
    assert "espacio exterior" not in pos
    _, pos, neg = scoring.señales("Dormitorio poco luminoso.")
    assert "luminoso" not in pos and "poco luminoso" in neg
    pts_muy, pos, _ = scoring.señales("Muy luminoso.")
    assert pos == ["muy luminoso"] and pts_muy == 6
    _, _, neg = scoring.señales("Noveno piso, interno pero muy luminoso, con vista al pulmón de manzana.")
    assert "unidad interna" not in neg


def test_valor_no_se_satura():
    assert scoring.valor_por_precio(1.0) == pytest.approx(0.5)
    curva = [scoring.valor_por_precio(r) for r in (0.6, 0.8, 1.0, 1.3, 1.45, 1.8, 2.5)]
    assert curva == sorted(curva) and len(set(curva)) == len(curva)
    assert curva[-1] < 1.0


def test_ambientes_fuera_de_lo_buscado_y_presupuesto():
    base = dict(moneda="ARS", expensas=100000, expensas_informadas=True,
                descripcion="Departamento luminoso al frente.")
    avisos = [{**base, "id": f"c{i}", "precio": 700000, "m2_total": 45, "ambientes": 2} for i in range(6)]
    casa = {**base, "id": "casa", "precio": 900000, "m2_total": 140, "ambientes": 5}
    r = {a["id"]: a for a in scoring.puntuar(avisos + [casa], presupuesto=1100000, dolar=1450,
                                               ambientes_buscados=[2, 3])}
    assert any("5 ambientes (buscaste 2-3)" in m for m in r["casa"]["motivos_en_contra"])
    assert any("presupuesto" in m for m in r["c0"]["motivos_a_favor"])


def test_duplicados_exigen_misma_superficie_y_toleran_un_typo():
    a = {"id": "1", "direccion": "Gaona 2000", "ambientes": 3, "m2_total": 123, "costo_mensual": 900000}
    b = {"id": "2", "direccion": "Gaona 2043", "ambientes": 3, "m2_total": 69, "costo_mensual": 700000}
    scoring.identificar_duplicados([a, b])
    assert not a.get("es_duplicado") and not b.get("es_duplicado")

    c = {"id": "3", "direccion": "JOSE P. TAMBORINI 6000", "ambientes": 2, "m2_total": 50, "costo_mensual": 850000}
    d = {"id": "4", "direccion": "JOSE P. TEMBORINI 6010", "ambientes": 2, "m2_total": 51, "costo_mensual": 815000}
    e = {"id": "5", "direccion": "JOSE P. TAMBORINI 6050", "ambientes": 2, "m2_total": 50, "costo_mensual": 800000}
    scoring.identificar_duplicados([c, d, e])
    assert c["es_duplicado"] and d["es_duplicado"] and e["es_duplicado"]
    # La diferencia de cada uno contra el más barato, no la del grupo entero.
    assert "diferencia de $15.000" in d["nota_negociacion"]
    assert "diferencia de $50.000" in c["nota_negociacion"]


def test_baja_de_precio_no_mezcla_monedas_y_suma_puntos():
    a = [{"id": "x", "precio": 650, "moneda": "USD"}]
    scoring.detectar_bajas_precio(a, {"x": {"precio": 900000, "moneda": "ARS"}})
    assert not a[0].get("baja_precio")

    base = dict(moneda="ARS", expensas=100000, expensas_informadas=True, m2_total=45,
                ambientes=2, descripcion="Departamento al frente.")
    avisos = [{**base, "id": f"c{i}", "precio": 700000} for i in range(6)]
    sin = {a["id"]: a for a in scoring.puntuar([dict(x) for x in avisos], dolar=1450)}
    con = {a["id"]: a for a in scoring.puntuar(
        [dict(x) for x in avisos], dolar=1450, historial={"c0": {"precio": 800000, "moneda": "ARS"}})}
    assert con["c0"]["baja_precio"] and con["c0"]["score"] > sin["c0"]["score"]


def test_sin_expensas_extraordinarias_no_es_sin_expensas():
    from zp import parseo
    assert parseo._leer_expensas("", "Sin expensas extraordinarias. Expensas aparte.") == (None, False)
    assert parseo._leer_expensas("", "PH sin expensas.") == (0.0, True)


# --------------------------------------------------------------------------- #
# Historial, novedades y corrida
# --------------------------------------------------------------------------- #

def test_novedades_entre_dos_busquedas(tmp_path):
    historial.registrar(tmp_path, [
        {"id": "a", "precio": 900000, "direccion": "Uno 100"},
        {"id": "b", "precio": 800000, "direccion": "Dos 200"},
    ], fecha="2026-11-01")
    historial.registrar(tmp_path, [
        {"id": "a", "precio": 850000},
        {"id": "c", "precio": 700000},
    ], fecha="2026-11-10")
    nov = historial.novedades(historial.cargar(tmp_path), [
        {"fecha": "2026-11-01", "completo": True}, {"fecha": "2026-11-10", "completo": True}])
    assert nov["nuevos"] == ["c"]
    assert [r["id"] for r in nov["retirados"]] == ["b"]
    assert nov["bajas"][0]["id"] == "a" and nov["bajas"][0]["pct"] == -6

    # Si la última búsqueda se cortó, no se puede afirmar que algo se retiró.
    nov = historial.novedades(historial.cargar(tmp_path), [
        {"fecha": "2026-11-01", "completo": True}, {"fecha": "2026-11-10", "completo": False}])
    assert nov["retirados"] == []
    assert historial.novedades({}, [{"fecha": "2026-11-01"}]) is None


def test_rankear_conserva_el_detalle_y_fotos_usa_los_mismos_parametros(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    monkeypatch.setattr("zp.geocodificador.geocodificar_direccion", lambda d, b="": None)
    carpeta = tmp_path / "run"
    base = dict(moneda="ARS", expensas=100000, expensas_informadas=True, m2_total=45,
                ambientes=2, descripcion="Departamento al frente, luminoso.")
    listado = [{**base, "id": f"c{i}", "precio": 700000} for i in range(6)]
    listado.append({**base, "id": "caro", "precio": 1500000})
    carpeta.mkdir()
    (carpeta / "listado.json").write_text(json.dumps(listado), encoding="utf-8")
    corrida.guardar_detalle(carpeta, "c0", {"dias_publicado": 40, "antiguedad": "20"})

    Args = argparse.Namespace(run="run", presupuesto=1000000, dolar=1450, top=5)
    assert cli.cmd_rankear(Args) == 0
    r = {a["id"]: a for a in json.loads((carpeta / "ranking.json").read_text(encoding="utf-8"))}
    assert r["c0"]["dias_publicado"] == 40
    assert r["caro"]["descartado"]

    # Lo que hacía `fotos`: volver a puntuar sin presupuesto revivía al caro.
    params = corrida.cargar_parametros(carpeta)
    assert params["presupuesto"] == 1000000
    ordenados = corrida.puntuar_corrida(carpeta, list(r.values()), params["presupuesto"], params["dolar"])
    assert {a["id"]: a for a in ordenados}["caro"]["descartado"]


class _SesionFalsa:
    canal = "falso"

    def __init__(self, DesafioError, falla_en: int):
        self.DesafioError = DesafioError
        self.falla_en = falla_en
        self.pedidas = 0
        self.pagina = SimpleNamespace(content=fx.html)

    def calentar(self):
        pass

    def ir(self, url, espera_selector=None):
        self.pedidas += 1
        if self.pedidas >= self.falla_en:
            raise self.DesafioError("Zonaprop pidió verificación")
        return fx.html()

    def scrollear(self):
        pass

    def esperar(self):
        pass


def test_buscar_guarda_lo_bajado_aunque_aparezca_el_captcha(tmp_path, monkeypatch, capsys):
    from contextlib import contextmanager
    from zp.navegador import DesafioError

    @contextmanager
    def navegador(*_a, **_kw):
        yield _SesionFalsa(DesafioError, falla_en=2)

    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    monkeypatch.setattr(cli, "_navegador", lambda: (DesafioError, navegador))
    args = argparse.Namespace(
        zona=["vicente-lopez"], ambientes=[2], tipos=["departamentos", "ph"], operacion="alquiler",
        paginas=5, precio_max=None, run="vl", headless=False, rapido=True, espera_captcha=1, canal="chrome")

    assert cli.cmd_buscar(args) == cli.SALIDA_DESAFIO
    listado = json.loads((tmp_path / "vl" / "listado.json").read_text(encoding="utf-8"))
    assert len(listado) > 0 and all(a["visto_en"] for a in listado)
    params = corrida.cargar_parametros(tmp_path / "vl")
    assert params["busquedas"][-1]["completo"] is False
    assert params["ambientes"] == [2]
    assert "INCOMPLETA" in capsys.readouterr().out


def test_corrida_vieja_muestra_novedades_en_la_primera_busqueda_nueva(tmp_path, monkeypatch):
    """Las corridas de antes no tienen búsquedas registradas: el listado que
    estaba en disco cuenta como la búsqueda anterior."""
    import os
    from contextlib import contextmanager
    from zp.navegador import DesafioError

    @contextmanager
    def navegador(*_a, **_kw):
        yield _SesionFalsa(DesafioError, falla_en=99)

    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    monkeypatch.setattr(cli, "_navegador", lambda: (DesafioError, navegador))
    monkeypatch.setattr("zp.geocodificador.geocodificar_direccion", lambda d, b="": None)
    carpeta = tmp_path / "vl"
    carpeta.mkdir()
    viejo = [{"id": "retirado-1", "precio": 700000, "moneda": "ARS", "direccion": "Vieja 100"}]
    (carpeta / "listado.json").write_text(json.dumps(viejo), encoding="utf-8")
    hace_un_mes = 1_700_000_000
    os.utime(carpeta / "listado.json", (hace_un_mes, hace_un_mes))

    args = argparse.Namespace(
        zona=["vicente-lopez"], ambientes=[2], tipos=["departamentos", "ph"], operacion="alquiler",
        paginas=1, precio_max=None, run="vl", headless=False, rapido=True, espera_captcha=1, canal="chrome")
    cli.cmd_buscar(args)
    cli.cmd_rankear(argparse.Namespace(run="vl", presupuesto=None, dolar=1450, top=5))

    params = corrida.cargar_parametros(carpeta)
    assert len(params["busquedas"]) == 2
    nov = historial.novedades(historial.cargar(carpeta), params["busquedas"])
    assert [r["id"] for r in nov["retirados"]] == ["retirado-1"]
    assert len(nov["nuevos"]) > 0


# --------------------------------------------------------------------------- #
# Seguimiento, dashboard y mensajes
# --------------------------------------------------------------------------- #

def test_seguimiento_marcar_e_importar(tmp_path):
    seguimiento.marcar(tmp_path, "1", "favorito")
    seguimiento.marcar(tmp_path, "2", "descartado", motivo="baño sin ventana")
    exportado = tmp_path / "export.json"
    exportado.write_text(json.dumps({
        "1": {"estado": None, "fecha": "2999-01-01T00:00:00"},           # desmarcado en el navegador
        "2": {"estado": "favorito", "fecha": "2000-01-01T00:00:00"},     # más viejo: no pisa
        "3": {"estado": "visita", "visita": "jueves 18", "fecha": "2999-01-01T00:00:00"},
    }), encoding="utf-8")
    actualizados, ignorados = seguimiento.importar(tmp_path, exportado)
    datos = seguimiento.cargar(tmp_path)
    assert "1" not in datos
    assert datos["2"]["estado"] == "descartado"
    assert datos["3"]["visita"] == "jueves 18"
    assert (actualizados, ignorados) == (2, 1)
    with pytest.raises(ValueError):
        seguimiento.marcar(tmp_path, "4", "cualquiera")


def test_dashboard_veredicto_duplicado_oculto_y_seguimiento(tmp_path):
    base = {"descartado": False, "precio": 700000, "moneda": "ARS", "m2_total": 50, "ambientes": 2}
    avisos = [
        {**base, "id": "barato", "score": 80, "costo_mensual": 800000, "direccion": "Uno 100",
         "es_duplicado": True, "duplicados_ids": ["caro"],
         "auditoria": {"veredicto": "APROBADO", "score_visual": 77, "resumen": "Todo sano.",
                       "hallazgos": [], "etapa": "primera"}},
        {**base, "id": "caro", "score": 79, "costo_mensual": 850000, "direccion": "Uno 100",
         "es_duplicado": True, "duplicados_ids": ["barato"]},
    ]
    destino = dashboard.generar_dashboard_html(
        "run", avisos, tmp_path, seguimiento_inicial={"barato": {"estado": "favorito", "fecha": "x"}})
    doc = destino.read_text(encoding="utf-8")
    assert "visual 77" in doc and "Todo sano." in doc
    assert 'class="card dup-caro"' in doc and 'id="card-barato"' in doc
    assert '"barato": {"estado": "favorito"' in doc
    assert "@media (max-width: 700px)" in doc
    # Sin hoja de contacto no hay botón de fotos que lleve a un 404.
    assert "Fotos 🖼️" not in doc


def test_mensaje_pregunta_lo_que_falta_y_dice_la_garantia_real():
    a = {"id": "1", "direccion": "Uno 100", "ambientes": 2, "tipo": "departamento",
         "expensas_imputadas": True, "ajuste_indice": "No especifica", "garantias_aceptadas": [],
         "auditoria": {"pregunta_para_inmobiliaria": "¿El baño tiene ventilación?"}}
    msg = visita.mensaje_consulta(a)
    assert "Vicente López" in msg and "CABA" in msg
    assert "¿El baño tiene ventilación?" in msg
    assert "expensas" in msg


def test_diff_sin_vs_usa_las_busquedas_registradas(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    carpeta = tmp_path / "run"
    carpeta.mkdir()
    (carpeta / "ranking.json").write_text(json.dumps([{"id": "a", "direccion": "Uno 100", "score": 70}]),
                                          encoding="utf-8")
    assert cli.cmd_diff(argparse.Namespace(run="run", vs=None)) == 0
    assert "una sola búsqueda" in capsys.readouterr().out

    historial.registrar(carpeta, [{"id": "b", "precio": 1, "direccion": "Dos 200"}], fecha="2026-11-01")
    historial.registrar(carpeta, [{"id": "a", "precio": 1}], fecha="2026-11-10")
    corrida.guardar_parametros(carpeta, busquedas=[{"fecha": "2026-11-01", "completo": True},
                                                   {"fecha": "2026-11-10", "completo": True}])
    assert cli.cmd_diff(argparse.Namespace(run="run", vs=None)) == 0
    salida = capsys.readouterr().out
    assert "Nuevos: 1" in salida and "Dos 200" in salida
