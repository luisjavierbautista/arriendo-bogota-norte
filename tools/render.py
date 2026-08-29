#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenera la página de una búsqueda a partir de sus datos. Corre después de barrido.py.

    python3 tools/render.py --busqueda norte
    python3 tools/render.py --busqueda occidente

Solo toca los bloques marcados de la página (DATA, GONE, .tiles, .verdict, título,
descripción y eyebrow); el diseño y el JavaScript se editan a mano en el HTML.
El resumen se reescribe entero en cada corrida: si solo se agregara, los párrafos
de corridas viejas quedarían contradiciendo los datos.
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
from comun import clave_edificio, ruta

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def cop(n):
    return "$" + format(int(round(n)), ",d").replace(",", ".")


def millones(n):
    m = n / 1e6
    return "$%s millones" % (("%.0f" % m) if m >= 10 else ("%.1f" % m).replace(".", ","))


def precio_texto(cfg, a):
    return millones(a["total"]) if a["op"] == "venta" else cop(a["total"])


def js(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float) and v == int(v): return str(int(v))
    if isinstance(v, (list, tuple)): return "[%s]" % ",".join(js(x) for x in v)
    return repr(v)


def num(v):
    return int(v) if isinstance(v, float) and v == int(v) else v


def primera(avisos, nuevos, caidos):
    """¿Es el primer barrido de esta búsqueda? Entonces todo aparece como nuevo."""
    return bool(avisos) and len(nuevos) == len(avisos) and not caidos


def m2txt(v):
    """Los portales publican áreas con decimales inventados; una cifra basta."""
    return ("%.0f" % v) if abs(v - round(v)) < 0.05 else ("%.1f" % v).replace(".", ",")


def coma(x, dec=1):
    return ("%.*f" % (dec, x)).replace(".", ",")


def nota(a):
    """Descripción factual, solo con lo que el aviso reporta."""
    inc = a.get("inc") or []
    hab = "habitaciones sin dato" if ("hab" in inc or not a["hab"]) else "%d habitaciones" % a["hab"]
    p = ["%s m² con %s" % (m2txt(a["m2"]), hab)]
    if a.get("ban"):
        p.append("%d baños" % a["ban"])
    if "parq" not in inc:
        p.append("%d parqueadero%s" % (a["parq"], "s" if a["parq"] != 1 else ""))
    t = ", ".join(p) + " en " + a["barrio"] + "."
    if a.get("piso"):
        t += " Piso %s." % a["piso"]
    return t


def flags(cfg, a):
    """Alertas de la ficha, según las reglas declaradas en la búsqueda."""
    f, via, inc = [], a.get("_via") or {}, a.get("inc") or []
    for r in cfg.get("reglas", []):
        t = r["tipo"]
        if t == "viaje":
            v = via.get(r["clave"])
            if v is None: continue
            if "max" in r and v <= r["max"]:
                f.append((r["texto"].format(v=v), r["sev"]))
            elif "min" in r and v >= r["min"]:
                f.append((r["texto"].format(v=v), r["sev"]))
        elif t == "admin_faltante":
            if a["op"] == "arriendo" and a.get("admin") is None:
                f.append((r["texto"], r["sev"]))
        elif t == "incierto":
            if r["campo"] in inc:
                f.append((r["texto"], r["sev"]))
        elif t == "cerca":
            km = a["dist"].get(r["ancla"])
            if km is not None and km < r["max_km"]:
                f.append((r["texto"].format(km=coma(km)), r["sev"]))
        elif t == "ascensor":
            if a["asc"] == "si":
                f.append((r["texto"], r["sev"]))
        elif t == "tope":
            tope = cfg["topes"][a["op"]]
            if a["total"] >= tope * r["fraccion"]:
                f.append((r["texto"].format(tope=millones(tope) if a["op"] == "venta" else cop(tope)),
                          r["sev"]))
    return f


def cargar_cache(cfg, cual):
    p = ruta(cfg, cual)
    if not os.path.exists(p):
        return {}
    return json.load(io.open(p, encoding="utf-8")).get("edificios", {})


def bloque_datos(cfg, avisos, nuevos):
    frec = cfg["frecuencia"]
    out = ["  var DATA = ["]
    for a in avisos:
        fl = ",".join('{t:%s, s:%s}' % (js(t), js(s)) for t, s in flags(cfg, a))
        out.append('    { op:%s, barrio:%s, canon:%s, admin:%s, m2:%s, hab:%s, ban:%s, parq:%s, dep:null,'
                   % (js(a["op"]), js(a["barrio"]), a["canon"], js(a.get("admin")),
                      js(num(a["m2"])), a["hab"], a.get("ban") or 0, a["parq"]))
        out.append('      estrato:%s, piso:%s, asc:%s, src:%s, date:%s, pub:%s, inc:%s,'
                   % (js(a.get("estrato")), js(a.get("piso")), js(a["asc"]), js(a["src"]),
                      js(a.get("date")), js(a.get("pub") or a["src"]), js(a.get("inc") or [])))
        out.append('      lat:%s, lon:%s, approx:false, url:%s, img:%s,'
                   % (a["lat"], a["lon"], js(a["url"]), js(a.get("img") or "")))
        out.append('      dist:{%s},' % ",".join("%s:%s" % (k, coma(v, 2).replace(",", "."))
                                                 for k, v in sorted(a["dist"].items())))
        if a["_via"]:
            out.append('      via:{%s}, semana:%d,'
                       % (",".join("%s:%d" % (k, a["_via"][k]) for k in frec if k in a["_via"]),
                          a["_semana"]))
        sv = a.get("_sv")
        if sv and sv.get("hay"):
            out.append('      sv:{f:%s, lat:%s, lon:%s},'
                       % (js(sv.get("fecha", "")), sv["lat"], sv["lon"]))
        elif sv:
            out.append("      sv:false,")
        if a["url"] in nuevos:
            out.append("      nuevo:true,")
        out.append('      note:%s,' % js(nota(a)))
        out.append('      flags:[%s] },' % fl)
    if len(out) > 1:
        out[-1] = out[-1][:-1]
    out.append("  ];")
    return "\n".join(out)


def bloque_caidos(cfg, caidos):
    g = ["  var GONE = ["]
    for c in caidos:
        tot = c.get("total", c["canon"] + (c.get("admin") or 0))
        op = c.get("op", "arriendo")
        g.append('    [%s,%s,%s,%s],'
                 % (js(c["barrio"]), js(millones(tot) if op == "venta" else cop(tot)),
                    js(m2txt(c["m2"]) + " m²"),
                    js("%s · %s · %s" % (op, ("%d hab" % c["hab"]) if c.get("hab") else "hab n/d",
                                         c["src"]))))
    if len(g) > 1:
        g[-1] = g[-1][:-1]
    g.append("  ];")
    return "\n".join(g)


def tiles(cfg, avisos, nuevos):
    n_asc = sum(1 for a in avisos if a["asc"] == "si")
    con_via = [a for a in avisos if a.get("_semana") is not None]
    mejor = min(con_via, key=lambda a: a["_semana"]) if con_via else None
    pri = comun.principal(cfg)["clave"]
    valores = {
        "total": len(avisos),
        "nuevos": len(nuevos),
        "ascensor": n_asc,
        "arriendo": sum(1 for a in avisos if a["op"] == "arriendo"),
        "venta": sum(1 for a in avisos if a["op"] == "venta"),
        "cerca_principal": sum(1 for a in avisos
                               if (a.get("_via") or {}).get(pri, 999) <= 20),
        "mejor_semana": ("%dh%02d" % (mejor["_semana"] // 60, mejor["_semana"] % 60)) if mejor else "n/d",
    }
    filas = []
    for i, (clave, etiqueta) in enumerate(cfg["tiles"]):
        filas.append('    <div class="tile%s"><div class="n">%s</div><div class="l">%s</div></div>'
                     % (" is-key" if i == 0 else "", valores.get(clave, "n/d"), etiqueta))
    return '  <div class="tiles">\n' + "\n".join(filas) + "\n  </div>"


def resumen(cfg, avisos, nuevos, caidos, fecha, es_primera):
    n_asc = sum(1 for a in avisos if a["asc"] == "si")
    unidad = cfg["textos"].get("unidad", "opciones")
    if es_primera:
        fr = ["Primer barrido de la zona: <strong>%d %s vigentes</strong> en los tres portales. "
              "Desde la próxima corrida esta nota dirá qué entró y qué se cayó."
              % (len(avisos), unidad)]
        nuevos = set()
    else:
        fr = ["El barrido del %s deja <strong>%d %s vigentes</strong>: %d que no estaban en la "
              "corrida anterior y %d que se cayeron de los portales."
              % (fecha, len(avisos), unidad, len(nuevos), len(caidos))]
    if len(cfg["operaciones"]) > 1:
        fr.append("Son %s." % " y ".join(
            "<strong>%d en %s</strong>" % (sum(1 for a in avisos if a["op"] == op), op)
            for op in cfg["operaciones"]))
    for op in cfg["operaciones"]:
        nu = [a for a in avisos if a["url"] in nuevos and a["op"] == op]
        if nu:
            b = min(nu, key=lambda a: a["total"])
            como = ("El más económico que entró" if len(cfg["operaciones"]) == 1
                    else "En %s, el más económico que entró" % op)
            fr.append("%s está en %s: %s m² por <strong>%s</strong>."
                      % (como, b["barrio"], m2txt(b["m2"]), precio_texto(cfg, b)))
    if not nuevos and not es_primera:
        fr.append("Ninguna opción nueva entró en esta corrida.")
    if cfg.get("resumen_ascensor"):
        fr.append("Solo <strong>%d de %d</strong> declaran ascensor en la ficha: el resto quedan "
                  "marcados como sin confirmar, no como sin ascensor." % (n_asc, len(avisos)))
    con_via = [a for a in avisos if a.get("_semana") is not None]
    if con_via:
        mejor = min(con_via, key=lambda a: a["_semana"])
        # Solo los dos trayectos que más pesan en la semana, y el total.
        claves = sorted(mejor["_via"], key=lambda c: -cfg["frecuencia"][c])[:2]
        nombres = {c: n for c, n, *_ in cfg["destinos"]}
        detalle = " y ".join("%d minutos a %s" % (mejor["_via"][c], nombres.get(c, c))
                             for c in claves)
        fr.append("En tiempos de viaje, el mejor ubicado es <strong>%s</strong>: %s, para un total "
                  "de %dh%02d por semana solo de ida."
                  % (mejor["barrio"], detalle, mejor["_semana"] // 60, mejor["_semana"] % 60))
    return ('  <div class="verdict">\n    <h2>Qué cambió</h2>\n'
            '    <p id="auto-resumen">\n      ' + " ".join(fr) + "\n    </p>\n"
            "    <p>\n      " + cfg["textos"]["evergreen"] + "\n    </p>\n  </div>")


def main():
    cfg = comun.cargar()
    d = json.load(io.open(ruta(cfg, "datos"), encoding="utf-8"))
    VIA, SV = cargar_cache(cfg, "viajes"), cargar_cache(cfg, "streetview")
    avisos, caidos = d["avisos"], d.get("caidos", [])
    nuevos = set(d.get("nuevos", []))
    gen = d.get("generado", "")
    try:
        y, m, day = gen.split("-")
        fecha = "%d %s %s" % (int(day), MESES[int(m) - 1], y)
    except Exception:
        fecha = gen

    frec = cfg["frecuencia"]
    for a in avisos:
        a.setdefault("op", "arriendo")
        a.setdefault("total", a["canon"] + (a.get("admin") or 0))
        # data.json de corridas viejas no traía distancias por ancla.
        if "dist" not in a:
            a["dist"] = comun.distancias(cfg, a["lat"], a["lon"])
        v = VIA.get(clave_edificio(a))
        a["_via"] = {k: v[k]["min"] for k in frec if k in v} if v else None
        a["_semana"] = (round(sum(a["_via"][k] * frec[k] for k in a["_via"])) if a["_via"] else None)
        a["_sv"] = SV.get(clave_edificio(a))

    es_primera = primera(avisos, nuevos, caidos)
    if es_primera:
        nuevos = set()   # marcarlo todo como nuevo no distingue nada

    p = ruta(cfg, "pagina")
    s = io.open(p, encoding="utf-8").read()

    def swap(txt, ini, nuevo):
        i = txt.index(ini)
        j = txt.index("\n  ];", i) + len("\n  ];")
        return txt[:i] + nuevo + txt[j:]

    # Llave de Maps Embed API: es publica por diseno y debe estar restringida por
    # dominio en Google Cloud. Si no esta configurada, la ficha abre Street View
    # en otra pestana en vez de incrustarlo.
    sv = os.environ.get("SV_EMBED_KEY", "").strip()
    s = re.sub(r'var SV_KEY = "[^"]*";', 'var SV_KEY = "%s";' % sv, s, count=1)
    # Llave de CARTO Basemaps: tambien es publica por diseno (viaja en la URL de cada
    # tile) y se restringe por dominio en el panel de CARTO. Sin ella el mapa carga
    # igual, contra la cuota compartida y sin garantia de servicio.
    carto = os.environ.get("CARTO_KEY", "").strip()
    s = re.sub(r'var CARTO_KEY = "[^"]*";', 'var CARTO_KEY = "%s";' % carto, s, count=1)
    s = re.sub(r'var FECHA_CORRIDA = "[^"]*";', 'var FECHA_CORRIDA = "%s";' % fecha, s, count=1)

    s = swap(s, "  var DATA = [", bloque_datos(cfg, avisos, nuevos))
    s = swap(s, "  var GONE = [", bloque_caidos(cfg, caidos))
    s = re.sub(r'  <div class="tiles">.*?\n  </div>', lambda _m: tiles(cfg, avisos, nuevos),
               s, count=1, flags=re.S)
    s = re.sub(r'  <div class="verdict">.*?\n  </div>',
               lambda _m: resumen(cfg, avisos, nuevos, caidos, fecha, es_primera),
               s, count=1, flags=re.S)

    t = cfg["textos"]
    s = re.sub(r'<div class="eyebrow">[^<]*</div>',
               '<div class="eyebrow">%s</div>' % t["eyebrow"].format(fecha=fecha), s, count=1)
    s = re.sub(r"<title>[^<]*</title>",
               "<title>%s</title>" % t["titulo_html"].format(n=len(avisos), fecha=fecha), s, count=1)
    s = re.sub(r'<meta name="description" content="[^"]*">',
               '<meta name="description" content="%s">'
               % t["descripcion_meta"].format(n=len(avisos)), s, count=1)

    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("%s regenerado: %d avisos, %d nuevos, %d caídos"
          % (cfg["salida"]["pagina"], len(avisos), len(nuevos), len(caidos)))
    if s.count("var DATA = [") != 1 or s.count("var GONE = [") != 1:
        print("AVISO: los marcadores DATA/GONE quedaron duplicados", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
