"""Generador de Ficha de Visita Presencial y Mensajes para Inmobiliarias.
"""

from __future__ import annotations

import html
import urllib.parse
from pathlib import Path


def _plata(v) -> str:
    if v is None:
        return "-"
    if v == 0:
        return "$0"
    return f"${v:,.0f}".replace(",", ".")


def generar_ficha_visita(run: str, top_avisos: list[dict], carpeta: Path) -> Path:
    """Genera una guía/checklist imprimible y móvil para el día de las visitas presenciales."""
    lineas = [
        f"# 📋 Planilla de Inspección Presencial · {run}",
        "",
        "> Llevá esta planilla en el celular o impresa el día que salgas a recorrer propiedades.",
        "",
        "## 🛠️ PROTOCOLO FORENSE EN 5 PASOS (Chequear en TODAS las visitas)",
        "",
        "- [ ] **1. Agua y Desagüe**:",
        "  - Abrir la canilla de la cocina y la ducha del baño simultáneamente para verificar presión.",
        "  - Mirar abajo de la bacha de la cocina con la linterna del celular (verificar sifón sin pérdidas ni aglomerado podrido).",
        "- [ ] **2. Electricidad y Tablero**:",
        "  - Ubicar el tablero general: apretar el botón **T (Test)** del disyuntor diferencial (debe cortar de inmediato).",
        "  - Contar enchufes en cocina y dormitorio (¿alcanzan para microondas, pava, heladera, computadora?).",
        "- [ ] **3. Humedad y Muros**:",
        "  - Alumbrar zócalos de madera (¿hinchados o con pintura descascarada?).",
        "  - Mirar esquinas superiores del techo y cielorraso del baño (¿moho por vapor o filtración?).",
        "- [ ] **4. Aberturas y Ventilación**:",
        "  - Subir y bajar persianas completas (verificar que no estén trabadas ni deshilachadas).",
        "  - Probar trabas y cierre hermético de ventanas.",
        "- [ ] **5. Gas y Calefacción**:",
        "  - Verificar rejillas reglamentarias de ventilación (arriba y abajo).",
        "  - Comprobar funcionamiento de estufa tiro balanceado / calefón.",
        "",
        "---",
        "",
        "## 🏡 FICHAS INDIVIDUALES POR PROPIEDAD",
        "",
    ]

    for idx, a in enumerate(top_avisos[:15], start=1):
        aid = a.get("id")
        score = a.get("score")
        dir_txt = a.get("direccion") or "Sin dirección"
        barrio = a.get("barrio") or ""
        costo = _plata(a.get("costo_mensual"))
        caja = _plata(a.get("caja_inicial_total"))
        tipo = (a.get("tipo") or "departamento").upper()
        m2 = a.get("m2_total") or "?"
        amb = a.get("ambientes") or "?"
        gar = ", ".join(a.get("garantias_aceptadas") or ["Consultar"])
        url = a.get("url") or "#"

        lineas += [
            f"### #{idx} · {dir_txt} ({tipo} · Score {score})",
            f"- **ID**: `{aid}` | **Barrio**: {barrio}",
            f"- **Costo Mensual**: {costo} | **Caja de Entrada**: {caja} | **Ambientes**: {amb} amb ({m2} m²)",
            f"- **Garantías declaradas**: {gar}",
            f"- **Link**: [Ver en Zonaprop]({url})",
            "",
            "**🔍 Preguntas específicas para hacerle al martillero in situ:**",
        ]
        preguntas = a.get("preguntas_visita") or []
        for p in preguntas:
            lineas.append(f"- [ ] {p}")

        lineas += [
            "",
            "**📝 Anotaciones de la visita:**",
            "- Calidad de luz natural (1 al 5): ⭐ ____",
            "- Nivel de ruido de la calle (1 al 5): 🔇 ____",
            "- Presión de agua / cañerías: ________________________________________________",
            "- Impresión del propietario / inmobiliaria: _________________________________",
            "- ¿Vale la pena hacer contraoferta?: [ ] Sí  [ ] No  (Oferta: $____________)",
            "",
            "---",
            "",
        ]

    destino = carpeta / "ficha_visita.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino


def generar_mensajes_inmobiliarias(run: str, top_avisos: list[dict], carpeta: Path) -> Path:
    """Genera mensajes_inmobiliarias.txt con textos listos para consultar por WhatsApp / Email."""
    bloques = [
        f"MENSAJES PREARMADOS DE CONSULTA PARA INMOBILIARIAS · {run}",
        "=" * 70,
        "Instrucciones: Copiá y pegá el mensaje para consultar a cada inmobiliaria.",
        "=" * 70,
        "",
    ]

    for idx, a in enumerate(top_avisos[:20], start=1):
        aid = a.get("id")
        score = a.get("score")
        dir_txt = a.get("direccion") or "Sin dirección"
        costo = _plata(a.get("costo_mensual"))
        amb = a.get("ambientes") or "?"
        tipo = (a.get("tipo") or "departamento").capitalize()
        url = a.get("url") or ""

        msg = (
            f"Hola! Te consulto por el alquiler del {tipo} de {amb} ambientes en {dir_txt} "
            f"(Ref Zonaprop #{aid}). ¿Sigue disponible? Cuento con garantía y recibos de sueldo listos. "
            f"¿Qué días y horarios tienen disponibles para coordinar una visita? Muchas gracias!"
        )

        bloques += [
            f"#{idx} | ID: {aid} | Score: {score} | {dir_txt} ({costo}/mes)",
            f"Link: {url}",
            "Mensaje:",
            f'"{msg}"',
            "-" * 70,
            "",
        ]

    destino = carpeta / "mensajes_inmobiliarias.txt"
    destino.write_text("\n".join(bloques), encoding="utf-8")
    return destino

