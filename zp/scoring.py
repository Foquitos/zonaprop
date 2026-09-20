"""Ranking por variables numéricas + señales del texto del aviso.

La idea: el scraper trae muchos avisos, pero mirar fotos cuesta caro. Así que
primero ordenamos por lo que se puede medir sin ojos, y recién después mandamos
a revisión visual el top N.

El score final va de 0 a 100 y se compone de tres bloques:

    valor      (0-45)  qué tan bien pagás el m² respecto del resto de la búsqueda
    calidad    (0-35)  bonos y penalizaciones que salen del texto y los features
    riesgo     (0-20)  cuánto NO huele a problema (humedad, oscuridad, edificio viejo)

Todos los pesos están en PESOS y son fáciles de tocar.
"""

from __future__ import annotations

import datetime
import re
import statistics
import unicodedata

from zp.comun import _plata

PESOS = {
    "valor": 45,
    "calidad": 35,
    "riesgo": 20,
}

# --------------------------------------------------------------------------- #
# Señales del texto
# --------------------------------------------------------------------------- #
# (regex, puntos, etiqueta). Puntos negativos = penalización.

BONOS = [
    (r"\bmuy luminos", 6, "muy luminoso"),
    (r"\bluminos", 4, "luminoso"),
    (r"orientaci[oó]n (norte|n\b|noreste|noroeste|ne\b|no\b)", 5, "orientación norte"),
    (r"\bal frente\b|\bdisposici[oó]n frente\b|\bfrente despejado\b", 3, "al frente"),
    (r"\bvista abierta|vista despejada|vista al r[ií]o", 4, "vista abierta"),
    (r"\ba estrenar\b", 5, "a estrenar"),
    (r"reciclado a nuevo|totalmente reciclado|reciclado\b", 4, "reciclado"),
    # 'Recién pintado' salió de acá a propósito: como bono se contradecía con la
    # señal de riesgo, que es donde corresponde que esté.
    (r"\bimpecable\b|excelente estado|muy buen estado", 2, "buen estado declarado"),
    (r"due[nñ]o\s+directo|sin\s+comisi[oó]n|sin\s+honorarios|trato\s+directo|propietario\s+directo", 5, "dueño directo (sin comisión)"),
    (r"doble vidrio|dvh\b|hermetic", 3, "doble vidrio (aislación)"),
    (r"losa radiante|calefacci[oó]n central|calefacci[oó]n por radiadores", 3, "buena calefacción"),
    (r"(?<!sin )(?<!no posee )(?<!no tiene )(\bbalc[oó]n|\bterraza\b|\bpatio\b)", 3, "espacio exterior"),
    (r"lavadero|espacio para lavarropas|conexi[oó]n para el lavarropas", 2, "lugar de lavarropas"),
    (r"(?<!no )(apto mascota|acepta mascota|apto perro|acepta 1 mascota)", 3, "acepta mascotas"),
    (r"placard", 1, "placards"),
    (r"aire acondicionado|split|fr[ií]o ?/? ?calor", 2, "aire acondicionado"),
    (r"cochera", 2, "cochera"),
    (r"seguridad 24|vigilancia 24", 1, "seguridad 24h"),
]

PENAS = [
    (r"\btemporal|temporari|alquiler por d[ií]a|renta temporaria|airbnb", -25, "ALQUILER TEMPORAL"),
    (r"a reciclar|para refaccionar|a refaccionar|apto reforma|necesita refacci", -18, "a refaccionar"),
    (r"\bhumedad|humedades|con moho|filtraci[oó]n|filtraciones|goteras?", -20, "MENCIONA HUMEDAD"),
    (r"contrafrente", -5, "contrafrente"),
    (r"\binterno\b|pulm[oó]n de manzana|al pulm[oó]n", -7, "unidad interna"),
    (r"planta baja|\bpb\b(?! con salida)", -5, "planta baja (más riesgo de humedad)"),
    (r"subsuelo|semisubsuelo|entrepiso interno", -12, "subsuelo"),
    (r"sin ascensor|por escalera", -4, "sin ascensor"),
    (r"no acepta mascota|sin excepci[oó]n.{0,20}(perros|gatos)|no mascota", -5, "no acepta mascotas"),
    (r"no apto profesional", -1, "no apto profesional"),
    (r"sin balc[oó]n|no posee balc[oó]n|no tiene balc[oó]n", -4, "sin balcón"),
    (r"orientaci[oó]n (sur|s\b|sureste|suroeste|se\b|so\b)", -3, "orientación sur"),
    (r"amoblado|amueblado|equipado con muebles", -6, "amoblado (suele ser temporal)"),
    (r"apto cr[eé]dito|ideal inversor|excelente potencial de alquiler", -2, "aviso orientado a inversor"),
]

# Señales que suben la probabilidad a priori de humedad, para priorizar la
# revisión de fotos. No penalizan el score directamente: alimentan riesgo_humedad.
RIESGO_HUMEDAD = [
    (r"planta baja|\bpb\b", 2, "planta baja"),
    (r"subsuelo|semisubsuelo", 3, "subsuelo"),
    (r"contrafrente|\binterno\b|pulm[oó]n", 2, "poco sol / poca ventilación"),
    (r"orientaci[oó]n (sur|s\b|sureste|suroeste)", 2, "orientación sur"),
    (r"terraza propia|[uú]ltimo piso|bajo techo|azotea", 2, "último piso (filtración de techo)"),
    (r"\bph\b|casa antigua|patio interno", 1, "PH / patio interno"),
    # 'Recién pintado' no baja el riesgo: sube el de que haya algo tapado. Es
    # justamente lo que se hace antes de publicar cuando había una mancha.
    (r"reci[eé]n pintado|pintado a nuevo|impecable pintura", 1, "recién pintado (mirar bien)"),
]
# El reciclado y el 'a estrenar' NO están en esta lista: los maneja
# riesgo_humedad() junto con la antigüedad, porque dependen uno del otro.


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def extraer_piso(texto: str) -> int | None:
    """Extrae el número de piso si se menciona en el texto."""
    t = _norm(texto)
    m = re.search(r"(?:piso\s+(\d{1,2})|(\d{1,2})\s*(?:ro|do|er|to|mo|vo|no|º|°|\.º|\.ª)?\s+piso)", t)
    if m:
        val = m.group(1) or m.group(2)
        try:
            return int(val)
        except ValueError:
            pass
    if re.search(r"\bplanta baja\b|\bpb\b", t):
        return 0
    palabras = {
        "primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4, "quinto": 5,
        "sexto": 6, "septimo": 7, "octavo": 8, "noveno": 9, "decimo": 10,
    }
    for p, num in palabras.items():
        if re.search(rf"\b{p}\s+piso\b", t):
            return num
    return None


def tiene_vista_abierta(texto: str) -> bool:
    t = _norm(texto)
    return bool(re.search(r"vista\s+(?:abierta|despejada|libre|panoramica|al rio)|piso alto", t))


_RE_FALSOS_FRENTE = re.compile(
    r"\b(?:tipo de frente|frente a\b|en frente de\b|frente al\b|frente del\b|frente de placard)",
    re.IGNORECASE,
)


def señales(texto: str, aviso: dict | None = None) -> tuple[int, list[str], list[str]]:
    """Devuelve (puntos_calidad, motivos_positivos, motivos_negativos)."""
    t = _norm(texto)
    pts, pos, neg = 0, [], []
    for patron, valor, etiqueta in BONOS:
        if re.search(_norm(patron), t):
            pts += valor
            pos.append(etiqueta)
    for patron, valor, etiqueta in PENAS:
        if re.search(_norm(patron), t):
            pts += valor
            neg.append(etiqueta)

    # 0. Filtrar falso 'a estrenar' por artefactos/cocina
    if "a estrenar" in pos:
        t_sin_artefactos = _RE_ESTRENAR_PARCIAL.sub(" ", t)
        if not re.search(r"\ba estrenar\b", t_sin_artefactos):
            pos.remove("a estrenar")
            pts -= 5

    # 0. Filtrar falso 'al frente' ("Tipo de frente: Cemento", "en frente de Tecnópolis")
    if "al frente" in pos:
        t_sin_falsos = _RE_FALSOS_FRENTE.sub(" ", t)
        if not re.search(r"\bal frente\b|\bdisposici[oó]n frente\b|\bfrente despejado\b", t_sin_falsos):
            pos.remove("al frente")
            pts -= 3

    # Corregir contradicciones frente / contrafrente y cruce con piso
    disposicion_oficial = _norm((aviso.get("disposicion") if aviso else "") or "")
    piso = extraer_piso(texto)
    vista_libre = tiene_vista_abierta(texto) or "muy luminoso" in pos

    # 1. Si la ficha oficial dice Contrafrente, no asignar 'al frente'
    if "contrafrente" in disposicion_oficial:
        if "al frente" in pos:
            pos.remove("al frente")
            pts -= 3

    # 2. Si la ficha oficial dice Frente, no asignar 'contrafrente'
    if "frente" in disposicion_oficial and "contrafrente" not in disposicion_oficial:
        if "contrafrente" in neg:
            neg.remove("contrafrente")
            pts += 5

    # 3. Si el texto menciona dormitorios al frente y al contrafrente (ventilación cruzada)
    if "al frente" in pos and "contrafrente" in neg:
        pos.remove("al frente")
        neg.remove("contrafrente")
        pts += 2  # -3 + 5
        pos.append("ventilación cruzada (frente y contrafrente)")

    # 4. Contrafrente en piso alto o con vista abierta no es oscuro: es tranquilo y luminoso
    if "contrafrente" in neg:
        if (piso is not None and piso >= 4) or vista_libre:
            neg.remove("contrafrente")
            pts += 5  # anula la penalización de -5
            desc_piso = f"en {piso}.º piso" if (piso is not None and piso >= 1) else "con vista abierta"
            pos.append(f"contrafrente {desc_piso} (tranquilo y luminoso)")

    return pts, pos, neg


# Valores no numéricos que Zonaprop pone en el campo antigüedad.
_ANTIGUEDAD_TEXTO = {
    "a estrenar": 0, "estrenar": 0, "nuevo": 0,
    "en pozo": 0, "en construccion": 0, "en construcción": 0,
}


def parsear_antiguedad(valor) -> tuple[int | None, str]:
    """Devuelve (años, etiqueta). None = el aviso no lo informa.

    Antes esto pasaba por un int() pelado: '20' andaba, pero 'A estrenar'
    devolvía None y se perdía la señal, y un campo vacío se confundía con
    'no informa'. Ahora se resuelven los tres casos por separado.
    """
    if valor is None:
        return None, "no informa"
    crudo = str(valor).strip()
    if not crudo:
        return None, "no informa"

    plano = _norm(crudo)
    if plano in _ANTIGUEDAD_TEXTO:
        return _ANTIGUEDAD_TEXTO[plano], crudo
    for clave, años in _ANTIGUEDAD_TEXTO.items():
        if clave in plano:
            return años, crudo

    m = re.search(r"\d+", plano)
    if not m:
        return None, crudo
    años = int(m.group(0))
    return (años, f"{años} años") if 0 <= años <= 200 else (None, crudo)


_RE_ANT_TEXTO = re.compile(
    r"(?:edificio|antiguedad|construccion)?\D{0,25}?(\d{1,3})\s*(?:anos|ano)\s*"
    r"(?:de\s*)?(?:antiguedad|construido)?|"
    r"(\d{1,3})\s*anos\s*de\s*antiguedad"
)


def _antiguedad_en_texto(texto: str) -> str | None:
    """Saca la antigüedad de frases como 'edificio de 38 años de antigüedad'."""
    t = _norm(texto)
    m = re.search(r"(\d{1,3})\s*a[nñ]os?\s*(?:de\s*)?(?:antig[uü]edad|construido)", t)
    if not m:
        m = re.search(r"(?:edificio|construcci[oó]n)\s+de\s+(\d{1,3})\s*a[nñ]os", t)
    if m:
        años = int(m.group(1))
        if 0 <= años <= 200:
            return str(años)
    return None


_RE_ESTRENAR_PARCIAL = re.compile(
    r"(?:artefacto|cocina|mueble|muebles|anafe|horno|termotanque|calefon|colch[oó]n|sanitarios?|grifer[ií]a|aberturas?|luces?|pintura|bacha|placard|placards)\s+(?:a\s+estrenar|nuevo|nueva|nuevos|nuevas)",
    re.IGNORECASE,
)


def estado_unidad(texto: str) -> str:
    """'a_estrenar' | 'reciclada' | 'normal', a partir del texto del aviso."""
    t = _norm(texto)
    t_limpio = _RE_ESTRENAR_PARCIAL.sub(" ", t)
    if re.search(r"\b(?:a estrenar|sin estrenar|nunca habitad|obra nueva|edificio nuevo)\b", t_limpio):
        return "a_estrenar"
    if re.search(r"reciclad|refaccionad|renovad|remodelad|puesta a nuevo|totalmente restaurad", t) or _RE_ESTRENAR_PARCIAL.search(t):
        return "reciclada"
    return "normal"


def riesgo_humedad(aviso: dict, texto: str) -> tuple[int, list[str]]:
    """0 = sin señales; 10+ = revisar fotos con lupa."""
    t = _norm(texto)
    puntos, motivos = 0, []

    piso = extraer_piso(texto)
    vista_libre = tiene_vista_abierta(texto) or "muy luminoso" in t

    for patron, valor, etiqueta in RIESGO_HUMEDAD:
        if re.search(_norm(patron), t):
            # Si es contrafrente pero en piso alto (>= 4) o con vista abierta, no suma riesgo de humedad
            if etiqueta == "poco sol / poca ventilación" and ((piso is not None and piso >= 4) or vista_libre):
                continue
            puntos += valor
            motivos.append(etiqueta)

    # La antigüedad es del EDIFICIO; el reciclado es de la UNIDAD.
    estado = aviso.get("estado_unidad") or estado_unidad(texto)
    aviso["estado_unidad"] = estado

    ant_declarada = aviso.get("antiguedad") or _antiguedad_en_texto(texto)
    ant, etiqueta_ant = parsear_antiguedad(ant_declarada)
    aviso["antiguedad_anios"] = ant
    aviso["antiguedad_label"] = etiqueta_ant

    tipo = aviso.get("tipo") or "departamento"
    antiguedad_sospechosa = False
    if ant is not None and ant < 5 and tipo in ("ph", "casa"):
        if not re.search(r"\b(?:obra nueva|a estrenar|en pozo|complejo nuevo)\b", t):
            antiguedad_sospechosa = True
            aviso["antiguedad_sospechosa"] = True

    if ant is None:
        if estado == "a_estrenar":
            puntos -= 2
            motivos.append("a estrenar")
        else:
            puntos += 1
            motivos.append("no informa antigüedad")
    else:
        if ant >= 60:
            bruto = 4
        elif ant >= 40:
            bruto = 2
        elif ant <= 10:
            bruto = 0 if antiguedad_sospechosa else -2
        else:
            bruto = 0

        # Si el edificio tiene 10+ años, no puede ser "a estrenar" estructuralmente
        if estado == "a_estrenar" and ant >= 10:
            estado = "reciclada"
            aviso["estado_unidad"] = "reciclada"

        if estado == "a_estrenar" and not antiguedad_sospechosa:
            bruto = min(bruto, -2)
            motivos.append("a estrenar")
        elif estado == "reciclada" and bruto > 0:
            bruto = bruto // 2
            motivos.append(f"{etiqueta_ant}, pero la unidad está reciclada")
        elif antiguedad_sospechosa:
            motivos.append(f"antigüedad sospechosa ({etiqueta_ant} en {tipo.upper()})")
        elif bruto != 0:
            motivos.append(
                f"edificio nuevo ({etiqueta_ant})" if bruto < 0 else f"{etiqueta_ant} de antigüedad"
            )
        puntos += bruto

    orient = _norm(aviso.get("orientacion") or "")
    if orient in ("s", "sur", "se", "sureste", "so", "suroeste"):
        puntos += 2
        motivos.append(f"orientación {aviso['orientacion']}")
    elif orient in ("n", "norte", "ne", "noreste", "no", "noroeste"):
        puntos -= 2
        motivos.append(f"orientación {aviso['orientacion']}")

    return max(0, puntos), motivos


def _entero(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Superficie y dimensiones
# --------------------------------------------------------------------------- #

_DESCUBIERTOS = {
    "terraza", "balcon", "patio", "jardin", "parrilla", "fondo",
    "solarium", "parque", "cochera", "porche", "guardacoche", "descubierto"
}
_CUBIERTOS = {
    "living", "comedor", "dormitorio", "habitacion", "cocina", "bano",
    "toilette", "hall", "distribuidor", "pasillo", "lavadero", "escritorio",
    "estar", "playroom", "dependencia", "antevano", "recepcion", "suite",
    "porche semicubierto", "galeria cubierta"
}

_NUM = re.compile(r"[\d.]+")


def _num(texto: str | None) -> float | None:
    if not texto:
        return None
    m = _NUM.search(texto.replace(",", "."))
    if not m:
        return None
    crudo = m.group(0)
    if crudo.count(".") >= 1 and len(crudo.split(".")[-1]) == 3:
        crudo = crudo.replace(".", "")
    try:
        return float(crudo)
    except ValueError:
        return None


def analizar_superficies(aviso: dict, texto: str) -> dict:
    """Extrae medidas ambiente por ambiente y detecta si los m² incluyen terraza/exterior."""
    patron = re.compile(
        r"([A-Za-zÁÉÍÓÚáéíóúñÑ/() -]{3,35}?)\s*[:=]?\s*"
        r"(\d+(?:[.,]\d+)?)\s*[xX*×]\s*(\d+(?:[.,]\d+)?)",
        re.UNICODE
    )

    cubiertos = []
    descubiertos = []

    for m in patron.finditer(texto):
        amb_raw = m.group(1).strip()
        amb_norm = _norm(amb_raw)
        d1 = _num(m.group(2))
        d2 = _num(m.group(3))
        if not d1 or not d2 or d1 > 50 or d2 > 50 or d1 * d2 < 0.5:
            continue
        area = round(d1 * d2, 2)

        es_desc = any(pal in amb_norm for pal in _DESCUBIERTOS)
        es_cub = any(pal in amb_norm for pal in _CUBIERTOS)

        if es_desc and not ("semicubierto" in amb_norm or "cubierta" in amb_norm):
            descubiertos.append((amb_raw, area))
        elif es_cub or "dormitorio" in amb_norm or "comedor" in amb_norm:
            cubiertos.append((amb_raw, area))
        else:
            cubiertos.append((amb_raw, area))

    m2_cub = sum(a for _, a in cubiertos)
    m2_desc = sum(a for _, a in descubiertos)

    m2_declarado = aviso.get("m2_total") or aviso.get("m2_cubierto")
    m2_confiable = True
    m2_cubierto_estimado = round(m2_cub, 1) if m2_cub > 0 else aviso.get("m2_cubierto")

    if m2_declarado and m2_cub > 0:
        discrepancia = (m2_declarado - m2_cub) / m2_declarado
        if discrepancia > 0.30:
            m2_confiable = False
    elif aviso.get("m2_total") and aviso.get("m2_cubierto"):
        if (aviso["m2_total"] - aviso["m2_cubierto"]) / aviso["m2_total"] > 0.30:
            m2_confiable = False
            m2_cubierto_estimado = aviso["m2_cubierto"]

    aviso["m2_confiable"] = m2_confiable
    aviso["m2_cubierto_estimado"] = m2_cubierto_estimado
    aviso["m2_descubierto_estimado"] = round(m2_desc, 1) if m2_desc > 0 else None

    return {
        "m2_confiable": m2_confiable,
        "m2_cubiertos_calculados": round(m2_cub, 1),
        "m2_descubiertos_calculados": round(m2_desc, 1),
        "cubiertos": cubiertos,
        "descubiertos": descubiertos,
    }


# --------------------------------------------------------------------------- #
# Duplicados por dirección
# --------------------------------------------------------------------------- #

def normalizar_direccion(dir_str: str) -> str:
    """Normaliza 'Laprida al 4500', 'Av. Laprida 4500', 'Laprida 4520' -> 'laprida_4500'."""
    if not dir_str:
        return ""
    t = _norm(dir_str)
    t = re.sub(r"\b(av|avenida|dr|doctor|gral|general|calle|pasaje|pje|tte|teniente)\.?\b", "", t)
    t = re.sub(r"\b(entre|y|esq|esquina)\b.*$", "", t)
    t = re.sub(r"\bal\b", "", t)
    m = re.search(r"([a-z\s]+?)\s*(\d+)", t)
    if m:
        calle = re.sub(r"\s+", " ", m.group(1).strip())
        num = int(m.group(2))
        altura_centena = (num // 100) * 100
        return f"{calle}_{altura_centena}"
    calle = re.sub(r"\s+", " ", t.strip())
    return calle


def identificar_duplicados(avisos: list[dict]):
    """Agrupa avisos por dirección y ambientes, identificando duplicados y diferencias de precio."""
    grupos: dict[tuple, list[dict]] = {}
    for a in avisos:
        d = a.get("direccion") or ""
        if not d:
            continue
        k = (normalizar_direccion(d), a.get("ambientes"))
        if k[0]:
            grupos.setdefault(k, []).append(a)

    for k, grupo in grupos.items():
        if len(grupo) > 1:
            costos = [a["costo_mensual"] for a in grupo if a.get("costo_mensual") is not None]
            if not costos:
                continue
            min_costo = min(costos)
            max_costo = max(costos)
            disparidad = max_costo - min_costo

            for a in grupo:
                a["es_duplicado"] = True
                a["duplicados_ids"] = [o["id"] for o in grupo if o["id"] != a["id"]]
                a["disparidad_precio"] = disparidad
                a["mejor_precio_duplicado"] = min_costo

                if disparidad > 0 and a.get("costo_mensual") is not None:
                    if a["costo_mensual"] == min_costo:
                        a.setdefault("motivos_a_favor", []).append(
                            f"mejor precio publicado (ahorro de {_plata(disparidad)} vs otra publicación de la misma propiedad)"
                        )
                        a["nota_negociacion"] = (
                            f"Publicado también a {_plata(max_costo)} por otra inmobiliaria "
                            f"(ahorro de {_plata(disparidad)} a tu favor)"
                        )
                    else:
                        a.setdefault("motivos_en_contra", []).append(
                            f"publicado más barato por otra inmobiliaria ({_plata(min_costo)} vs {_plata(a['costo_mensual'])}; diferencia de {_plata(disparidad)})"
                        )
                        a["nota_negociacion"] = (
                            f"Publicado a {_plata(min_costo)} por otra inmobiliaria "
                            f"(diferencia de {_plata(disparidad)} para negociar)"
                        )


# --------------------------------------------------------------------------- #
# Costo y valor
# --------------------------------------------------------------------------- #


def alquiler_en_pesos(aviso: dict, dolar: float) -> float | None:
    precio = aviso.get("precio")
    if precio is None:
        return None
    if (aviso.get("moneda") or "").upper() == "USD":
        return precio * dolar
    return precio


def costo_mensual(aviso: dict, dolar: float) -> float | None:
    """Alquiler + expensas, todo en pesos.

    Si el aviso no informa expensas se usa `expensas_estimadas`, que carga
    `imputar_expensas()`.
    """
    alquiler = alquiler_en_pesos(aviso, dolar)
    if alquiler is None:
        return None
    if aviso.get("expensas_informadas"):
        exp = aviso.get("expensas") or 0.0
    else:
        exp = aviso.get("expensas_estimadas")
        if exp is None:
            return None
    return alquiler + exp


def imputar_expensas(avisos: list[dict], dolar: float) -> float | None:
    """Estima las expensas de los avisos que no las informan.

    La referencia es la mediana de expensas/alquiler entre los avisos de la
    MISMA búsqueda que sí las publican y son departamentos. Los PH y casas
    sin consorcio no pagan expensas de edificio, por lo que si no declaran
    o dicen 'sin expensas' se estiman en 0.
    """
    ratios = []
    for a in avisos:
        alq = alquiler_en_pesos(a, dolar)
        tipo = a.get("tipo") or "departamento"
        if a.get("expensas_informadas") and alq and a.get("expensas") and tipo == "departamento":
            ratios.append(a["expensas"] / alq)
    ratio = statistics.median(ratios) if len(ratios) >= 5 else None

    for a in avisos:
        tipo = a.get("tipo") or "departamento"
        if a.get("expensas_informadas"):
            a["expensas_estimadas"] = a.get("expensas") or 0.0
            a["expensas_imputadas"] = False
        else:
            if tipo in ("ph", "casa"):
                a["expensas_estimadas"] = 0.0
                a["expensas_imputadas"] = False
            else:
                alq = alquiler_en_pesos(a, dolar)
                a["expensas_estimadas"] = (alq * ratio) if (alq and ratio) else None
                a["expensas_imputadas"] = True
    return ratio


def datos_faltantes(aviso: dict, texto: str) -> list[tuple[str, int]]:
    """Qué no dice el aviso, entre lo que debería decir, y cuánto cuesta."""
    faltan: list[tuple[str, int]] = []

    if not (aviso.get("m2_total") or aviso.get("m2_cubierto")):
        faltan.append(("superficie", 5))

    largo = len((texto or "").strip())
    if largo < 120:
        faltan.append(("descripción (casi no dice nada)", 8))
    elif largo < 260:
        faltan.append(("descripción (muy corta)", 5))

    paso_por_detalle = bool(aviso.get("descripcion_completa") or aviso.get("fotos_totales"))
    if paso_por_detalle:
        for campo, etiqueta in (("antiguedad", "antigüedad"),
                                ("orientacion", "orientación"),
                                ("disposicion", "disposición")):
            if not str(aviso.get(campo) or "").strip():
                faltan.append((etiqueta, 3))
    return faltan


def parsear_contrato(texto: str) -> dict:
    """Extrae de forma estructurada los requisitos y condiciones contractuales."""
    t = _norm(texto)

    # 1. Garantías
    garantias = []
    if re.search(r"finaer|cauci[oó]n|seguro de cauci[oó]n|respaldo", t):
        garantias.append("FINAER / Seguro de Caución")
    if re.search(r"garant[ií]a\s+(?:propietaria\s+)?(?:de|en)\s+caba|garante\s+de\s+capital", t):
        garantias.append("Garantía Propietaria CABA")
    if re.search(r"garant[ií]a\s+(?:propietaria\s+)?(?:de|en)\s+(?:provincia|pba|zona\s+norte|vicente\s+l[oó]pez)", t):
        garantias.append("Garantía Propietaria PBA")
    if not any("Propietaria" in g for g in garantias) and re.search(r"garant[ií]a\s+propietaria", t):
        garantias.append("Garantía Propietaria (CABA / PBA)")
    if re.search(r"recibo\s+de\s+sueldo|ingresos?\s+demostrables?|demostraci[oó]n\s+de\s+ingresos", t):
        garantias.append("Demostración de ingresos / Recibo de sueldo")
    if not garantias and re.search(r"garant[ií]a", t):
        garantias.append("Consultar tipo de garantía")

    # 2. Mascotas
    if re.search(r"no\s+(?:se\s+)?(?:aceptan?|admiten?|permite)\s+mascotas|sin\s+mascotas|prohibido\s+mascotas|\bno\s+mascotas?\b", t):
        mascotas = "No acepta mascotas"
    elif re.search(r"(?:solo|acepta)\s+mascota\s+peque[nñ]a|acepta\s+1\s+mascota|solo\s+gato|no\s+perro", t):
        mascotas = "Solo gatos o mascota pequeña"
    elif re.search(r"apto\s+mascotas?|acepta\s+mascotas?|pet\s+friendly", t):
        mascotas = "Acepta mascotas"
    else:
        mascotas = "No especifica"

    # 3. Ajuste (frecuencia e índice)
    frecuencia = "No especifica"
    if re.search(r"trimestral|cada\s+3\s+meses|aumentos?\s+trimestrales?", t):
        frecuencia = "Trimestral (cada 3 meses)"
    elif re.search(r"cuatrimestral|cada\s+4\s+meses|aumentos?\s+cuatrimestrales?", t):
        frecuencia = "Cuatrimestral (cada 4 meses)"
    elif re.search(r"semestral|cada\s+6\s+meses|aumentos?\s+semestrales?", t):
        frecuencia = "Semestral (cada 6 meses)"
    elif re.search(r"anual|cada\s+12\s+meses|cada\s+a[nñ]o", t):
        frecuencia = "Anual"

    indice = "No especifica"
    if re.search(r"\bipc\b|inflaci[oó]n", t):
        indice = "IPC"
    elif re.search(r"\bicl\b|locativo", t):
        indice = "ICL"
    elif re.search(r"\bcac\b", t):
        indice = "CAC"
    elif re.search(r"\buva\b", t):
        indice = "UVA"

    # 4. Depósito
    deposito = "No especifica"
    m_usd = re.search(r"dep[oó]sito.*?(?:u\$s|usd|\$)\s*(\d[\d.]*)", t)
    m_mes = re.search(r"(\d+\s*mes(?:es)?)\s+(?:de\s+dep[oó]sito|dep[oó]sito)|dep[oó]sito.*?(\d+\s*mes(?:es)?)", t)
    mes_txt = (m_mes.group(1) or m_mes.group(2)) if m_mes else ""
    if m_usd and mes_txt:
        moneda_match = re.search(r"(u\$s|usd|\$)", t[m_usd.start():m_usd.end()])
        mon_str = moneda_match.group(1).upper() if moneda_match else "$"
        deposito = f"{mes_txt.strip().upper()} ({mon_str} {m_usd.group(1).strip()})"
    elif m_usd:
        deposito = f"USD {m_usd.group(1).strip()}" if "u$s" in t or "usd" in t else f"${m_usd.group(1).strip()}"
    elif mes_txt:
        deposito = mes_txt.strip().upper()

    # 5. Plazo
    plazo = "No especifica"
    if re.search(r"24\s+meses|2\s+a[nñ]os|dos\s+\(2\)\s+a[nñ]os", t):
        plazo = "2 años (24 meses)"
    elif re.search(r"36\s+meses|3\s+a[nñ]os|tres\s+\(3\)\s+a[nñ]os", t):
        plazo = "3 años"
    elif re.search(r"temporal|temporario", t):
        plazo = "Temporal"

    # 6. Costos adicionales / impuestos
    costos = []
    if re.search(r"abl|tasas?\s+municipales?", t):
        costos.append("ABL / Tasas municipales")
    if re.search(r"seguro\s+de\s+incendio|seguro\s+del\s+inmueble", t):
        costos.append("Seguro de incendio")
    if re.search(r"sellado", t):
        costos.append("Sellado de contrato")
    if re.search(r"honorarios?|comisi[oó]n", t):
        costos.append("Honorarios inmobiliarios")

    return {
        "garantias_aceptadas": garantias,
        "politica_mascotas": mascotas,
        "ajuste_frecuencia": frecuencia,
        "ajuste_indice": indice,
        "deposito_monto": deposito,
        "plazo_contrato": plazo,
        "costos_adicionales": costos,
    }


def calcular_dias_mercado(fecha_str: str) -> int | None:
    """Calcula cuántos días lleva publicado el aviso a partir de fecha_publicacion."""
    if not fecha_str:
        return None
    try:
        limpio = fecha_str.split("T")[0].split(" ")[0].strip()
        partes = [int(p) for p in limpio.split("-")]
        if len(partes) == 3:
            dt = datetime.date(partes[0], partes[1], partes[2])
            hoy = datetime.date.today()
            dias = (hoy - dt).days
            return max(0, dias)
    except Exception:
        pass
    return None


def analizar_entorno(aviso: dict, texto: str) -> dict:
    """Analiza la micro-ubicación, avenidas principales y conectividad."""
    dir_txt = f"{aviso.get('direccion', '')} {aviso.get('barrio', '')} {texto}".lower()

    avenidas = []
    if re.search(r"\blaprida\b", dir_txt):
        avenidas.append("Av. Laprida")
    if re.search(r"\bmitre\b", dir_txt):
        avenidas.append("Av. Mitre")
    if re.search(r"\bmaip[uú]\b", dir_txt):
        avenidas.append("Av. Maipú")
    if re.search(r"\bconstituyentes\b", dir_txt):
        avenidas.append("Av. Constituyentes")
    if re.search(r"\bpanamericana\b", dir_txt):
        avenidas.append("Autopista Panamericana")
    if re.search(r"\bgeneral paz\b|\bgral\.?\s*paz\b", dir_txt):
        avenidas.append("Av. General Paz")
    if re.search(r"\bsan mart[ií]n\b", dir_txt):
        avenidas.append("Av. San Martín")

    if avenidas:
        entorno_tipo = f"Sobre/próximo a {', '.join(avenidas)} (acceso rápido y transporte; evaluar ruido en aberturas)"
    else:
        entorno_tipo = "Calle residencial"

    trenes = []
    if re.search(r"estaci[oó]n\s+(?:ffcc\s+)?padilla|estaci[oó]n\s+padilla", dir_txt):
        trenes.append("Estación Padilla (FFCC Belgrano Norte)")
    if re.search(r"estaci[oó]n\s+(?:ffcc\s+)?j\.?\s*b\.?\s*justo|estaci[oó]n\s+juan\s+b\s+justo", dir_txt):
        trenes.append("Estación J. B. Justo (FFCC Mitre)")
    if re.search(r"estaci[oó]n\s+(?:ffcc\s+)?florida|estaci[oó]n\s+florida", dir_txt):
        trenes.append("Estación Florida")
    if re.search(r"estaci[oó]n\s+(?:ffcc\s+)?arist[oó]bulo\s+del\s+valle", dir_txt):
        trenes.append("Estación Aristóbulo del Valle")

    return {
        "entorno_tipo": entorno_tipo,
        "avenidas_cercanas": avenidas,
        "estaciones_cercanas": trenes,
        "coordenadas": (aviso.get("latitude"), aviso.get("longitude")),
    }


def generar_preguntas_visita(aviso: dict) -> list[str]:
    """Genera una lista de 3 a 5 preguntas clave y técnicas para la visita presencial."""
    preguntas = []
    ant = aviso.get("antiguedad_anios")
    tipo = aviso.get("tipo") or "departamento"

    # 1. Antigüedad e instalaciones
    if ant is not None and ant >= 30:
        preguntas.append(f"El edificio tiene {ant} años: ¿en qué fecha se renovaron cañerías troncales de agua, gas y la instalación eléctrica?")
    elif aviso.get("antiguedad_sospechosa"):
        preguntas.append("La antigüedad declarada es baja para el tipo de propiedad: ¿cuál es la antigüedad real de la construcción?")

    # 2. Expensas y servicios en PH
    if tipo in ("ph", "casa"):
        if aviso.get("expensas_estimadas") == 0.0 or aviso.get("expensas") == 0.0:
            preguntas.append("PH sin expensas: ¿el agua corriente tiene bomba/tanque compartido o individual, y cómo se gestionan gastos de pasillo y techos?")
    else:
        if aviso.get("expensas_imputadas"):
            preguntas.append("No informa expensas en la publicación: ¿a cuánto ascendió la última liquidación de expensas ordinarias?")

    # 3. Superficie y terrazas
    if not aviso.get("m2_confiable") and aviso.get("m2_cubierto_estimado"):
        preguntas.append(f"Superficie declarada ({aviso.get('m2_usado', 0):.0f} m²): ¿cuántos m² son cubiertos habitables según plano y cuántos corresponden a la terraza/patio?")

    # 4. Ajuste y requisitos
    ajuste_idx = aviso.get("ajuste_indice")
    ajuste_frec = aviso.get("ajuste_frecuencia")
    if not ajuste_idx or ajuste_idx == "No especifica":
        preguntas.append("¿Bajo qué índice exacto (IPC o ICL) y con qué periodicidad se ajustará el alquiler?")

    # 5. Estado general / orientación
    if not aviso.get("orientacion"):
        preguntas.append("¿Hacia qué punto cardinal orienta el living y los dormitorios principales para la luz solar de la tarde/mañana?")

    return preguntas[:4]


def calcular_caja_inicial(aviso: dict, dolar: float = 1450.0) -> tuple[float, str, dict]:
    """Calcula el desembolso total de entrada (caja inicial al momento de la firma)."""
    alquiler = alquiler_en_pesos(aviso, dolar) or 0.0
    if alquiler <= 0:
        return 0.0, "No calculable", {}

    adelanto = alquiler
    dep_txt = (aviso.get("deposito_monto") or "").upper()
    m_usd = re.search(r"(?:U\$S|USD)\s*(\d[\d.]*)", dep_txt)
    m_ars = re.search(r"\$\s*(\d[\d.]*)", dep_txt)
    m_meses = re.search(r"(\d+)\s*MES", dep_txt)

    deposito = None
    dep_label = None

    if m_usd:
        try:
            num_str = m_usd.group(1).replace(".", "").strip()
            if num_str:
                num_usd = float(num_str)
                deposito = num_usd * dolar
                dep_label = f"Depósito USD {num_usd:,.0f}".replace(",", ".")
        except Exception:
            pass

    if deposito is None and m_ars:
        try:
            num_str = m_ars.group(1).replace(".", "").strip()
            if num_str:
                num_ars = float(num_str)
                deposito = num_ars
                dep_label = f"Depósito {_plata(deposito)}"
        except Exception:
            pass

    if deposito is None and m_meses:
        try:
            cant_meses = int(m_meses.group(1))
            deposito = cant_meses * alquiler
            dep_label = f"Depósito ({cant_meses} meses)"
        except Exception:
            pass

    if deposito is None:
        deposito = alquiler
        dep_label = "Depósito (1 mes est.)"

    es_dueno = bool(aviso.get("es_dueno_directo"))
    barrio = _norm(aviso.get("barrio") or "")
    es_caba = "capital" in barrio or "caba" in barrio or "buenos aires (caba)" in barrio

    if es_dueno or es_caba:
        honorarios = 0.0
        hon_label = "Honorarios $0 (dueño directo / CABA)"
    else:
        # En PBA: Ley 10.973 (4.15% sobre contrato 24 meses -> ~1 mes)
        honorarios = 24 * alquiler * 0.0415
        hon_label = f"Honorarios PBA ({_plata(honorarios)})"

    if es_caba:
        sellado = 0.0
        sel_label = "Sellado $0 (CABA exento)"
    else:
        sellado = 24 * alquiler * 0.005
        sel_label = f"Sellado PBA ({_plata(sellado)})"

    informes = min(90000.0, max(45000.0, alquiler * 0.07))
    total = adelanto + deposito + honorarios + sellado + informes
    desglose = {
        "adelanto": adelanto,
        "deposito": deposito,
        "honorarios": honorarios,
        "sellado": sellado,
        "informes": informes,
        "total": total,
    }
    resumen = (
        f"{_plata(total)} (Adelanto {_plata(adelanto)} + {dep_label} + {hon_label} + {sel_label} + Informes {_plata(informes)})"
    )
    return total, resumen, desglose


def simular_evolucion_alquiler(aviso: dict, dolar: float = 1450.0, inflacion_mensual: float = 0.03) -> dict:
    """Proyecta la cuota del alquiler a 24 meses según periodicidad de ajuste e IPC mensual estimado."""
    alq = alquiler_en_pesos(aviso, dolar) or 0.0
    if alq <= 0:
        return {}

    frec = (aviso.get("ajuste_frecuencia") or "").lower()
    if "cuatrimestral" in frec or "4 meses" in frec:
        meses_salto = 4
    elif "semestral" in frec or "6 meses" in frec:
        meses_salto = 6
    elif "anual" in frec or "12 meses" in frec or "1 año" in frec:
        meses_salto = 12
    else:
        meses_salto = 3

    cuotas = []
    precio_actual = alq
    for mes in range(1, 25):
        if mes > 1 and (mes - 1) % meses_salto == 0:
            factor = (1.0 + inflacion_mensual) ** meses_salto
            precio_actual *= factor
        cuotas.append(precio_actual)

    total_2_anios = sum(cuotas)
    mes_1 = cuotas[0]
    mes_6 = cuotas[5]
    mes_12 = cuotas[11]
    mes_24 = cuotas[23]

    resumen = (
        f"Mes 1: {_plata(mes_1)} -> Mes 6: {_plata(mes_6)} -> Mes 12: {_plata(mes_12)} -> Mes 24: {_plata(mes_24)} "
        f"(Total 2 años estimado: ~{_plata(total_2_anios)} con IPC 3% mensual)"
    )

    return {
        "mes_1": mes_1,
        "mes_6": mes_6,
        "mes_12": mes_12,
        "mes_24": mes_24,
        "total_2_anios": total_2_anios,
        "meses_salto": meses_salto,
        "resumen": resumen,
    }


def detectar_alerta_gran_angular(aviso: dict, texto: str) -> str | None:
    """Detecta si hay ambientes con medidas reducidas pero fotos potencialmente sobredimensionadas."""
    t = _norm(texto)
    m2_cub = aviso.get("m2_cubierto_estimado") or aviso.get("m2_cubierto") or aviso.get("m2_total")
    amb = aviso.get("ambientes")

    m_chico = re.search(r"(?:dormitorio|habitaci[oó]n|living).*?(\b[12]\.[0-9]{1,2}\s*x\s*[123]\.[0-9]{1,2})", t)
    if m_chico:
        return f"Ambientes de medidas angostas ({m_chico.group(1)}m): lente gran angular puede sobredimensionar el espacio en las fotos"
    if amb and amb >= 3 and m2_cub and m2_cub < 48:
        return f"3 ambientes en solo {m2_cub:.0f} m² cubiertos: verificar proporciones reales contra el angular de las fotos"
    return None


def detectar_bajas_precio(avisos: list[dict], historial: dict | None = None):
    """Detecta si los avisos bajaron de precio respecto a un historial de versiones previas."""
    if not historial:
        return
    for a in avisos:
        prev = historial.get(a["id"])
        if not prev:
            continue
        p_prev = prev.get("precio")
        p_act = a.get("precio")
        if p_prev and p_act and p_prev > p_act:
            diff = p_prev - p_act
            pct = round((diff / p_prev) * 100)
            if pct >= 3:
                a["baja_precio"] = True
                a["precio_anterior"] = p_prev
                a["ahorro_baja"] = diff
                a["descuento_porcentaje"] = pct
                a["nota_baja_precio"] = (
                    f"Bajó un {pct}% ({_plata(p_prev)} -> {_plata(p_act)}; ahorro de {_plata(diff)})"
                )
                a.setdefault("motivos_a_favor", []).insert(
                    0, f"📉 BAJA DE PRECIO: Bajó un {pct}% ({_plata(p_prev)} -> {_plata(p_act)})"
                )


def detectar_datos_sospechosos(aviso: dict, mediana: float | None = None) -> list[str]:
    """Detecta inconsistencias o errores de parseo en superficie o precio.

    Dos chequeos forenses:
      a) m2_total/ambientes fuera de [12, 60] m² por ambiente. Si falta m2_total
         o ambientes, o ambientes es 0, no se marca (faltante no es implausible).
      b) costo_m2_ranking fuera de [0.25x, 4x] la mediana. Si falta el dato o
         la mediana es None o 0, no se marca.
    """
    motivos: list[str] = []

    # a) m2_total/ambientes fuera de [12, 60] m² por ambiente
    m2_tot = aviso.get("m2_total")
    amb = aviso.get("ambientes")
    if m2_tot is not None and amb is not None:
        try:
            m2_val = float(m2_tot)
            amb_val = float(amb)
            if amb_val > 0 and m2_val > 0:
                m2_por_amb = m2_val / amb_val
                if m2_por_amb < 12 or m2_por_amb > 60:
                    m2_txt = f"{int(m2_val)}" if m2_val == int(m2_val) else f"{m2_val:.1f}"
                    amb_txt = f"{int(amb_val)} ambiente" if amb_val == 1 else f"{int(amb_val)} ambientes"
                    motivos.append(f"declara {m2_txt} m² para {amb_txt}")
        except (TypeError, ValueError):
            pass

    # b) costo_m2_ranking fuera de [0.25x, 4x] la mediana de referencia
    c_m2 = aviso.get("costo_m2_ranking")
    if c_m2 is None:
        c_m2 = aviso.get("costo_m2")
    if c_m2 is not None and mediana is not None and mediana > 0:
        try:
            c_m2_val = float(c_m2)
            if c_m2_val < 0.25 * mediana or c_m2_val > 4.0 * mediana:
                motivos.append(
                    f"precio por m² anómalo ({_plata(c_m2_val)}/m² vs mediana {_plata(mediana)}/m²)"
                )
        except (TypeError, ValueError):
            pass

    aviso["datos_sospechosos"] = motivos
    return motivos


def puntuar(avisos: list[dict], presupuesto: float | None = None, dolar: float = 1450.0,
            historial: dict | None = None) -> list[dict]:
    """Agrega score y columnas explicativas a cada aviso. Devuelve la lista ordenada."""
    # Asegurar detección de tipo y re-evaluar 'sin expensas' sobre descripciones completas
    for a in avisos:
        if not a.get("tipo"):
            from zp.parseo import detectar_tipo
            a["tipo"] = detectar_tipo(
                a.get("url", ""),
                a.get("titulo", ""),
                a.get("descripcion_completa") or a.get("descripcion") or "",
            )
        if not a.get("expensas_informadas"):
            from zp.parseo import _leer_expensas
            exp, inf = _leer_expensas(
                str(a.get("expensas") or ""),
                a.get("descripcion_completa") or a.get("descripcion") or "",
                titulo=a.get("titulo") or "",
                url=a.get("url") or "",
                tipo=a.get("tipo", ""),
            )
            if inf:
                a["expensas"] = exp
                a["expensas_informadas"] = inf

    # 0) Estimar las expensas que faltan, antes de calcular cualquier costo.
    ratio_ref = imputar_expensas(avisos, dolar)

    # 1) Costo, análisis de superficies y $/m² de cada uno.
    for a in avisos:
        a["costo_mensual"] = costo_mensual(a, dolar)
        texto = " ".join(
            str(a.get(k) or "")
            for k in ("titulo", "descripcion", "descripcion_completa", "destacado",
                      "disposicion", "luminosidad", "orientacion")
        )
        analizar_superficies(a, texto)

        m2 = a.get("m2_total") or a.get("m2_cubierto")
        a["m2_usado"] = m2

        if not a.get("m2_confiable") and a.get("m2_cubierto_estimado"):
            m2_calc = a["m2_cubierto_estimado"]
            a["costo_m2_ranking"] = (a["costo_mensual"] / m2_calc) if (a["costo_mensual"] and m2_calc) else None
        else:
            a["costo_m2_ranking"] = (a["costo_mensual"] / m2) if (a["costo_mensual"] and m2) else None

        a["costo_m2"] = (a["costo_mensual"] / m2) if (a["costo_mensual"] and m2) else None
        alq = alquiler_en_pesos(a, dolar)
        exp = a.get("expensas_estimadas")
        a["ratio_expensas"] = (exp / alq) if (alq and exp) else None

    # 2) Referencia de mercado: mediana del $/m² de la búsqueda y control de anomalías.
    #
    # ¿Por qué dos pasadas (y no una sola, ni iterativo ni recursivo)?
    # El gate de precio/m² (b) requiere comparar contra la mediana de mercado, pero
    # si calculamos la mediana con todos los avisos crudos, errores groseros de
    # parseo (como 2 amb declarando 2.769 m² o alquileres de $6.000) envenenan la
    # referencia misma que necesitamos para evaluar.
    # Por eso se resuelve en dos pasadas determinísticas:
    #   (a) Mediana provisional usando SOLO el gate geométrico (m²/ambiente en [12, 60]),
    #       el cual es intrínseco a cada aviso y no depende de ninguna mediana externa.
    #   (b) Con esa mediana provisional se evalúa el gate de precio/m² (fuera de [0.25x, 4x]).
    #   (c) Con todos los sospechosos identificados (por gate a o b), se calcula la
    #       mediana definitiva por estrato de ambientes (o global con menos de 5 avisos)
    #       excluyendo a TODOS los sospechosos.

    # (a) Gate geométrico independiente + cálculo de mediana provisional
    sospechosos_geo = set()
    for a in avisos:
        motivos_geo = detectar_datos_sospechosos(a, mediana=None)
        if motivos_geo:
            sospechosos_geo.add(id(a))

    prov_estratos: dict[int, list[float]] = {}
    prov_global: list[float] = []
    for a in avisos:
        if id(a) not in sospechosos_geo and a.get("costo_m2_ranking"):
            c = a["costo_m2_ranking"]
            prov_global.append(c)
            amb = _entero(a.get("ambientes"))
            if amb and amb > 0:
                prov_estratos.setdefault(amb, []).append(c)

    med_prov_global = statistics.median(prov_global) if prov_global else None
    med_prov_estratos = {
        amb: statistics.median(vals)
        for amb, vals in prov_estratos.items()
        if len(vals) >= 5
    }

    # (b) Evaluación del gate de precio/m² con la referencia provisional
    for a in avisos:
        amb = _entero(a.get("ambientes"))
        if amb and amb in med_prov_estratos:
            med_ref_prov = med_prov_estratos[amb]
        else:
            med_ref_prov = med_prov_global

        detectar_datos_sospechosos(a, med_ref_prov)

    # (c) Mediana definitiva por estrato de ambientes excluyendo sospechosos
    def_estratos: dict[int, list[float]] = {}
    def_global: list[float] = []
    for a in avisos:
        if not a.get("datos_sospechosos") and a.get("costo_m2_ranking"):
            c = a["costo_m2_ranking"]
            def_global.append(c)
            amb = _entero(a.get("ambientes"))
            if amb and amb > 0:
                def_estratos.setdefault(amb, []).append(c)

    med_def_global = statistics.median(def_global) if def_global else None
    med_def_estratos = {
        amb: statistics.median(vals)
        for amb, vals in def_estratos.items()
        if len(vals) >= 5
    }

    for a in avisos:
        amb = _entero(a.get("ambientes"))
        if amb and amb in med_def_estratos:
            a["mediana_usada"] = med_def_estratos[amb]
            a["mediana_origen"] = f"{amb} amb"
        else:
            # OJO: este fallback tiene un sesgo conocido. La mediana global está
            # dominada por los 2 ambientes, que son la mayor parte de la oferta,
            # y el $/m² baja con el tamaño de la unidad: según ZPIndex (agosto
            # 2026, CABA) un monoambiente vale 18.378 $/m² contra 16.886 de un
            # 2 ambientes, casi 9% más caro POR SER CHICO, no por ser caro.
            # Así que a un monoambiente que cae acá se lo compara contra una
            # referencia que le queda baja y su 'valor' sale subestimado.
            # El arreglo no es inventar un factor: es ajustar la mediana global
            # por el gradiente real de mercado de ZPIndex para esa cantidad de
            # ambientes. Queda pendiente para cuando exista zp/zpindex.py.
            a["mediana_usada"] = med_def_global
            a["mediana_origen"] = "global"

    for a in avisos:
        texto = " ".join(
            str(a.get(k) or "")
            for k in ("titulo", "descripcion", "descripcion_completa", "destacado",
                      "disposicion", "luminosidad", "orientacion")
        )

        # --- dueño directo ---
        if re.search(r"due[nñ]o\s+directo|sin\s+comisi[oó]n|sin\s+honorarios|trato\s+directo|propietario\s+directo", _norm(texto)):
            a["es_dueno_directo"] = True
        else:
            a["es_dueno_directo"] = False

        # --- valor ---
        if a.get("datos_sospechosos"):
            valor = 0.35
        else:
            costo_ref = a.get("costo_m2_ranking") or a.get("costo_m2")
            mediana = a.get("mediana_usada")
            if costo_ref and mediana:
                rel = mediana / costo_ref
                valor = max(0.0, min(1.0, (rel - 0.55) / 0.9))
            else:
                valor = 0.35
        a["valor_vs_mercado"] = round(valor, 3)

        # --- calidad ---
        pts, pos, neg = señales(texto, a)

        for m in a.get("datos_sospechosos", []):
            neg.append(f"datos dudosos: {m}")

        if not a.get("m2_confiable"):
            pts -= 4
            neg.append(
                f"$/m² no confiable (declara {a.get('m2_usado', 0):.0f} m² pero tiene ~{a.get('m2_cubierto_estimado', 0):.0f} m² cubiertos; incluye exterior/terraza)"
            )

        if a.get("expensas_imputadas"):
            pts -= 6
            if a.get("expensas_estimadas"):
                neg.append(
                    f"no informa expensas (estimadas en {_plata(a['expensas_estimadas'])})"
                )
            else:
                neg.append("no informa expensas y no hay con qué estimarlas")

        faltantes = datos_faltantes(a, texto)
        if faltantes:
            pts -= sum(costo for _, costo in faltantes)
            neg.append("aviso con poca info: falta "
                       + ", ".join(etiqueta for etiqueta, _ in faltantes))
        a["datos_faltantes"] = [etiqueta for etiqueta, _ in faltantes]

        # --- requisitos contractuales estructurados ---
        contrato = parsear_contrato(texto)
        a["garantias_aceptadas"] = contrato["garantias_aceptadas"]
        a["politica_mascotas"] = contrato["politica_mascotas"]
        a["ajuste_frecuencia"] = contrato["ajuste_frecuencia"]
        a["ajuste_indice"] = contrato["ajuste_indice"]
        a["deposito_monto"] = contrato["deposito_monto"]
        a["plazo_contrato"] = contrato["plazo_contrato"]
        a["costos_adicionales"] = contrato["costos_adicionales"]

        # --- días en mercado ---
        dias = calcular_dias_mercado(a.get("fecha_publicacion") or "")
        a["dias_publicado"] = dias
        if dias is not None:
            if dias <= 7:
                pos.append("oportunidad reciente (< 7 días en mercado)")
            elif dias >= 45:
                pos.append(f"en mercado hace {dias} días (margen para negociar valor)")

        # --- micro-entorno ---
        entorno = analizar_entorno(a, texto)
        a["entorno_tipo"] = entorno["entorno_tipo"]
        a["avenidas_cercanas"] = entorno["avenidas_cercanas"]
        a["estaciones_cercanas"] = entorno["estaciones_cercanas"]

        # --- caja inicial de entrada ---
        caja_tot, caja_res, caja_des = calcular_caja_inicial(a, dolar)
        a["caja_inicial_total"] = caja_tot
        a["caja_inicial_resumen"] = caja_res
        a["caja_inicial_desglose"] = caja_des

        # --- simulación de inflación / evolución de cuota a 24 meses ---
        proy = simular_evolucion_alquiler(a, dolar=dolar)
        a["proyeccion_alquiler"] = proy
        a["proyeccion_resumen"] = proy.get("resumen", "")

        # --- alerta gran angular ---
        alerta_ga = detectar_alerta_gran_angular(a, texto)
        a["alerta_gran_angular"] = alerta_ga

        a["motivos_a_favor"] = pos
        a["motivos_en_contra"] = neg
        calidad = max(0.0, min(1.0, (pts + 20) / 55))
        a["calidad_texto"] = round(calidad, 3)

        # --- riesgo ---
        r, motivos_r = riesgo_humedad(a, texto)
        a["riesgo_humedad"] = r
        a["motivos_riesgo"] = motivos_r
        seguridad = max(0.0, 1 - r / 10)

        # --- preguntas para la visita ---
        a["preguntas_visita"] = generar_preguntas_visita(a)
        if alerta_ga:
            a["preguntas_visita"].insert(0, alerta_ga)

        score = (
            PESOS["valor"] * valor
            + PESOS["calidad"] * calidad
            + PESOS["riesgo"] * seguridad
        )

        # --- filtros duros ---
        motivos_descarte = []
        if presupuesto and a.get("costo_mensual") and a["costo_mensual"] > presupuesto:
            sufijo = " estimado" if a.get("expensas_imputadas") else ""
            motivos_descarte.append(
                f"supera el presupuesto ({_plata(a['costo_mensual'])}{sufijo})"
            )
        if a.get("precio") is None:
            motivos_descarte.append("precio a consultar")
        if a.get("costo_mensual") is None and a.get("precio") is not None:
            motivos_descarte.append("no informa expensas y no hay con qué estimarlas")
        if any("TEMPORAL" in m for m in neg):
            motivos_descarte.append("alquiler temporal")
        if a.get("ratio_expensas") and a["ratio_expensas"] > 0.45:
            motivos_descarte.append(
                f"expensas altísimas ({a['ratio_expensas']:.0%} del alquiler)"
            )
        a["descartado"] = bool(motivos_descarte)
        a["motivos_descarte"] = motivos_descarte

        a["score"] = round(score if not motivos_descarte else score * 0.25, 1)

    # 3) Identificar duplicados y disparidades de precios para negociación
    identificar_duplicados(avisos)

    # 4) Detectar bajas de precio contra historial previo si existe
    detectar_bajas_precio(avisos, historial)

    # Los descartados quedan SIEMPRE después de todos los vivos (False < True).
    # Dentro de cada grupo, ordenados por score descendente (-score).
    return sorted(avisos, key=lambda a: (bool(a.get("descartado")), -a["score"]))



