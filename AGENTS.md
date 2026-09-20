# Zonaprop · Auditor Forense de Alquileres

Scraper de Zonaprop (Playwright) + scoring + generación de dossier/dashboard.
Pipeline: `buscar` → `rankear` → `fotos` → `dossier`.

## Convenciones NO negociables

- **Todo el código, comentarios, docstrings y salida al usuario van en español.**
  Los nombres de funciones y variables también (`puntuar`, `avisos`, `carpeta`).
- Python 3.10+, `from __future__ import annotations` al tope de cada módulo.
- Sin dependencias nuevas salvo que se pidan explícitamente. Las actuales:
  playwright, selectolax, requests, Pillow.
- Playwright se importa SOLO dentro de funciones, nunca a nivel de módulo:
  `rankear`, `dossier`, `zonas` y `menu` tienen que correr sin él instalado.
- Los archivos de `salida/` son datos reales del usuario: NO los borres ni los
  regeneres. Podés leerlos.
- Tests: `python -m pytest tests/ -q`. Hoy pasan 71. No podés bajar ese número.
  El fixture (`tests/fixture_listado.py`) es una captura real del sitio; no lo
  edites para que un test pase.

## Estructura

```
zp.py                 CLI: buscar, rankear, fotos, dossier, diff, zonas, menu
zp/zonas.py           catálogo de zonas + validación del <h1>
zp/urls.py            armado de URLs de Zonaprop
zp/navegador.py       Playwright + detección de desafío Cloudflare
zp/parseo.py          parseo de listado (data-qa) y detalle (JSON embebido)
zp/scoring.py         pesos, señales del texto, ranking
zp/fotos.py           descarga de fotos + hojas de contacto
zp/geocodificador.py  Nominatim + caché en disco
zp/mapa.py            export GeoJSON / KML
zp/dashboard.py       dashboard HTML con Leaflet
zp/visita.py          ficha imprimible + mensajes de WhatsApp
zp/prompt.py          prompt maestro para el LLM
zp/menu.py            menú Tkinter
```

## Estilo

- Comentarios que explican **por qué**, no qué. El repo ya tiene varios que
  documentan decisiones (por qué no se recortan las últimas fotos, por qué no
  se recarga la página durante el captcha). Seguí ese tono: directo, concreto.
- Nada de `except Exception: pass` nuevo. Si tenés que atrapar, avisá por
  `print` con contexto.
- Los helpers de formato de plata devuelven `$1.234.567` (punto como separador
  de miles, estilo argentino).
