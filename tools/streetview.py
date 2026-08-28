#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Averigua si hay Street View en cada edificio y de qué año es la foto.

Usa el endpoint de metadatos, que **no se cobra**: solo dice si existe panorama,
dónde está exactamente y de cuándo es. Así la página no ofrece "ver fachada" en
puntos sin cobertura, y muestra la fecha para que sepas si la foto está vieja.

El caché es por coordenada de edificio, igual que los tiempos de viaje.

    export GOOGLE_MAPS_API_KEY=...        # o ~/.config/arriendo/gmaps.key
    python3 tools/streetview.py --busqueda occidente
    python3 tools/streetview.py --recalcular
"""
import io, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import clave_edificio, ruta

META = "https://maps.googleapis.com/maps/api/streetview/metadata"


def metadatos(key, lat, lon, intentos=3):
    d = None
    url = "%s?location=%s,%s&radius=70&source=outdoor&key=%s" % (META, lat, lon, key)
    for n in range(intentos):
        r = subprocess.run(["curl", "-s", "--max-time", "25", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except ValueError:
            time.sleep(1 + n)
            continue
        if d.get("status") in ("OK", "ZERO_RESULTS"):
            return d, None
        # REQUEST_DENIED justo después de habilitar la API suele ser propagación
        time.sleep(2 + 2 * n)
    return None, ((d.get("error_message") or d.get("status", "?"))[:110]
                  if isinstance(d, dict) else "sin respuesta")


def main():
    cfg = comun.cargar()
    key = comun.llave_google()
    cache_p = ruta(cfg, "streetview")
    avisos = json.load(io.open(ruta(cfg, "datos"), encoding="utf-8"))["avisos"]
    cache = {}
    if os.path.exists(cache_p) and "--recalcular" not in sys.argv:
        cache = json.load(io.open(cache_p, encoding="utf-8")).get("edificios", {})

    pendientes, vistos = [], set()
    for a in avisos:
        k = clave_edificio(a)
        if k in cache or k in vistos:
            continue
        vistos.add(k)
        pendientes.append(a)

    print("edificios: %d · en caché: %d · por consultar: %d"
          % (len({clave_edificio(a) for a in avisos}), len(cache), len(pendientes)))

    err = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for a, (d, e) in zip(pendientes, ex.map(
                lambda a: metadatos(key, a["lat"], a["lon"]), pendientes)):
            if e:
                err += 1
                if err <= 5:
                    print("  %-24s ERROR %s" % (a["barrio"], e))
                continue
            k = clave_edificio(a)
            if d.get("status") == "OK":
                cache[k] = {"hay": True, "fecha": d.get("date", ""),
                            "lat": round(d["location"]["lat"], 6),
                            "lon": round(d["location"]["lng"], 6)}
            else:
                cache[k] = {"hay": False}

    with io.open(cache_p, "w", encoding="utf-8") as fh:
        json.dump({"edificios": cache}, fh, ensure_ascii=False, indent=1)
    fechas = sorted(v.get("fecha", "") for v in cache.values() if v.get("hay"))
    print("%s: %d edificios · con panorama %d · sin panorama %d · errores %d"
          % (cfg["salida"]["streetview"], len(cache),
             sum(1 for v in cache.values() if v.get("hay")),
             sum(1 for v in cache.values() if not v.get("hay")), err))
    if fechas:
        print("fotos entre %s y %s" % (fechas[0], fechas[-1]))


if __name__ == "__main__":
    main()
