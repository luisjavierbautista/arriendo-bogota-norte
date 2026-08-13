# Barrido automático

`python3 tools/barrido.py` recorre los cuatro portales y escribe `data.json` en la raíz.
No necesita navegador ni llaves: los cuatro sirven los datos en el HTML del servidor si se
piden con cabeceras de navegador.

```
python3 tools/barrido.py --dry   # solo imprime el resumen
python3 tools/barrido.py         # además escribe data.json
```

Imprime **NUEVO** y **CAYÓ** comparando contra el `data.json` anterior, así que el diff sale gratis.

## Qué sí y qué no hace

- **Fincaraíz** y **Properati** se recorren por localidad (Usaquén y Suba, todas las páginas);
  **Metrocuadrado** y **Ciencuadras**, barrio por barrio, porque su buscador no entiende localidades.
- **Ascensor**: solo lo marca como confirmado cuando Fincaraíz trae la amenidad `Ascensor`.
  Metrocuadrado y Ciencuadras lo publican en la ficha de detalle, que este script no abre;
  esos quedan en `nd`. El script **subestima**, nunca inventa un ascensor.
- **Properati** no publica coordenadas en la tarjeta del listado. Sus avisos se registran en el
  log como "requiere revisión manual" y no entran a `data.json`.
- **Ciencuadras** devuelve una búsqueda de toda la ciudad cuando no reconoce el barrio; esos
  resultados se descartan y quedan anotados en el log.
- Se descarta todo lo que quede a más de 8 km de Portales del Country.

## Actualizar la página

`data.json` es la fuente. `index.html` lleva el arreglo `DATA` embebido: hay que regenerarlo
desde `data.json` y volver a empujar. El agente programado hace ese paso.

## Tiempos de viaje

`python3 tools/viajes.py` calcula, para cada edificio, cuánto toma llegar en carro a los cinco
destinos fijos, con el tráfico previsto por Google para **el día y la hora reales** de cada
compromiso (no una franja genérica). Escribe `viajes.json`.

```
export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
python3 tools/viajes.py               # solo consulta los edificios que faltan
python3 tools/viajes.py --recalcular  # rehace todo
```

- El caché está **por coordenada de edificio**, no por aviso: un mismo edificio se consulta una
  sola vez aunque su aviso cambie de portal, de precio o de id. El barrido diario no gasta cuota.
- El agente programado **no necesita la llave**: usa `viajes.json` tal como está y las fichas de
  edificios nuevos salen marcadas como "sin tiempos de viaje todavía".
- **El tiempo al colegio es en carro**, no el de la ruta escolar. Sirve para comparar apartamentos
  entre sí; la ruta real recoge a otros niños y depende de cuál asignen.
- Los destinos y sus horarios están en `DESTINOS`, dentro de `tools/viajes.py`.
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

## Quién corre qué

| Cuándo | Quién | Qué hace |
|---|---|---|
| 07:00 Bogotá, diario | Agente programado en la nube | `barrido.py` + `render.py`, commit y push. **No tiene la llave**: los edificios nuevos quedan marcados como "sin tiempos de viaje todavía". |
| 07:35 Bogotá, diario | GitHub Actions (`.github/workflows/viajes.yml`) | Completa los tiempos que falten con la llave de Secrets, vuelve a renderizar y publica. |

La llave vive en **Secrets del repo** (`GOOGLE_MAPS_API_KEY`), nunca en el código. Para rotarla:

```
gh secret set GOOGLE_MAPS_API_KEY --repo luisjavierbautista/arriendo-bogota-norte
```

Si el workflow no encuentra la llave, no falla: deja los edificios sin tiempos y lo anota como aviso.
Antes de publicar verifica que no se haya colado ninguna credencial, buscando por la **forma** de una
llave de Google (`AIza` + 35 caracteres) y no por su prefijo literal, que si no el chequeo se detecta
a sí mismo y siempre falla.
