#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiempos de viaje en carro con tráfico, de cada apartamento a los destinos de la búsqueda.

Usa la Routes API de Google con `departureTime` en la próxima ocurrencia real de
cada compromiso, así que el número sale con el tráfico previsto de ese día y esa hora.

Los tiempos se guardan con la coordenada del edificio como llave: un mismo edificio
se consulta una sola vez aunque su aviso cambie de portal o de precio. Por eso el
barrido diario no gasta cuota: solo se consultan los edificios que aún no están
en el caché.

    export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
    python3 tools/viajes.py --busqueda occidente
    python3 tools/viajes.py --recalcular
    python3 tools/viajes.py --limite 20   # tope de edificios por corrida
"""
import datetime as dt
import io, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import clave_edificio, ruta

API = "https://routes.googleapis.com/directions/v2:computeRoutes"
BOGOTA = dt.timezone(dt.timedelta(hours=-5))


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


def main():
    cfg = comun.cargar()
    destinos = cfg["destinos"]
    key = comun.llave_google()
    cache_p = ruta(cfg, "viajes")
    avisos = json.load(io.open(ruta(cfg, "datos"), encoding="utf-8"))["avisos"]
    cache = {}
    if os.path.exists(cache_p) and "--recalcular" not in sys.argv:
        cache = json.load(io.open(cache_p, encoding="utf-8")).get("edificios", {})

    limite = 10 ** 6
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])

    salidas = {c: proxima(d, h) for c, _n, _la, _lo, d, h in destinos}
    pendientes, vistos = [], set()
    for a in avisos:
        k = clave_edificio(a)
        if k in cache or k in vistos:
            continue
        vistos.add(k)
        pendientes.append(a)
    pendientes = pendientes[:limite]
    print("edificios: %d · en caché: %d · por consultar: %d"
          % (len({clave_edificio(a) for a in avisos}), len(cache), len(pendientes)))

    def uno(a):
        fila = {}
        for cl, _n, la, lo, _d, _h in destinos:
            res, err = consulta(key, (a["lat"], a["lon"]), (la, lo), salidas[cl])
            if err:
                return a, None, "%s: %s" % (cl, err)
            fila[cl] = res
        return a, fila, None

    hechos, fallos = 0, 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for a, fila, err in ex.map(uno, pendientes):
            if err:
                fallos += 1
                if fallos <= 5:
                    print("  %-24s ERROR %s" % (a["barrio"], err))
                continue
            cache[clave_edificio(a)] = fila
            hechos += 1
            if hechos <= 40 or hechos % 25 == 0:
                print("  %-24s %s" % (a["barrio"],
                      " · ".join("%s %dmin" % (c, fila[c]["min"]) for c, *_ in destinos)))

    with io.open(cache_p, "w", encoding="utf-8") as fh:
        json.dump({"actualizado": dt.datetime.now(BOGOTA).strftime("%Y-%m-%d"),
                   "destinos": [{"clave": c, "nombre": n, "lat": la, "lon": lo,
                                 "dias": d, "hora": h, "salida_consultada": salidas[c]}
                                for c, n, la, lo, d, h in destinos],
                   "edificios": cache}, fh, ensure_ascii=False, indent=1)
    print("%s: %d edificios (%d nuevos, %d fallos)"
          % (cfg["salida"]["viajes"], len(cache), hechos, fallos))
    if fallos > len(pendientes) / 3 and pendientes:
        sys.exit("Demasiados fallos: reviso llave o cuota antes de publicar.")


if __name__ == "__main__":
    main()
