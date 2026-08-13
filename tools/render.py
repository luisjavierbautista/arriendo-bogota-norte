#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenera index.html a partir de data.json. Corre después de tools/barrido.py."""
import io, json, os, re, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def cop(n):
    return "$" + format(int(round(n)), ",d").replace(",", ".")


def js(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float) and v == int(v): return str(int(v))
    return repr(v)


def num(v):
    return int(v) if isinstance(v, float) and v == int(v) else v


def nota(a):
    """Descripción factual, solo con lo que el aviso reporta."""
    p = ["%s m² con %d habitaciones" % (str(num(a["m2"])).replace(".", ","), a["hab"])]
    if a.get("ban"): p.append("%d baños" % a["ban"])
    p.append("%d parqueadero%s" % (a["parq"], "s" if a["parq"] != 1 else ""))
    t = ", ".join(p) + " en " + a["barrio"] + "."
    if a.get("piso"): t += " Piso %s." % a["piso"]
    return t


def flags(a):
    f = []
    v, sem = a.get("_via"), a.get("_semana")
    if v:
        if v.get("colegio") is not None and v["colegio"] <= 26:
            f.append(("Colegio a %d minutos, de lo mejor de la lista." % v["colegio"], "ok"))
        if v.get("oficina") is not None and v["oficina"] >= 38:
            f.append(("La oficina en Fontibón queda a %d minutos en pico." % v["oficina"], "warn"))
    if a.get("admin") is None:
        f.append(("El aviso no informa la administración.", "crit"))
    if a["km"] < 2:
        f.append(("A %s km de tu casa actual." % ("%.1f" % a["km"]).replace(".", ","), "ok"))
    if a["asc"] == "si":
        f.append(("Ascensor confirmado en la ficha.", "ok"))
    if a["canon"] + (a["admin"] or 0) >= 4_950_000:
        f.append(("Queda en el tope de $5.000.000.", "warn"))
    return f


# Cuántas veces por semana se hace cada trayecto, para el índice de viaje semanal.
FRECUENCIA = {"gimnasio": 2, "musica": 1, "teatro": 1, "colegio": 5, "oficina": 2.5}


def viajes():
    ruta = os.path.join(RAIZ, "viajes.json")
    if not os.path.exists(ruta):
        return {}
    return json.load(io.open(ruta, encoding="utf-8")).get("edificios", {})


def main():
    d = json.load(io.open(os.path.join(RAIZ, "data.json"), encoding="utf-8"))
    VIA = viajes()
    avisos, caidos = d["avisos"], d.get("caidos", [])
    nuevos = set(d.get("nuevos", []))
    gen = d.get("generado", "")
    try:
        y, m, day = gen.split("-")
        fecha = "%d %s %s" % (int(day), MESES[int(m) - 1], y)
    except Exception:
        fecha = gen

    for a in avisos:
        v = VIA.get("%.4f|%.4f" % (a["lat"], a["lon"]))
        a["_via"] = {k: v[k]["min"] for k in FRECUENCIA if k in v} if v else None
        a["_semana"] = (round(sum(a["_via"][k] * FRECUENCIA[k] for k in a["_via"]))
                        if a["_via"] else None)

    out = ["  var DATA = ["]
    for a in avisos:
        fl = ",".join('{t:%s, s:%s}' % (js(t), js(s)) for t, s in flags(a))
        out.append('    { barrio:%s, canon:%s, admin:%s, m2:%s, hab:%s, ban:%s, parq:%s, dep:null,'
                   % (js(a["barrio"]), a["canon"], js(a["admin"]), js(num(a["m2"])), a["hab"],
                      a.get("ban") or 0, a["parq"]))
        out.append('      estrato:%s, piso:%s, asc:%s, src:%s, date:%s, pub:%s,'
                   % (js(a.get("estrato")), js(a.get("piso")), js(a["asc"]), js(a["src"]),
                      js(a.get("date")), js(a.get("pub") or a["src"])))
        out.append('      lat:%s, lon:%s, approx:false, url:%s, img:%s,'
                   % (a["lat"], a["lon"], js(a["url"]), js(a.get("img") or "")))
        if a["_via"]:
            out.append('      via:{%s}, semana:%d,'
                       % (",".join("%s:%d" % (k, a["_via"][k]) for k in FRECUENCIA if k in a["_via"]),
                          a["_semana"]))
        out.append('      note:%s,' % js(nota(a)))
        out.append('      flags:[%s] },' % fl)
    out[-1] = out[-1][:-1]
    out.append("  ];")
    bloque = "\n".join(out)

    g = ["  var GONE = ["]
    for c in caidos:
        g.append('    [%s,%s,%s,%s],' % (js(c["barrio"]), js(cop(c["canon"] + (c.get("admin") or 0))),
                 js(str(num(c["m2"])).replace(".", ",") + " m²"),
                 js("%d hab · %d parq · %s" % (c["hab"], c["parq"], c["src"]))))
    if len(g) > 1:
        g[-1] = g[-1][:-1]
    g.append("  ];")
    gone = "\n".join(g)

    p = os.path.join(RAIZ, "index.html")
    s = io.open(p, encoding="utf-8").read()

    def swap(txt, ini, nuevo):
        i = txt.index(ini)
        j = txt.index("\n  ];", i) + len("\n  ];")
        return txt[:i] + nuevo + txt[j:]

    s = swap(s, "  var DATA = [", bloque)
    s = swap(s, "  var GONE = [", gone)

    n_asc = sum(1 for a in avisos if a["asc"] == "si")
    n_km = sum(1 for a in avisos if a["km"] < 2)
    con_via = [a for a in avisos if a.get("_semana") is not None]
    mejor = min(con_via, key=lambda a: a["_semana"]) if con_via else None
    tiles = ('  <div class="tiles">\n'
             '    <div class="tile is-key"><div class="n">%d</div><div class="l">candidatos vigentes hoy</div></div>\n'
             '    <div class="tile"><div class="n">%d</div><div class="l">no estaban en el barrido anterior</div></div>\n'
             '    <div class="tile"><div class="n">%d</div><div class="l">con ascensor confirmado en la ficha</div></div>\n'
             '    <div class="tile"><div class="n">%s</div><div class="l">el mejor viaje semanal, solo ida</div></div>\n'
             '  </div>') % (len(avisos), len(nuevos), n_asc,
                            ("%dh%02d" % (mejor["_semana"] // 60, mejor["_semana"] % 60)) if mejor else "n/d")
    s = re.sub(r'  <div class="tiles">.*?\n  </div>', lambda _m: tiles, s, count=1, flags=re.S)

    s = re.sub(r'<div class="eyebrow">[^<]*</div>',
               '<div class="eyebrow">Búsqueda de arriendo · Bogotá norte · 4 portales · actualizado %s</div>' % fecha,
               s, count=1)
    s = re.sub(r"<title>[^<]*</title>",
               "<title>Arriendo Bogotá norte — %d candidatos, %s</title>" % (len(avisos), fecha), s, count=1)
    s = re.sub(r'(<meta name="description" content="[^"]*?)\d+( candidatos[^"]*">)',
               lambda m: m.group(1) + str(len(avisos)) + m.group(2), s, count=1)

    baratos = [a for a in avisos if a["url"] in nuevos and a["canon"] + (a["admin"] or 0) < 3_500_000]
    cerca = [a for a in avisos if a["url"] in nuevos and a["km"] < 2]
    frases = ["El barrido del %s deja <strong>%d candidatos vigentes</strong>: %d que no estaban "
              "en la corrida anterior y %d que se cayeron de los portales."
              % (fecha, len(avisos), len(nuevos), len(caidos))]
    if cerca:
        c = min(cerca, key=lambda a: a["km"])
        frases.append("Entre los nuevos hay uno en <strong>%s a %s km</strong> de tu casa, por %s al mes."
                      % (c["barrio"], ("%.1f" % c["km"]).replace(".", ","),
                         cop(c["canon"] + (c["admin"] or 0))))
    if baratos:
        b = min(baratos, key=lambda a: a["canon"] + (a["admin"] or 0))
        frases.append("El más económico que entró es un %s de %s m² por <strong>%s</strong>."
                      % (b["barrio"], str(num(b["m2"])).replace(".", ","),
                         cop(b["canon"] + (b["admin"] or 0))))
    if not cerca and not baratos:
        frases.append("Ninguno de los nuevos baja de $3.500.000 ni queda a menos de 2 km.")
    frases.append("Solo <strong>%d de %d</strong> declaran ascensor en la ficha: el resto quedan marcados "
                  "como sin confirmar, no como sin ascensor." % (n_asc, len(avisos)))
    if mejor:
        frases.append("En tiempos de viaje, el mejor ubicado es <strong>%s</strong>: %d minutos al colegio "
                      "y %d a la oficina, para un total de %dh%02d por semana solo de ida."
                      % (mejor["barrio"], mejor["_via"]["colegio"], mejor["_via"]["oficina"],
                         mejor["_semana"] // 60, mejor["_semana"] % 60))
    # El bloque .verdict se reescribe entero en cada corrida: si solo se agregara
    # el resumen, los párrafos de corridas viejas quedarían contradiciendo los datos.
    evergreen = (
        "      Los cuatro portales publican el mismo apartamento con precios y datos distintos, así que "
        "cada aviso se deduplica por coordenada y área, no por enlace. La cifra grande de cada ficha es "
        "el <strong>costo mensual total</strong>: en Suba la mayoría incluye la administración en el "
        "canon y en Usaquén casi siempre va aparte, y compararlos por canon llevaría a escoger mal. "
        "Los tiempos de viaje son en carro, con el tráfico previsto por Google para el día y la hora "
        "reales de cada compromiso. El del colegio es referencia comparativa entre apartamentos, no el "
        "tiempo de la ruta escolar, que recoge a otros niños y depende de cuál les asignen.")
    verdict = ('  <div class="verdict">\n    <h2>Qué cambió</h2>\n'
               '    <p id="auto-resumen">\n      ' + " ".join(frases) + "\n    </p>\n"
               "    <p>\n" + evergreen + "\n    </p>\n  </div>")
    s = re.sub(r'  <div class="verdict">.*?\n  </div>', lambda _m: verdict, s, count=1, flags=re.S)

    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("index.html regenerado: %d avisos, %d nuevos, %d caídos, %d con ascensor"
          % (len(avisos), len(nuevos), len(caidos), n_asc))
    if s.count("var DATA = [") != 1 or s.count("var GONE = [") != 1:
        print("AVISO: los marcadores DATA/GONE quedaron duplicados", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
