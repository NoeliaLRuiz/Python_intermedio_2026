"""Arma docs/index.html (para GitHub Pages) a partir de docs/tablero.html.

tablero.html es el contenido de la página sin <html>/<head>/<body>, que es el formato que pide
la publicación como artifact; GitHub Pages necesita el documento completo.
"""
from pathlib import Path

DOCS = Path(__file__).parent
contenido = (DOCS / "tablero.html").read_text(encoding="utf-8")
html = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '</head>\n<body>\n' + contenido + '\n</body>\n</html>\n')
(DOCS / "index.html").write_text(html, encoding="utf-8")
print("Escrito", DOCS / "index.html")
