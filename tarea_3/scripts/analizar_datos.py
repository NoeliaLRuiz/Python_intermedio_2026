"""Paso 3: calcula los indicadores y las cifras de los hallazgos.

Lee datos/procesados, escribe datos/procesados/hallazgos.json e imprime un resumen. Las cifras de
este resumen son las que van en el dashboard, el README, el reel y LinkedIn.

Uso:  python scripts/analizar_datos.py
"""
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROCESADOS = RAIZ / "datos" / "procesados"


def top(tabla, columna, n=5):
    t = tabla.nlargest(n, columna)
    return [{"region": r, columna: round(v, 1)} for r, v in zip(t.region, t[columna])]


def main():
    panel = pd.read_csv(PROCESADOS / "panel_regiones.csv")
    nac = pd.read_csv(PROCESADOS / "nacional.csv").set_index("anio")
    lima = pd.read_csv(PROCESADOS / "denuncias_lima_distritos.csv")
    ultimo = {c: int(panel.dropna(subset=[c]).anio.max()) for c in ["victimizacion", "tasa_homicidios", "tasa_extorsiones"]}
    h = {"ultimo_anio": ultimo}

    # Hallazgo 1. Menos víctimas: la victimización bajó en casi todas las regiones
    vic = panel.pivot(index="region", columns="anio", values="victimizacion")
    a = ultimo["victimizacion"]
    h["h1"] = {"nacional_2010": round(nac.loc[2010, "victimizacion"], 1), "nacional_2011": round(nac.loc[2011, "victimizacion"], 1),
               f"nacional_{a}": round(nac.loc[a, "victimizacion"], 1),
               "regiones_que_bajan_desde_2010": int((vic[a] < vic[2010]).sum()), "regiones": len(vic),
               f"mas_victimizacion_{a}": top(panel[panel.anio == a], "victimizacion")}

    # Hallazgo 2. Más violencia: homicidios, ataques con arma de fuego y extorsión al alza
    hom = panel.pivot(index="region", columns="anio", values="tasa_homicidios")
    b, c = ultimo["tasa_homicidios"], ultimo["tasa_extorsiones"]
    h["h2"] = {"homicidios_2014": int(nac.loc[2014, "homicidios"]), f"homicidios_{b}": int(nac.loc[b, "homicidios"]),
               "tasa_homicidios_2014": round(nac.loc[2014, "tasa_homicidios"], 1),
               f"tasa_homicidios_{b}": round(nac.loc[b, "tasa_homicidios"], 1),
               "regiones_con_mas_homicidios_que_en_2014": int((hom[b] > hom[2014]).sum()),
               "lima_metropolitana_veces": round(hom.loc["Lima Metropolitana", b] / hom.loc["Lima Metropolitana", 2014], 1),
               "arma_fuego_2012": nac.loc[2012, "victimas_arma_fuego"], f"arma_fuego_{a}": round(nac.loc[a, "victimas_arma_fuego"], 1),
               "extorsiones_2018": int(nac.loc[2018, "extorsiones"]), f"extorsiones_{c}": int(nac.loc[c, "extorsiones"]),
               "extorsiones_veces": round(nac.loc[c, "extorsiones"] / nac.loc[2018, "extorsiones"], 1)}

    # Hallazgo 3. Dónde: la violencia grave se concentra en otras regiones que el delito común
    ult_hom, ult_ext = panel[panel.anio == b], panel[panel.anio == c]
    top_hom, top_ext = top(ult_hom, "tasa_homicidios", 6), top(ult_ext, "tasa_extorsiones", 6)
    en_ambos = sorted({r["region"] for r in top_hom} & {r["region"] for r in top_ext})
    cruce = panel[panel.anio == b]
    h["h3"] = {f"top_tasa_homicidios_{b}": top_hom, f"top_tasa_extorsiones_{c}": top_ext,
               "en_ambos_top6": en_ambos,
               f"correlacion_victimizacion_homicidios_{b}": round(cruce.victimizacion.corr(cruce.tasa_homicidios), 2) + 0.0}

    # Extra. Lima Metropolitana: distritos con más denuncias de extorsión por 100 mil habitantes.
    # Se dejan fuera los distritos de menos de 20 mil habitantes: con 2 denuncias ya tendrían una tasa alta.
    ext_lima = lima[(lima.anio == c) & (lima.modalidad == "Extorsión") & (lima.poblacion >= 20_000)].nlargest(5, "tasa")
    h["extra_lima"] = [{"distrito": d, "denuncias": int(n), "tasa": round(t, 1)}
                       for d, n, t in zip(ext_lima.distrito, ext_lima.denuncias, ext_lima.tasa)]

    (PROCESADOS / "hallazgos.json").write_text(json.dumps(h, ensure_ascii=False, indent=2, default=float), encoding="utf-8")

    h1, h2, h3 = h["h1"], h["h2"], h["h3"]
    print("HALLAZGO 1. Menos victimas")
    print(f"  Victimización nacional: {h1['nacional_2010']} % (2010), {h1['nacional_2011']} % (2011), "
          f"{h1[f'nacional_{a}']} % ({a})")
    print(f"  Regiones con menos victimización en {a} que en 2010: {h1['regiones_que_bajan_desde_2010']} de {h1['regiones']}")
    print(f"  Más victimización en {a}: {h1[f'mas_victimizacion_{a}']}")
    print("\nHALLAZGO 2. Mas violencia")
    print(f"  Homicidios: {h2['homicidios_2014']:,} (2014) -> {h2[f'homicidios_{b}']:,} ({b}); tasa "
          f"{h2['tasa_homicidios_2014']} -> {h2[f'tasa_homicidios_{b}']} por 100 mil")
    print(f"  Regiones con más homicidios por habitante que en 2014: {h2['regiones_con_mas_homicidios_que_en_2014']} de 26;"
          f" Lima Metropolitana x{h2['lima_metropolitana_veces']}")
    print(f"  Víctimas atacadas con arma de fuego: {h2['arma_fuego_2012']} % (2012) -> {h2[f'arma_fuego_{a}']} % ({a})")
    print(f"  Denuncias de extorsión: {h2['extorsiones_2018']:,} (2018) -> {h2[f'extorsiones_{c}']:,} ({c}), "
          f"x{h2['extorsiones_veces']}")
    print("\nHALLAZGO 3. Donde")
    print(f"  Tasa de homicidios {b}: {h3[f'top_tasa_homicidios_{b}']}")
    print(f"  Tasa de extorsiones {c}: {h3[f'top_tasa_extorsiones_{c}']}")
    print(f"  En los dos primeros 6: {h3['en_ambos_top6']}")
    print(f"  Correlación entre victimización y tasa de homicidios ({b}): {h3[f'correlacion_victimizacion_homicidios_{b}']}")
    print(f"\nEXTRA. Lima Metropolitana, extorsión {c} por 100 mil: {h['extra_lima']}")


if __name__ == "__main__":
    main()