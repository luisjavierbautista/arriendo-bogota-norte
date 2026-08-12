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
    if a.get("admin") is None:
        f.append(("El aviso no informa la administración.", "crit"))
    if a["km"] < 2:
        f.append(("A %s km de tu casa actual." % ("%.1f" % a["km"]).replace(".", ","), "ok"))
    if a["asc"] == "si":
        f.append(("Ascensor confirmado en la ficha.", "ok"))
    if a["canon"] + (a["admin"] or 0) >= 4_450_000:
        f.append(("Queda en el tope de $4.500.000.", "warn"))
    return f


def main():
    d = json.load(io.open(os.path.join(RAIZ, "data.json"), encoding="utf-8"))
    avisos, caidos = d["avisos"], d.get("caidos", [])
    nuevos = set(d.get("nuevos", []))
    gen = d.get("generado", "")
    try:
        y, m, day = gen.split("-")
        fecha = "%d %s %s" % (int(day), MESES[int(m) - 1], y)
    except Exception:
        fecha = gen

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
    tiles = ('  <div class="tiles">\n'
             '    <div class="tile is-key"><div class="n">%d</div><div class="l">candidatos vigentes hoy</div></div>\n'
             '    <div class="tile"><div class="n">%d</div><div class="l">no estaban en el barrido anterior</div></div>\n'
             '    <div class="tile"><div class="n">%d</div><div class="l">a menos de 2 km de tu casa actual</div></div>\n'
             '    <div class="tile"><div class="n">%d</div><div class="l">con ascensor confirmado en la ficha</div></div>\n'
             '  </div>') % (len(avisos), len(nuevos), n_km, n_asc)
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
    # El bloque .verdict se reescribe entero en cada corrida: si solo se agregara
    # el resumen, los párrafos de corridas viejas quedarían contradiciendo los datos.
    evergreen = (
        "      Los cuatro portales publican el mismo apartamento con precios y datos distintos, así que "
        "cada aviso se deduplica por coordenada y área, no por enlace. La cifra grande de cada ficha es "
        "el <strong>costo mensual total</strong>: en Suba la mayoría incluye la administración en el "
        "canon y en Usaquén casi siempre va aparte, y compararlos por canon llevaría a escoger mal.")
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
