#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Barrido de apartamentos sobre los portales, guiado por una búsqueda de busquedas/.

Corre sin navegador: los portales entregan los datos en el HTML del servidor si se
piden con cabeceras de navegador.

    python3 tools/barrido.py --busqueda norte
    python3 tools/barrido.py --busqueda occidente --dry
"""
import io, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import get, dentro, distancias, bonito, sinacento, ruta

# Cada portal nombra la operación a su manera.
RUTA_FR = {"arriendo": "arriendo", "venta": "venta"}
ENLACE_FR = {"arriendo": "apartamento-en-arriendo", "venta": "apartamento-en-venta"}
RUTA_M2 = {"arriendo": "arriendo", "venta": "venta"}
CAMPO_M2 = {"arriendo": "mvalorarriendo", "venta": "mvalorventa"}
RUTA_CC = {"arriendo": "arriendo", "venta": "venta"}


def normaliza_barrio(cfg, crudo):
    """En modo barrios exige que caiga en la lista; en modo radio acepta y embellece."""
    s = re.sub(r"\s+", " ", sinacento(crudo).replace("-", " "))
    if cfg["filtro"] == "radio":
        return bonito(s) or "Sin barrio"
    alias = cfg.get("alias", {})
    if s in alias:
        return alias[s]
    for b in sorted(cfg["barrios"], key=len, reverse=True):
        if re.search(r"\b" + re.escape(b) + r"\b", s):
            return alias.get(b, bonito(b))
    return None


def cabe(cfg, op, hab, parq, area, total):
    c = cfg["criterios"]
    return (c["hab_min"] <= hab <= c["hab_max"] and parq >= c["parq_min"]
            and area >= c["m2_min"] and 0 < total <= cfg["topes"][op])


def add(res, d):
    if not d.get("lat"):
        return
    k = "%.4f|%.4f|%d|%s" % (d["lat"], d["lon"], int(d["m2"]), d["op"])
    prev = res.get(k)
    if prev and prev["admin"] is not None and d["admin"] is None:
        return                      # preferimos el aviso que sí informa administración
    res[k] = d


# ---------------------------------------------------------------- Fincaraíz
def fincaraiz(cfg, res, log):
    c = cfg["criterios"]
    for op in cfg["operaciones"]:
        base = ("https://www.fincaraiz.com.co/%s/apartamentos/%%s/bogota/"
                "%d-o-mas-habitaciones/hasta-%d/m2-desde-%d"
                % (RUTA_FR[op], c["hab_min"], cfg["topes"][op], c["m2_min"]))
        patron = re.compile(r'"link":"(/%s[^"]+)"' % ENLACE_FR[op])
        for loc in cfg["localidades"]:
            for pg in range(1, 8):
                s = get(base % loc + ("" if pg == 1 else "/pagina%d" % pg)).replace('\\"', '"')
                ms = list(patron.finditer(s))
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
                    if not cabe(cfg, op, hab, par, area, total):
                        continue
                    lat = re.search(r'"latitude":(-?[\d.]+)', post)
                    lon = re.search(r'"longitude":(-?[\d.]+)', post)
                    if not (lat and lon):
                        continue
                    la, lo = float(lat.group(1)), float(lon.group(1))
                    if not dentro(cfg, la, lo):
                        continue
                    barrio = normaliza_barrio(cfg, link.split("/")[1]
                                              .replace(ENLACE_FR[op] + "-en-", "")
                                              .replace("-bogota", ""))
                    if not barrio:
                        continue
                    fac = re.search(r'"facilities":(\[.*?\])(?=,"m2")', post)
                    img = re.search(r'"image":"(https://[^"]+?\.jpg)"', post)
                    cre = re.search(r'"created_at":"([\d-]+)"', post)
                    own = None
                    for x in re.finditer(r'"owner":\{"id":\d+,"name":"([^"]*)"', pre):
                        own = x
                    add(res, dict(op=op, barrio=barrio, canon=canon,
                        admin=(total - canon) if op == "arriendo" else None,
                        m2=area, hab=hab, ban=int(re.sub(r"[^\d]", "", sh("bathrooms")) or 0),
                        parq=par, estrato=sh("stratum") or None, piso=sh("floor") or None,
                        asc="si" if (fac and "Ascensor" in fac.group(1)) else "nd",
                        src="Fincaraíz", url=link, lat=la, lon=lo,
                        img=img.group(1) if img else "", date=cre.group(1) if cre else None,
                        pub=own.group(1) if own else "Fincaraíz"))
                    n += 1
                log.append("Fincaraíz %s %s p%d: %d avisos, %d aptos" % (op, loc, pg, len(ms), n))


# ---------------------------------------------------------------- Metrocuadrado
def metrocuadrado(cfg, res, log):
    def uno(par):
        op, b = par
        s = get("https://www.metrocuadrado.com/apartamento/%s/bogota/%s/"
                % (RUTA_M2[op], b.replace(" ", "-")))
        if not s:
            return op, b, 0, 0
        s = s.replace('\\"', '"')
        trozos = s.split('"contactPhone":')[1:]
        n = 0
        for t in trozos:
            w = t[:9000]

            def g(k):
                m = re.search(r'"%s":"?([^",}]*)' % k, w)
                return m.group(1) if m else ""

            def num(v):
                try: return float(re.sub(r"[^0-9.]", "", str(v)) or 0)
                except ValueError: return 0
            hab, par = int(num(g("mnrocuartos"))), int(num(g("mnrogarajes")))
            precio = num(g(CAMPO_M2[op]))
            admin = num(g("mvaloradministracion")) if op == "arriendo" else 0
            area = max(num(g("mareac")), num(g("marea")), num(g("areaprivada")))
            if not cabe(cfg, op, hab, par, area, precio + admin):
                continue
            lm = re.search(r'"localizacion":\{"lon":(-?[\d.]+),"lat":([\d.]+)', w)
            if not lm:
                continue
            la, lo = float(lm.group(2)), float(lm.group(1))
            if not dentro(cfg, la, lo):
                continue
            barrio = normaliza_barrio(cfg, g("mnombrecomunbarrio") or g("mbarrio"))
            if not barrio:
                continue
            link, foto = g("link"), g("mprimerafotoinmueble")
            ident = link.split("/")[-1]
            add(res, dict(op=op, barrio=barrio, canon=int(precio),
                admin=(int(admin) if (op == "arriendo" and admin) else None),
                m2=area, hab=hab, ban=int(num(g("mnrobanos"))), parq=par,
                estrato=None, piso=None, asc="nd", src="Metrocuadrado", url=link,
                lat=la, lon=lo,
                img=("https://multimedia.metrocuadrado.com/%s/%s_x.jpg" % (ident, foto)) if foto else "",
                date=None, pub="Metrocuadrado"))
            n += 1
        return op, b, len(trozos), n
    tareas = [(op, b) for op in cfg["operaciones"] for b in cfg["barrios"]]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for op, b, tot, n in ex.map(uno, tareas):
            if n:
                log.append("Metrocuadrado %s %s: %d avisos, %d aptos" % (op, b, tot, n))


# ---------------------------------------------------------------- Ciencuadras
def ciencuadras(cfg, res, log):
    def uno(par):
        op, b = par
        h = get("https://www.ciencuadras.com/%s/apartamento/bogota/%s"
                % (RUTA_CC[op], b.replace(" ", "-")))
        m = re.search(r'id="searchResults-schema">(\{.*?\})</script>', h, re.S)
        if not m:
            return op, b, 0, 0
        try:
            d = json.loads(m.group(1))
        except ValueError:
            return op, b, 0, 0
        n = 0
        for it in d.get("itemListElement", []):
            p = it["item"]; o = p["offers"]; io_ = o["itemOffered"]
            try: precio = int(float(o["price"]))
            except (ValueError, KeyError): continue
            try: area = float(io_["floorSize"]["value"])
            except (ValueError, KeyError, TypeError): area = 0
            g = io_.get("geo", {})
            try: la, lo = float(g.get("latitude")), float(g.get("longitude"))
            except (TypeError, ValueError): continue
            # Ciencuadras cae a una búsqueda de toda la ciudad cuando no reconoce el
            # barrio; el filtro geográfico deja fuera esos resultados sin más trámite.
            if not dentro(cfg, la, lo):
                continue
            c = cfg["criterios"]
            if area < c["m2_min"] or not (0 < precio <= cfg["topes"][op]):
                continue
            barrio = normaliza_barrio(cfg, p["url"].split("/")[-1]
                                      .replace("apartamento-en-%s-en-" % RUTA_CC[op], "")
                                      .rsplit("-", 1)[0].replace("-bogota", ""))
            if not barrio:
                continue
            # Ciencuadras no publica habitaciones ni garajes: quedan en 0 = sin dato,
            # nunca en el mínimo pedido (sería afirmar algo que el aviso no dice).
            add(res, dict(op=op, barrio=barrio, canon=precio, admin=None, m2=area,
                hab=0, ban=int(io_.get("numberOfBathroomsTotal") or 0),
                parq=0, inc=["hab", "parq"], estrato=None, piso=None, asc="nd",
                src="Ciencuadras", url=p["url"].replace("https://www.ciencuadras.com", ""),
                lat=la, lon=lo, img=p.get("image", ""), date=None, pub="Ciencuadras"))
            n += 1
        return op, b, len(d.get("itemListElement", [])), n
    tareas = [(op, b) for op in cfg["operaciones"] for b in cfg["barrios"]]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for op, b, tot, n in ex.map(uno, tareas):
            if n:
                log.append("Ciencuadras %s %s: %d de %d aptos" % (op, b, n, tot))


# ---------------------------------------------------------------- Properati
def properati(cfg, res, log):
    """Properati responde 401 desde agosto de 2026: bloquea la descarga.

    Se deja el intento para detectar cuándo vuelva, pero no aporta avisos.
    """
    u = "https://www.properati.com.co/s/%s-bogota-d-c/apartamento/arriendo" % cfg["localidades"][0]
    h = get(u, intentos=1)
    log.append("Properati: %s" % ("responde de nuevo, hay que reactivar el parser"
                                  if len(h) > 5000 else "bloqueado (401), sin avisos"))


def main():
    cfg = comun.cargar()
    log, res = [], {}
    for fn in (fincaraiz, metrocuadrado, ciencuadras, properati):
        try:
            fn(cfg, res, log)
        except Exception as e:
            log.append("ERROR en %s: %s" % (fn.__name__, e))

    filas = sorted(res.values(), key=lambda r: (r["op"], r["canon"] + (r["admin"] or 0)))
    for r in filas:
        r["total"] = r["canon"] + (r["admin"] or 0)
        r["dist"] = distancias(cfg, r["lat"], r["lon"])
        r["km"] = r["dist"][comun.principal(cfg)["clave"]]

    p = ruta(cfg, "datos")
    previo = json.load(io.open(p, encoding="utf-8"))["avisos"] if os.path.exists(p) else []
    ident = lambda a: "%.4f|%.4f|%d|%s" % (a["lat"], a["lon"], int(a["m2"]), a.get("op", "arriendo"))
    antes = {ident(a) for a in previo if a.get("lat")}
    ahora = {ident(a) for a in filas}
    nuevos = [a for a in filas if ident(a) not in antes]
    caidos = [a for a in previo if a.get("lat") and ident(a) not in ahora]

    print("=" * 64)
    print("Búsqueda: %s" % cfg["titulo"])
    for op in cfg["operaciones"]:
        print("  %-9s %d vigentes" % (op, sum(1 for a in filas if a["op"] == op)))
    print("Total: %d · nuevos: %d · caídos: %d" % (len(filas), len(nuevos), len(caidos)))
    porportal = {}
    for a in filas:
        porportal[a["src"]] = porportal.get(a["src"], 0) + 1
    print("Por portal: %s" % porportal)
    print("=" * 64)
    for a in nuevos[:40]:
        print("  NUEVO %-8s %-24s $%s  %s m²  %.1f km" %
              (a["op"], a["barrio"], format(a["total"], ",d").replace(",", "."), a["m2"], a["km"]))
    for a in caidos[:20]:
        print("  CAYÓ  %-8s %-24s $%s" %
              (a.get("op", "?"), a["barrio"], format(a["total"], ",d").replace(",", ".")))
    print("-" * 64)
    for l in log[:60]:
        print("  " + l)

    if "--dry" in sys.argv:
        return
    with io.open(p, "w", encoding="utf-8") as fh:
        json.dump({"generado": subprocess.run(["date", "+%Y-%m-%d"], capture_output=True,
                                              text=True).stdout.strip(),
                   "busqueda": cfg["id"], "avisos": filas,
                   "nuevos": [a["url"] for a in nuevos], "caidos": caidos}, fh,
                  ensure_ascii=False, indent=1)
    print("\n%s escrito con %d avisos" % (cfg["salida"]["datos"], len(filas)))


if __name__ == "__main__":
    main()
