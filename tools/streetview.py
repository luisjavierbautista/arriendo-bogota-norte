#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Averigua si hay Street View en cada edificio y de qué año es la foto.

Usa el endpoint de metadatos, que **no se cobra**: solo dice si existe panorama,
dónde está exactamente y de cuándo es. Así la página no ofrece "ver fachada" en
puntos sin cobertura, y muestra la fecha para que sepas si la foto está vieja.

El caché es por coordenada de edificio, igual que los tiempos de viaje.

    export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
    python3 tools/streetview.py
    python3 tools/streetview.py --recalcular
"""
import io, json, os, subprocess, sys, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RAIZ, "streetview.json")
META = "https://maps.googleapis.com/maps/api/streetview/metadata"


def llave():
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if k:
        return k
    ruta = os.path.expanduser("~/.config/arriendo/gmaps.key")
    if os.path.exists(ruta):
        return io.open(ruta, encoding="utf-8").read().strip()
    sys.exit("Falta la llave. Ponla en GOOGLE_MAPS_API_KEY o en ~/.config/arriendo/gmaps.key")


def metadatos(key, lat, lon, intentos=3):
    url = "%s?location=%s,%s&radius=70&source=outdoor&key=%s" % (META, lat, lon, key)
    for n in range(intentos):
        r = subprocess.run(["curl", "-s", "--max-time", "25", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except ValueError:
            time.sleep(1 + n)
            continue
        est = d.get("status")
        if est in ("OK", "ZERO_RESULTS"):
            return d, None
        # REQUEST_DENIED justo después de habilitar la API suele ser propagación
        time.sleep(2 + 2 * n)
    return None, (d.get("error_message") or d.get("status", "?"))[:110] if isinstance(d, dict) else "sin respuesta"


def main():
    key = llave()
    avisos = json.load(io.open(os.path.join(RAIZ, "data.json"), encoding="utf-8"))["avisos"]
    cache = {}
    if os.path.exists(CACHE) and "--recalcular" not in sys.argv:
        cache = json.load(io.open(CACHE, encoding="utf-8")).get("edificios", {})

    pendientes, vistos = [], set()
    for a in avisos:
        k = "%.4f|%.4f" % (a["lat"], a["lon"])
        if k in cache or k in vistos:
            continue
        vistos.add(k)
        pendientes.append(a)

    print("edificios: %d · en caché: %d · por consultar: %d"
          % (len({"%.4f|%.4f" % (a["lat"], a["lon"]) for a in avisos}), len(cache), len(pendientes)))

    con, sin, err = 0, 0, 0
    for a in pendientes:
        k = "%.4f|%.4f" % (a["lat"], a["lon"])
        d, e = metadatos(key, a["lat"], a["lon"])
        if e:
            print("  %-22s ERROR %s" % (a["barrio"], e))
            err += 1
            if err >= 5:
                print("Cinco errores seguidos: me detengo para no gastar en vano.")
                break
            continue
        if d.get("status") == "OK":
            cache[k] = {"hay": True, "fecha": d.get("date", ""),
                        "lat": round(d["location"]["lat"], 6), "lon": round(d["location"]["lng"], 6)}
            con += 1
        else:
            cache[k] = {"hay": False}
            sin += 1

    with io.open(CACHE, "w", encoding="utf-8") as fh:
        json.dump({"edificios": cache}, fh, ensure_ascii=False, indent=1)
    fechas = sorted(v.get("fecha", "") for v in cache.values() if v.get("hay"))
    print("streetview.json: %d edificios · con panorama %d · sin panorama %d · errores %d"
          % (len(cache), sum(1 for v in cache.values() if v.get("hay")),
             sum(1 for v in cache.values() if not v.get("hay")), err))
    if fechas:
        print("fotos entre %s y %s" % (fechas[0], fechas[-1]))


if __name__ == "__main__":
    main()
