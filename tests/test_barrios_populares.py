"""Tests de la cercanía a barrios populares del RENABAP.

    python -m pytest tests/test_barrios_populares.py -q

Corren contra el recorte de AMBA bundleado en datos/, sin red.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zp import barrios_populares as bp


def test_hay_datos_bundleados():
    barrios = bp._cargar()
    assert len(barrios) > 1000, "el recorte de AMBA deberia tener ~1677 barrios"
    assert all(b["anillos"] for b in barrios)


# Coordenadas verificadas a mano contra el mapa del RENABAP.
@pytest.mark.parametrize("nombre, lat, lng, esperado_max_m", [
    ("Retiro, al lado de Villa 31", -34.5850, -58.3760, 100),
    ("Bajo Flores, al lado de 1-11-14", -34.6480, -58.4470, 200),
])
def test_detecta_barrios_conocidos(nombre, lat, lng, esperado_max_m):
    info = bp.mas_cercano(lat, lng)
    assert info is not None, nombre
    assert info["distancia_m"] <= esperado_max_m, f"{nombre}: {info}"


def test_recoleta_no_esta_cerca_de_ninguno():
    """Control negativo: si esto empieza a dar cerca, algo se rompió."""
    info = bp.mas_cercano(-34.5955, -58.3930)
    assert info is not None
    assert info["distancia_m"] > 1000


def test_la_distancia_es_al_borde_no_al_centro():
    """Un punto dentro del polígono da 0, y el borde da menos que el centro.

    Importa porque un barrio de 40 hectáreas tiene un centro que puede estar a
    600 m de su propia esquina: medir al centro subestima la cercanía real.
    """
    barrio = max(bp._cargar(), key=lambda b: len(b["anillos"][0]))
    anillo = barrio["anillos"][0]
    # un vértice del borde está, por definición, a distancia ~0 del polígono
    lng, lat = anillo[0][0], anillo[0][1]
    assert bp._dist_a_barrio(lng, lat, barrio) < 1.0


def test_gana_el_que_pesa_no_el_que_esta_mas_cerca():
    """El caso real que motivó el modelo continuo.

    Pumacahua al 1600 está a 175 m de Villa 13 Bis (165 familias) y a 602 m de
    la 1-11-14 (15.400 familias). Con tramos discretos de distancia ganaba el
    barrio chico y cercano, y el aviso se llevaba una penalización menor
    justamente por lo que más importaba.
    """
    info, pts, detalle = bp.evaluar(-34.64117, -58.444505)
    assert info is not None
    assert "1-11-14" in info["nombre"], "debe pesar la villa grande, no la de al lado"
    assert pts < -10, f"la penalizacion quedo floja: {pts}"
    # y el texto tiene que nombrar igual al más cercano, para no ocultarlo
    assert "Villa 13 Bis" in detalle


def test_el_tamanio_del_barrio_cambia_la_penalizacion():
    chico = {"distancia_m": 200, "familias": 30, "nombre": "x", "clasificacion": "Asentamiento"}
    grande = {"distancia_m": 200, "familias": 12000, "nombre": "y", "clasificacion": "Villa"}
    assert bp._penalizacion(grande)[0] < bp._penalizacion(chico)[0]


def test_mas_lejos_penaliza_menos_y_se_corta():
    cerca = {"distancia_m": 100, "familias": 5000, "nombre": "x", "clasificacion": "Villa"}
    lejos = {"distancia_m": 900, "familias": 5000, "nombre": "x", "clasificacion": "Villa"}
    fuera = {"distancia_m": 1500, "familias": 5000, "nombre": "x", "clasificacion": "Villa"}
    assert bp._penalizacion(cerca)[0] < bp._penalizacion(lejos)[0] < 0
    assert bp._penalizacion(fuera)[0] == 0.0


def test_sin_coordenadas_no_rompe():
    assert bp.mas_cercano(None, None) is None
    assert bp.evaluar(None, None) == (None, 0.0, None)
    assert bp.evaluar("no es un numero", "tampoco") == (None, 0.0, None)


def test_descripcion_concuerda_en_genero():
    """'Villa' es femenino y 'asentamiento' masculino."""
    villa = {"distancia_m": 300, "nombre": "Villa 31", "clasificacion": "Villa",
             "familias": 100, "dentro": False}
    asent = {"distancia_m": 300, "nombre": "Monterrey", "clasificacion": "Asentamiento",
             "familias": 40, "dentro": False}
    assert "de la villa Villa 31" in bp.descripcion(villa)
    assert "del asentamiento Monterrey" in bp.descripcion(asent)
    assert bp.descripcion(None) == "sin dato"


def test_no_dice_cero_cuadras():
    """A 15 m no se dice '~0 cuadras'."""
    info = {"distancia_m": 15, "nombre": "X", "clasificacion": "Villa",
            "familias": 100, "dentro": False}
    assert "0 cuadras" not in bp.descripcion(info)
    assert "1 cuadras" not in bp.descripcion(info)


# --------------------------------------------------------------------------- #
# Visualización y artefactos (dossier, dashboard, visita, prompt)
# --------------------------------------------------------------------------- #
import importlib.util as _il

_spec = _il.spec_from_file_location("cli_zp", Path(__file__).resolve().parents[1] / "zp.py")
cli = _il.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def test_dossier_con_barrio_popular_incluye_distancia(tmp_path, monkeypatch):
    """El dossier de un aviso con barrio_popular incluye la distancia en el markdown."""
    import json

    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    carpeta = tmp_path / "run-dossier"
    carpeta.mkdir(parents=True, exist_ok=True)

    aviso = {
        "id": "1001",
        "score": 82.5,
        "direccion": "Pumacahua al 1600",
        "barrio": "Flores",
        "precio": 650000,
        "moneda": "ARS",
        "costo_mensual": 720000,
        "descartado": False,
        "barrio_popular": "a 602 m (~5 cuadras) de la villa Padre Rodolfo Ricciardelli (Ex Villa 1-11-14) (RENABAP), 15.400 familias",
        "barrio_popular_distancia_m": 602,
        "barrio_popular_nombre": "Padre Rodolfo Ricciardelli (Ex Villa 1-11-14)",
    }
    (carpeta / "ranking.json").write_text(json.dumps([aviso]), encoding="utf-8")

    class Args:
        run = "run-dossier"
        top = 5
        max_descripcion = 0

    ret = cli.cmd_dossier(Args)
    assert ret == 0

    dossier_path = carpeta / "dossier.md"
    assert dossier_path.exists()
    md = dossier_path.read_text(encoding="utf-8")
    assert "602" in md
    assert "Barrio popular" in md or "barrio_popular" in md


def test_dashboard_badge_segun_distancia(tmp_path):
    """El dashboard de un aviso a 300 m incluye el badge, y el de uno a 3000 m no."""
    from zp import dashboard

    aviso_cerca = {
        "id": "cerca",
        "score": 75.0,
        "direccion": "Av. Varela 1200",
        "barrio": "Flores",
        "precio": 700000,
        "moneda": "ARS",
        "costo_mensual": 700000,
        "descartado": False,
        "barrio_popular": "a 300 m (~3 cuadras) de la villa 1-11-14 (RENABAP), 15.000 familias",
        "barrio_popular_distancia_m": 300,
        "barrio_popular_nombre": "Villa 1-11-14",
    }
    aviso_lejos = {
        "id": "lejos",
        "score": 75.0,
        "direccion": "Av. Santa Fe 2500",
        "barrio": "Recoleta",
        "precio": 700000,
        "moneda": "ARS",
        "costo_mensual": 700000,
        "descartado": False,
        "barrio_popular": "a 3000 m de un barrio popular",
        "barrio_popular_distancia_m": 3000,
        "barrio_popular_nombre": "Barrio Lejano",
    }

    dash_cerca = dashboard.generar_dashboard_html("run-cerca", [aviso_cerca], tmp_path / "cerca")
    html_cerca = dash_cerca.read_text(encoding="utf-8")
    assert "badge badge-renabap" in html_cerca
    assert "barrio popular a 300 m" in html_cerca

    dash_lejos = dashboard.generar_dashboard_html("run-lejos", [aviso_lejos], tmp_path / "lejos")
    html_lejos = dash_lejos.read_text(encoding="utf-8")
    assert "barrio popular a 3000 m" not in html_lejos
    assert "barrio popular a" not in html_lejos


def test_sin_dato_no_rompe_generadores(tmp_path, monkeypatch):
    """Un aviso sin el dato (None) no rompe ninguno de los cuatro generadores."""
    import json
    from zp import dashboard, prompt, visita

    monkeypatch.setattr(cli, "SALIDA", tmp_path)
    carpeta = tmp_path / "run-sin-dato"
    carpeta.mkdir(parents=True, exist_ok=True)

    aviso_sin_dato = {
        "id": "sin_dato",
        "score": 70.0,
        "direccion": "Corrientes 1000",
        "barrio": "Centro",
        "precio": 600000,
        "moneda": "ARS",
        "costo_mensual": 600000,
        "descartado": False,
        "barrio_popular": None,
        "barrio_popular_distancia_m": None,
        "barrio_popular_nombre": None,
    }

    # 1. Dossier
    (carpeta / "ranking.json").write_text(json.dumps([aviso_sin_dato]), encoding="utf-8")
    class Args:
        run = "run-sin-dato"
        top = 5
        max_descripcion = 0

    ret = cli.cmd_dossier(Args)
    assert ret == 0
    assert (carpeta / "dossier.md").exists()

    # 2. Dashboard
    dash_file = dashboard.generar_dashboard_html("run-sin-dato", [aviso_sin_dato], carpeta)
    assert dash_file.exists()

    # 3. Visita
    visita_file = visita.generar_ficha_visita("run-sin-dato", [aviso_sin_dato], carpeta)
    assert visita_file.exists()

    # 4. Prompt
    prompt_file = prompt.generar_prompt_diagnostico("run-sin-dato", [aviso_sin_dato], carpeta)
    assert prompt_file.exists()
