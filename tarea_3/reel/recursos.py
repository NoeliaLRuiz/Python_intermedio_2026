"""Paso 1 del reel: prepara las imágenes y la música.

1. Abre el dashboard publicado con Microsoft Edge (Playwright), elige los filtros de cada escena, fotografía
   el gráfico y lo centra sobre un fondo oscuro de 1080 x 1920. Guarda un PNG por escena en reel/recursos/fondos/.
2. Descarga la música (Kevin MacLeod, licencia CC BY 4.0) y guarda sus primeros 90 segundos en reel/recursos/musica.mp3.

Uso:  python reel/recursos.py            (o --url http://localhost:8000 para usar la versión local)
"""
import argparse
import subprocess
from pathlib import Path

import imageio_ffmpeg
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RECURSOS = AQUI / "recursos"
FONDOS = RECURSOS / "fondos"
URL = "https://noelialruiz.github.io/Python_intermedio_2026/tarea_3/web/"
MUSICA = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Lightless%20Dawn.mp3"
W, H = 1080, 1920
FONDO = (13, 13, 13)                  # el mismo negro de la página en modo oscuro
CAJA = (40, 700, 1040, 1350)          # zona libre entre la cifra (arriba) y los subtítulos (abajo)
CAJA_PORTADA = (40, 700, 1040, 1090)  # en la última escena, debajo van los créditos

# Escena → (filtros que se eligen en la página, qué se fotografía)
CAPTURAS = {
    "victimizacion": ({}, "#ev-victimizacion"),
    "homicidios": ({"#filtro-indicador": "tasa_homicidios", "#filtro-anio": "2024"}, "#grafico-mapa"),
    "arma_fuego": ({}, "#ev-victimas_arma_fuego"),
    "extorsion_mes": ({"#filtro-modalidad": "Extorsión"}, "#grafico-mensual"),
    "extorsion_mapa": ({"#filtro-indicador": "tasa_extorsiones", "#filtro-anio": "2025"}, "#grafico-mapa"),
    "dos_mapas": ({"#filtro-anio": "2024"}, "#grafico-cruce"),
    "portada": ({}, "portada"),
}


def componer(captura, destino, caja):
    """Centra la captura dentro de la caja, sin deformarla, sobre el fondo oscuro."""
    img = Image.open(captura).convert("RGB")
    x0, y0, x1, y1 = caja
    escala = min((x1 - x0) / img.width, (y1 - y0) / img.height)
    img = img.resize((round(img.width * escala), round(img.height * escala)), Image.LANCZOS)
    lienzo = Image.new("RGB", (W, H), FONDO)
    lienzo.paste(img, (x0 + (x1 - x0 - img.width) // 2, y0 + (y1 - y0 - img.height) // 2))
    lienzo.save(destino)


def capturar_fondos(url):
    FONDOS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(channel="msedge")      # usa el Edge instalado en Windows
        # Ventana angosta (como un celular grande) y escala 2: cada gráfico ocupa ~1000 px de ancho.
        # La portada se toma en una ventana ancha, para que el título y los 4 indicadores entren a lo ancho.
        angosta = navegador.new_page(viewport={"width": 540, "height": 1200}, device_scale_factor=2,
                                     color_scheme="dark")
        ancha = navegador.new_page(viewport={"width": 1100, "height": 1000}, color_scheme="dark")
        for nombre, (filtros, selector) in CAPTURAS.items():
            pagina = ancha if selector == "portada" else angosta
            pagina.goto(url, wait_until="networkidle")
            pagina.wait_for_selector("#grafico-mapa .main-svg")
            for filtro, valor in filtros.items():
                pagina.select_option(filtro, valor)
            pagina.wait_for_timeout(1000)                  # deja que Plotly termine de redibujar
            captura = FONDOS / f"_{nombre}_captura.png"
            if selector == "portada":                      # título, filtros e indicadores del dashboard
                fin = pagina.locator("#kpis").bounding_box()
                pagina.screenshot(path=captura, clip={"x": 0, "y": 0, "width": 1100, "height": fin["y"] + fin["height"] + 12})
                componer(captura, FONDOS / f"{nombre}.png", CAJA_PORTADA)
            else:                                          # la tarjeta completa: título y gráfico
                pagina.locator(selector).locator("xpath=..").screenshot(path=captura)
                componer(captura, FONDOS / f"{nombre}.png", CAJA)
            captura.unlink()
            print(f"  fondo listo: {nombre}.png")
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
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=URL)
    a = p.parse_args()
    capturar_fondos(a.url)
    preparar_musica()


if __name__ == "__main__":
    main()