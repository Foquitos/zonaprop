"""Tests contra capturas reales de Zonaprop en formato gzip.

Valida el parseo de listado y detalle sobre HTML real sin mockear:
- Captura de listado: tests/capturas/listado-villa-urquiza-2amb-2026-09.html.gz
- Captura de detalle: tests/capturas/detalle-51264287-2026-09.html.gz
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from zp import parseo, scoring

DIR_CAPTURAS = Path(__file__).parent / "capturas"
RUTA_LISTADO = DIR_CAPTURAS / "listado-villa-urquiza-2amb-2026-09.html.gz"
RUTA_DETALLE = DIR_CAPTURAS / "detalle-51264287-2026-09.html.gz"


def test_listado_captura_real():
    """Verifica que el listado real devuelva 30 avisos con datos clave en la mayoría."""
    with gzip.open(RUTA_LISTADO, "rt", encoding="utf-8") as f:
        html = f.read()

    avisos = parseo.parsear_listado(html)
    assert len(avisos) == 30

    con_precio = sum(1 for a in avisos if a.precio is not None)
    con_m2 = sum(1 for a in avisos if (a.m2_total is not None or a.m2_cubierto is not None))
    con_amb = sum(1 for a in avisos if a.ambientes is not None)
    con_dir = sum(1 for a in avisos if (a.direccion or "").strip())

    # La mayoría (más de la mitad, > 15) debe tener estos campos no vacíos
    assert con_precio > 15
    assert con_m2 > 15
    assert con_amb > 15
    assert con_dir > 15


def test_detalle_captura_real():
    """Verifica que el detalle real extraiga 19 días de publicación, fotos y descripción completa."""
    with gzip.open(RUTA_DETALLE, "rt", encoding="utf-8") as f:
        html = f.read()

    detalle = parseo.parsear_detalle(html)
    assert detalle.get("dias_publicado") == 19
    assert len(detalle.get("fotos", [])) > 0
    assert bool((detalle.get("descripcion_completa") or "").strip())


def test_captura_real_no_trae_coordenadas():
    """Verifica que parsear_detalle no devuelva coordenadas en la captura real.

    Si en el futuro Zonaprop agrega lat/lng en el HTML del detalle, este test
    fallará para alertar del cambio y permitir reactivar la lectura directa.
    """
    with gzip.open(RUTA_DETALLE, "rt", encoding="utf-8") as f:
        html = f.read()

    detalle = parseo.parsear_detalle(html)
    assert "latitude" not in detalle
    assert "longitude" not in detalle


def test_tarjetas_listado_real_no_traen_fecha():
    """Verifica que el listado real no incluya la fecha en las tarjetas (0 'Publicado hace').

    Esto justifica técnicamente por qué el dato solo puede obtenerse visitando el detalle.
    """
    with gzip.open(RUTA_LISTADO, "rt", encoding="utf-8") as f:
        html = f.read()

    assert html.count("Publicado hace") == 0


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Publicado hace 1 dia", 1),
        ("publicado hace 1 día", 1),
        ("hace 1 dia", 1),
        ("hace 1 día", 1),
        ("Publicado hace 19 dias", 19),
        ("publicado hace 19 días", 19),
        ("hace 25 dias", 25),
        ("Publicado hoy", 0),
        ("hoy", 0),
        ("HOY", 0),
        ("Publicado ayer", 1),
        ("ayer", 1),
        ("AYER", 1),
        ("Publicado hace más de un año", 365),
        ("Publicado hace mas de un anio", 365),
        ("hace mas de un anio", 365),
        ("HACE MAS DE UN ANIO", 365),
        ("hace más de 1 año", 365),
        ("hace mas de 1 anio", 365),
        ("", None),
        ("Consultar", None),
        ("sin datos", None),
    ],
)
def test_variantes_dias_publicado(texto, esperado):
    """Verifica todas las variantes requeridas de antigüedad relativa."""
    assert parseo.parsear_dias_publicado(texto) == esperado


def test_dos_caminos_parsear_detalle():
    """Verifica los dos caminos de extracción: prefijo de clase CSS y regex plana."""
    # Camino 1: Prefijo de clase CSS userViews-module__post-antiquity-views con hash dinámico
    html_css = (
        '<html><body><div class="userViews-module__section-container___2M_OV">'
        '<p class="userViews-module__post-antiquity-views___XYZ99">Publicado hace 5 dias</p>'
        '</div></body></html>'
    )
    d1 = parseo.parsear_detalle(html_css)
    assert d1.get("dias_publicado") == 5

    # Camino 2: Sin la clase CSS, detectado por regex sobre texto plano
    html_plano = '<html><body><div>Publicado hace 12 dias</div></body></html>'
    d2 = parseo.parsear_detalle(html_plano)
    assert d2.get("dias_publicado") == 12


def test_dias_publicado_afecta_puntuacion_scoring():
    """Verifica los escalones de score según los días publicado."""
    base = {
        "precio": 800000,
        "moneda": "ARS",
        "expensas": 80000,
        "expensas_informadas": True,
        "m2_total": 50,
        "ambientes": 2,
        "descripcion": "Departamento luminoso al frente con balcón.",
    }

    # Contexto para establecer mediana
    contexto = [
        {**base, "id": f"ctx_{i}", "precio": 800000 + i * 10000}
        for i in range(5)
    ]

    # <= 7 días: +1 punto ("recien publicado")
    a_reciente = {**base, "id": "reciente", "dias_publicado": 4}
    # 30 a 59 días: +2 puntos ("un mes largo...")
    a_mes = {**base, "id": "mes", "dias_publicado": 40}
    # >= 60 días: +3 puntos ("{N} dias publicado...")
    a_largo = {**base, "id": "largo", "dias_publicado": 75}
    # 8 a 29 días: 0 puntos
    a_neutro = {**base, "id": "neutro", "dias_publicado": 15}
    # None: 0 puntos
    a_sin_dato = {**base, "id": "sin_dato", "dias_publicado": None}

    r = {
        a["id"]: a
        for a in scoring.puntuar(
            contexto + [a_reciente, a_mes, a_largo, a_neutro, a_sin_dato],
            dolar=1450,
        )
    }

    # Motivos a favor
    assert "recien publicado" in r["reciente"]["motivos_a_favor"]
    assert "un mes largo en el mercado (margen para negociar)" in r["mes"]["motivos_a_favor"]
    assert "75 dias publicado: hay margen para negociar, pero preguntá por que no se alquilo" in r["largo"]["motivos_a_favor"]

    # Neutro y sin dato no agregan etiqueta ni suman puntos
    assert not any("publicado" in m or "mercado" in m for m in r["neutro"]["motivos_a_favor"])
    assert not any("publicado" in m or "mercado" in m for m in r["sin_dato"]["motivos_a_favor"])

    # Verificación de calidad_texto escalonada: largo (+3) > mes (+2) > reciente (+1) > neutro/sin dato (+0)
    assert r["largo"]["calidad_texto"] > r["mes"]["calidad_texto"]
    assert r["mes"]["calidad_texto"] > r["reciente"]["calidad_texto"]
    assert r["reciente"]["calidad_texto"] > r["neutro"]["calidad_texto"]
    assert r["neutro"]["calidad_texto"] == r["sin_dato"]["calidad_texto"]
