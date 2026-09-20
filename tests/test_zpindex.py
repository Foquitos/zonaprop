"""Tests unitarios para zp/zpindex.py y su integración con scoring.

    python -m pytest tests/test_zpindex.py -q
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zp import scoring, zonas, zpindex


# --------------------------------------------------------------------------- #
# Tarea 1: Consulta de referencias y mapeo de zonas
# --------------------------------------------------------------------------- #

def test_referencia_valores_esperados_y_region_desconocida():
    """referencia() devuelve los valores esperados del snapshot y None para regiones desconocidas."""
    # Valores exactos CABA agosto 2026
    assert zpindex.referencia("caba", 1) == 18378.0
    assert zpindex.referencia("caba", 2) == 16886.0
    assert zpindex.referencia("caba", 3) == 16278.0

    # Valores exactos GBA Norte agosto 2026
    assert zpindex.referencia("gba_norte", 2) == 16384.0
    assert zpindex.referencia("gba_norte", 3) == 15781.0

    # Monoambiente en GBA Norte (extrapolación documentada según gradiente CABA)
    ref_mono_gba = zpindex.referencia("gba_norte", 1)
    assert ref_mono_gba is not None
    # 16384 * (18378 / 16886) ≈ 17832
    assert ref_mono_gba == pytest.approx(16384.0 * (18378.0 / 16886.0), abs=1.0)
    assert ref_mono_gba > 16384.0

    # Ambientes superiores al máximo relevado (más cercano: 3 amb)
    assert zpindex.referencia("caba", 4) == 16278.0
    assert zpindex.referencia("caba", 5) == 16278.0
    assert zpindex.referencia("gba_norte", 4) == 15781.0

    # Región desconocida: NUNCA inventa un valor, devuelve None
    assert zpindex.referencia("cordoba", 2) is None
    assert zpindex.referencia("rosario", 1) is None
    assert zpindex.referencia("mendoza", 3) is None
    assert zpindex.referencia("", 2) is None
    assert zpindex.referencia(None, 2) is None

    # Ambientes inválidos
    assert zpindex.referencia("caba", 0) is None
    assert zpindex.referencia("caba", -1) is None


def test_region_de_zona_mapeo_catalogo():
    """region_de_zona() mapea al menos caballito->caba y vicente-lopez->gba_norte, y cubre todo el catálogo."""
    # Slugs conocidos de la consigna
    assert zpindex.region_de_zona("caballito") == "caba"
    assert zpindex.region_de_zona("parque-chacabuco") == "caba"
    assert zpindex.region_de_zona("villa-urquiza") == "caba"
    assert zpindex.region_de_zona("nunez") == "caba"
    assert zpindex.region_de_zona("vicente-lopez") == "gba_norte"
    assert zpindex.region_de_zona("villa-martelli") == "gba_norte"

    # Cobertura completa de zonas.py: todos los barrios de CABA mapean a 'caba'
    for z in zonas.CABA:
        res = zpindex.region_de_zona(z.slug)
        assert res == "caba", f"La zona CABA {z.slug} no mapeó a 'caba' (dio '{res}')"

    # Todos los partidos y localidades de GBA Norte mapean a 'gba_norte'
    for z in zonas.GBA_NORTE:
        res = zpindex.region_de_zona(z.slug)
        assert res == "gba_norte", f"La zona GBA Norte {z.slug} no mapeó a 'gba_norte' (dio '{res}')"

    # Zona desconocida devuelve cadena vacía
    assert zpindex.region_de_zona("bariloche") == ""
    assert zpindex.region_de_zona("") == ""


# --------------------------------------------------------------------------- #
# Tarea 2: Corrección del sesgo del fallback a mediana global
# --------------------------------------------------------------------------- #

def test_monoambiente_solo_usa_mediana_global_ajustada_y_sube_valor():
    """Un monoambiente solo entre 2 ambientes usa la mediana global AJUSTADA y su 'valor' queda MAS ALTO."""
    # 5 avisos de 2 ambientes en CABA a $800.000 (50 m² cubiertos -> 16.000 $/m²)
    # Esto conforma un estrato representativo de 2 amb y define la mediana global
    avisos_2amb = [
        {
            "id": f"2amb_{i}",
            "precio": 800000 + i * 10000,
            "moneda": "ARS",
            "expensas": 80000,
            "expensas_informadas": True,
            "m2_total": 50,
            "m2_cubierto": 50,
            "ambientes": 2,
            "barrio": "Caballito, Capital Federal",
            "descripcion": "Departamento 2 ambientes luminoso",
        }
        for i in range(5)
    ]

    # 1 monoambiente solo (estrato con < 5 avisos -> cae a fallback global)
    # 30 m² cubiertos a $540.000 -> 18.000 $/m²
    aviso_mono = {
        "id": "mono_1",
        "precio": 540000,
        "moneda": "ARS",
        "expensas": 50000,
        "expensas_informadas": True,
        "m2_total": 30,
        "m2_cubierto": 30,
        "ambientes": 1,
        "barrio": "Caballito, Capital Federal",
        "descripcion": "Monoambiente luminoso",
    }

    todos = avisos_2amb + [aviso_mono]
    res = {a["id"]: a for a in scoring.puntuar(todos, dolar=1450)}

    mono = res["mono_1"]

    # 1. El origen de la mediana debe ser 'global ajustada por ZPIndex'
    assert mono["mediana_origen"] == "global ajustada por ZPIndex"

    # 2. La mediana usada debe estar escalada por el gradiente de mercado
    # En CABA: referencia(1 amb) / referencia(2 amb) = 18378 / 16886 ≈ 1.088357 (+8.8%)
    costos_m2 = [a["costo_m2_ranking"] for a in res.values() if not a.get("datos_sospechosos")]
    med_global_cruda = statistics.median(costos_m2)

    factor_esperado = zpindex.referencia("caba", 1) / zpindex.referencia("caba", 2)
    assert mono["mediana_usada"] == pytest.approx(med_global_cruda * factor_esperado, rel=1e-3)
    assert mono["mediana_usada"] > med_global_cruda

    # 3. El 'valor_vs_mercado' debe quedar estrictamente MÁS ALTO que con la mediana global cruda
    costo_mono = mono["costo_m2_ranking"]
    rel_cruda = med_global_cruda / costo_mono
    valor_crudo = round(max(0.0, min(1.0, (rel_cruda - 0.55) / 0.9)), 3)

    assert mono["valor_vs_mercado"] > valor_crudo


# --------------------------------------------------------------------------- #
# Tarea 3: Señal informativa vs_zpindex y normalización
# --------------------------------------------------------------------------- #

def test_vs_zpindex_es_none_sin_superficie():
    """Sin m² no hay con qué comparar: vs_zpindex queda en None, no en un invento."""
    aviso = {
        "id": "sin_m2", "precio": 800000, "moneda": "ARS",
        "expensas": 80000, "expensas_informadas": True,
        "m2_total": None, "m2_cubierto": None, "ambientes": 2,
        "barrio": "Caballito, Capital Federal",
        "descripcion": "Departamento en excelente ubicación",
    }
    r = scoring.puntuar([aviso], dolar=1450)[0]
    assert r["vs_zpindex"] is None
    assert r["nota_zpindex"] is None


def test_vs_zpindex_none_cuando_los_m2_incluyen_terraza():
    """Si m2_confiable es False, los m² totales incluyen exterior y no son comparables.

    La unidad media de ZPIndex es cubierta + balcón, no cubierta + terraza de 49 m².
    """
    desc = ("Living 5.00 x 4.00. Dormitorio 4.00 x 3.00. Dormitorio 3.00 x 3.00. "
            "Cocina 3.00 x 2.00. Baño 2.00 x 1.50. Terraza 7.00 x 7.00.")
    aviso = {
        "id": "conterraza", "precio": 900000, "moneda": "ARS",
        "m2_total": 100, "ambientes": 3,
        "barrio": "Caballito, Capital Federal", "descripcion": desc,
    }
    r = scoring.puntuar([aviso], dolar=1450)[0]
    assert r["m2_confiable"] is False
    assert r["vs_zpindex"] is None


def test_aviso_con_alquiler_y_m2_totales_da_ratio_correcto():
    """El ratio se calcula sobre m² TOTALES contra la referencia en la misma base.

    CABA 2 amb: $886.527 por una unidad de 50 m² cubiertos + 5 de balcón,
    o sea 16.119 $/m² totales. Las expensas NO entran en este cálculo, porque
    ZPIndex mide alquiler solo.
    """
    REF = 886527 / 55  # 16.118,7 $/m² total

    def av(nid, factor, expensas):
        return {
            "id": nid, "precio": round(55 * REF * factor), "moneda": "ARS",
            "expensas": expensas, "expensas_informadas": True,
            "m2_total": 55, "ambientes": 2,
            "barrio": "Caballito, Capital Federal", "descripcion": "Departamento estándar",
        }

    res = {a["id"]: a for a in scoring.puntuar(
        [av("exacto", 1.00, 70000), av("caro", 1.12, 50000), av("barato", 0.90, 60000)],
        dolar=1450)}

    assert res["exacto"]["vs_zpindex"] == 1.0
    assert "en línea con la referencia ZPIndex para CABA 2 amb" in res["exacto"]["nota_zpindex"]
    assert res["caro"]["vs_zpindex"] == 1.12
    assert "12% por encima" in res["caro"]["nota_zpindex"]
    assert res["barato"]["vs_zpindex"] == 0.90
    assert "10% por debajo" in res["barato"]["nota_zpindex"]


def test_texto_incompleto_no_produce_una_superficie_cubierta_inventada():
    """Si el texto enumera sólo algunos ambientes, NO se estima la superficie.

    Acá el aviso declara 50 m², el texto suma 32 de living y dormitorio, y nombra
    un balcón de 5. Los 13 m² que faltan son cocina, baño y circulación que el
    texto no enumeró: la superficie cubierta real ronda los 45, no los 32. Sin
    evidencia de superficie descubierta que explique el hueco, se respeta lo
    declarado en vez de inventar un divisor.

    Antes esto dejaba m2_cubierto_estimado en 32 y marcaba la unidad como no
    confiable. Visto en datos reales era peor: un aviso que sólo decía
    "baño 1x2" terminaba con 2.0 m² cubiertos para un 2 ambientes de 45 m².
    """
    desc = "Living de 5.00 x 4.00. Dormitorio de 4.00 x 3.00. Balcón de 5.00 x 1.00."
    aviso = {
        "id": "estimado", "precio": 540352, "moneda": "ARS",
        "m2_total": 50, "m2_cubierto": None, "ambientes": 2,
        "barrio": "Caballito, Capital Federal", "descripcion": desc,
    }

    r = scoring.puntuar([aviso], dolar=1450)[0]
    assert r["m2_cubierto_estimado"] is None
    assert r["m2_confiable"] is True


def test_actualizar_sin_pypdf_avisa_y_no_falla(monkeypatch):
    """Si pypdf no está disponible, actualizar() devuelve None sin lanzar excepción."""
    monkeypatch.setitem(sys.modules, "pypdf", None)

    res = zpindex.actualizar(2026, 8)
    assert res is None
    # El snapshot bundleado sigue intacto
    assert zpindex.SNAPSHOT["fecha"] == "2026-08"
    assert zpindex.referencia("caba", 2) == 16886.0


def test_actualizar_con_mock_actualiza_snapshot(monkeypatch):
    """Con pypdf y respuesta HTTP mockeada, actualizar() reextrae y actualiza el snapshot."""
    mock_pypdf = MagicMock()
    monkeypatch.setitem(sys.modules, "pypdf", mock_pypdf)

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"%PDF-1.4 mock"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    monkeypatch.setattr(zpindex.urllib.request, "urlopen", MagicMock(return_value=mock_resp))

    # Mock del texto del PDF para CABA y GBA Norte
    def _mock_parsear(texto, region):
        if region == "caba":
            return {1: 19000.0, 2: 17000.0, 3: 16500.0}
        return {2: 16500.0, 3: 15900.0}

    monkeypatch.setattr(zpindex, "_parsear_texto_pdf", _mock_parsear)

    snap_original = dict(zpindex.SNAPSHOT["regiones"]["caba"])
    try:
        nuevo = zpindex.actualizar(2026, 8)
        assert nuevo is not None
        assert zpindex.SNAPSHOT["regiones"]["caba"][1] == 19000.0
        assert zpindex.referencia("caba", 1) == 19000.0
    finally:
        # Restaurar snapshot original
        zpindex.SNAPSHOT["fecha"] = "2026-08"
        zpindex.SNAPSHOT["regiones"]["caba"] = snap_original
