"""Paso 1: descarga los datos originales y anota de dónde viene cada archivo.

Si un archivo ya está en datos/originales, no se vuelve a descargar. Así, correr el proyecto otra vez
da los mismos resultados. Para actualizar un archivo, bórralo y vuelve a correr este script.

Uso:  python scripts/obtener_datos.py
"""
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
ORIGINALES = RAIZ / "datos" / "originales"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
PORTAL = "https://www.datosabiertos.gob.pe/sites/default/files/"
MAPAS = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/"

FUENTES = {
    "mininter_denuncias_2018_2026.csv": (
        PORTAL + "DATASET_Denuncias%20Policiales%20-%20Enero%202018%20a%20Septiembre%202026.csv",
        "MININTER. Denuncias policiales registradas en el SIDPOL por año, mes, distrito y modalidad, "
        "enero 2018 a setiembre 2026. https://www.datosabiertos.gob.pe/dataset/denuncias-policiales-registradas-nivel-nacional-mininter"),
    "mininter_denuncias_diccionario.xlsx": (
        PORTAL + "DICCIONARIO_DATOS_Denuncias_Policiales_Abr%202026.xlsx",
        "MININTER. Diccionario de datos de las denuncias policiales"),
    "mininter_indicadores_diccionario.xlsx": (
        PORTAL + "DICCIONAR_DATOS_%20Ind_%20Plan_Acc_Seg_Ciud_Jun%202026.xlsx",
        "MININTER. Diccionario de los indicadores de seguridad ciudadana (códigos de indicador y de ubigeo)"),
    "peru_provincial_simple.geojson": (
        MAPAS + "peru_provincial_simple.geojson",
        "Límites provinciales del Perú (github.com/juaneladio/peru-geojson, licencia MPL-2.0)"),
    "peru_distrital_simple.geojson": (
        MAPAS + "peru_distrital_simple.geojson",
        "Límites distritales del Perú (github.com/juaneladio/peru-geojson, licencia MPL-2.0)"),
}

# Los indicadores vienen en un ZIP con un CSV por mes de actualización; se guarda solo el más reciente.
INDICADORES_ZIP = PORTAL + ("DataSet%20Indicadores%20para%20Planes%20de%20Acci%C3%B3n%20de%20Seguridad"
                            "%20Ciudadana%20-%20Agosto%202026.zip")
INDICADORES_CSV = "DATASET_Ind_Plan_Acc_Seg_Ciud_2009 a Ago. 2026.csv"
INDICADORES = "mininter_indicadores_2009_ago2026.csv"


def descargar(url):
    respuesta = requests.get(url, headers=NAVEGADOR, timeout=300)
    respuesta.raise_for_status()
    return respuesta.content


def main():
    ORIGINALES.mkdir(parents=True, exist_ok=True)
    registro_ruta = ORIGINALES / "fuentes.json"
    registro = json.loads(registro_ruta.read_text(encoding="utf-8")) if registro_ruta.exists() else {}
    hoy = date.today().isoformat()

    print("Descargando archivos (el de denuncias pesa unos 28 MB):")
    for nombre, (url, descripcion) in FUENTES.items():
        destino = ORIGINALES / nombre
        if destino.exists():
            print(f"  ya existe: {nombre}")
        else:
            destino.write_bytes(descargar(url))
            print(f"  descargado: {nombre} ({destino.stat().st_size / 1024:,.0f} KB)")
            registro[nombre] = {"url": url, "descripcion": descripcion, "fecha_descarga": hoy}

    destino = ORIGINALES / INDICADORES
    if destino.exists():
        print(f"  ya existe: {INDICADORES}")
    else:
        with zipfile.ZipFile(io.BytesIO(descargar(INDICADORES_ZIP))) as zf:
            nombre_en_zip = next(n for n in zf.namelist() if n.endswith(INDICADORES_CSV))
            destino.write_bytes(zf.read(nombre_en_zip))
        print(f"  descargado: {INDICADORES} ({destino.stat().st_size / 1024:,.0f} KB)")
        registro[INDICADORES] = {
            "url": INDICADORES_ZIP, "fecha_descarga": hoy,
            "descripcion": "MININTER. Indicadores de seguridad ciudadana por región, provincia y distrito, "
                           "2009 a agosto 2026 (victimización ENAPRES, homicidios CEIC, denuncias SIDPOL y otros). "
                           "https://www.datosabiertos.gob.pe/dataset/indicadores-de-seguridad-ciudadana-y-tendencias-territoriales-mininter"}

    registro_ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo. Fuentes anotadas en {registro_ruta.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()