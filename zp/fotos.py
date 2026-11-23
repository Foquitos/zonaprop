"""Descarga de fotos y armado de la hoja de contacto.

Dos salidas por aviso:

  fotos/<id>/01.jpg, 02.jpg, ...   las fotos en resolución alta (1200px)
  contactos/<id>.jpg               una sola imagen con todas en grilla, numeradas

La hoja de contacto sirve para el triage rápido ("¿cuál de estas 14 fotos tiene
algo raro?"); la foto individual sirve para confirmar. Mirar 20 hojas de
contacto cuesta lo mismo que mirar 20 fotos sueltas, y cubre 250.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.zonaprop.com.ar/",
}


COLA = 5  # cuántas fotos del final se reservan siempre


def muestrear(urls: list[str], maximo: int) -> tuple[list[str], set[int]]:
    """Elige qué fotos bajar cuando hay más que el tope, y cuáles son del final.

    Las inmobiliarias suben las fotos en un orden bastante constante: primero
    living y cocina, al final la fachada, el palier, los amenities y el plano.
    Cortar con `urls[:maximo]` se comía justo la fachada, que es donde se ve el
    escurrimiento bajo los balcones y el revoque saltado. Este muestreo se
    queda con el arranque y reserva siempre las últimas COLA.

    Devuelve (urls elegidas, índices 1-based que vienen del final).
    """
    if len(urls) <= maximo:
        elegidas = list(urls)
        marca_desde = max(1, len(elegidas) - COLA + 1)
    else:
        cabeza = urls[: maximo - COLA]
        cola = urls[-COLA:]
        elegidas = cabeza + cola
        marca_desde = len(cabeza) + 1
    return elegidas, set(range(marca_desde, len(elegidas) + 1))


def _base_url(u: str) -> str:
    return u.split("?")[0]


def descargar(urls: list[str], destino: Path, maximo: int = 16) -> list[Path]:
    """Baja las fotos elegidas como 01.jpg, 02.jpg... y devuelve las que quedaron.

    El número del archivo ES el número de la foto en la hoja de contacto, y
    queda fijo aunque alguna descarga falle: si se cae la 3, la hoja muestra
    1, 2, 4, 5... en vez de renumerar desde la 3 en adelante. Antes se
    numeraba por posición, y una sola foto rota corría todos los números: las
    marcas naranjas, el "mirar sí o sí las 12-16" del dossier y los hallazgos
    del auditor terminaban apuntando a otra foto.

    `urls.json` guarda qué URL corresponde a cada número. Si la inmobiliaria
    cambia la galería, el slot cuya URL cambió se vuelve a bajar en vez de
    reusar la foto vieja del caché.
    """
    destino.mkdir(parents=True, exist_ok=True)
    guardadas: list[Path] = []
    elegidas, _ = muestrear(urls, maximo)

    indice_archivo = destino / "urls.json"
    previas: dict[str, str] = {}
    if indice_archivo.exists():
        try:
            previas = json.loads(indice_archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"    ! no pude leer {indice_archivo} ({e}); vuelvo a bajar todas las fotos")
            previas = {}
    sin_indice = not indice_archivo.exists()

    for i, u in enumerate(elegidas, start=1):
        ruta = destino / f"{i:02d}.jpg"
        misma_url = previas.get(str(i)) == _base_url(u)
        # Sin urls.json (fotos bajadas antes de que existiera) se confía en el
        # caché como antes: no hay con qué comparar.
        if ruta.exists() and (misma_url or sin_indice):
            guardadas.append(ruta)
            continue
        try:
            r = requests.get(u, headers=HEADERS, timeout=30)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            img.save(ruta, "JPEG", quality=88)
            guardadas.append(ruta)
        except Exception as e:  # una foto rota no debe frenar la corrida
            print(f"    ! no pude bajar la foto {i}: {e}")

    indice_archivo.write_text(
        json.dumps({str(i): _base_url(u) for i, u in enumerate(elegidas, start=1)},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return guardadas


def numero_de_foto(ruta: Path, posicion: int) -> int:
    """El número que se imprime en la hoja: el del archivo (07.jpg -> 7)."""
    return int(ruta.stem) if ruta.stem.isdigit() else posicion


def _fuente(tam: int):
    for ruta in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default()


def hoja_contacto(fotos: list[Path], salida: Path, titulo: str, columnas: int = 3,
                  ancho_celda: int = 620, marcadas: set[int] | None = None) -> Path | None:
    """Arma una grilla numerada con todas las fotos del aviso.

    `marcadas` son los números (1-based) de las fotos del final de la galería,
    que se resaltan en naranja: ahí suelen estar la fachada, el palier y el
    plano, y son las que hay que mirar sí o sí para el diagnóstico de humedad.
    """
    if not fotos:
        return None

    marcadas = marcadas or set()
    alto_celda = int(ancho_celda * 0.72)
    filas = (len(fotos) + columnas - 1) // columnas
    margen, banda = 12, 92

    lienzo = Image.new(
        "RGB",
        (columnas * ancho_celda + margen * (columnas + 1),
         banda + filas * alto_celda + margen * (filas + 1)),
        (24, 24, 27),
    )
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.text((margen, 16), titulo[:110], font=_fuente(28), fill=(245, 245, 245))
    if marcadas:
        dibujo.text(
            (margen, 56),
            "En naranja, el final de la galería: fachada, palier, amenities, plano.",
            font=_fuente(20), fill=(255, 150, 60),
        )

    for idx, ruta in enumerate(fotos):
        n = numero_de_foto(ruta, idx + 1)
        fila, col = divmod(idx, columnas)
        x = margen + col * (ancho_celda + margen)
        y = banda + margen + fila * (alto_celda + margen)
        try:
            img = Image.open(ruta).convert("RGB")
        except (OSError, ValueError) as e:
            print(f"    ! la foto {ruta.name} está dañada y queda fuera de la hoja: {e}")
            continue
        img = _encajar(img, ancho_celda, alto_celda)
        lienzo.paste(img, (x, y))

        if n in marcadas:
            dibujo.rectangle([x, y, x + ancho_celda - 1, y + alto_celda - 1],
                             outline=(255, 150, 60), width=5)

        # Pastilla de número de foto con alto contraste para visión artificial del LLM
        ancho_badge = 62 if n >= 10 else 46
        alto_badge = 34
        bx0, by0 = x + 6, y + 6
        bx1, by1 = bx0 + ancho_badge, by0 + alto_badge

        if n in marcadas:
            fondo = (255, 145, 40)
            texto = (10, 10, 10)
            borde = (255, 200, 120)
        else:
            fondo = (15, 15, 18)
            texto = (255, 230, 80)
            borde = (75, 75, 80)

        # Dibujar pastilla con borde sutil
        dibujo.rounded_rectangle([bx0, by0, bx1, by1], radius=4, fill=fondo, outline=borde, width=1)
        # Centrar el número en la pastilla
        tx = bx0 + ancho_badge // 2
        ty = by0 + alto_badge // 2
        dibujo.text((tx, ty), f"{n}", font=_fuente(22), fill=texto, anchor="mm")

    salida.parent.mkdir(parents=True, exist_ok=True)
    lienzo.save(salida, "JPEG", quality=88)
    return salida


def _encajar(img: Image.Image, ancho: int, alto: int) -> Image.Image:
    """Recorta al centro para llenar la celda sin deformar."""
    ratio_dest, ratio_orig = ancho / alto, img.width / img.height
    if ratio_orig > ratio_dest:
        nuevo_ancho = int(img.height * ratio_dest)
        izq = (img.width - nuevo_ancho) // 2
        img = img.crop((izq, 0, izq + nuevo_ancho, img.height))
    else:
        nuevo_alto = int(img.width / ratio_dest)
        arriba = (img.height - nuevo_alto) // 2
        img = img.crop((0, arriba, img.width, arriba + nuevo_alto))
    return img.resize((ancho, alto), Image.LANCZOS)
