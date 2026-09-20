# Scraper & Análisis Forense de Alquileres de Zonaprop

[![Developed with Vibecoding](https://img.shields.io/badge/Developed%20with-Vibecoding%20%E2%9C%A8-8a2be2?style=for-the-badge)](https://en.wikipedia.org/wiki/Vibe_coding)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automated-green?style=for-the-badge&logo=playwright)](https://playwright.dev/)

> ⚡ **Proyecto desarrollado con metodología Vibecoding**: Construido de manera ágil, modular e iterativa en colaboración con Inteligencia Artificial, integrando scraping resiliente, heurísticas financieras, visión computacional con LLMs y dashboards interactivos.

Dos etapas: el scraper corre en tu máquina y deja los datos en `salida/<run>/`;
después se alimentan los LLMs (Claude / Gemini) o se visualiza en el dashboard para el análisis pericial, incluida la revisión de fotos.

La separación no es un capricho: Zonaprop está detrás de DataDome y bloquea IPs
de datacenter, así que desde el entorno cloud no se puede scrapear (lo probé,
rebota). Desde tu conexión con un navegador real anda bien.

## Instalación (una vez)

```bash
pip install -r requirements.txt
playwright install chromium
```

Para desarrollo y correr la suite de tests (`python -m pytest tests/`):

```bash
pip install -r requirements-dev.txt
```

## Uso: el menú

```bash
python zp.py menu
```

Abre una ventana con el árbol de zonas a la izquierda, los filtros a la derecha
y los cuatro pasos abajo, con el log en vivo. Al hacer clic en una zona se
explica qué abarca, que es donde está la diferencia entre "Vicente López, el
partido entero" y "Vicente López, la localidad". Con Ctrl + clic se eligen
varias y se hace una corrida por cada una.

Cada botón lanza el mismo `zp.py` de la terminal como subproceso, y abajo de
los botones se muestra el comando exacto, para copiarlo cuando quieras
automatizar algo sin la ventana.

Tkinter viene con Python, así que no hay que instalar nada extra.

## Uso: la terminal

```bash
# 1. Barrer el listado. Una búsqueda por cada valor de --ambientes, dedup por id.
python zp.py buscar --zona vicente-lopez --ambientes 1 2 --paginas 6

# 2. Puntuar por precio, m², expensas y señales del texto.
python zp.py rankear --run vicente-lopez-1-2amb-alquiler --presupuesto 900000 --dolar 1450

# 3. Bajar el detalle y las fotos del top 20 (esta es la etapa lenta).
python zp.py fotos --run vicente-lopez-1-2amb-alquiler --top 20

# 4. Armar el markdown que acompaña a las fotos.
python zp.py dossier --run vicente-lopez-1-2amb-alquiler
```

Después me pasás `salida/<run>/dossier.md` y la carpeta `salida/<run>/contactos/`,
y te devuelvo el análisis. Si querés que mire alguna foto en detalle, están
sueltas en `salida/<run>/fotos/<id>/`.

## Las zonas

```bash
python zp.py zonas                      # el catálogo completo
python zp.py zonas --buscar martelli    # filtrado
```

Hay tres niveles y conviene tenerlos claros porque el nombre no alcanza:

| Nivel | Ejemplo | Qué trae |
|---|---|---|
| Región | `gba-norte`, `capital-federal` | Miles de avisos. Sirve para sondear precios, no para buscar |
| Partido | `vicente-lopez`, `san-isidro` | Todo el partido: Olivos, Florida, La Lucila, Munro, Carapachay, Villa Martelli y la localidad de Vicente López |
| Localidad o barrio | `villa-martelli`, `olivos`, `nunez` | Una sola |

**Zonaprop no tira 404 cuando el slug no existe.** Devuelve status 200 con
resultados de otro lado, y sin darte cuenta te llevás 600 avisos equivocados.
Los casos que verifiqué a mano:

| Lo que parece razonable | Lo que devuelve |
|---|---|
| `zona-norte` | 45.738 avisos **de toda la Argentina** |
| `barrio-chino` | 45.738 avisos de toda la Argentina |
| `san-martin` | 4 avisos de San Martín, **Mendoza** — hay que usar `general-san-martin` |
| `la-lucila` | 0 avisos — hay que usar `la-lucila-vicente-lopez` |
| `florida-belgrano` | "Belgrano, CABA **o** Florida, Vicente López": el guion de más lo interpreta como dos zonas |

Por eso cada zona del catálogo guarda el texto que Zonaprop tiene que devolver
en el `<h1>`, y el scraper compara antes de guardar nada. Si no coincide, corta
la corrida con el diagnóstico en vez de seguir. El catálogo está en
`zp/zonas.py`; agregar una zona es agregar una línea, pero conviene abrir la URL
primero y copiar el `<h1>` textual.

### Parámetros

| Flag | Qué hace |
|---|---|
| `--zona` | slug del catálogo: `vicente-lopez`, `villa-martelli`, `nunez`, `capital-federal` |
| `--ambientes` | uno o varios, ej. `1 2`. Se hace una búsqueda por cada uno |
| `--tipos` | `departamentos ph casas` (default: departamentos y PH) |
| `--paginas` | tope de páginas por búsqueda; cada página son 30 avisos |
| `--presupuesto` | tope de **alquiler + expensas**, no solo del alquiler |
| `--dolar` | cotización para convertir los avisos en USD (default 1450) |
| `--top` | cuántos avisos pasan a la etapa de fotos |
| `--headless` | sin ventana. Más rápido pero más detectable, y no podés resolver la verificación; usalo recién en la segunda corrida |
| `--espera-captcha` | segundos para tildar el casillero de verificación (default 240) |
| `--canal` | `chrome` (default, el instalado) o `chromium` (el de Playwright) |

### Sobre la verificación de seguridad

Zonaprop usa **Cloudflare**. Cuando salta, aparece la pantalla de "Un momento... /
Verificación de seguridad en curso" con el casillero para tildar.

Cuando eso pasa, el scraper **no toca más la página**: te avisa en el log, espera
hasta 4 minutos (`--espera-captcha`, o el campo del menú) y chequea una vez por
segundo si ya pasaste. No recarga, no navega, no reintenta. Vos tildás el
casillero con calma y sigue solo.

Una vez resuelta, la cookie queda en `.perfil-chrome/` y las corridas siguientes
no la vuelven a pedir por un buen rato.

Para que salte menos seguido:

- **Corré sin `--headless` la primera vez.** Sin ventana no hay forma de tildar
  nada. El menú te avisa si lo tenés tildado. Una vez que la cookie está
  guardada, sí podés volver a headless.
- **Se usa el Chrome que tenés instalado**, no el Chromium de Playwright, porque
  recibe bastantes menos verificaciones. Si no lo encuentra, cae solo al de
  Playwright. Se puede forzar con `--canal chromium`.
- **Se pasa primero por la home** antes de ir a la búsqueda. Entrar directo a una
  URL de resultados sin cookies y sin referer es de las cosas que más lo disparan.
- **No uses `--rapido`.** Entre página y página hay una pausa aleatoria de 2 a 4
  segundos a propósito. Y bajá `--paginas` si te frena seguido.

## Qué sale del scraping

De la tarjeta del listado: precio, moneda, expensas, m² totales y cubiertos,
ambientes, dormitorios, baños, cocheras, dirección, barrio, inmobiliaria y el
copete de la descripción.

De la página de detalle (solo del top N, porque es una request por aviso):
**antigüedad del edificio, orientación, disposición (frente/contrafrente/interno),
luminosidad declarada**, la descripción completa y la galería entera en 1200px.

Esos cuatro campos del detalle son los que más mueven la aguja y no están en el
listado, por eso el flujo está partido en dos.

## Cómo se arma el score

`score = 45 × valor + 35 × calidad + 20 × (1 − riesgo)`

- **valor**: tu $/m² contra la mediana de $/m² de esa misma búsqueda. O sea, no
  contra un número inventado: contra lo que se está pidiendo hoy en esa zona por
  ese tipo de unidad.
- **calidad**: bonos y penalizaciones que salen del texto del aviso y de los
  features. Luminoso, orientación norte, a estrenar, doble vidrio, balcón,
  acepta mascotas suman; a refaccionar, contrafrente, interno, subsuelo, sin
  ascensor, pide garantía de CABA restan.
- **riesgo**: probabilidad a priori de humedad, antes de mirar una sola foto.
  Planta baja, subsuelo, contrafrente, orientación sur, último piso y edificios
  de más de 40 años la suben; los edificios nuevos la bajan. Este número **no es
  un veredicto**, es el orden en que reviso las fotos.

  La antigüedad es del **edificio** y el reciclado es de la **unidad**: reciclar
  un departamento no arregla la terraza, la fachada ni las cañerías troncales,
  que es de donde viene la mayoría de las filtraciones. Por eso un reciclado
  amortigua la penalización por antigüedad a la mitad, no la borra. Y "recién
  pintado" ahora **sube** el riesgo en vez de bajarlo: es justo lo que se hace
  antes de sacar las fotos cuando había una mancha.

Se descarta directo (score × 0.25) lo que supera el presupuesto, lo que no
publica precio, los alquileres temporales y los que tienen expensas por encima
del 45% del alquiler.

### El dato que falta también es dato

Tres reglas que salieron de revisar la primera corrida:

- **Expensas no informadas.** No valen cero. Se estiman con la mediana de
  expensas/alquiler de los avisos de esa misma búsqueda que sí las publican
  (mejor que un porcentaje fijo: no son las mismas expensas en una torre con
  amenities de Olivos que en un PH de Villa Martelli), se marcan como estimadas
  en el CSV y en el dossier, y restan puntos. Los ceros declarados quedan fuera
  del cálculo de la mediana: un PH sin consorcio no es "expensas baratas".
- **Avisos escuetos.** Un aviso de tres líneas no tiene nada malo escrito
  porque no tiene nada escrito. Antes eso lo dejaba arriba del que avisa
  honestamente que es planta baja. Ahora cada dato ausente —superficie,
  descripción, y después de la etapa de fotos también antigüedad, orientación y
  disposición— resta.
- **Antigüedad.** Se distingue "no informa" de "cero años", se entienden los
  valores no numéricos (`A estrenar`, `En pozo`) que antes se perdían, y se saca
  del texto cuando la ficha no la trae ("edificio de 38 años de antigüedad").

Los pesos y las listas de señales están en `zp/scoring.py`, en `PESOS`, `BONOS`,
`PENAS` y `RIESGO_HUMEDAD`. Están pensadas para que las toques.

### Dos criterios configurados por defecto
 
- **Garantía**: los avisos que piden garantía propietaria *exclusiva de CABA* restan
  puntos si se busca alquilar con garantía de Provincia de Buenos Aires (o seguros de caución FINAER). Vale la pena consultarlo
  igual, muchas inmobiliarias lo flexibilizan.
- **Alquiler temporal**: en Vicente López y Olivos buena parte de la oferta
  publicada en USD es temporal o amoblada. Se descarta por defecto; si querés
  verla, sacá esa regla de `PENAS`.

## Las hojas de contacto

`python zp.py fotos` arma, además de bajar las fotos sueltas, una imagen por
aviso con todas las fotos en grilla y numeradas (`salida/<run>/contactos/<id>.jpg`).

Mirar 20 hojas de contacto cuesta lo mismo que mirar 20 fotos sueltas y cubre
250 fotos. Sirve para el triage: encuentro en cuáles hay algo raro y después voy
a la foto individual en alta para confirmar. Por eso el script guarda las dos
cosas.

**Las últimas fotos de la galería nunca se recortan.** Las inmobiliarias suben
las fotos en un orden bastante constante: primero living y cocina, al final la
fachada, el palier, los amenities y el plano. Cortar con `fotos[:16]` se comía
justo la fachada, que es donde se ve el chorreado bajo los balcones y el revoque
saltado — y es lo que contradice al texto del aviso cuando el interior está
recién pintado. Ahora, cuando la galería supera el tope, se toma el arranque y
se reservan siempre las últimas 5, que además van marcadas en naranja en la hoja
de contacto y listadas en el dossier.

Qué busco exactamente en cada foto está en [RUBRICA_FOTOS.md](RUBRICA_FOTOS.md),
incluida la lista de lo que una foto **no** puede decir.

## El dossier lleva el aviso entero

`dossier.md` incluye la descripción completa de cada publicación, sin recortar.
Tuvo un tope de 900 caracteres que era un error del mismo tipo que el de las
fotos: cortaba la cola. En los avisos de Zonaprop el final es justo donde van
los requisitos —qué garantía piden y de qué jurisdicción, mascotas, meses de
adelanto y depósito, ajuste, honorarios—, que es lo que decide si un
departamento es viable antes de ir a verlo. El score nunca se vio afectado
(se calcula sobre el texto completo que guarda `ranking.json`), pero al que leía
el dossier le faltaba esa parte.

Si alguna vez necesitás acotarlo, está `--max-descripcion N`; por defecto es 0,
o sea entera.

Antes de correr `fotos` el dossier solo tiene el copete de la tarjeta, que corta
Zonaprop. En ese caso lo aclara, para que no se lea como el aviso completo.

## Estructura

```
zp.py                 CLI: buscar, rankear, fotos, dossier, zonas, menu
zp/menu.py            el menú visual (Tkinter)
zp/zonas.py           catálogo de zonas verificadas + validación del h1
zp/urls.py            armado de las URLs semánticas de Zonaprop
zp/navegador.py       Playwright con perfil persistente y detección de captcha
zp/parseo.py          listado (data-qa) y detalle (JSON embebido)
zp/scoring.py         pesos, señales del texto, datos faltantes y ranking
zp/fotos.py           descarga, muestreo que conserva la fachada, hojas de contacto
tests/                fixture con la estructura real + 46 tests
tests/test_desafio.py test de integración del captcha con un servidor local
salida/<run>/         listado.json, ranking.csv, fotos/, contactos/, dossier.md
```

Playwright se importa recién cuando hace falta un navegador, así que `rankear`,
`dossier`, `zonas` y `menu` funcionan aunque no esté instalado.

## Mantenimiento

Zonaprop cambia el front cada tanto. Los puntos que se pueden romper:

0. **El proveedor anti-bot.** Hoy es Cloudflare; antes de agosto de 2026 la
   detección buscaba marcas de DataDome y por eso el desafío pasaba
   desapercibido. Si algún día ni se detecta ni se pasa, las marcas están en
   `_MARCAS_CLOUDFLARE` y `_MARCAS_DATADOME` en `zp/navegador.py`. El síntoma es
   que el paso se cuelga o termina sin avisos en vez de frenarse pidiéndote que
   tildes el casillero.


1. Los `data-qa` de las tarjetas (`POSTING_CARD_PRICE`, `expensas`,
   `POSTING_CARD_FEATURES`, ...). Son bastante estables porque los usan para sus
   propios tests.
2. El regex `resizeUrl1200x1200` del detalle, que es de donde sale la galería
   completa.

Si un día `buscar` devuelve 0 avisos, es lo primero a revisar. `python -m pytest
tests/` corre contra el fixture y te dice si el parser sigue en pie, pero el
fixture es una copia de agosto de 2026: si el sitio cambió, hay que recapturar.

Y una tercera, más silenciosa: los slugs de zona. Si Zonaprop renombra o mueve
una zona, el catálogo queda viejo, pero la validación del `<h1>` lo va a
cantar en la primera corrida en vez de dejarte con datos de otro lado.

---

## 🤖 Metodología de Desarrollo: Vibecoding

Este proyecto fue concebido y desarrollado bajo la filosofía **Vibecoding**: un proceso de ingeniería de software rápido, iterativo y altamente colaborativo guiado por Inteligencia Artificial / LLMs.

### ¿Cómo se estructuró el Vibecoding en este proyecto?
1. **Modelado y Arquitectura Híbrida**: La lógica pesada y determinística (scraping con Playwright, bypass y persistencia de Cloudflare, parsing de JSON embebido y cálculo de matriz financiera/scoring) corre en Python local.
2. **Razonamiento Multimodal (Vision LLM)**: En vez de forzar reglas rígidas para evaluar la calidad estética y estructural, el sistema compila *hojas de contacto fotográficas* y un *dossier markdown estructurado* para que un LLM actúe como un perito arquitecto forense detectando vicios ocultos (humedad, falta de luz, lente gran angular engañoso).
3. **Iteración Guiada por Feedback Empírico**: Cada feature (manejo de desafíos anti-bot, inferencia de expensas, deduplicación de avisos entre inmobiliarias, preservación de fotos de fachadas) nació de corridas reales y ajustes conversacionales inmediatos con el asistente IA.

