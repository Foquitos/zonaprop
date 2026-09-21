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
