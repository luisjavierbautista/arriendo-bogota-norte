#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiempos de viaje en carro con tráfico, de cada apartamento a los destinos fijos.

Usa la Routes API de Google con `departureTime` en la próxima ocurrencia real de
cada compromiso, así que el número sale con el tráfico previsto de ese día y esa hora.

Los tiempos se guardan en `viajes.json`, con la coordenada del edificio como llave:
un mismo edificio se consulta una sola vez aunque su aviso cambie de portal o de
precio. Por eso el barrido diario no gasta cuota: solo se consultan los edificios
que aún no están en el caché.

    export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
    python3 tools/viajes.py               # completa lo que falte
    python3 tools/viajes.py --recalcular  # rehace todo
    python3 tools/viajes.py --limite 20   # tope de edificios por corrida
"""
import datetime as dt
import io, json, os, subprocess, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RAIZ, "viajes.json")
API = "https://routes.googleapis.com/directions/v2:computeRoutes"

# clave, nombre, lat, lon, días (0=lunes), hora local de salida
DESTINOS = [
    ("gimnasio", "Gimnasio",        4.69303710255897,  -74.04503808903183, [0, 4], "16:30"),
    ("musica",   "Música",          4.680695121068617, -74.04778755833742, [5],    "08:15"),
    ("teatro",   "Teatro y música", 4.691391936030174, -74.0621500231654,  [5],    "10:00"),
    ("colegio",  "Colegio",         4.791606282797884, -74.04790371605132, [0, 4], "07:15"),
    ("oficina",  "Oficina",         4.659585482746221, -74.10831628903188, [0, 4], "07:00"),
]
BOGOTA = dt.timezone(dt.timedelta(hours=-5))


def llave():
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if k:
        return k
    ruta = os.path.expanduser("~/.config/arriendo/gmaps.key")
    if os.path.exists(ruta):
        return io.open(ruta, encoding="utf-8").read().strip()
    sys.exit("Falta la llave. Ponla en GOOGLE_MAPS_API_KEY o en ~/.config/arriendo/gmaps.key")


def proxima(dias, hora):
    """Próxima ocurrencia futura de ese día y hora, en hora de Bogotá."""
    h, m = (int(x) for x in hora.split(":"))
    ahora = dt.datetime.now(BOGOTA)
    for d in range(1, 15):
        cand = (ahora + dt.timedelta(days=d)).replace(hour=h, minute=m, second=0, microsecond=0)
        if cand.weekday() in dias:
            return cand.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise RuntimeError("no encontré una fecha futura para %s %s" % (dias, hora))


def consulta(key, org, dst, salida):
    cuerpo = {
        "origin": {"location": {"latLng": {"latitude": org[0], "longitude": org[1]}}},
        "destination": {"location": {"latLng": {"latitude": dst[0], "longitude": dst[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "departureTime": salida,
        "languageCode": "es-CO",
        "units": "METRIC",
    }
    r = subprocess.run(
        ["curl", "-s", "--max-time", "40", "-X", "POST", API,
         "-H", "Content-Type: application/json",
         "-H", "X-Goog-Api-Key: " + key,
         "-H", "X-Goog-FieldMask: routes.duration,routes.staticDuration,routes.distanceMeters",
         "-d", json.dumps(cuerpo)],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return None, "respuesta ilegible: " + r.stdout[:120]
    if "error" in d:
        return None, "%s: %s" % (d["error"].get("status", "?"), d["error"].get("message", "")[:120])
    rutas = d.get("routes") or []
    if not rutas:
        return None, "sin ruta"
    ru = rutas[0]
    seg = lambda v: int(str(v).rstrip("s") or 0)
    return {"min": round(seg(ru.get("duration", "0s")) / 60),
            "min_libre": round(seg(ru.get("staticDuration", "0s")) / 60),
            "km": round(ru.get("distanceMeters", 0) / 1000, 1)}, None


def clave_coord(a):
    return "%.4f|%.4f" % (a["lat"], a["lon"])


def main():
    key = llave()
    avisos = json.load(io.open(os.path.join(RAIZ, "data.json"), encoding="utf-8"))["avisos"]
    cache = {}
    if os.path.exists(CACHE) and "--recalcular" not in sys.argv:
        cache = json.load(io.open(CACHE, encoding="utf-8")).get("edificios", {})

    limite = 10 ** 6
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])

    salidas = {c: proxima(d, h) for c, _n, _la, _lo, d, h in DESTINOS}
    pendientes = [a for a in avisos if clave_coord(a) not in cache]
    print("edificios en data.json: %d · ya en caché: %d · por consultar: %d"
          % (len({clave_coord(a) for a in avisos}), len(cache), len({clave_coord(a) for a in pendientes})))

    hechos, fallos = 0, 0
    vistos = set()
    for a in pendientes:
        k = clave_coord(a)
        if k in vistos or hechos >= limite:
            continue
        vistos.add(k)
        fila = {}
        for cl, nombre, la, lo, _d, _h in DESTINOS:
            res, err = consulta(key, (a["lat"], a["lon"]), (la, lo), salidas[cl])
            if err:
                print("  %-22s %-9s ERROR %s" % (a["barrio"], cl, err))
                fallos += 1
                break
            fila[cl] = res
        else:
            cache[k] = fila
            hechos += 1
            print("  %-22s %s" % (a["barrio"],
                  " · ".join("%s %dmin" % (c, fila[c]["min"]) for c, *_ in DESTINOS)))
        if fallos >= 3:
            print("Tres fallos seguidos: reviso llave o cuota y me detengo.")
            break

    with io.open(CACHE, "w", encoding="utf-8") as fh:
        json.dump({"actualizado": dt.datetime.now(BOGOTA).strftime("%Y-%m-%d"),
                   "destinos": [{"clave": c, "nombre": n, "lat": la, "lon": lo,
                                 "dias": d, "hora": h, "salida_consultada": salidas[c]}
                                for c, n, la, lo, d, h in DESTINOS],
                   "edificios": cache}, fh, ensure_ascii=False, indent=1)
    print("viajes.json: %d edificios (%d nuevos, %d fallos)" % (len(cache), hechos, fallos))


if __name__ == "__main__":
    main()
