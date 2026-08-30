# Qué se mira en las fotos

Esto es lo que reviso cuando me pasás las hojas de contacto. Lo dejo escrito para
que sepas qué esperar y qué NO se puede sacar de una foto.

## 1. Humedad y agua

La humedad casi nunca se fotografía de frente, pero deja rastros que los avisos
no siempre alcanzan a tapar:

| Señal | Qué suele significar |
|---|---|
| Mancha amarronada o amarillenta en el encuentro pared-cielorraso | Filtración desde arriba (baño del piso de arriba, terraza, canaleta) |
| Pintura descascarada o "burbujeada" en el zócalo, primeros 40-60 cm de pared | Humedad de cimientos por capilaridad — es la cara y difícil de arreglar |
| Puntitos negros en las esquinas del techo, sobre todo en baño y cocina | Moho por condensación: ventilación insuficiente |
| Revoque abombado, pared con textura irregular bajo la pintura | Humedad vieja tapada con enduido |
| Cerco de pintura fresca de un color apenas distinto | Reparación reciente de una mancha |
| Mueble grande o cuadro en un lugar raro, plantas contra una pared | Puede estar tapando algo (señal débil, se anota como sospecha) |
| Ventana con condensación o vidrio empañado | Aislación mala + poca ventilación |
| Óxido en los marcos de aberturas de chapa, en la base | Agua acumulada |
| Baño sin ventana ni extractor visible | Condensación garantizada a mediano plazo |

## 1 bis. La fachada, que es la que no miente

Esta sección existe porque en la primera corrida fallé acá. El interior de un
departamento se pinta antes de fotografiarlo; la fachada de un edificio de
ocho pisos, no. Cuando el texto del aviso y la fachada se contradicen, **le creo
a la fachada**.

Las fotos de fachada, palier, contrafrente y amenities casi siempre están al
**final** de la galería. El script ahora las reserva siempre y las marca en
naranja en la hoja de contacto, incluso cuando hay que recortar la galería.

Qué se lee en una fachada:

| Señal | Qué significa |
|---|---|
| Chorreado verde o negro bajo los balcones y las ventanas | Desagües tapados o mal resueltos: el agua corre por la pared en vez de bajar por el caño |
| Manchas oscuras verticales desde la losa de un balcón | Filtración en el balcón de esa unidad — si es el del aviso, importa mucho |
| Revoque saltado o parches de otro color | Reparaciones sueltas, casi siempre por humedad |
| Medianera sin revocar o con ladrillo a la vista sin sellar | El ladrillo desnudo chupa agua y la pasa a los departamentos que dan a esa pared |
| Canaletas y bajadas oxidadas o desprendidas | Nadie las mantiene: se va a filtrar |
| Aire acondicionado goteando sobre la pared, mancha bajo cada split | Detalle menor, pero habla del mantenimiento del consorcio |
| Vidrios repuestos de distinto tono, balcones con cerramientos truchos | Edificio sin reglamento efectivo |
| Andamios, red de obra o cartel de refacción | Puede ser bueno (están arreglando) o malo (expensas extraordinarias en camino). Es pregunta para la visita |

También sirve para ubicar la unidad: si en la fachada contás los pisos y
encontrás el balcón del departamento, se ve qué le da sombra y si está bajo la
línea de escurrimiento de una terraza.

## 2. Luz natural

- Sombras duras en el piso y luz cálida al ras = sol directo entra de verdad.
- Todas las fotos con luces prendidas de día, o gran angular exagerado = suele
  compensar un ambiente oscuro.
- Vista desde la ventana: si se ve una pared a pocos metros, es contrafrente o
  pulmón, aunque el aviso diga "vista abierta".
- Cruzo esto con la `orientación` y la `disposición` que trae la ficha de
  Zonaprop, que a veces contradicen al texto del aviso.

## 3. Estado real de las instalaciones

- Cocina: mesada de granito o mármol reconstituido vs. laminado hinchado en los
  bordes; muebles bajo mesada con las puertas alabeadas.
- Baño: azulejo de los 70/80 vs. porcelanato; canilla monocomando vs. bicomando;
  presencia de bañera vs. ducha (dice bastante de la última reforma).
- Electricidad: cables por fuera, cajas a la vista, tomas de dos patas planas
  sin descarga a tierra = instalación vieja.
- Calefacción: si no se ve ni split ni radiador ni tiro balanceado en ninguna
  foto, probablemente no haya, y en un 2 ambientes en zona norte eso importa.
- Pisos: parquet levantado o manchado en zonas específicas puede marcar una
  filtración pasada.

## 4. Trampas del aviso

- Fotos renderizadas o de otro departamento del mismo edificio ("unidad tipo").
- Fotos de la pileta, el gym y el río, y solo 2 del departamento: cuando la
  proporción se inclina a los amenities, casi siempre la unidad es floja.
- Fotos viejas: aire acondicionado de un modelo discontinuado, calendario o TV
  a la vista.
- El mismo ambiente fotografiado desde 4 ángulos para inflar la galería.

## Lo que una foto NO puede decir

Y por eso lo dejo fuera del score en vez de inventarlo:

- **Ruido.** Ni la avenida ni el vecino ni el ascensor.
- **Olor a humedad**, que suele aparecer antes que la mancha.
- **Presión de agua** y si el agua caliente llega al baño en invierno.
- **Estado de las expensas** y si el consorcio tiene deuda o obras votadas.
- **Cuánto sol entra en junio**, que es lo que importa, no en la foto de
  noviembre a las 3 de la tarde.

Todo eso solo sale de la visita. El objetivo del análisis es que llegues a la
visita con 5 candidatos ordenados y una lista de qué mirar en cada uno, no
reemplazarla.

## Formato de la salida

Por cada aviso te devuelvo:

```
59553528 — Perú al 1200 · $770.000/mes · 40 m²
  Riesgo de humedad: MEDIO
    · foto 7: mancha marrón difusa en el ángulo del cielorraso del baño
    · foto 3: zócalo del living con pintura levantada, ~30 cm
  Luz: buena — sombras duras en fotos 1 y 2, orientación N confirmada
  Estado: cocina reformada, baño original (azulejo hasta el techo, bicomando)
  Para preguntar en la visita: si la mancha del baño es del departamento de
  arriba y si hubo arreglo de cañería en el último año
```

Con eso más el ranking por variables sale la recomendación final.
