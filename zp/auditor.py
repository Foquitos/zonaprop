"""Auditoría de avisos con la API de Claude: fotos + texto -> veredicto.

Reemplaza el paso manual de copiar PROMPT_LLM.md, dossier.md y las hojas de
contacto en un chat. El veredicto vuelve al programa (`auditoria.json`) y de
ahí al dashboard, la ficha de visita y los mensajes a inmobiliarias.

Dos pasadas:

  primera   Sonnet mira la hoja de contacto de cada aviso. Barato: se puede
            correr sobre todo el top.
  segunda   Opus revisa los que la primera no descartó, con las fotos sueltas
            en resolución completa (la hoja de contacto recorta los bordes de
            cada foto, que es justo donde se ve la deformación del gran
            angular) y con el veredicto de Sonnet a la vista para confirmarlo
            o corregirlo.

Una llamada por aviso, no una gigante con todos: así se puede cortar y
retomar, reintentar uno solo, y no se vuelve a pagar por un aviso que no
cambió (ver `huella`).

`anthropic` se importa sólo dentro de las funciones que llaman a la API, igual
que Playwright: el resto del programa tiene que andar sin él.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import io
import json
from pathlib import Path

from zp import bloques, corrida, perfil

MODELOS = {
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
MODELO_POR_ETAPA = {"primera": "sonnet", "segunda": "opus"}

# USD por millón de tokens (entrada, salida). Sólo para estimar el gasto y
# cortar con --tope-usd; la cuenta real la lleva la Console.
PRECIOS = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# Estimación previa por aviso, medida sobre las hojas reales (~4.7k tokens de
# imagen + ~3.5k de texto + ~2.5k de salida) y, en la segunda, ~16 fotos sueltas.
COSTO_ESTIMADO_AVISO = {"primera": 0.045, "segunda": 0.20}

# La API rechaza imágenes de más de 5 MB.
MAX_BYTES_IMAGEN = 4_500_000

VEREDICTOS = ("APROBADO", "CON_RESERVAS", "DESCARTADO")
TIPOS_HALLAZGO = ("humedad", "fachada", "instalacion", "espacio", "luz",
                  "estado", "trampa_aviso", "otro")

ESQUEMA = {
    "type": "object",
    "properties": {
        "veredicto": {"type": "string", "enum": list(VEREDICTOS)},
        "score_visual": {"type": "integer"},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "resumen": {"type": "string"},
        "vicio_critico": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "hallazgos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "foto": {"type": "integer"},
                    "tipo": {"type": "string", "enum": list(TIPOS_HALLAZGO)},
                    "gravedad": {"type": "string", "enum": ["leve", "media", "grave"]},
                    "observacion": {"type": "string"},
                },
                "required": ["foto", "tipo", "gravedad", "observacion"],
                "additionalProperties": False,
            },
        },
        "contradicciones": {"type": "array", "items": {"type": "string"}},
        "fotos_a_revisar_en_visita": {"type": "array", "items": {"type": "integer"}},
        "preguntas_visita": {"type": "array", "items": {"type": "string"}},
        "pregunta_para_inmobiliaria": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "negociacion": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "diferencias_con_revision_previa": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": [
        "veredicto", "score_visual", "confianza", "resumen", "vicio_critico",
        "hallazgos", "contradicciones", "fotos_a_revisar_en_visita",
        "preguntas_visita", "pregunta_para_inmobiliaria", "negociacion",
        "diferencias_con_revision_previa",
    ],
    "additionalProperties": False,
}


class CorteAuditoria(Exception):
    """Un error que hace inútil seguir con el resto de los avisos (sin
    credenciales, sin créditos, rate limit persistente)."""


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parents[1]


def _rubrica() -> str:
    ruta = RAIZ / "RUBRICA_FOTOS.md"
    if not ruta.exists():
        return ""
    return ruta.read_text(encoding="utf-8")


def prompt_sistema() -> str:
    """El system prompt. Es idéntico en todas las llamadas para que el caché
    de prompts lo cobre a 0.1x desde el segundo aviso."""
    return f"""Sos un perito arquitecto que audita avisos de alquiler de Zonaprop (CABA y GBA Norte, Argentina) para una persona que busca dónde vivir.

## Quién alquila
- Contrato de {perfil.PERFIL['plazo_meses']} meses.
- Garantías disponibles: {perfil.describir_garantias()}. No descartes un aviso por pedir garantía propietaria de CABA o de Provincia: tiene las dos.
- Tiene recibos de sueldo.

## Qué te llega por cada aviso
- Un bloque YAML con los datos que el programa ya extrajo (precio, expensas, superficie, contrato, señales del texto, distancia a barrios populares del RENABAP).
- La descripción del aviso, entera.
- Las fotos: o una hoja de contacto (una grilla con cada foto numerada en una pastilla en la esquina; las de borde naranja son el final de la galería, donde suelen estar fachada, palier y plano), o las fotos sueltas precedidas por "Foto N". Puede faltar algún número si esa descarga falló: usá siempre el número que ves impreso o anunciado, nunca la posición.

## Tu trabajo
Cruzar lo declarado con lo que muestran las fotos y decidir si vale la pena ir a verlo.

1. Humedad, filtraciones y estado del edificio. La fachada no miente: si el texto y la fachada se contradicen, creele a la fachada.
2. Distorsión del gran angular contra los m² y las medidas declaradas.
3. Instalaciones (eléctrica, gas, calefacción, cocina, baño) y luz natural real.
4. Trampas del aviso: renders, fotos de otra unidad, galería inflada con amenities.
5. Viabilidad económica y contractual: costo total, caja de entrada, ajuste, expensas.

## Reglas
- Cada hallazgo cita el número de foto donde se ve. Si no lo ves en una foto concreta, no es un hallazgo: va en preguntas_visita o en contradicciones.
- No inventes. Si una foto no deja ver algo (por resolución, encuadre o porque no está), decilo con confianza "baja" en vez de suponer.
- Lo que una foto no puede decir (ruido, olor, presión de agua, estado del consorcio, sol en invierno) va a preguntas_visita, nunca a hallazgos.
- La cercanía a un barrio popular del RENABAP es un dato de informalidad en la tenencia de la tierra, no una estadística de delito. No lo uses como motivo de descarte por sí solo.

## Veredicto
- APROBADO: sin fallas graves a la vista, vale la pena coordinar visita pronto.
- CON_RESERVAS: visitable, pero hay un punto crítico que se tiene que chequear en persona.
- DESCARTADO: vicio grave visible (humedad estructural, estado ruinoso), distribución inviable o trampa contractual.

score_visual va de 0 (no se puede vivir ahí) a 100 (impecable), y mide sólo lo que se ve en las fotos.
resumen es una sola oración, la que leería alguien que tiene diez segundos.
vicio_critico es null si no hay ninguno.
pregunta_para_inmobiliaria es UNA pregunta concreta para mandar por WhatsApp antes de ir, sobre lo que más importa aclarar de este aviso; null si no hace falta.
negociacion: si hay margen (duplicado más barato, baja de precio, mucho tiempo publicado, defectos visibles), cómo usarlo; null si no hay.
diferencias_con_revision_previa: sólo si te pasan una revisión previa; qué confirmás y qué corregís. null si no hay revisión previa.
Escribí en castellano rioplatense, directo y concreto.

## Rúbrica de referencia
{_rubrica()}
"""


# --------------------------------------------------------------------------- #
# Entradas
# --------------------------------------------------------------------------- #

def _imagen_b64(ruta: Path) -> str:
    datos = ruta.read_bytes()
    if len(datos) > MAX_BYTES_IMAGEN:
        from PIL import Image

        img = Image.open(io.BytesIO(datos)).convert("RGB")
        calidad = 85
        while True:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=calidad)
            datos = buf.getvalue()
            if len(datos) <= MAX_BYTES_IMAGEN or calidad <= 40:
                break
            calidad -= 15
            img = img.resize((int(img.width * 0.85), int(img.height * 0.85)))
    return base64.standard_b64encode(datos).decode("ascii")


def _bloque_imagen(ruta: Path) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": _imagen_b64(ruta)},
    }


def fotos_sueltas(carpeta: Path, aviso_id: str) -> list[tuple[int, Path]]:
    dir_fotos = carpeta / "fotos" / aviso_id
    if not dir_fotos.exists():
        return []
    salida = []
    for ruta in sorted(dir_fotos.glob("*.jpg")):
        if ruta.stem.isdigit():
            salida.append((int(ruta.stem), ruta))
    return salida


def hoja_contacto(carpeta: Path, aviso_id: str) -> Path | None:
    ruta = carpeta / "contactos" / f"{aviso_id}.jpg"
    return ruta if ruta.exists() else None


def numeros_disponibles(carpeta: Path, aviso_id: str) -> set[int]:
    """Qué números de foto existen de verdad, para validar lo que cita el modelo."""
    return {n for n, _ in fotos_sueltas(carpeta, aviso_id)}


def armar_contenido(carpeta: Path, aviso: dict, etapa: str,
                    previa: dict | None = None) -> list[dict]:
    aid = str(aviso["id"])
    texto = "\n".join(
        [f"# Aviso {aid}", ""]
        + bloques.bloque_yaml(aviso)
        + ["## Descripción del aviso", ""]
        + bloques.bloque_descripcion(aviso)
    )
    contenido: list[dict] = [{"type": "text", "text": texto}]

    if etapa == "segunda" and fotos_sueltas(carpeta, aid):
        finales = sorted(aviso.get("fotos_final_galeria") or [])
        contenido.append({
            "type": "text",
            "text": ("Fotos sueltas en resolución completa."
                     + (f" Las {', '.join(map(str, finales))} son el final de la galería "
                        "(fachada, palier, plano)." if finales else "")),
        })
        for n, ruta in fotos_sueltas(carpeta, aid):
            contenido.append({"type": "text", "text": f"Foto {n}"})
            contenido.append(_bloque_imagen(ruta))
    else:
        hoja = hoja_contacto(carpeta, aid)
        if hoja:
            contenido.append({"type": "text", "text": "Hoja de contacto con las fotos numeradas:"})
            contenido.append(_bloque_imagen(hoja))

    if previa:
        contenido.append({
            "type": "text",
            "text": ("Revisión previa de otro modelo, mirando sólo la hoja de contacto. "
                     "Confirmala o corregila mirando las fotos vos mismo; no la des por buena:\n"
                     + json.dumps(previa, ensure_ascii=False, indent=2)),
        })
    return contenido


def huella(carpeta: Path, aviso: dict, etapa: str, modelo: str,
           previa: dict | None = None) -> str:
    """Cambia si cambia cualquier cosa que el modelo ve. Si no cambió, no se
    vuelve a pagar la auditoría de ese aviso."""
    aid = str(aviso["id"])
    h = hashlib.sha256()
    partes = {
        "prompt": hashlib.sha256(prompt_sistema().encode("utf-8")).hexdigest(),
        "esquema": ESQUEMA,
        "modelo": modelo,
        "etapa": etapa,
        "descripcion": aviso.get("descripcion_completa") or aviso.get("descripcion") or "",
        "precio": aviso.get("precio"),
        "moneda": aviso.get("moneda"),
        "expensas": aviso.get("expensas"),
        "m2": aviso.get("m2_total"),
        "previa": previa,
    }
    h.update(json.dumps(partes, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    imagenes: list[Path] = []
    if etapa == "segunda" and fotos_sueltas(carpeta, aid):
        imagenes = [r for _, r in fotos_sueltas(carpeta, aid)]
    elif hoja_contacto(carpeta, aid):
        imagenes = [hoja_contacto(carpeta, aid)]
    for ruta in imagenes:
        h.update(ruta.name.encode())
        h.update(hashlib.sha256(ruta.read_bytes()).digest())
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Respuesta
# --------------------------------------------------------------------------- #

def validar_veredicto(datos: dict, disponibles: set[int], aviso_id: str) -> dict:
    """Descarta lo que cite fotos inexistentes en vez de mostrarlo como hecho."""
    if datos.get("veredicto") not in VEREDICTOS:
        raise ValueError(f"veredicto desconocido: {datos.get('veredicto')!r}")
    try:
        datos["score_visual"] = max(0, min(100, int(datos.get("score_visual") or 0)))
    except (TypeError, ValueError):
        datos["score_visual"] = 0

    if disponibles:
        validos = []
        for h in datos.get("hallazgos") or []:
            if h.get("foto") in disponibles:
                validos.append(h)
            else:
                print(f"    ! {aviso_id}: el modelo citó la foto {h.get('foto')}, que no existe; "
                      f"descarto ese hallazgo ({(h.get('observacion') or '')[:60]})")
        datos["hallazgos"] = validos
        datos["fotos_a_revisar_en_visita"] = [
            n for n in datos.get("fotos_a_revisar_en_visita") or [] if n in disponibles
        ]
    return datos


def _texto_respuesta(respuesta) -> str:
    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "text":
            return bloque.text
    raise ValueError("la respuesta no trae ningún bloque de texto")


def _costo_usd(modelo: str, uso) -> float:
    pin, pout = PRECIOS.get(modelo, PRECIOS["claude-opus-5-5"])
    entrada = getattr(uso, "input_tokens", 0) or 0
    escritura = getattr(uso, "cache_creation_input_tokens", 0) or 0
    lectura = getattr(uso, "cache_read_input_tokens", 0) or 0
    salida = getattr(uso, "output_tokens", 0) or 0
    return (entrada * pin + escritura * pin * 1.25 + lectura * pin * 0.1
            + salida * pout) / 1_000_000


def _tokens(uso) -> dict:
    return {
        k: getattr(uso, k, 0) or 0
        for k in ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens")
    }


# --------------------------------------------------------------------------- #
# Llamada
# --------------------------------------------------------------------------- #

def crear_cliente():
    try:
        import anthropic
    except ImportError as e:
        raise CorteAuditoria(
            "Falta el SDK de Anthropic. Instalalo con:\n"
            "    .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from e
    try:
        return anthropic.Anthropic(max_retries=4)
    except anthropic.AnthropicError as e:
        raise CorteAuditoria(_ayuda_credenciales(str(e))) from e


def _ayuda_credenciales(detalle: str) -> str:
    return (
        f"No hay credenciales para la API de Claude ({detalle}).\n"
        "  1. En claude.ai > Settings > Billing > API credits, reclamá los créditos\n"
        "     de Max vinculando una organización de la Console.\n"
        "  2. En platform.claude.com, creá una API key en ESA organización.\n"
        "  3. Guardala en la variable de entorno ANTHROPIC_API_KEY, por ejemplo:\n"
        "       setx ANTHROPIC_API_KEY \"sk-ant-...\"\n"
        "     y abrí una consola nueva (o reiniciá el menú)."
    )


def llamar(cliente, modelo: str, contenido: list[dict]):
    """Un aviso, una llamada. Devuelve la respuesta cruda del SDK."""
    return cliente.beta.messages.create(
        model=modelo,
        max_tokens=16000,
        # Si el clasificador de seguridad rechaza la llamada (muy raro con
        # fotos de departamentos), la API la reintenta sola con otro modelo
        # en vez de devolver un rechazo.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=[{"type": "text", "text": prompt_sistema(),
                 "cache_control": {"type": "ephemeral"}}],
        output_config={
            # Opus 5.5 trae "medium" por defecto; para leer humedad en una
            # foto conviene que piense más.
            "effort": "high",
            "format": {"type": "json_schema", "schema": ESQUEMA},
        },
        messages=[{"role": "user", "content": contenido}],
    )


def auditar_aviso(cliente, carpeta: Path, aviso: dict, etapa: str, modelo: str,
                  previa: dict | None = None) -> dict:
    """Audita un aviso y devuelve la entrada para auditoria.json.

    Los errores de la API que no ameritan cortar todo se convierten en una
    entrada con "error" (sin huella, así se reintenta en la próxima corrida).
    """
    import anthropic

    aid = str(aviso["id"])
    base = {"modelo": modelo, "fecha": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        respuesta = llamar(cliente, modelo, armar_contenido(carpeta, aviso, etapa, previa))
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise CorteAuditoria(_ayuda_credenciales(f"{type(e).__name__}: {e}")) from e
    except TypeError as e:
        # Sin API key el SDK no falla al crear el cliente sino en el primer
        # pedido, y con un TypeError en vez de un error propio.
        if "authentication" in str(e).lower():
            raise CorteAuditoria(_ayuda_credenciales("no encontré ANTHROPIC_API_KEY")) from e
        raise
    except anthropic.RateLimitError as e:
        raise CorteAuditoria(
            f"La API sigue limitando la velocidad después de varios reintentos ({e}). "
            "Lo auditado hasta acá quedó guardado; volvé a correr en un rato y sigue desde donde quedó."
        ) from e
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            raise CorteAuditoria(
                "Se acabaron los créditos de la API de este mes (o todavía no los reclamaste). "
                "Lo auditado hasta acá quedó guardado."
            ) from e
        print(f"    ! {aid}: la API rechazó el pedido ({e})")
        return {**base, "error": f"BadRequest: {e}"}
    except anthropic.APIConnectionError as e:
        print(f"    ! {aid}: sin conexión con la API ({e})")
        return {**base, "error": f"Conexión: {e}"}
    except anthropic.APIStatusError as e:
        print(f"    ! {aid}: error {e.status_code} de la API ({e})")
        return {**base, "error": f"HTTP {e.status_code}: {e}"}

    modelo_real = getattr(respuesta, "model", None) or modelo
    uso = getattr(respuesta, "usage", None)
    base.update(modelo=modelo_real, tokens=_tokens(uso), costo_usd=round(_costo_usd(modelo_real, uso), 4))
    if modelo_real != modelo:
        print(f"    · {aid}: {modelo} rechazó el pedido y lo respondió {modelo_real}")

    if respuesta.stop_reason == "refusal":
        print(f"    ! {aid}: el modelo se negó a responder")
        return {**base, "error": "El modelo se negó a responder (refusal)"}
    if respuesta.stop_reason == "max_tokens":
        print(f"    ! {aid}: la respuesta se cortó por largo")
        return {**base, "error": "Respuesta cortada (max_tokens)"}

    try:
        datos = json.loads(_texto_respuesta(respuesta))
        datos = validar_veredicto(datos, numeros_disponibles(carpeta, aid), aid)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"    ! {aid}: no pude interpretar la respuesta ({e})")
        return {**base, "error": f"Respuesta inválida: {e}"}

    base["veredicto"] = datos
    return base


# --------------------------------------------------------------------------- #
# auditoria.json
# --------------------------------------------------------------------------- #

def cargar(carpeta: Path) -> dict:
    datos = corrida.leer_json(carpeta / "auditoria.json", {})
    if not isinstance(datos, dict):
        return {"avisos": {}}
    datos.setdefault("avisos", {})
    return datos


def guardar(carpeta: Path, datos: dict) -> None:
    corrida.escribir_json(carpeta / "auditoria.json", datos)


def veredicto_vigente(entrada: dict | None) -> dict | None:
    """El último veredicto válido: el de Opus si hubo segunda revisión."""
    if not entrada:
        return None
    for etapa in ("segunda", "primera"):
        e = entrada.get(etapa)
        if e and e.get("veredicto"):
            return {**e["veredicto"], "etapa": etapa, "modelo": e.get("modelo"),
                    "fecha": e.get("fecha")}
    return None


def anotar_avisos(carpeta: Path, avisos: list[dict]) -> int:
    """Le pega a cada aviso en memoria su veredicto vigente (clave "auditoria").

    No toca ranking.json: el veredicto se muestra al lado del score, no lo
    modifica, porque el modelo puede ver humedad donde no la hay.
    """
    datos = cargar(carpeta)
    n = 0
    for a in avisos:
        v = veredicto_vigente(datos["avisos"].get(str(a.get("id"))))
        if v:
            a["auditoria"] = v
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Corrida completa
# --------------------------------------------------------------------------- #

def elegir_avisos(carpeta: Path, ranking: list[dict], etapa: str, top: int,
                  ids: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Qué avisos auditar. Devuelve (elegidos, avisos sobre lo que quedó afuera)."""
    notas: list[str] = []
    datos = cargar(carpeta)
    if ids:
        por_id = {str(a["id"]): a for a in ranking}
        faltan = [i for i in ids if i not in por_id]
        if faltan:
            notas.append(f"no están en el ranking: {', '.join(faltan)}")
        candidatos = [por_id[i] for i in ids if i in por_id]
    else:
        candidatos = [a for a in ranking if not a.get("descartado")]

    def tiene_fotos(a):
        return bool(hoja_contacto(carpeta, str(a["id"])) or fotos_sueltas(carpeta, str(a["id"])))

    elegidos = []
    for a in candidatos:
        aid = str(a["id"])
        if not tiene_fotos(a):
            continue
        if etapa == "segunda":
            v = (datos["avisos"].get(aid) or {}).get("primera") or {}
            if not v.get("veredicto"):
                continue
            if not ids and v["veredicto"]["veredicto"] == "DESCARTADO":
                continue
        elegidos.append(a)
        if not ids and len(elegidos) >= top:
            break

    # Sólo se avisa por los del top que se quedan afuera: si el ranking cambió
    # desde el último `fotos`, hay avisos nuevos arriba sin hojas de contacto.
    ventana = candidatos if ids else candidatos[:top]
    sin_fotos = sum(1 for a in ventana if not tiene_fotos(a))
    if sin_fotos and etapa == "primera":
        notas.append(f"{sin_fotos} de los primeros {len(ventana)} del ranking no tienen fotos todavía "
                     "(corré `fotos` para incluirlos)")
    return elegidos, notas


def auditar_corrida(carpeta: Path, ranking: list[dict], etapa: str = "primera",
                    modelo_corto: str | None = None, top: int = 20,
                    ids: list[str] | None = None, forzar: bool = False,
                    tope_usd: float | None = None, cliente=None) -> dict:
    modelo_corto = modelo_corto or MODELO_POR_ETAPA[etapa]
    modelo = MODELOS[modelo_corto]
    elegidos, notas = elegir_avisos(carpeta, ranking, etapa, top, ids)
    for n in notas:
        print(f"  · {n}")
    resumen = {"auditados": 0, "salteados": 0, "errores": 0, "costo_usd": 0.0, "cortado": None}
    if not elegidos:
        if etapa == "segunda":
            print("No hay avisos para la segunda revisión: corré primero la auditoría con Sonnet.")
        else:
            print("No hay avisos con fotos para auditar.")
        return resumen

    datos = cargar(carpeta)
    pendientes = []
    for a in elegidos:
        aid = str(a["id"])
        entrada = datos["avisos"].get(aid) or {}
        previa = None
        if etapa == "segunda":
            previa = (entrada.get("primera") or {}).get("veredicto")
        hu = huella(carpeta, a, etapa, modelo, previa)
        actual = entrada.get(etapa) or {}
        if not forzar and actual.get("huella") == hu and actual.get("veredicto"):
            resumen["salteados"] += 1
            continue
        pendientes.append((a, previa, hu))

    if resumen["salteados"]:
        print(f"  · {resumen['salteados']} ya estaban auditados y no cambiaron (--forzar para repetirlos)")
    if not pendientes:
        print("Nada nuevo para auditar.")
        return resumen

    estimado = COSTO_ESTIMADO_AVISO[etapa] * len(pendientes)
    print(f"Audito {len(pendientes)} avisos con {modelo} "
          f"(~USD {estimado:.2f} estimado{', tope USD ' + format(tope_usd, '.2f') if tope_usd else ''})\n")

    try:
        cliente = cliente or crear_cliente()
    except CorteAuditoria as e:
        resumen["cortado"] = str(e)
        print(e)
        return resumen
    fallas_seguidas = 0
    for i, (a, previa, hu) in enumerate(pendientes, 1):
        aid = str(a["id"])
        if tope_usd is not None and resumen["costo_usd"] >= tope_usd:
            resumen["cortado"] = f"se llegó al tope de USD {tope_usd:.2f}"
            print(f"\nCorto: {resumen['cortado']}.")
            break
        print(f"[{i}/{len(pendientes)}] {aid} · {(a.get('direccion') or '')[:50]}")
        try:
            entrada = auditar_aviso(cliente, carpeta, a, etapa, modelo, previa)
        except CorteAuditoria as e:
            resumen["cortado"] = str(e)
            print(f"\n{e}")
            break

        resumen["costo_usd"] += entrada.get("costo_usd") or 0.0
        if entrada.get("veredicto"):
            entrada["huella"] = hu
            resumen["auditados"] += 1
            fallas_seguidas = 0
            v = entrada["veredicto"]
            print(f"    {v['veredicto']} · visual {v['score_visual']} · {v['resumen'][:90]}")
        else:
            resumen["errores"] += 1
            fallas_seguidas += 1

        datos["avisos"].setdefault(aid, {})[etapa] = entrada
        # Se guarda después de CADA aviso: si se corta la luz o se toca
        # "Frenar", lo pagado no se pierde.
        guardar(carpeta, datos)

        if fallas_seguidas >= 3:
            resumen["cortado"] = "tres errores seguidos de la API"
            print(f"\nCorto: {resumen['cortado']}. Lo auditado quedó guardado.")
            break

    escribir_markdown(carpeta, ranking, datos)
    print(f"\n{resumen['auditados']} auditados · {resumen['errores']} con error · "
          f"gasto estimado USD {resumen['costo_usd']:.2f}")
    print(f"-> {carpeta / 'auditoria.json'}")
    print(f"-> {carpeta / 'auditoria.md'}")
    return resumen


def escribir_markdown(carpeta: Path, ranking: list[dict], datos: dict) -> Path:
    """La versión para leer de auditoria.json, en el orden del ranking."""
    lineas = [f"# Auditoría de fotos · {carpeta.name}", ""]
    por_id = {str(a["id"]): a for a in ranking}
    orden = [aid for aid in (str(a["id"]) for a in ranking) if aid in datos["avisos"]]
    orden += [aid for aid in datos["avisos"] if aid not in por_id]
    for aid in orden:
        entrada = datos["avisos"][aid]
        a = por_id.get(aid, {})
        lineas.append(f"## {aid} · {a.get('direccion') or '?'}")
        for etapa in ("primera", "segunda"):
            e = entrada.get(etapa)
            if not e:
                continue
            titulo = "Primera revisión" if etapa == "primera" else "Segunda revisión"
            if e.get("error"):
                lineas += [f"**{titulo}** ({e.get('modelo')}): error — {e['error']}", ""]
                continue
            v = e["veredicto"]
            lineas += [
                f"**{titulo}** ({e.get('modelo')}, {e.get('fecha', '')[:10]}): "
                f"**{v['veredicto']}** · score visual {v['score_visual']} · confianza {v['confianza']}",
                "",
                v["resumen"],
                "",
            ]
            if v.get("vicio_critico"):
                lineas.append(f"- **Vicio crítico**: {v['vicio_critico']}")
            for h in v.get("hallazgos") or []:
                lineas.append(f"- Foto {h['foto']} ({h['tipo']}, {h['gravedad']}): {h['observacion']}")
            for c in v.get("contradicciones") or []:
                lineas.append(f"- Contradicción: {c}")
            if v.get("diferencias_con_revision_previa"):
                lineas.append(f"- Contra la primera revisión: {v['diferencias_con_revision_previa']}")
            if v.get("negociacion"):
                lineas.append(f"- Negociación: {v['negociacion']}")
            if v.get("preguntas_visita"):
                lineas.append("- Para preguntar en la visita:")
                lineas += [f"  - {p}" for p in v["preguntas_visita"]]
            lineas.append("")
    destino = carpeta / "auditoria.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino
