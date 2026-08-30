"""Genera HTML con la misma estructura que devuelve Zonaprop hoy.

Los atributos y el formato de los textos están copiados de una captura real de
/departamentos-ph-alquiler-vicente-lopez-2-ambientes.html (agosto 2026).
Sirve para probar el parser sin pegarle al sitio.
"""

CARD = """
<div class="postingCardLayout-module__posting-card-layout" data-id="{id}"
     data-posting-type="PROPERTY" data-qa="posting PROPERTY"
     data-to-posting="/propiedades/clasificado/{slug}-{id}.html">
  <div data-qa="POSTING_CARD_GALLERY">
    <img src="https://imgar.zonapropcdn.com/avisos/1/00/59/05/25/66/360x266/205124267{id}.jpg?isFirstImage=true"/>
    <img src="https://imgar.zonapropcdn.com/avisos/1/00/59/05/25/66/360x266/205124298{id}.jpg"/>
  </div>
  <div class="postingPrices-module__price">
    <div data-qa="POSTING_CARD_PRICE">{precio}</div>
    {bloque_expensas}
  </div>
  <h3 class="postingCard-module__highlight">{badge}</h3>
  <h2 class="postingCard-module__title">{titulo}</h2>
  <h3 data-qa="POSTING_CARD_FEATURES">{features}</h3>
  <div class="postingLocations-module__location-address">{direccion}</div>
  <h2 data-qa="POSTING_CARD_LOCATION">{barrio}</h2>
  <h3 data-qa="POSTING_CARD_DESCRIPTION">{descripcion}</h3>
  <div data-qa="POSTING_CARD_PUBLISHER">{publicador}</div>
</div>
"""

AVISOS = [
    dict(id="59052566", slug="alclapin-amoblad-2-ambientes-balcon", precio="USD 2.500",
         expensas="890.000", badge="Terraza", titulo="Departamento en Vicente López",
         features="100 m² tot. | 90 m² cub. | 2 amb. | 1 dorm. | 1 baño | 1 coch.",
         direccion="Av Libertador al 100", barrio="Vicente López, Vicente López",
         publicador="ONE BROKERS",
         descripcion="Espectacular departamento amoblado. Enorme living apaisado. "
                     "Salida a balcón terraza. Aire acondicionado central. Excelente vista al río."),
    dict(id="59553528", slug="alclphin-ph-1-dormitorio-florida", precio="$ 700.000",
         expensas="70.000", badge="Luminoso", titulo="PH 2 ambientes en Florida",
         features="40 m² tot. | 40 m² cub. | 2 amb. | 1 dorm. | 1 baño",
         direccion="Perú al 1200", barrio="Florida, Vicente López",
         publicador="DIC PROPIEDADES S.A.",
         descripcion="Departamento tipo casa de 2 ambientes ubicado dentro de complejo con "
                     "expensas mínimas ubicado en Florida Belgrano en la calle Perú al 1200 "
                     "entre Roca y Urquiza. Próximo a estación Florida ffcc línea Belgrano, a "
                     "Panamericana y a calle San Martín, en una ubicación donde se encuentran "
                     "todo tipo de medios de transporte público. El edificio es de estilo "
                     "moderno con solo 10 años de antigüedad. Existe la posibilidad de "
                     "alquilar cochera. Este departamento se encuentra en planta baja con "
                     "acceso independiente. Cuenta con 1 dormitorio con placard. Se ingresa a "
                     "un living comedor espacioso y luminoso que posee un mueble empotrado "
                     "multifunción que brinda mucho lugar de guardado. Luego está la cocina "
                     "integrada equipada con amoblamientos completos, espacio para lavarropas "
                     "y heladera. El agua caliente es por calefón y el baño es completo. Los "
                     "pisos son de porcelanato."),
    dict(id="59855694", slug="alclapin-depto-tipo-ph-sin-expensas", precio="$ 620.000",
         expensas=None, badge="", titulo="PH 2 ambientes sin expensas",
         features="45 m² tot. | 45 m² cub. | 2 amb. | 1 dorm. | 1 baño",
         direccion="Juan B. Justo al 800", barrio="Florida, Vicente López",
         publicador="Diego Novello",
         descripcion="¡Sin expensas! Departamento tipo PH 2 ambientes en planta baja, "
                     "totalmente independiente y listo para mudarse. Ubicado sobre Juan B. "
                     "Justo, en Florida, Vicente López, este 2 ambientes en planta baja es "
                     "impecable y cuenta con salida directa a la calle, brindando "
                     "independencia, comodidad y fácil acceso. Lo más destacado: depto tipo "
                     "PH 2 ambientes, no paga expensas, recién pintado, listo para ingresar, "
                     "planta baja con ingreso independiente y salida directa a la calle, aire "
                     "acondicionado frío calor en cada ambiente, cómoda cocina con muebles "
                     "sobre y bajo mesada, conexión para el lavarropas, dormitorio con "
                     "placard. Requisitos para ingresar: contrato de alquiler por 24 meses "
                     "con actualización trimestral según IPC, ingresos demostrables "
                     "equivalentes como mínimo a 2 veces el valor del alquiler, antigüedad "
                     "laboral mínima de 1 año, garantía propietaria familiar directo o seguro "
                     "de caución, 1 mes de alquiler adelantado, seguro contra incendio. "
                     "No acepta mascotas sin excepción perros y gatos."),
    dict(id="58506752", slug="alclapin-alquiler-temporal-con-muebles", precio="USD 1.800",
         expensas="450.000", badge="", titulo="Torre Nila La Lucila",
         features="70 m² tot. | 2 amb. | 1 dorm. | 2 baño | 1 coch.",
         direccion="Av. Libertador al 3500", barrio="La Lucila, Vicente López",
         publicador="Alec Hyland",
         descripcion="Espectacular departamento en alquiler temporal con vista abierta. "
                     "Totalmente amoblado y equipado. Roof top con piscina, spa con sauna."),
    dict(id="59983990", slug="alclapin-departamento-vicente-lopez", precio="$ 780.000",
         expensas="180.000", badge="", titulo="2 ambientes reciclado a nuevo",
         features="55 m² tot. | 52 m² cub. | 2 amb. | 1 dorm. | 1 baño",
         direccion="Laprida al 300", barrio="Vicente López, Vicente López",
         publicador="L.A PROPIEDADES",
         descripcion="Departamento de 2 ambientes de 55 m² reciclado a nuevo en piso 16 con "
                     "balcón. Excelente departamento de 2 ambientes en venta y en alquiler, "
                     "de 55 m² totales, ubicado en un piso 16 al contrafrente en la "
                     "distinguida zona de Vicente López. La propiedad se encuentra situada en "
                     "un edificio de 38 años de antigüedad equipado con 2 ascensores. La "
                     "unidad ha sido reciclada a nuevo, destacándose por su luminosidad, sus "
                     "acabados modernos y su agradable orientación Sureste con vistas "
                     "despejadas. Su distribución comprende un confortable living comedor "
                     "equipado con aire acondicionado y salida directa al balcón al "
                     "contrafrente, cocina independiente con sector de lavadero integrado, 1 "
                     "dormitorio de buenas dimensiones con placard empotrado y gran ventanal, "
                     "y 1 baño completo con bañera."),
    dict(id="59554450", slug="alclapin-2-ambientes-con-cochera-olivos", precio="$ 850.000",
         expensas="290.000", badge="", titulo="2 ambientes con cochera en Olivos",
         features="52 m² tot. | 48 m² cub. | 2 amb. | 1 dorm. | 1 baño | 1 coch.",
         direccion="Corrientes al 200", barrio="Olivos, Vicente López",
         publicador="PASTORI PROPIEDADES",
         descripcion="Alquiler de departamento 2 ambientes con cochera en Olivos. Opción sin "
                     "cochera. Contrato por 2 años con ajuste trimestral por IPC. "
                     "Condiciones: 1 mes de adelanto, 1 mes de depósito, certificación de "
                     "firmas, demostración de ingresos de inquilinos excluyente, honorarios "
                     "inmobiliarios, garantía propietaria o seguro de caución, informes. No "
                     "aceptan mascotas sin excepción gatos y perros. Excelente departamento "
                     "2 ambientes más cochera cubierta en un primer piso al contrafrente. "
                     "Cuenta con un gran living comedor con salida a balcón, cocina "
                     "independiente con lavadero incorporado, un cómodo dormitorio con "
                     "placards e interiores y un baño completo. Calefacción por tiro "
                     "balanceado y aire frío calor en el living. El edificio cuenta con "
                     "baulera individual, cochera cubierta, un sum y pileta."),
]


# Casos que en la primera corrida se colaron mal y ahora están cubiertos.
AVISOS += [
    # No informa expensas: no hay bloque data-qa="expensas" ni mención en el texto.
    # Antes se cargaba como $0 y ganaba el ranking.
    dict(id="60010001", slug="alclapin-2-amb-olivos-sin-dato", precio="$ 640.000",
         expensas=None, badge="", titulo="2 ambientes en Olivos",
         features="48 m² tot. | 46 m² cub. | 2 amb. | 1 dorm. | 1 baño",
         direccion="Malaver al 500", barrio="Olivos, Vicente López",
         publicador="Inmobiliaria sin dato",
         descripcion="Departamento de 2 ambientes en Olivos. Living comedor con "
                     "balcón, cocina integrada, dormitorio con placard, baño completo."),
    # A estrenar, con la antigüedad no numérica que antes se perdía.
    dict(id="60010002", slug="alclapin-monoambiente-a-estrenar", precio="$ 690.000",
         expensas="140.000", badge="", titulo="Monoambiente a estrenar",
         features="38 m² tot. | 35 m² cub. | 1 amb. | 1 baño | 1 coch.",
         direccion="Av. Mitre al 2400", barrio="Villa Martelli, Vicente López",
         publicador="Campus Norte",
         descripcion="Venta y alquiler anual con ajuste trimestral por IPC. Monoambiente a "
                     "estrenar con cochera fija, ubicado al frente con orientación Este, muy "
                     "luminoso. Excelente distribución para aprovechar los espacios. "
                     "Amenities: 2 piscinas, gimnasio, salón de fiestas, sector de parrillas, "
                     "zonas chill out y área co-working, seguridad 24 hs. Campus Norte fue "
                     "concebido como un hito que cambiará la fisonomía del barrio, con "
                     "grandes espacios verdes y ambientes amplios y luminosos. Se encuentra a "
                     "700 metros del cruce entre Avenida General Paz y la Autopista "
                     "Panamericana, con cercanía al Dot Baires Shopping."),
]


def html() -> str:
    cards = "".join(
        CARD.format(
            **{**a,
               "bloque_expensas": (
                   f'<div data-qa="expensas">$ {a["expensas"]} Expensas</div>'
                   if a["expensas"] is not None else ""
               )}
        )
        for a in AVISOS
    )
    return f"""<!doctype html><html><body>
      <h1>357 Departamentos o PH con 2 ambientes en alquiler en Vicente López, GBA Norte</h1>
      {cards}
      <div data-qa="PAGING_1">1</div><div data-qa="PAGING_2">2</div>
    </body></html>"""


# La página que devuelve Cloudflare cuando salta la verificación. El título y
# los textos están copiados de una captura real (30/8/2026).
DESAFIO_CLOUDFLARE = """<!doctype html><html lang="es"><head>
<title>Un momento...</title>
<meta http-equiv="refresh" content="390">
</head><body>
<div class="main-wrapper">
  <h1>www.zonaprop.com.ar</h1>
  <h2>Verificación de seguridad en curso</h2>
  <p>Este sitio web utiliza un servicio de seguridad para protegerse contra bots
     maliciosos. Esta página se muestra mientras el sitio web verifica que tú no
     eres un bot.</p>
  <div id="challenge-stage"><div class="cf-turnstile" data-sitekey="0xAAA"></div></div>
  <p>Verifique que es un ser humano</p>
</div>
<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1?ray=98f1"></script>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
</body></html>"""

# La de DataDome, por si Zonaprop vuelve a cambiar de proveedor.
DESAFIO_DATADOME = """<!doctype html><html><head><title>zonaprop.com.ar</title></head>
<body><script src="https://geo.captcha-delivery.com/captcha/?initialCid=AHrl"></script>
</body></html>"""


DETALLE = """<!doctype html><html><body>
<div id="longDescription">Departamento tipo casa de 2 ambientes ubicado dentro de complejo
con expensas mínimas. Living comedor espacioso y muy luminoso.</div>
<script>
  window.avisoInfo = {
    'pictures': [{"multimediaTypeId":2,"order":0,"resizeUrl1200x1200":"https://imgar.zonapropcdn.com/avisos/resize/1/00/59/55/35/28/1200x1200/2064026704.jpg?isFirstImage=true"},
                 {"order":1,"resizeUrl1200x1200":"https://imgar.zonapropcdn.com/avisos/resize/1/00/59/55/35/28/1200x1200/2064026735.jpg"},
                 {"order":2,"resizeUrl1200x1200":"https://imgar.zonapropcdn.com/avisos/resize/1/00/59/55/35/28/1200x1200/2064026745.jpg"}],
    'mainFeatures': {"100000
1":{"featureId":"1000015","label":"tot.","measure":"m²","value":"40"},
      "1000016":{"featureId":"1000016","label":"antigüedad","measure":null,"value":"20"},
      "1000019":{"featureId":"1000019","label":"Disposición","measure":null,"value":"Frente"},
      "1000029":{"featureId":"1000029","label":"Orientación","measure":null,"value":"N"},
      "1000030":{"featureId":"1000030","label":"Luminosidad","measure":null,"value":"Muy luminoso"}},
    "publishedDate":"2026-08-05"
  };
</script></body></html>"""
