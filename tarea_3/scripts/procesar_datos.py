"""Paso 2: limpia los archivos originales y arma las tablas del análisis y del dashboard.

Lee datos/originales y escribe en datos/procesados:
  panel_regiones.csv           una fila por región y año (2010-2025): victimización, homicidios, extorsión…
  nacional.csv                 lo mismo para el total del país
  denuncias_regiones.csv       denuncias por región, año y modalidad, con su tasa por 100 mil habitantes
  denuncias_mensual.csv        denuncias del país por mes y modalidad (enero 2018 a setiembre 2026)
  denuncias_lima_distritos.csv denuncias en los 43 distritos de Lima Metropolitana, por año y modalidad
y en web/data: datos.json, regiones.geojson y lima_distritos.geojson, listos para la página.

Uso:  python scripts/procesar_datos.py
"""
import json
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
ORIGINALES = RAIZ / "datos" / "originales"
PROCESADOS = RAIZ / "datos" / "procesados"
WEB = RAIZ / "web" / "data"
ULTIMO_ANIO = 2025          # 2026 está incompleto: solo entra en la serie mensual

# Las 26 regiones con el código que usa el Mininter: departamentos 1 a 25 (sin el 15), Lima Metropolitana
# (1501, la provincia de Lima) y Región Lima (1599, las otras 9 provincias del departamento de Lima).
REGIONES = {
    1: "Amazonas", 2: "Áncash", 3: "Apurímac", 4: "Arequipa", 5: "Ayacucho", 6: "Cajamarca", 7: "Callao",
    8: "Cusco", 9: "Huancavelica", 10: "Huánuco", 11: "Ica", 12: "Junín", 13: "La Libertad", 14: "Lambayeque",
    1501: "Lima Metropolitana", 1599: "Región Lima", 16: "Loreto", 17: "Madre de Dios", 18: "Moquegua",
    19: "Pasco", 20: "Piura", 21: "Puno", 22: "San Martín", 23: "Tacna", 24: "Tumbes", 25: "Ucayali",
}

# Indicadores del Mininter que se usan (ver el diccionario). En homicidios, extorsión y secuestro la
# columna VALORES es el número de casos y VALORES_2 la tasa; en el resto, VALORES_2 es el valor final.
INDICADORES = {
    10: ("victimizacion", "VALORES_2"),          # % de personas de 15 años a más víctimas de algún delito (ENAPRES)
    11: ("victimas_arma_fuego", "VALORES_2"),    # % de víctimas atacadas con arma de fuego (ENAPRES, urbano)
    30: ("homicidios", "VALORES"),               # número de homicidios (CEIC)
    7: ("extorsiones", "VALORES"),               # denuncias de extorsión (SIDPOL)
    8: ("secuestros", "VALORES"),                # denuncias de secuestro (SIDPOL)
    31: ("feminicidios", "VALORES_2"),           # número de feminicidios
}
MODALIDADES = {"Violencia contra la mujer e integrantes": "Violencia contra la mujer y el grupo familiar"}


def codigo_region(ubigeo):
    """Código de región a partir del ubigeo del distrito: 150132 → 1501 (Lima Metropolitana),
    150501 → 1599 (Región Lima), 70101 → 7 (Callao)."""
    departamento, provincia = ubigeo // 10000, ubigeo // 100
    if provincia == 1501:
        return 1501
    return 1599 if departamento == 15 else departamento


def leer_indicadores():
    ind = pd.read_csv(ORIGINALES / "mininter_indicadores_2009_ago2026.csv", encoding="utf-8-sig")
    ind = ind[ind.AMBITO.isin([0, 1]) & (ind.ANIO <= ULTIMO_ANIO)]
    tablas = []
    for codigo, (nombre, columna) in INDICADORES.items():
        t = ind[ind.INDICADOR == codigo][["UBIGEO_DASH", "ANIO", columna]].rename(columns={columna: nombre})
        tablas.append(t.set_index(["UBIGEO_DASH", "ANIO"]))
    # La población proyectada es la misma en todos los indicadores de una región y año
    poblacion = ind.groupby(["UBIGEO_DASH", "ANIO"]).POBLACION_PROYECTADA.max().rename("poblacion")
    panel = pd.concat(tablas + [poblacion], axis=1).reset_index().rename(columns={"UBIGEO_DASH": "codigo", "ANIO": "anio"})
    panel = panel[panel.anio >= 2010]
    for caso in ["homicidios", "extorsiones", "secuestros"]:
        panel[f"tasa_{caso}"] = panel[caso] / panel.poblacion * 100_000      # por 100 mil habitantes
    panel["region"] = panel.codigo.map(REGIONES).fillna("Perú")
    columnas = ["codigo", "region", "anio", "poblacion", "victimizacion", "victimas_arma_fuego", "homicidios",
                "tasa_homicidios", "extorsiones", "tasa_extorsiones", "secuestros", "tasa_secuestros", "feminicidios"]
    return panel[columnas].sort_values(["codigo", "anio"])


def leer_denuncias(poblacion):
    den = pd.read_csv(ORIGINALES / "mininter_denuncias_2018_2026.csv")
    print(f"Denuncias: {len(den):,} filas, {den.cantidad.sum():,} denuncias")
    # Limpieza: nombres de modalidad, filas repetidas y región según el ubigeo del distrito
    den["modalidad"] = den.P_MODALIDADES.replace(MODALIDADES)
    llave = ["ANIO", "MES", "UBIGEO_HECHO", "DIST_HECHO", "modalidad"]
    print(f"  filas repetidas (misma fecha, distrito y modalidad), se suman: {den.duplicated(llave).sum()}")
    den = den.groupby(llave, as_index=False).cantidad.sum()
    den["codigo"] = den.UBIGEO_HECHO.map(codigo_region)
    assert den.codigo.isin(REGIONES).all(), "Hay ubigeos que no corresponden a ninguna región"

    mensual = (den.groupby(["ANIO", "MES", "modalidad"], as_index=False).cantidad.sum()
               .rename(columns={"ANIO": "anio", "MES": "mes", "cantidad": "denuncias"}))

    anual = den[den.ANIO <= ULTIMO_ANIO]
    regiones = (anual.groupby(["codigo", "ANIO", "modalidad"], as_index=False).cantidad.sum()
                .rename(columns={"ANIO": "anio", "cantidad": "denuncias"})
                .merge(poblacion, on=["codigo", "anio"], how="left"))
    assert regiones.poblacion.notna().all(), "Falta la población de alguna región"
    regiones["tasa"] = regiones.denuncias / regiones.poblacion * 100_000
    regiones["region"] = regiones.codigo.map(REGIONES)

    lima = (anual[anual.codigo == 1501].groupby(["UBIGEO_HECHO", "DIST_HECHO", "ANIO", "modalidad"], as_index=False)
            .cantidad.sum().rename(columns={"UBIGEO_HECHO": "ubigeo", "DIST_HECHO": "distrito",
                                            "ANIO": "anio", "cantidad": "denuncias"}))
    return mensual, regiones, lima


def poblacion_distritos():
    """Población de los distritos de Lima Metropolitana, tomada del indicador 2 (tiene todos los distritos)."""
    ind = pd.read_csv(ORIGINALES / "mininter_indicadores_2009_ago2026.csv", encoding="utf-8-sig")
    d = ind[(ind.AMBITO == 3) & (ind.INDICADOR == 2) & (ind.UBIGEO_DASH // 100 == 1501)]
    return d[["UBIGEO_DASH", "ANIO", "POBLACION_PROYECTADA"]].rename(
        columns={"UBIGEO_DASH": "ubigeo", "ANIO": "anio", "POBLACION_PROYECTADA": "poblacion"})

def sin_tildes(texto):
    """'Breña ' → 'BRENA': mayúsculas, sin tildes ni espacios de más, para unir nombres de dos fuentes."""
    return " ".join(unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper().split())


def armar_mapas(distritos_lima):
    """Mapa de las 26 regiones (se unen las provincias) y mapa de los 43 distritos de Lima Metropolitana."""
    prov = gpd.read_file(ORIGINALES / "peru_provincial_simple.geojson")
    prov["codigo"] = prov.FIRST_IDPR.astype(int).map(lambda p: codigo_region(p * 100 + 1))
    regiones = prov.dissolve(by="codigo", as_index=False)[["codigo", "geometry"]]
    regiones["region"] = regiones.codigo.map(REGIONES)
    regiones["geometry"] = regiones.geometry.simplify(0.005, preserve_topology=True)
    assert set(regiones.codigo) == set(REGIONES), "Al mapa le falta alguna región"

    # El mapa de distritos del IGN no trae ubigeo: se une por el nombre con los distritos de las denuncias
    dist = gpd.read_file(ORIGINALES / "lima_callao_distritos.geojson")
    lima = dist[dist.provincia == "LIMA"].copy()
    lima["clave"] = lima.distrito.map(sin_tildes).replace({"LURIGANCHO": "LURIGANCHO - CHOSICA"})
    nombres = distritos_lima[["ubigeo", "distrito"]].drop_duplicates()
    nombres["clave"] = nombres.distrito.map(sin_tildes)
    lima = lima[["clave", "geometry"]].merge(nombres, on="clave", how="left")[["ubigeo", "distrito", "geometry"]]
    assert len(lima) == 43 and lima.ubigeo.notna().all(), "Algún distrito de Lima no se pudo unir por su nombre"
    lima["geometry"] = lima.geometry.simplify(0.0005, preserve_topology=True)
    return regiones, lima


def registros(tabla):
    """Tabla → lista de diccionarios para JSON, con None donde falta el dato."""
    return json.loads(tabla.round(2).to_json(orient="records", force_ascii=False))


def main():
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    panel = leer_indicadores()
    nacional, panel = panel[panel.codigo == 0], panel[panel.codigo != 0]
    assert panel.codigo.nunique() == 26 and not panel.duplicated(["codigo", "anio"]).any()
    print(f"Indicadores: 26 regiones, {panel.anio.min()}-{panel.anio.max()}")

    mensual, den_regiones, lima = leer_denuncias(panel[["codigo", "anio", "poblacion"]])
    lima = lima.merge(poblacion_distritos(), on=["ubigeo", "anio"], how="left")
    assert lima.poblacion.notna().all(), "Falta la población de algún distrito de Lima"
    lima["tasa"] = lima.denuncias / lima.poblacion * 100_000

    # Revisión cruzada: las extorsiones de la base de denuncias deben parecerse a las del indicador oficial
    ext = den_regiones[den_regiones.modalidad == "Extorsión"].groupby("anio").denuncias.sum()
    dif = (ext / nacional.set_index("anio").extorsiones - 1).dropna() * 100
    print(f"  extorsiones: diferencia entre las dos bases del Mininter, de {dif.min():.1f} % a {dif.max():.1f} %")

    mapa_regiones, mapa_lima = armar_mapas(lima)

    panel.to_csv(PROCESADOS / "panel_regiones.csv", index=False, encoding="utf-8")
    nacional.to_csv(PROCESADOS / "nacional.csv", index=False, encoding="utf-8")
    den_regiones.to_csv(PROCESADOS / "denuncias_regiones.csv", index=False, encoding="utf-8")
    mensual.to_csv(PROCESADOS / "denuncias_mensual.csv", index=False, encoding="utf-8")
    lima.to_csv(PROCESADOS / "denuncias_lima_distritos.csv", index=False, encoding="utf-8")

    web = {
        "fuentes": json.loads((ORIGINALES / "fuentes.json").read_text(encoding="utf-8")),
        "regiones": REGIONES,
        "panel": registros(panel),
        "nacional": registros(nacional),
        "denuncias_regiones": registros(den_regiones.drop(columns="poblacion")),
        "denuncias_mensual": registros(mensual),
        "denuncias_lima": registros(lima.drop(columns="poblacion")),
    }
    (WEB / "datos.json").write_text(json.dumps(web, ensure_ascii=False), encoding="utf-8")
    mapa_regiones.to_file(WEB / "regiones.geojson", driver="GeoJSON")
    mapa_lima.to_file(WEB / "lima_distritos.geojson", driver="GeoJSON")
    print("Listo: tablas en datos/procesados y archivos para la web en web/data")


if __name__ == "__main__":
    main()