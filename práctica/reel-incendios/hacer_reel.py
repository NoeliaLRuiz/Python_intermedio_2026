"""Pasos 2 y 3 del reel: tu voz con Qwen3-TTS, subtítulos con Whisper y video con Pillow + ffmpeg.

Uso (después de revisar el guion contra el texto):
    .venv\\Scripts\\python hacer_reel.py --guion salidas/guion_revisado.json --voz mi_voz.m4a --autor "Tu nombre"

Salidas en salidas/: reel.mp4 (1080 x 1920, 30 fps, H.264 + AAC, -14 LUFS), reel.srt, portada.png y posts.md.
Cada escena narrada se guarda en salidas/escenas/: si se corre de nuevo, solo se narra lo que cambió.
"""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
import warnings
from pathlib import Path

import imageio_ffmpeg
import jiwer
import numpy as np
import pyloudnorm
import soundfile as sf
from num2words import num2words
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

AQUI = Path(__file__).parent
SALIDAS, FONDOS, FUENTES = AQUI / "salidas", AQUI / "fondos", AQUI / "fuentes"
W, H, FPS, SR = 1080, 1920, 30, 24000
NARANJA, BLANCO = (255, 138, 31), (255, 255, 255)
MAX_WER = 0.25          # si Whisper entiende mal más del 25 % de las palabras, se narra de nuevo
INTENTOS = 3
MAX_SEGUNDOS = 60     # la tarea pide un reel de 30 a 60 segundos
# Zonas seguras de Reels: arriba la barra de la app, abajo el pie y a la derecha los botones
ARRIBA, ABAJO, IZQ, DER = 230, 420, 70, 170

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def fuente(peso, tam):
    return ImageFont.truetype(str(FUENTES / f"BarlowCondensed-{peso}.ttf"), tam)


# ---------------------------------------------------------------- texto

def numeros_a_palabras(texto):
    """'56 %' -> 'cincuenta y seis por ciento'; 'S/ 501 570' -> 'quinientos un mil quinientos setenta soles'."""
    def cambiar(m):
        moneda, num, unidad = m.group(1), m.group(2), m.group(3) or ""
        entero, _, dec = re.sub(r"[ .](?=\d{3}\b)", "", num).partition(",")
        palabras = num2words(int(entero), lang="es")
        if dec:
            palabras += " coma " + num2words(int(dec), lang="es")
        unidades = {"%": " por ciento", "ha": " hectáreas", "km": " kilómetros", "m": " metros"}
        return palabras + unidades.get(unidad.strip(), unidad and " " + unidad) + (" soles" if moneda else "")
    return re.sub(r"(S/\s*)?(\d{1,3}(?:[ .]\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(\s?%|\s(?:ha|km|m)\b)?", cambiar, texto)


def normalizar(texto):
    texto = numeros_a_palabras(texto).lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", texto)).strip()


# ---------------------------------------------------------------- audio

def a_wav(origen, destino, segundos=None):
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(origen), "-ac", "1", "-ar", str(SR)]
    if segundos:
        cmd += ["-t", str(segundos)]
    subprocess.run(cmd + [str(destino)], check=True)


def huella(*partes):
    h = hashlib.sha1()
    for p in partes:
        h.update(p if isinstance(p, bytes) else str(p).encode("utf-8"))
    return h.hexdigest()[:10]


def narrar_escenas(guion, voz, modelo_tts, whisper, texto_voz=None):
    import torch
    from qwen_tts import Qwen3TTSModel

    carpeta = SALIDAS / "escenas"
    carpeta.mkdir(parents=True, exist_ok=True)
    ref = carpeta / "referencia.wav"
    a_wav(voz, ref, segundos=20)
    ref_text = texto_voz or " ".join(s.text.strip() for s in whisper.transcribe(str(ref), language="es")[0])
    print(f"Tu grabación dice: «{ref_text}»" + ("" if texto_voz else " (transcrito por Whisper; corrígelo con --texto-voz)"))
    firma_voz = huella(Path(voz).read_bytes(), modelo_tts, ref_text)

    tts, prompt = None, None
    escenas = []
    for i, e in enumerate(guion["escenas"], 1):
        texto = numeros_a_palabras(e["frase"])
        base = carpeta / f"escena_{i:02d}_{huella(texto, firma_voz)}"
        if base.with_suffix(".json").exists():
            escenas.append(json.loads(base.with_suffix(".json").read_text(encoding="utf-8")))
            print(f"Escena {i}: ya estaba narrada (WER {escenas[-1]['wer']:.0%})")
            continue
        if tts is None:
            print("Cargando Qwen3-TTS…", flush=True)
            tts = Qwen3TTSModel.from_pretrained(modelo_tts, device_map="cpu", dtype=torch.float32)
            prompt = tts.create_voice_clone_prompt(ref_audio=str(ref), ref_text=ref_text)
        mejor = None
        for intento in range(1, INTENTOS + 1):
            t0 = time.time()
            torch.manual_seed(1000 + 10 * i + intento)
            # A veces el modelo no cierra la frase y sigue generando: tope de ~1,6 veces lo esperable
            # (unas 2 palabras por segundo; el códec produce unos 12,5 tokens por segundo de audio)
            tope = int(12.5 * (len(texto.split()) / 2.0 * 1.6 + 3))
            wavs, sr = tts.generate_voice_clone(text=texto, language="Spanish", voice_clone_prompt=prompt,
                                                max_new_tokens=tope)
            audio = wavs[0].astype("float32")
            sf.write(base.with_suffix(".wav"), audio, sr)
            segs, _ = whisper.transcribe(str(base.with_suffix(".wav")), language="es", word_timestamps=True)
            palabras = [{"p": w.word.strip(), "ini": w.start, "fin": w.end} for s in segs for w in s.words]
            oido = " ".join(p["p"] for p in palabras)
            wer = jiwer.wer(normalizar(texto), normalizar(oido) or "-")
            print(f"Escena {i}, intento {intento}: {len(audio) / sr:.1f} s de voz en {time.time() - t0:.0f} s; "
                  f"Whisper entendió mal el {wer:.0%}", flush=True)
            if mejor is None or wer < mejor["wer"]:
                mejor = {"audio": audio, "palabras": palabras, "wer": wer, "oido": oido}
            if wer <= MAX_WER:
                break
        sf.write(base.with_suffix(".wav"), mejor["audio"], SR)
        datos = {"wav": str(base.with_suffix(".wav")), "palabras": mejor["palabras"], "wer": mejor["wer"],
                 "oido": mejor["oido"], "texto": texto}
        base.with_suffix(".json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        if mejor["wer"] > MAX_WER:
            print(f"  ¡Ojo! La escena {i} quedó con {mejor['wer']:.0%} de error. Whisper oyó: «{mejor['oido']}»")
        escenas.append(datos)
    return escenas


def unir_audio(escenas, destino):
    """Une las escenas con pausas, deja el volumen en -14 LUFS y devuelve dónde empieza cada escena."""
    pausa = lambda s: np.zeros(int(SR * s), dtype="float32")
    partes, tramos, desfases, t = [pausa(0.3)], [], [], 0.3
    for e in escenas:
        audio, _ = sf.read(e["wav"], dtype="float32")
        a0 = 0.0
        if e["palabras"]:  # recorta el silencio o el ruido que el modelo deja antes y después de hablar
            a0 = max(0.0, e["palabras"][0]["ini"] - 0.15)
            a1 = min(len(audio) / SR, e["palabras"][-1]["fin"] + 0.35)
            audio = audio[int(a0 * SR):int(a1 * SR)]
        desfases.append(a0)
        tramos.append((t, t + len(audio) / SR))
        partes += [audio, pausa(0.4)]
        t += len(audio) / SR + 0.4
    partes.append(pausa(0.8))
    audio = np.concatenate(partes)
    factor = 1.0
    if len(audio) / SR > MAX_SEGUNDOS:  # si pasa del máximo, se acelera un poco sin cambiar el tono
        factor = len(audio) / SR / (MAX_SEGUNDOS - 1)
        crudo, rapido = destino.with_name("sin_acelerar.wav"), destino.with_name("acelerado.wav")
        sf.write(crudo, audio, SR)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(crudo), "-filter:a", f"atempo={factor:.4f}",
                        "-ar", str(SR), str(rapido)], check=True)
        audio, _ = sf.read(rapido, dtype="float32")
        tramos = [(a / factor, b / factor) for a, b in tramos]
        print(f"Audio acelerado {factor:.3f} veces para no pasar de {MAX_SEGUNDOS} s")
    medidor = pyloudnorm.Meter(SR)
    for _ in range(3):  # subir a -14 LUFS y redondear los picos con un limitador suave, sin saturar
        audio = pyloudnorm.normalize.loudness(audio, medidor.integrated_loudness(audio), -14.0)
        alto = np.abs(audio) > 0.8
        audio[alto] = np.sign(audio[alto]) * (0.8 + 0.18 * np.tanh((np.abs(audio[alto]) - 0.8) / 0.18))
    sf.write(destino, audio, SR)
    return tramos, desfases, factor, len(audio) / SR, medidor.integrated_loudness(audio)


# ---------------------------------------------------------------- subtítulos

def tiempos_de_palabras(frase, palabras, ini, fin):
    """Empareja las palabras del guion con las que Whisper fechó; las que no empatan se interpolan."""
    visibles = frase.split()
    fichas, de_quien = [], []
    for k, v in enumerate(visibles):
        for f in normalizar(v).split():
            fichas.append(f)
            de_quien.append(k)
    oidas, tiempos = [], []
    for p in palabras:
        partes = normalizar(p["p"]).split() or ["_"]
        paso = (p["fin"] - p["ini"]) / len(partes)
        for j, f in enumerate(partes):
            oidas.append(f)
            tiempos.append((p["ini"] + j * paso, p["ini"] + (j + 1) * paso))
    ini_v, fin_v = [None] * len(visibles), [None] * len(visibles)
    for a, b, n in difflib.SequenceMatcher(None, fichas, oidas, autojunk=False).get_matching_blocks():
        for j in range(n):
            k = de_quien[a + j]
            t0, t1 = tiempos[b + j]
            ini_v[k] = t0 if ini_v[k] is None else min(ini_v[k], t0)
            fin_v[k] = t1 if fin_v[k] is None else max(fin_v[k], t1)
    conocidos = [k for k in range(len(visibles)) if ini_v[k] is not None]
    if not conocidos:  # Whisper no fechó nada: reparto por largo de palabra
        pesos = np.cumsum([0] + [len(v) + 1 for v in visibles])
        return [(v, ini + (fin - ini) * pesos[k] / pesos[-1], ini + (fin - ini) * pesos[k + 1] / pesos[-1])
                for k, v in enumerate(visibles)]
    xs = np.array(conocidos, dtype=float)
    ini_i = np.interp(range(len(visibles)), xs, [ini_v[k] for k in conocidos], left=0, right=fin - ini)
    fin_i = np.interp(range(len(visibles)), xs, [fin_v[k] for k in conocidos], left=0.2, right=fin - ini)
    return [(v, ini + float(a), ini + float(max(b, a + 0.05))) for v, a, b in zip(visibles, ini_i, fin_i)]


def bloques_de_subtitulo(palabras, max_letras=21):
    bloques, actual = [], []
    for p in palabras:
        if actual and (sum(len(q[0]) + 1 for q in actual) + len(p[0]) > max_letras):
            bloques.append(actual)
            actual = []
        actual.append(p)
        if p[0][-1] in ".,;:?!":
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def srt(bloques, ruta):
    hms = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"
    lineas = []
    for n, b in enumerate(bloques, 1):
        lineas += [str(n), f"{hms(b[0][1])} --> {hms(b[-1][2])}", " ".join(p[0] for p in b), ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


# ---------------------------------------------------------------- imagen

CLAVES_FONDO = [("rio_tambo", r"r[ií]o tambo|ash[aá]ninka|satipo|sentinel|dnbr|quemad[ao]s? en"),
                ("bomberos", r"bomber|compa[ñn][ií]a"),
                ("edificios", r"edificaci|vivienda|casas|techos"),
                ("ayuda", r"per[uú] pendiente|don[oóa]|soles|s/|ciudadan"),
                ("cobertura", r"pastizal|bosque|cobertura|matorral|cultivo")]


def elegir_fondo(e):
    if e.get("fondo"):
        return e["fondo"]
    texto = f"{e['frase']} {e['etiqueta']} {e['cifra']}".lower()
    return next((nombre for nombre, patron in CLAVES_FONDO if re.search(patron, texto)), "focos")


def degradado(alto, arriba=True, opacidad=215):
    a = np.linspace(opacidad, 0, alto) if arriba else np.linspace(0, opacidad, alto)
    capa = np.zeros((alto, W, 4), dtype="uint8")
    capa[..., 3] = a[:, None].astype("uint8")
    return Image.fromarray(capa, "RGBA")


def envolver(texto, fnt, ancho):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if fnt.getlength(prueba) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + [actual]


def capa_fija(e, titulo, n_escena, total, final, autor, fuente_txt):
    """Lo que no cambia durante la escena: oscurecido, encabezado, aviso de IA, cifra y etiqueta."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    capa.alpha_composite(degradado(900), (0, 0))
    capa.alpha_composite(degradado(760, arriba=False, opacidad=235), (0, H - 760))
    d = ImageDraw.Draw(capa)
    d.text((IZQ, ARRIBA + 34), titulo.upper(), font=fuente("SemiBold", 34), fill=(255, 255, 255, 215))
    aviso = "Voz generada con IA"
    fa = fuente("SemiBold", 30)
    ancho = fa.getlength(aviso) + 28
    d.rounded_rectangle((IZQ, ARRIBA + 86, IZQ + ancho, ARRIBA + 130), radius=22, fill=(0, 0, 0, 150), outline=(255, 255, 255, 120))
    d.text((IZQ + 14, ARRIBA + 91), aviso, font=fa, fill=BLANCO)
    cifra = e["cifra"].replace("¡¡", "")
    tam = 260
    while fuente("Bold", tam).getlength(cifra) > W - IZQ - DER and tam > 90:
        tam -= 10
    d.text((IZQ - 6, ARRIBA + 170), cifra, font=fuente("Bold", tam), fill=NARANJA)
    fe = fuente("SemiBold", 62)
    y = ARRIBA + 170 + tam + 10
    for linea in envolver(e["etiqueta"], fe, W - IZQ - DER):
        d.text((IZQ, y), linea, font=fe, fill=BLANCO)
        y += 70
    if final:
        fc = fuente("Medium", 34)
        lineas = [l for l in [f"Reel de {autor}" if autor else "", *envolver(f"Datos: {fuente_txt}", fc, W - IZQ - DER - 40)] if l]
        y = H - ABAJO - 250 - 42 * len(lineas)
        d.rounded_rectangle((IZQ - 18, y - 14, W - DER + 18, y + 42 * len(lineas) + 6), radius=14, fill=(0, 0, 0, 190))
        for linea in lineas:
            d.text((IZQ, y), linea, font=fc, fill=(255, 255, 255, 230))
            y += 42
    return capa


def dibujar_barras(d, n_escena, total, avance):
    ancho = (W - IZQ - DER - (total - 1) * 10) / total
    for k in range(total):
        x0 = IZQ + k * (ancho + 10)
        d.rounded_rectangle((x0, ARRIBA, x0 + ancho, ARRIBA + 8), radius=4, fill=(255, 255, 255, 90))
        lleno = 1 if k < n_escena else (avance if k == n_escena else 0)
        if lleno > 0:
            d.rounded_rectangle((x0, ARRIBA, x0 + ancho * lleno, ARRIBA + 8), radius=4, fill=BLANCO)


def dibujar_subtitulo(d, bloque, t):
    fs = fuente("Bold", 72)
    espacio = fs.getlength(" ")
    anchos = [fs.getlength(p[0]) for p in bloque]
    total = sum(anchos) + espacio * (len(bloque) - 1)
    x = (W - DER + IZQ - total) / 2
    y = H - ABAJO - 190
    d.rounded_rectangle((x - 26, y - 16, x + total + 26, y + 96), radius=18, fill=(0, 0, 0, 165))
    for (palabra, ini, fin), ancho in zip(bloque, anchos):
        d.text((x, y), palabra, font=fs, fill=NARANJA if ini <= t < fin + 0.05 else BLANCO)
        x += ancho + espacio


def fondo_en(imagen, avance):
    """Acercamiento lento (efecto Ken Burns): del 100 % al 106 % a lo largo de la escena."""
    z = 1 + 0.06 * avance
    w, h = W / z, H / z
    x0, y0 = (W - w) / 2, (H - h) / 2
    return imagen.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


# ---------------------------------------------------------------- todo junto

def main():
    global SALIDAS
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--guion", required=True, help="guion revisado (JSON)")
    p.add_argument("--voz", required=True, help="tu grabación de 15 a 20 segundos (.m4a, .ogg, .mp3, .wav)")
    p.add_argument("--autor", default="", help="tu nombre, para el cierre del reel")
    p.add_argument("--texto-voz", help="lo que dices en la grabación, palabra por palabra (si Whisper se equivoca)")
    p.add_argument("--fuente", default="INPE (VIIRS), Sentinel-2, ESA WorldCover, Google Open Buildings, OpenStreetMap y COEN-INDECI",
                   help="de dónde vienen los datos")
    p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    p.add_argument("--whisper", default="small")
    p.add_argument("--salidas", default=str(SALIDAS), help="carpeta de salida")
    a = p.parse_args()
    SALIDAS = Path(a.salidas)

    from faster_whisper import WhisperModel

    guion = json.loads(Path(a.guion).read_text(encoding="utf-8"))
    marcadas = [i for i, e in enumerate(guion["escenas"], 1) if "¡¡" in e["cifra"]]
    if marcadas:
        sys.exit(f"Las escenas {marcadas} tienen cifras marcadas con ¡¡: revísalas contra el texto antes de narrar.")
    SALIDAS.mkdir(exist_ok=True)
    t0 = time.time()

    whisper = WhisperModel(a.whisper, device="cpu", compute_type="int8")
    escenas = narrar_escenas(guion, a.voz, a.tts, whisper, a.texto_voz)
    wav = SALIDAS / "reel.wav"
    tramos, desfases, factor, duracion, lufs = unir_audio(escenas, wav)
    print(f"Audio: {duracion:.1f} s, {lufs:.1f} LUFS")
    if not 30 <= duracion <= 60:
        print(f"  ¡Ojo! El reel dura {duracion:.0f} s; la tarea pide de 30 a 60.")

    palabras = []
    for e, g, (ini, fin), d in zip(escenas, guion["escenas"], tramos, desfases):
        palabras.append(tiempos_de_palabras(g["frase"], [dict(q, ini=(q["ini"] - d) / factor, fin=(q["fin"] - d) / factor) for q in e["palabras"]], ini, fin))
    bloques = [bloques_de_subtitulo(pp) for pp in palabras]
    srt([b for bb in bloques for b in bb], SALIDAS / "reel.srt")

    fondos = {}
    for g in guion["escenas"]:
        nombre = elegir_fondo(g)
        if nombre not in fondos:
            fondos[nombre] = Image.open(FONDOS / f"{nombre}.png").convert("RGB").resize((W, H))
    total = len(guion["escenas"])
    capas = [capa_fija(g, guion.get("titulo", "¿Qué se quemó?"), i, total, i == total - 1, a.autor, a.fuente)
             for i, g in enumerate(guion["escenas"])]

    escritor = imageio_ffmpeg.write_frames(
        str(SALIDAS / "reel.mp4"), (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        quality=None, audio_path=str(wav), audio_codec="aac", macro_block_size=8,
        output_params=["-crf", "26", "-maxrate", "1.4M", "-bufsize", "2.8M", "-preset", "veryfast",  # menos de 10 MB para GitHub
                       "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", "-shortest"])
    escritor.send(None)
    n_cuadros = int(duracion * FPS)
    for c in range(n_cuadros):
        t = c / FPS
        i = next((k for k, (ini, fin) in enumerate(tramos) if t < fin + 0.4), total - 1)
        ini, fin = tramos[i]
        inicio_visual = tramos[i - 1][1] + 0.4 if i else 0.0
        avance = min(1.0, max(0.0, (t - inicio_visual) / max(fin + 0.4 - inicio_visual, 0.1)))
        cuadro = fondo_en(fondos[elegir_fondo(guion["escenas"][i])], avance).convert("RGBA")
        entrada = min(1.0, (t - inicio_visual) / 0.35)  # la cifra aparece en 0,35 s
        capa = capas[i] if entrada >= 1 else Image.fromarray(
            (np.asarray(capas[i]) * np.array([1, 1, 1, entrada])).astype("uint8"), "RGBA")
        cuadro.alpha_composite(capa)
        d = ImageDraw.Draw(cuadro)
        dibujar_barras(d, i, total, avance)
        bloque = next((b for b in bloques[i] if b[0][1] - 0.05 <= t <= b[-1][2] + 0.25), None)
        if bloque:
            dibujar_subtitulo(d, bloque, t)
        if c == int(1.2 * FPS):
            cuadro.convert("RGB").save(SALIDAS / "portada.png")
        escritor.send(cuadro.convert("RGB").tobytes())
        if c % (5 * FPS) == 0:
            print(f"  video: {t:4.0f} s de {duracion:.0f}", flush=True)
    escritor.close()

    posts = guion.get("posts", {})
    nota = "Voz generada con IA."
    texto_posts = [f"# Posts · {guion.get('titulo', 'Reel')}", "",
                   "Revisados contra el README del Reto C antes de publicar.", ""]
    for red, nombre in [("instagram", "Instagram"), ("x", "X"), ("linkedin", "LinkedIn")]:
        cuerpo = posts.get(red, "").strip()
        if nota.lower() not in cuerpo.lower():
            cuerpo += f"\n\n{nota}"
        texto_posts += [f"## {nombre}", "", cuerpo, ""]
    (SALIDAS / "posts.md").write_text("\n".join(texto_posts), encoding="utf-8")
    peso = (SALIDAS / "reel.mp4").stat().st_size / 1e6
    print(f"\nListo en {time.time() - t0:.0f} s: {SALIDAS / 'reel.mp4'} ({peso:.1f} MB, {duracion:.1f} s), "
          "reel.srt, portada.png y posts.md")


if __name__ == "__main__":
    main()
