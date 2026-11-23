"""Quién alquila: lo que el scoring, el auditor y los mensajes necesitan saber.

Antes esto estaba repetido a mano en tres lugares y se contradecía: el prompt
decía "garante en CABA y PBA", INSTRUCCIONES_PROYECTO.md decía "PBA / FINAER
(no de CABA)" y los mensajes a inmobiliarias decían "cuento con garantía" a
secas. Un solo lugar evita que el LLM descarte un aviso por una garantía que
en realidad sí se tiene.
"""

from __future__ import annotations

PERFIL = {
    # Los padres pueden salir de garantes: tienen una casa en Vicente López
    # (PBA) y un departamento en Capital (CABA). El seguro de caución queda
    # como alternativa si una inmobiliaria no acepta propietaria.
    "garantias": {
        "propietaria_caba": True,
        "propietaria_pba": True,
        "seguro_caucion": True,
    },
    "recibos_de_sueldo": True,
    "plazo_meses": 24,
}


def describir_garantias() -> str:
    """Una línea en castellano para el prompt y los mensajes."""
    g = PERFIL["garantias"]
    partes = []
    if g["propietaria_caba"] and g["propietaria_pba"]:
        partes.append("garantía propietaria en CABA y en Provincia (Vicente López)")
    elif g["propietaria_caba"]:
        partes.append("garantía propietaria en CABA")
    elif g["propietaria_pba"]:
        partes.append("garantía propietaria en Provincia")
    if g["seguro_caucion"]:
        partes.append("seguro de caución (FINAER) como alternativa")
    return ", y ".join(partes) if partes else "sin garantía propietaria"


def acepta_garantia(garantias_aviso: list[str]) -> bool | None:
    """¿Alguna de las garantías que pide el aviso la puede cubrir el inquilino?

    None = el aviso no dice nada concreto, no se puede saber.
    """
    if not garantias_aviso:
        return None
    g = PERFIL["garantias"]
    for item in garantias_aviso:
        t = item.lower()
        if "caba" in t and "pba" in t and (g["propietaria_caba"] or g["propietaria_pba"]):
            return True
        if "propietaria caba" in t and g["propietaria_caba"]:
            return True
        if "propietaria pba" in t and g["propietaria_pba"]:
            return True
        if ("caución" in t or "caucion" in t or "finaer" in t) and g["seguro_caucion"]:
            return True
    concretas = [x for x in garantias_aviso
                 if "consultar" not in x.lower() and "ingresos" not in x.lower()]
    return False if concretas else None
