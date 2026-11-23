"""Bloques de texto por aviso que comparten el dossier y el auditor.

Estaban adentro de `cmd_dossier`. El auditor necesita mandarle al modelo
exactamente lo mismo que lee el usuario en el dossier, y parsear dossier.md de
vuelta habría sido frágil: mejor que ambos armen el texto con las mismas
funciones.
"""

from __future__ import annotations

import json

from zp.comun import _plata


def texto_expensas(a: dict) -> str:
    if a.get("tipo") in ("ph", "casa") and not a.get("expensas_informadas"):
        return "$0 (PH/casa sin expensas declaradas ni consorcio)"
    if not a.get("expensas_imputadas"):
        return f"declaradas por el aviso ({_plata(a.get('expensas'))})"
    return f"NO declaradas, estimadas con la mediana de la búsqueda ({_plata(a.get('expensas_estimadas'))})"


def bloque_yaml(a: dict) -> list[str]:
    """Bloque estructurado para que el LLM lo lea sin ambigüedad."""
    bp_txt = (a.get("barrio_popular") or "sin dato").replace('"', '\\"')
    bp_dist = a.get("barrio_popular_distancia_m")
    dias = a.get("dias_publicado")
    return [
        "```yaml",
        f"id: \"{a['id']}\"",
        f"score: {a.get('score')}",
        f"tipo: \"{a.get('tipo', 'departamento')}\"",
        f"es_dueno_directo: {'true' if a.get('es_dueno_directo') else 'false'}",
        f"costo_mensual: {_plata(a.get('costo_mensual'))}",
        f"alquiler: \"{a.get('moneda', 'ARS')} {_plata(a.get('precio'))}\"",
        f"expensas: \"{texto_expensas(a)}\"",
        "superficie:",
        f"  total_declarada: {a.get('m2_total') or 'null'}",
        f"  cubierta_estimada: {a.get('m2_cubierto_estimado') or a.get('m2_total') or 'null'}",
        f"  confiable: {'true' if a.get('m2_confiable', True) else 'false'}",
        f"ambientes: {a.get('ambientes') or 'null'}",
        f"dormitorios: {a.get('dormitorios') or 'null'}",
        "edificio:",
        f"  antiguedad: \"{a.get('antiguedad') or 'no informa'}\"",
        f"  orientacion: \"{a.get('orientacion') or 'no informa'}\"",
        f"  disposicion: \"{a.get('disposicion') or 'no informa'}\"",
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
        f"  barrio_popular_cercano: \"{bp_txt}\"",
        f"  barrio_popular_distancia_m: {bp_dist if bp_dist is not None else 'null'}",
        "mercado:",
        f"  dias_publicado: {dias if dias is not None else 'null'}",
        f"  baja_precio: {'true' if a.get('baja_precio') else 'false'}",
        f"  duplicados: {json.dumps(a.get('duplicados_ids') or [])}",
        "señales_del_texto:",
        f"  a_favor: {json.dumps(a.get('motivos_a_favor') or [], ensure_ascii=False)}",
        f"  en_contra: {json.dumps(a.get('motivos_en_contra') or [], ensure_ascii=False)}",
        f"  riesgo_humedad_a_priori: {a.get('riesgo_humedad', 0)}",
        "```",
        "",
    ]


def bloque_descripcion(a: dict, tope: int = 0) -> list[str]:
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


def linea_fotos(a: dict) -> str:
    total = a.get("fotos_totales")
    if not total:
        return "- **Fotos**: todavía no descargadas (falta correr `fotos`)"
    finales = ", ".join(str(n) for n in a.get("fotos_final_galeria") or [])
    return (f"- **Fotos**: {total} en la galería. Mirar sí o sí las {finales}: "
            "son el final de la galería, donde suelen estar la fachada, el "
            "palier y el plano")
