"""La figura del informe: cuántas cifras acertó Claude en cada modo y cuánto tardó.

    uv run grafico.py          # lee resultados.csv y resultados_sin_salida.csv, escribe grafico.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent
SUPERFICIE, TEXTO, TEXTO_2, GRILLA = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLOR = {"acierta": "#2a78d6", "no sabe": "#eb6834", "se equivoca": "#e34948"}
NEUTRO = "#9a9993"
ETIQUETA = {"acierta": "aciertos", "no sabe": "«no sé»", "se equivoca": "errores"}

res = pd.concat([pd.read_csv(AQUI / "resultados.csv").assign(corrida=""),
                 pd.read_csv(AQUI / "resultados_sin_salida.csv").assign(corrida=" · sin permiso de «no sé»")])
res["fila"] = res.modo.map({"memoria": "Solo memoria", "mcp": "Con el MCP"}) + res.corrida
orden = ["Solo memoria", "Solo memoria · sin permiso de «no sé»", "Con el MCP", "Con el MCP · sin permiso de «no sé»"]
conteo = res.groupby("fila").resultado.value_counts().unstack(fill_value=0).reindex(orden)
segundos = res.groupby("fila").segundos.mean().reindex(orden)
n = int(conteo.iloc[0].sum())

plt.rcParams.update({"font.size": 10, "text.color": TEXTO, "axes.labelcolor": TEXTO_2,
                     "xtick.color": TEXTO_2, "ytick.color": TEXTO})
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.9), width_ratios=[1.6, 1], sharey=True, facecolor=SUPERFICIE)
y = range(len(orden))[::-1]

izquierda = pd.Series(0, index=orden)
for r in ["acierta", "se equivoca", "no sabe"]:
    if r not in conteo:
        continue
    a.barh(y, conteo[r], left=izquierda, height=0.55, color=COLOR[r], edgecolor=SUPERFICIE, linewidth=2,
           label=ETIQUETA[r].capitalize().replace("«n", "«N"))
    for yi, (v, x0) in zip(y, zip(conteo[r], izquierda)):
        if v:
            a.text(x0 + v / 2, yi, f"{v} {ETIQUETA[r]}", ha="center", va="center", color=TEXTO, fontweight="bold")
    izquierda += conteo[r]
a.set_xlim(0, n)
a.set_title(f"Respuestas a las {n} preguntas", loc="left", fontweight="bold")
a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncols=3, frameon=False)

b.barh(y, segundos, height=0.55, color=NEUTRO)
for yi, s in zip(y, segundos):
    b.text(s + 0.4, yi, f"{s:.1f} s", va="center", color=TEXTO)
b.set_xlim(0, segundos.max() * 1.25)
b.set_title("Segundos por pregunta", loc="left", fontweight="bold")

for ax in (a, b):
    ax.set_facecolor(SUPERFICIE)
    ax.set_yticks(list(y), orden)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ax.spines.values():
        lado.set_visible(False)
a.set_xticks([])
b.set_xticks([])

fig.suptitle("Con el MCP, Claude acertó las 10 cifras del presupuesto; sin él, no dio ninguna",
             x=0.01, ha="left", fontsize=13, fontweight="bold")
fig.text(0.01, 0.885, "10 preguntas sobre la ejecución 2025 (Consulta Amigable del MEF) · Claude Haiku · "
         "ninguna respuesta equivocada", color=TEXTO_2)
fig.text(0.01, 0.02, "Fuente: resultados.csv y resultados_sin_salida.csv, generados con evaluar.py el 28-10-2026.",
         color=TEXTO_2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.05, 0.98, 0.88))
fig.savefig(AQUI / "grafico.png", dpi=200, facecolor=SUPERFICIE)
print("grafico.png listo")
