"""Generador del Prompt Maestro para diagnóstico forense de avisos con LLM.

Crea un archivo PROMPT_LLM.md listo para copiar y pegar en Claude o Gemini junto
al dossier.md y las hojas de contacto en contactos/.
"""

from __future__ import annotations

from pathlib import Path


def generar_prompt_diagnostico(run: str, top_avisos: list[dict], carpeta: Path) -> Path:
    """Genera un archivo PROMPT_LLM.md en la carpeta del run."""
    total_avisos = len(top_avisos)
    ids_lista = ", ".join(str(a["id"]) for a in top_avisos[:10])

    contenido = f"""# 🏛️ INSTRUCCIONES DE AUDITORÍA FORENSE INMOBILIARIA

**Búsqueda**: `{run}`
**Total de candidatos analizados**: {total_avisos} avisos (Top IDs: {ids_lista}...)
**Archivos adjuntos**: `dossier.md` (metadatos y requisitos) + `contactos/<id>.jpg` (hojas de contacto con fotos numeradas).

---

## 🎯 TU ROL Y OBJETIVO
Sos un **Perito Arquitecto y Auditor Forense Inmobiliario**. Tu tarea es inspeccionar de forma crítica y minuciosa los departamentos/PHs candidatos a alquiler, cruzando los **datos declarados en `dossier.md`** con la **evidencia visual de las hojas de contacto (`contactos/<id>.jpg`)**.

El usuario busca una vivienda para alquilar por 2 años, cuenta con garante en CABA y PBA (y opción FINAER), y necesita:
1. **Detectar vicios ocultos de humedad, estructurales o de instalaciones** antes de visitar.
2. **Desarmar distorsiones espaciales** (fotos con lente gran angular vs m² cubiertos reales).
3. **Evaluar la viabilidad económica y contractual** (caja inicial de entrada, ajuste, expensas reales).
4. **Identificar oportunidades de negociación agresiva** (duplicados entre inmobiliarias, propiedades estancadas o con bajas de precio).

---

## 🔍 METODOLOGÍA DE INSPECCIÓN VISUAL (Foto por Foto)

Al analizar la hoja de contacto `contactos/<id>.jpg`, revisá específicamente:

### 1. Humedad y Filtraciones (Mirar con lupa)
- **Zócalos y partes bajas de paredes**: ¿Hay pintura descascarada, aureolas amarillentas, zócalos de madera hinchados o revoque abombado? (Típico de humedad de cimientos o PH en PB).
- **Cielorrasos y esquinas superiores**: ¿Se ven manchas oscuras de moho por condensación o marcas de chorreado desde techos/terrazas?
- **Bajo mesada y vanitory**: ¿El aglomerado del mueble está hinchado o podrido por goteo de sifones?
- **Recién pintado sospechoso**: ¿Hay paredes con pintura hiper fresca y despareja que parecen tapar una mancha reciente?

### 2. Espacio y Distorsión de Gran Angular
- **Deformación en bordes**: ¿Las puertas, camas o zócalos se ven curvados o estirados en los extremos de la foto?
- **Cruce con medidas**: Si el texto declara dormitorio de $2.50 \\times 2.60\\text{{ m}}$, no te dejes engañar por una foto que parece una suite presidencial.

### 3. Instalaciones y Mantenimiento
- **Instalación eléctrica**: ¿Tiene disyuntor diferencial y llaves térmicas modernas, o tapones antiguos? ¿Hay enchufes suficientes?
- **Calefacción y cañerías**: ¿Tiene estufa tiro balanceado instalada? ¿Se ven caños de termofusión exteriores o cañerías de plomo/hierro originales?
- **Luz natural real**: ¿La foto tiene las luces del techo encendidas a pleno sol? Si es contrafrente en piso bajo, verificá si da a un pulmón oscuro o si tiene luz natural directa.

---

## 📋 FORMATO DE RESPUESTA ESPERADO

Por favor estructurá tu respuesta de la siguiente forma:

### 1. Tabla Resumen y Veredicto Final
| # | ID | Dirección | Score Inicial | Score Visual | Veredicto | Vicio Crítico Detectado / Fortaleza |
|---|---|---|---|---|---|---|
| 1 | 59658007 | Laprida 4500 | 76.9 | **XX** | APROBADO / CON RESERVAS / DESCARTADO | ... |
| 2 | ... | ... | ... | ... | ... | ... |

*(Veredictos posibles: **APROBADO** = Sin fallas graves, apto para coordinar visita prioritaria; **CON RESERVAS** = Visitable pero requiere chequear punto crítico in situ; **DESCARTADO** = Vicio grave de humedad, distribución inviable o trampa contractual).*

---

### 2. Diagnóstico Detallado de los Top Candidatos (Top 5-10)
Para cada aviso clave:
- **Análisis de Fotos Clave**:
  - *Foto #X*: [Observación precisa, ej: "En la foto 4 se observa escurrimiento bajo la ventana"].
  - *Foto #Y*: [Observación, ej: "Bajo mesada en buen estado, cerámicos sanos"].
- **Riesgos Ocultos y Contradicciones**: [Qué oculta la publicación o qué contradice las fotos].
- **Análisis Contractual y Financiero**: [Evaluación de caja de entrada, expensas y cláusula de ajuste].
- **Estrategia de Negociación**:
  - *Precio de entrada sugerido / Contraoferta*: [Si es duplicado o lleva días publicado, cómo ofertar].
  - *Preguntas obligatorias para hacerle al martillero en la visita*.

---

### 3. Plan de Acción Recomendado (Orden de Visitas)
1. **Prioridad 1 para visitar**: [ID y motivo].
2. **Prioridad 2 para visitar**: [ID y motivo].
3. **Propiedades a descartar inmediatamente**: [IDs y motivos concretos].
"""

    destino = carpeta / "PROMPT_LLM.md"
    destino.write_text(contenido.strip(), encoding="utf-8")
    return destino

