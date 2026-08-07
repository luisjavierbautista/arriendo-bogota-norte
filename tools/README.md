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
