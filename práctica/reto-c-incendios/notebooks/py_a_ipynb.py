"""Convierte un script con celdas «# %%» en un notebook .ipynb."""
import re
import sys
from pathlib import Path

import nbformat

origen = Path(sys.argv[1])
celdas = []
for bloque in re.split(r"^# %%", origen.read_text(encoding="utf-8"), flags=re.M)[1:]:
    cabecera, _, cuerpo = bloque.partition("\n")
    if "[markdown]" in cabecera:
        texto = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in cuerpo.strip().splitlines())
        celdas.append(nbformat.v4.new_markdown_cell(texto))
    else:
        celdas.append(nbformat.v4.new_code_cell(cuerpo.strip()))
nb = nbformat.v4.new_notebook(cells=celdas, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"}})
nbformat.write(nb, origen.with_suffix(".ipynb"))
print("Escrito", origen.with_suffix(".ipynb"), len(celdas), "celdas")
