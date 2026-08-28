# Barrido automático

El repo sirve **dos búsquedas**, descritas en `busquedas/*.json`. Todas las herramientas reciben
`--busqueda` y por defecto usan `norte`.

| Búsqueda | Qué busca | Zona | Publica en |
|---|---|---|---|
| `norte` | arriendo, ≥100 m², 3+ hab, ≥1 parqueadero, ≤$5.000.000 | lista de barrios del norte, ≤8 km de Portales del Country | `/norte/` |
| `occidente` | arriendo ≤$2.000.000 **y** venta ≤$500.000.000, ≥45 m², 2–3 hab | 3 km alrededor de El Tiempo (Calle 26) o 2,5 km de la casa en Kennedy | `/occidente/` |

Cada búsqueda declara sus topes, criterios, anclas, destinos de viaje, umbrales de color, reglas de
alerta y textos. Para cambiar precio, zona o barrios se edita el JSON, no el código.

`python3 tools/barrido.py --busqueda occidente` recorre los portales y escribe el `data.json` de esa
búsqueda. No necesita navegador ni llaves: los portales sirven los datos en el HTML del servidor si se
piden con cabeceras de navegador.

```
python3 tools/barrido.py --busqueda occidente --dry   # solo imprime el resumen
python3 tools/barrido.py --busqueda occidente         # además escribe el data.json
```

Imprime **NUEVO** y **CAYÓ** comparando contra el `data.json` anterior, así que el diff sale gratis.

## Qué sí y qué no hace

- **Fincaraíz** se recorre por localidad (todas las páginas); **Metrocuadrado** y **Ciencuadras**,
  barrio por barrio, porque su buscador no entiende localidades.
- **Properati responde 401 desde agosto de 2026** y ya no entrega avisos. El barrido lo sigue
  tanteando una vez por corrida y lo anota en el log, para enterarnos si vuelve; mientras tanto
  las páginas dicen «3 portales».
- **Ascensor**: solo lo marca como confirmado cuando Fincaraíz trae la amenidad `Ascensor`.
  Metrocuadrado y Ciencuadras lo publican en la ficha de detalle, que este script no abre;
  esos quedan en `nd`. El script **subestima**, nunca inventa un ascensor.
- **Ciencuadras no publica habitaciones ni garajes.** Esos avisos llevan `inc:["hab","parq"]` y la
  página los muestra como *sin dato*, nunca como cero ni como el mínimo pedido.
- **Ciencuadras** devuelve una búsqueda de toda la ciudad cuando no reconoce el barrio; el filtro
  geográfico de la búsqueda descarta esos resultados.
- En `occidente` el filtro es **por radio alrededor de las anclas**, no por lista de barrios: por eso
  aparecen barrios que nadie pidió, y por eso no depende de que el portal etiquete bien el barrio.

## Actualizar la página

El `data.json` de cada búsqueda es la fuente; su página lleva el arreglo `DATA` embebido.

```
python3 tools/render.py --busqueda norte        # reescribe norte/index.html
python3 tools/render.py --busqueda occidente    # reescribe occidente/index.html
python3 tools/portada.py                        # reescribe la portada del sitio
```

La portada de la raíz (`index.html`) la escribe entera `tools/portada.py` a partir de los
`busquedas/*.json` y sus datos, así que nunca queda anunciando cifras viejas. Los datos y cachés de
cada búsqueda viven en su carpeta (`norte/`, `occidente/`).

`render.py` solo toca los bloques marcados (`DATA`, `GONE`, `.tiles`, `.verdict`, título, descripción
y eyebrow). El diseño y el JavaScript de cada página se editan a mano en su HTML. El resumen se
**reescribe entero** en cada corrida: si solo se agregara, los párrafos viejos quedarían
contradiciendo los datos.

## Tiempos de viaje

`python3 tools/viajes.py --busqueda X` calcula, para cada edificio, cuánto toma llegar en carro a los
destinos de esa búsqueda, con el tráfico previsto por Google para **el día y la hora reales** de cada
compromiso (no una franja genérica). Escribe `viajes.json`.

```
export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
python3 tools/viajes.py --busqueda occidente   # solo consulta los edificios que faltan
python3 tools/viajes.py --recalcular           # rehace todo
python3 tools/viajes.py --limite 80            # tope de edificios por corrida
```

- El caché está **por coordenada de edificio**, no por aviso: un mismo edificio se consulta una
  sola vez aunque su aviso cambie de portal, de precio o de id. El barrido diario no gasta cuota.
- El agente programado **no necesita la llave**: usa `viajes.json` tal como está y las fichas de
  edificios nuevos salen marcadas como "sin tiempos de viaje todavía".
- **El tiempo al colegio (búsqueda `norte`) es en carro**, no el de la ruta escolar. Sirve para
  comparar apartamentos entre sí; la ruta real recoge a otros niños y depende de cuál asignen.
- Los destinos y sus horarios están en `destinos` dentro de `busquedas/*.json`.
- La llave nunca se guarda en el repo. `viajes.json` solo contiene minutos y kilómetros.

## Fachadas

`python3 tools/streetview.py` consulta el endpoint de **metadatos** de Street View, que **no se cobra**:
solo dice si hay panorama en ese punto, dónde está exactamente y de cuándo es la foto. Escribe
`streetview.json`. La ficha usa la coordenada real del panorama, muestra el mes de la foto y esconde
el botón donde no hay cobertura.

Por defecto el botón **abre Street View en otra pestaña**, sin llave y sin costo. Para verlo
incrustado en la ficha hace falta una llave de **Maps Embed API**, que es pública por diseño y por
eso debe ser **una llave aparte, restringida por referente HTTP** al dominio del sitio. Cuando
exista, se guarda como *variable* del repo (no secreto, porque va al HTML):

```
gh variable set SV_EMBED_KEY --repo luisjavierbautista/arriendo-bogota-norte
```

Sin esa variable el sitio funciona igual, solo que abriendo en otra pestaña. **La variable ya está
configurada.**

Antes de publicar una llave de embed, comprueba que solo pueda hacer lo gratuito. Estos cuatro
chequeos deben dar exactamente esto:

| Petición | Esperado |
|---|---|
| Maps Embed con `Referer` de tu dominio | 200 y responde |
| Maps Embed sin `Referer` | 403 |
| `maps/api/streetview` (imagen, se cobra) sin `Referer` | 403 |
| Routes API | negada |

Si la imagen de Street View devuelve 200 sin referente, la llave todavía tiene esa API habilitada y
**no se puede publicar**: la restricción por dominio no la protege. Hay que quitar Street View Static
API de las restricciones de la llave y dejar solo Maps Embed API. Los cambios tardan unos minutos en
propagar.

## Recién aparecidos

`data.json` guarda en `nuevos` las URLs que no estaban en la corrida anterior, comparando por
**inmueble** (coordenada + área) y no por enlace, para que un aviso que cambia de portal no cuente
como nuevo. `render.py` los marca con `nuevo:true` y la página los distingue en tres lugares: una
insignia junto al barrio, un borde de acento en la ficha y un aro en la pastilla del mapa. El filtro
"Solo los nuevos" deja únicamente esos.

La marca dura hasta la siguiente corrida: al día siguiente, los de hoy dejan de estar marcados.

## Quién corre qué

| Cuándo | Quién | Qué hace |
|---|---|---|
| 07:00 Bogotá, diario | Agente programado en la nube | `barrido.py` + `render.py` **de las dos búsquedas**, commit y push. **No tiene la llave**: los edificios nuevos quedan marcados como "sin tiempos de viaje todavía". |
| 07:35 Bogotá, diario | GitHub Actions (`.github/workflows/viajes.yml`) | Completa tiempos y fachadas de las dos búsquedas con la llave de Secrets, vuelve a renderizar y publica. |

La llave vive en **Secrets del repo** (`GOOGLE_MAPS_API_KEY`), nunca en el código. Para rotarla:

```
gh secret set GOOGLE_MAPS_API_KEY --repo luisjavierbautista/arriendo-bogota-norte
```

Si el workflow no encuentra la llave, no falla: deja los edificios sin tiempos y lo anota como aviso.
Antes de publicar verifica que no se haya colado ninguna credencial, buscando por la **forma** de una
llave de Google (`AIza` + 35 caracteres) y no por su prefijo literal, que si no el chequeo se detecta
a sí mismo y siempre falla.
