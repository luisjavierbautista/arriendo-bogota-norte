#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Barrido de apartamentos en arriendo en el norte de Bogotá sobre cuatro portales.

Corre sin navegador: los cuatro portales entregan los datos en el HTML del servidor
si se piden con cabeceras de navegador. Produce data.json y un resumen por consola.

    python3 tools/barrido.py            # barre y escribe data.json
    python3 tools/barrido.py --dry      # barre y solo imprime el resumen
"""
import json, math, os, re, subprocess, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CAB = ["-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
       "-H", "Accept-Language: es-CO,es;q=0.9",
       "-H", "Sec-Fetch-Mode: navigate", "-H", "Sec-Fetch-Dest: document",
       "-H", "Upgrade-Insecure-Requests: 1"]

# ---------------------------------------------------------------- criterios
MIN_M2, MIN_HAB, MIN_PARQ, TOPE = 100, 3, 1, 4_500_000
HOME = (4.7093816, -74.0345729)          # Portales del Country
KM_LAT, KM_LON = 110.574, 111.320 * math.cos(math.radians(4.718))

BARRIOS = [
 "multicentro","recodo del country","nuevo country","portales del country","country",
 "santa barbara","santa barbara central","santa barbara oriental","santa barbara occidental",
 "san patricio","navarra","chico navarra","la calleja","atabanza","el recreo de los frailes",
 "malibu","alhambra","monaco","pasadena","las villas","iberia","ciudad jardin norte","casigua",
 "cordoba","lagos de cordoba","niza","pontevedra","potosi","la alborada","morato",
 "colina campestre","bella suiza","molinos norte","santa ana","santa ana oriental"]

# nombre crudo del portal -> etiqueta que se muestra
ALIAS = {
 "chico navarra":"Navarra", "monaco":"Alhambra", "niza norte":"Niza", "niza 8":"Niza",
 "ub cordoba niza":"Córdoba", "ub cordoba":"Córdoba", "ub hacienda cordoba niza":"Córdoba",
 "lagos de cordoba atabanza":"Atabanza", "molinos del norte":"Molinos Norte",
 "contry":"Country", "country club":"Country", "la colina campestre":"Colina Campestre",
 "colina campestre zona urbana":"Colina Campestre", "niza zona urbana":"Niza",
 "santa barbara alta":"Santa Bárbara", "santa barbara oriental":"Santa Bárbara",
 "santa barbara occidental":"Santa Bárbara", "prados de la calleja":"La Calleja",
 "la calleja alta":"La Calleja", "la calleja cedritos":"La Calleja",
 "atalaya iberia":"Iberia", "parque central pontevedra":"Pontevedra",
}
BONITO = {b: " ".join(w.capitalize() for w in b.split()) for b in BARRIOS}
BONITO.update({"santa barbara":"Santa Bárbara","santa barbara central":"Santa Bárbara Central",
 "cordoba":"Córdoba","lagos de cordoba":"Lagos de Córdoba","potosi":"Potosí","malibu":"Malibú",
 "ciudad jardin norte":"Ciudad Jardín Norte","monaco":"Alhambra","chico navarra":"Navarra",
 "el recreo de los frailes":"El Recreo de los Frailes","la alborada":"La Alborada",
 "la calleja":"La Calleja","las villas":"Las Villas","santa ana oriental":"Santa Ana Oriental"})


def sinacento(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def normaliza_barrio(crudo):
    """Devuelve la etiqueta de barrio si cae en la lista, o None."""
    s = sinacento(crudo).replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    if s in ALIAS: return ALIAS[s]
    if s in BONITO: return BONITO[s]
    for b in sorted(BARRIOS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(b) + r"\b", s):
            return ALIAS.get(b, BONITO.get(b, b.title()))
    return None


def km(lat, lon):
    return round(math.hypot((lat - HOME[0]) * KM_LAT, (lon - HOME[1]) * KM_LON), 2)


def get(url, intentos=2):
    for _ in range(intentos):
        r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA] + CAB + [url],
                           capture_output=True, text=True)
        if r.stdout and len(r.stdout) > 2000:
            return r.stdout
    return ""


def clave(d):
    """Identidad del inmueble: coordenada redondeada + área.

    El diff usa esto y no la URL a propósito: un mismo apartamento cambia de
    portal o se republica con otro id cada pocos dias, y comparar por URL lo
    reportaria como caido y nuevo el mismo dia.
    """
    return "%.4f|%.4f|%d" % (d["lat"], d["lon"], int(d["m2"]))


def add(res, d):
    """Deduplica por coordenada redondeada + área."""
    if not d.get("lat"):
        return
    k = clave(d)
    prev = res.get(k)
    # nos quedamos con el que informe administración
    if prev and prev["admin"] is not None and d["admin"] is None:
        return
    res[k] = d


# ---------------------------------------------------------------- Fincaraíz
FR_BASE = ("https://www.fincaraiz.com.co/arriendo/apartamentos/%s/bogota/"
           "3-o-mas-habitaciones/hasta-4500000/m2-desde-100/edificados")
LINK_FR = re.compile(r'"link":"(/apartamento-en-arriendo[^"]+)"')


def fincaraiz(res, log):
    for loc in ["usaquen", "suba"]:
        for pg in range(1, 6):
            s = get(FR_BASE % loc + ("" if pg == 1 else "/pagina%d" % pg)).replace('\\"', '"')
            ms = list(LINK_FR.finditer(s))
            if not ms:
                break
            n = 0
            for i, m in enumerate(ms):
                link = m.group(1)
                pre = s[ms[i - 1].end() if i else max(0, m.start() - 12000): m.start()]
                post = s[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 9000]
                pm = None
                for x in re.finditer(r'"price":\{"amount":(\d+),"admin_included":(\d+)', pre):
                    pm = x
                if not pm:
                    continue
                canon, total = int(pm.group(1)), int(pm.group(2))

                def sh(f):
                    y = None
                    for x in re.finditer(r'\{"field":"%s","value":"([^"]*)"' % f, pre):
                        y = x
                    return y.group(1) if y else ""
                hab = int(sh("bedrooms") or 0)
                par = int(re.sub(r"[^\d]", "", sh("garage")) or 0)
                am = re.match(r"([\d.,]+)", (sh("m2Built") or sh("m2apto")).strip())
                area = float(am.group(1).replace(",", ".")) if am else 0
                if hab < MIN_HAB or par < MIN_PARQ or area < MIN_M2 or total > TOPE or canon <= 0:
                    continue
                barrio = normaliza_barrio(link.split("/")[1]
                                          .replace("apartamento-en-arriendo-en-", "")
                                          .replace("-bogota", ""))
                if not barrio:
                    continue
                fac = re.search(r'"facilities":(\[.*?\])(?=,"m2")', post)
                lat = re.search(r'"latitude":(-?[\d.]+)', post)
                lon = re.search(r'"longitude":(-?[\d.]+)', post)
                img = re.search(r'"image":"(https://[^"]+?\.jpg)"', post)
                cre = re.search(r'"created_at":"([\d-]+)"', post)
                own = None
                for x in re.finditer(r'"owner":\{"id":\d+,"name":"([^"]*)"', pre):
                    own = x
                if not (lat and lon):
                    continue
                add(res, dict(barrio=barrio, canon=canon, admin=total - canon, m2=area, hab=hab,
                    ban=int(re.sub(r"[^\d]", "", sh("bathrooms")) or 0), parq=par,
                    estrato=sh("stratum") or None, piso=sh("floor") or None,
                    asc="si" if (fac and "Ascensor" in fac.group(1)) else "nd",
                    src="Fincaraíz", url=link, lat=float(lat.group(1)), lon=float(lon.group(1)),
                    img=img.group(1) if img else "", date=cre.group(1) if cre else None,
                    pub=own.group(1) if own else "Fincaraíz"))
                n += 1
            log.append("Fincaraíz %s p%d: %d avisos, %d aptos" % (loc, pg, len(ms), n))


# ---------------------------------------------------------------- Metrocuadrado
def metrocuadrado(res, log):
    def uno(b):
        s = get("https://www.metrocuadrado.com/apartamento/arriendo/bogota/%s/" % b.replace(" ", "-"))
        if not s:
            return b, 0, 0
        s = s.replace('\\"', '"')
        trozos = s.split('"contactPhone":')[1:]
        n = 0
        for c in trozos:
            w = c[:9000]

            def g(k):
                m = re.search(r'"%s":"?([^",}]*)' % k, w)
                return m.group(1) if m else ""

            def num(v):
                try: return float(re.sub(r"[^0-9.]", "", str(v)) or 0)
                except ValueError: return 0
            hab, par = int(num(g("mnrocuartos"))), int(num(g("mnrogarajes")))
            canon, admin = num(g("mvalorarriendo")), num(g("mvaloradministracion"))
            area = max(num(g("mareac")), num(g("marea")), num(g("areaprivada")))
            if hab < MIN_HAB or par < MIN_PARQ or area < MIN_M2 or canon <= 0 or canon + admin > TOPE:
                continue
            barrio = normaliza_barrio(g("mnombrecomunbarrio") or g("mbarrio"))
            if not barrio:
                continue
            lm = re.search(r'"localizacion":\{"lon":(-?[\d.]+),"lat":([\d.]+)', w)
            if not lm:
                continue
            link = g("link")
            foto = g("mprimerafotoinmueble")
            ident = link.split("/")[-1]
            add(res, dict(barrio=barrio, canon=int(canon), admin=(int(admin) if admin else None),
                m2=area, hab=hab, ban=int(num(g("mnrobanos"))), parq=par,
                estrato=None, piso=None, asc="nd", src="Metrocuadrado", url=link,
                lat=float(lm.group(2)), lon=float(lm.group(1)),
                img=("https://multimedia.metrocuadrado.com/%s/%s_x.jpg" % (ident, foto)) if foto else "",
                date=None, pub="Metrocuadrado"))
            n += 1
        return b, len(trozos), n
    with ThreadPoolExecutor(max_workers=6) as ex:
        for b, tot, n in ex.map(uno, BARRIOS):
            if n:
                log.append("Metrocuadrado %s: %d avisos, %d aptos" % (b, tot, n))


# ---------------------------------------------------------------- Ciencuadras
def ciencuadras(res, log):
    def uno(b):
        h = get("https://www.ciencuadras.com/arriendo/apartamento/bogota/" + b.replace(" ", "-"))
        tot = re.search(r"(\d+)\s*Resultados", h)
        t = int(tot.group(1)) if tot else -1
        if t >= 200:                      # no reconoce el barrio y cae a toda la ciudad
            return b, t, 0, True
        m = re.search(r'id="searchResults-schema">(\{.*?\})</script>', h, re.S)
        if not m:
            return b, t, 0, False
        try:
            d = json.loads(m.group(1))
        except ValueError:
            return b, t, 0, False
        n = 0
        for it in d.get("itemListElement", []):
            p = it["item"]; o = p["offers"]; io_ = o["itemOffered"]
            try: precio = int(float(o["price"]))
            except (ValueError, KeyError): continue
            try: area = float(io_["floorSize"]["value"])
            except (ValueError, KeyError, TypeError): area = 0
            g = io_.get("geo", {})
            try: lat, lon = float(g.get("latitude")), float(g.get("longitude"))
            except (TypeError, ValueError): continue
            if area < MIN_M2 or precio <= 0 or precio > TOPE:
                continue
            if not (4.66 < lat < 4.80 and -74.12 < lon < -74.01):   # fuera de Bogotá norte
                continue
            barrio = normaliza_barrio(p["url"].split("/")[-1]
                                      .replace("apartamento-en-arriendo-en-", "")
                                      .rsplit("-", 1)[0].replace("-bogota", ""))
            if not barrio:
                continue
            add(res, dict(barrio=barrio, canon=precio, admin=None, m2=area, hab=MIN_HAB,
                ban=int(io_.get("numberOfBathroomsTotal") or 0), parq=1, estrato=None, piso=None,
                asc="nd", src="Ciencuadras", url=p["url"].replace("https://www.ciencuadras.com", ""),
                lat=lat, lon=lon, img=p.get("image", ""), date=None, pub="Ciencuadras"))
            n += 1
        return b, t, n, False
    with ThreadPoolExecutor(max_workers=6) as ex:
        for b, t, n, fb in ex.map(uno, BARRIOS):
            if fb:
                log.append("Ciencuadras %s: descartado, cayó a búsqueda de toda la ciudad (%d)" % (b, t))
            elif n:
                log.append("Ciencuadras %s: %d resultados, %d aptos" % (b, t, n))


# ---------------------------------------------------------------- Properati
CARD_PR = re.compile(
    r'<a href="(https://www\.properati\.com\.co/detalle/[^"]+)" class="title"[^>]*>(.*?)</a>(.*?)'
    r'(?=<a href="https://www\.properati\.com\.co/detalle/[^"]+" class="title"|$)', re.S)


def properati(res, log):
    vistos = set()
    for loc in ["usaquen-bogota-d-c", "suba-bogota-d-c"]:
        for pg in range(1, 20):
            h = get("https://www.properati.com.co/s/%s/apartamento/arriendo" % loc
                    + ("" if pg == 1 else "/%d" % pg))
            cards = CARD_PR.findall(h)
            if not cards:
                break
            nuevos = n = 0
            for url, _t, tail in cards:
                if url in vistos:
                    continue
                vistos.add(url); nuevos += 1
                pr = re.search(r'snippet__price">([^<]*)', tail)
                lo = re.search(r'snippet__location">([^<]*)', tail)
                hb = re.search(r'bedrooms-value">(\d+)', tail)
                ar = re.search(r'area-value">([\d.,]+)', tail)
                if not (pr and lo and hb and ar and "car_park" in tail):
                    continue
                canon = int(re.sub(r"[^\d]", "", pr.group(1)) or 0)
                hab = int(hb.group(1))
                area = float(ar.group(1).replace(".", "").replace(",", "."))
                if hab < MIN_HAB or area < MIN_M2 or canon < 1_000_000 or canon > TOPE:
                    continue
                barrio = normaliza_barrio(lo.group(1).split(",")[0])
                if not barrio:
                    continue
                # Properati no publica coordenada en la tarjeta: se marca aproximada
                log.append("Properati %s (%s, %d m²): sin coordenada, requiere revisión manual"
                           % (barrio, pr.group(1).strip(), area))
                n += 1
            if nuevos == 0:
                break
            if n:
                log.append("Properati %s p%d: %d con criterios" % (loc, pg, n))


# ---------------------------------------------------------------- principal
def main():
    log, res = [], {}
    for fn in (fincaraiz, metrocuadrado, ciencuadras, properati):
        try:
            fn(res, log)
        except Exception as e:                       # un portal caído no tumba el barrido
            log.append("ERROR en %s: %s" % (fn.__name__, e))

    filas = [r for r in res.values() if km(r["lat"], r["lon"]) <= 8]
    filas.sort(key=lambda r: r["canon"] + (r["admin"] or 0))
    for r in filas:
        r["km"] = km(r["lat"], r["lon"])
        r["total"] = r["canon"] + (r["admin"] or 0)

    ruta = os.path.join(RAIZ, "data.json")
    previo = []
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            previo = json.load(fh).get("avisos", [])
    antes = {clave(a) for a in previo if a.get("lat")}
    ahora = {clave(a) for a in filas}
    nuevos = [a for a in filas if clave(a) not in antes]
    caidos = [a for a in previo if a.get("lat") and clave(a) not in ahora]

    print("=" * 62)
    print("Candidatos vigentes:      %d" % len(filas))
    print("Nuevos desde el anterior: %d" % len(nuevos))
    print("Caídos:                   %d" % len(caidos))
    print("Con ascensor confirmado:  %d" % sum(1 for a in filas if a["asc"] == "si"))
    print("A menos de 2 km:          %d" % sum(1 for a in filas if a["km"] < 2))
    print("Barrios con oferta:       %d" % len({a["barrio"] for a in filas}))
    porportal = {}
    for a in filas:
        porportal[a["src"]] = porportal.get(a["src"], 0) + 1
    print("Por portal:               %s" % porportal)
    print("=" * 62)
    for a in nuevos:
        print("  NUEVO  %-22s $%s  %s m²  %.1f km" %
              (a["barrio"], format(a["total"], ",d").replace(",", "."), a["m2"], a["km"]))
    for a in caidos:
        print("  CAYÓ   %-22s $%s  %s m²" %
              (a["barrio"], format(a["total"], ",d").replace(",", "."), a["m2"]))
    print("-" * 62)
    for l in log:
        print("  " + l)

    if "--dry" in sys.argv:
        return
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"generado": subprocess.run(["date", "+%Y-%m-%d"], capture_output=True,
                                              text=True).stdout.strip(),
                   "avisos": filas, "nuevos": [a["url"] for a in nuevos], "caidos": caidos},
                  fh, ensure_ascii=False, indent=1)
    print("\ndata.json escrito con %d avisos" % len(filas))


if __name__ == "__main__":
    main()
