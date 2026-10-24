"""Fondos verticales (1080 x 1920) para el reel, hechos con los datos del Reto C.

Se corre con el entorno del reto, que tiene geopandas:
    ..\\reto-c-incendios\\.venv\\Scripts\\python fondos.py

Deja en fondos/: focos.png, cobertura.png, bomberos.png, edificios.png, ayuda.png y rio_tambo.png.
El mapa ocupa la franja central; arriba van la cifra y abajo los subtítulos.
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

RETO = Path(__file__).parent.parent / "reto-c-incendios"
SALIDA = Path(__file__).parent / "fondos"
SALIDA.mkdir(exist_ok=True)

FONDO, BORDE, TENUE = "#0e1311", "#3b4842", "#202a25"
COBERTURA = {"Pastizal": "#f2cf5b", "Bosque": "#4fbf5a", "Matorral": "#c9a93a", "Suelo desnudo": "#b9a58f",
             "Cultivo": "#ff5fa2", "Agua": "#4aa3ff"}
TRAMOS = {"≤ 10 km": "#4f8dff", "10 a 30 km": "#e0b54a", "30 a 60 km": "#ff7a2f", "más de 60 km": "#ff3b3b"}

deps = gpd.read_file(RETO / "data/raw/peru_departamental_simple.geojson")
inc = gpd.read_file(RETO / "data/processed/incendios_100ha.geojson")
inc["x"], inc["y"] = inc.geometry.centroid.x, inc.geometry.centroid.y
bomberos = pd.DataFrame([{"lon": e.get("lon", e.get("center", {}).get("lon")), "lat": e.get("lat", e.get("center", {}).get("lat"))}
                         for e in json.loads((RETO / "data/raw/bomberos_osm.json").read_text(encoding="utf-8"))["elements"]])
ayuda = pd.read_csv(RETO / "data/perupendiente_totales.csv").groupby("departamento").total_publicado.sum()


def lienzo():
    fig = plt.figure(figsize=(10.8, 19.2), dpi=100, facecolor=FONDO)
    ax = fig.add_axes([0.0, 0.17, 1.0, 0.6])  # franja central de la pantalla
    ax.set_facecolor(FONDO)
    ax.set_axis_off()
    return fig, ax


def base(ax, colores=None):
    deps.plot(ax=ax, color=colores if colores is not None else TENUE, edgecolor=BORDE, linewidth=0.8)
    ax.set_xlim(-81.6, -68.4)
    ax.set_ylim(-18.6, 0.2)


def guardar(fig, nombre):
    fig.savefig(SALIDA / nombre, facecolor=FONDO)
    plt.close(fig)
    print("listo", SALIDA / nombre)


def brillo(ax, x, y, tam, color):
    """Puntos con halo: tres capas del mismo punto, de grande y tenue a chico y fuerte."""
    for escala, alfa in [(5, 0.06), (2.2, 0.18), (1, 0.9)]:
        ax.scatter(x, y, s=tam * escala, color=color, alpha=alfa, linewidths=0)


tam = np.sqrt(inc.huella_ha) * 4

fig, ax = lienzo(); base(ax)
brillo(ax, inc.x, inc.y, tam, "#ff7a1a")
guardar(fig, "focos.png")

fig, ax = lienzo(); base(ax)
for clase, color in COBERTURA.items():
    sub = inc[inc.cobertura_principal == clase]
    brillo(ax, sub.x, sub.y, tam[sub.index], color)
guardar(fig, "cobertura.png")

fig, ax = lienzo(); base(ax)
for tramo, color in TRAMOS.items():
    sub = inc[inc.tramo_bomberos == tramo]
    brillo(ax, sub.x, sub.y, tam[sub.index], color)
ax.scatter(bomberos.lon, bomberos.lat, marker="^", s=70, color="white", linewidths=0)
guardar(fig, "bomberos.png")

fig, ax = lienzo(); base(ax)
ax.scatter(inc.x, inc.y, s=tam, color="#ff7a1a", alpha=0.25, linewidths=0)
con = inc.dropna(subset=["edif_1km"])  # el GeoJSON ya trae las edificaciones de los 20 más grandes
brillo(ax, con.x, con.y, np.sqrt(con.edif_1km) * 22, "#58a6ff")
guardar(fig, "edificios.png")

fig, ax = lienzo()
alfa = deps.NOMBDEP.map(ayuda).fillna(0) / ayuda.max()
colores = [matplotlib.colors.to_hex(np.array(matplotlib.colors.to_rgb("#f2c94c")) * a + np.array(matplotlib.colors.to_rgb(TENUE)) * (1 - a))
           if a > 0 else TENUE for a in alfa]
base(ax, colores)
ax.scatter(inc.x, inc.y, s=tam * 0.6, color="#ff7a1a", alpha=0.55, linewidths=0)
guardar(fig, "ayuda.png")

# Río Tambo: imagen Sentinel-2 de después con el contorno quemado, recortada a vertical
img = Image.open(RETO / "docs/img/rt_despues.jpg").convert("RGB")
capa = Image.open(RETO / "docs/img/rt_contorno.png").convert("RGBA").resize(img.size)
img = Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB")
escala = 1920 / img.height
img = img.resize((round(img.width * escala), 1920), Image.LANCZOS)
arr = np.asarray(img).copy()
fuera = (arr.min(axis=2) >= 230) & (arr.max(axis=2) - arr.min(axis=2) < 4)  # el gris muy claro de fuera de la zona
arr[fuera] = (14, 19, 17)
img = Image.fromarray(arr)
izq = (img.width - 1080) // 2
img.crop((izq, 0, izq + 1080, 1920)).save(SALIDA / "rio_tambo.png")
print("listo", SALIDA / "rio_tambo.png")
