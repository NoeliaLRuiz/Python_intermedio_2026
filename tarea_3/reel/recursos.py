"""Paso 1 del reel: prepara el fondo, los gráficos y la música.

1. Fondo (1080 x 1920): degradado azul oscuro con la silueta del Perú muy tenue → reel/recursos/fondo.png
2. Gráficos: abre reel/graficos.html (los mismos datos del dashboard, en grande) con Microsoft Edge y guarda
   cada gráfico de 1000 x 650 con fondo transparente → reel/recursos/graficos/<nombre>.png
3. Portada: una captura real del dashboard (título e indicadores) → reel/recursos/graficos/portada.png
4. Música: los primeros 90 segundos de «Lightless Dawn» (Kevin MacLeod, CC BY 4.0) → reel/recursos/musica.mp3

Uso, desde la carpeta tarea_3:  python reel/recursos.py
"""
import functools
import http.server
import json
import subprocess
import threading
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
TAREA = AQUI.parent
RECURSOS = AQUI / "recursos"
GRAFICOS = RECURSOS / "graficos"
MUSICA = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Lightless%20Dawn.mp3"
W, H = 1080, 1920
GRAFICOS_DEL_REEL = ["mapa_portada", "victimizacion", "homicidios", "arma_fuego", "extorsion_anual", "cuatro_regiones",
                     "dos_mapas"]


def armar_fondo():
    """Degradado del azul del dashboard (arriba) a casi negro (abajo), con el mapa del Perú en línea tenue."""
    arriba, abajo = np.array([16, 52, 104]), np.array([6, 10, 22])
    t = np.linspace(0, 1, H)[:, None, None]
    lienzo = ((1 - t) * arriba + t * abajo).repeat(W, axis=1).astype("uint8")
    fondo = Image.fromarray(lienzo, "RGB")
    regiones = json.loads((TAREA / "web" / "data" / "regiones.geojson").read_text(encoding="utf-8"))
    # Mapa grande y desplazado a la derecha: de longitud -81,5 a -68,5 y de latitud 0,5 a -18,5
    a_pixel = lambda lon, lat: (180 + (lon + 81.5) / 13 * 1250, 260 + (0.5 - lat) / 19 * 1750)
    capa = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(capa)
    for f in regiones["features"]:
        g = f["geometry"]
        poligonos = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for p in poligonos:
            d.line([a_pixel(*c) for c in p[0]], fill=255, width=3)
    capa = capa.filter(ImageFilter.GaussianBlur(1))
    blanco = Image.new("RGB", (W, H), (120, 170, 235))
    fondo = Image.composite(blanco, fondo, capa.point(lambda v: v * 0.10))     # 10 % de opacidad
    fondo.save(RECURSOS / "fondo.png")
    print("  fondo listo: fondo.png")


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):       # no muestra cada archivo que pide el navegador
        pass


def servidor_local():
    """Sirve la carpeta tarea_3 en http://localhost:<puerto> (el navegador necesita un servidor para leer los datos)."""
    manejador = functools.partial(Silencioso, directory=str(TAREA))
    servidor = http.server.ThreadingHTTPServer(("localhost", 0), manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://localhost:{servidor.server_address[1]}"


def capturar(url):
    GRAFICOS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(channel="msedge")      # usa el Edge instalado en Windows
        pagina = navegador.new_page(viewport={"width": 1000, "height": 650})
        for nombre in GRAFICOS_DEL_REEL:
            pagina.goto(f"{url}/reel/graficos.html?grafico={nombre}", wait_until="networkidle")
            pagina.wait_for_selector("body[data-listo='1']")
            pagina.locator("#grafico").screenshot(path=GRAFICOS / f"{nombre}.png", omit_background=True)
            print(f"  gráfico listo: {nombre}.png")
        # Portada: el dashboard en modo oscuro, del título a los 4 indicadores
        ancha = navegador.new_page(viewport={"width": 1100, "height": 1000}, color_scheme="dark")
        ancha.goto(f"{url}/web/", wait_until="networkidle")
        ancha.wait_for_selector("#grafico-mapa .main-svg")
        ancha.wait_for_timeout(1500)                      # espera a que terminen las animaciones de entrada
        fin = ancha.locator("#kpis").bounding_box()
        captura = GRAFICOS / "_portada.png"
        ancha.screenshot(path=captura, clip={"x": 0, "y": 0, "width": 1100, "height": fin["y"] + fin["height"] + 12})
        img = Image.open(captura)
        img.thumbnail((1000, 390), Image.LANCZOS)
        img.save(GRAFICOS / "portada.png")
        captura.unlink()
        print("  captura lista: portada.png")
        navegador.close()


def preparar_musica():
    destino = RECURSOS / "musica.mp3"
    if destino.exists():
        print("  ya existe: musica.mp3")
        return
    completa = RECURSOS / "_musica_completa.mp3"
    respuesta = requests.get(MUSICA, headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
    respuesta.raise_for_status()
    completa.write_bytes(respuesta.content)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(completa),
                    "-t", "90", "-b:a", "128k", str(destino)], check=True)
    completa.unlink()
    print("  música lista: musica.mp3 (90 s de «Lightless Dawn», Kevin MacLeod, CC BY 4.0)")


def main():
    RECURSOS.mkdir(parents=True, exist_ok=True)
    armar_fondo()
    servidor, url = servidor_local()
    try:
        capturar(url)
    finally:
        servidor.shutdown()
    preparar_musica()


if __name__ == "__main__":
    main()