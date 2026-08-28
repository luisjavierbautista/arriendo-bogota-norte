#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Piezas compartidas por las herramientas: configuración, geografía y descargas."""
import io, json, math, os, re, subprocess, sys, unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CAB = ["-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
       "-H", "Accept-Language: es-CO,es;q=0.9",
       "-H", "Sec-Fetch-Mode: navigate", "-H", "Sec-Fetch-Dest: document",
       "-H", "Upgrade-Insecure-Requests: 1"]
KM_LAT, KM_LON = 110.574, 111.320 * math.cos(math.radians(4.65))


def cargar(argv=None):
    """Lee la búsqueda pedida con --busqueda; por defecto, la del norte."""
    argv = sys.argv if argv is None else argv
    nombre = "norte"
    if "--busqueda" in argv:
        nombre = argv[argv.index("--busqueda") + 1]
    ruta = os.path.join(RAIZ, "busquedas", nombre + ".json")
    if not os.path.exists(ruta):
        sys.exit("No existe la búsqueda '%s' (%s)" % (nombre, ruta))
    cfg = json.load(io.open(ruta, encoding="utf-8"))
    cfg["_ruta"] = ruta
    return cfg


def ruta(cfg, salida):
    p = os.path.join(RAIZ, cfg["salida"][salida])
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    return p


def km_entre(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * KM_LAT, (lon1 - lon2) * KM_LON)


def principal(cfg):
    for a in cfg["anclas"]:
        if a.get("principal"):
            return a
    return cfg["anclas"][0]


def distancias(cfg, lat, lon):
    """Kilómetros en línea recta a cada ancla de la búsqueda."""
    return {a["clave"]: round(km_entre(lat, lon, a["lat"], a["lon"]), 2) for a in cfg["anclas"]}


def dentro(cfg, lat, lon):
    """¿La coordenada entra en la zona de la búsqueda?"""
    ca = cfg.get("caja")
    if ca and not (ca[0] < lat < ca[1] and ca[2] < lon < ca[3]):
        return False
    if cfg["filtro"] == "radio":
        return any(km_entre(lat, lon, a["lat"], a["lon"]) <= a.get("radio_km", 4.0)
                   for a in cfg["anclas"])
    p = principal(cfg)
    return km_entre(lat, lon, p["lat"], p["lon"]) <= cfg.get("recorte_km", 99)


def sinacento(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def bonito(s):
    menudas = {"de", "del", "la", "las", "los", "el", "y"}
    ps = [p for p in sinacento(s).split() if p]
    if not ps:
        return ""
    return " ".join(p.capitalize() if i == 0 or p not in menudas else p for i, p in enumerate(ps))


def get(url, intentos=2):
    for _ in range(intentos):
        r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA] + CAB + [url],
                           capture_output=True, text=True)
        if r.stdout and len(r.stdout) > 2000:
            return r.stdout
    return ""


def llave_google():
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if k:
        return k
    p = os.path.expanduser("~/.config/arriendo/gmaps.key")
    if os.path.exists(p):
        return io.open(p, encoding="utf-8").read().strip()
    sys.exit("Falta la llave. Ponla en GOOGLE_MAPS_API_KEY o en ~/.config/arriendo/gmaps.key")


def clave_edificio(a):
    """Identidad física: coordenada redondeada. Sirve de llave de caché."""
    return "%.4f|%.4f" % (a["lat"], a["lon"])
