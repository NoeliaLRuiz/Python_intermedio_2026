"""Paso 2 del reel: tu voz con Qwen3-TTS, subtítulos con Whisper, música de fondo y video con Pillow + ffmpeg.

Adaptado del reel de la sesión 15 (práctica/reel-incendios). Uso, desde la carpeta tarea_3:
    python reel/hacer_reel.py --voz reel/mi_voz.ogg --autor "Tu nombre"

Salidas en reel/: reel.mp4 (1080 x 1920, 30 fps, H.264 + AAC), subtitulos.srt y portada.png.
Cada escena narrada se guarda en reel/cache/: si se corre de nuevo, solo se narra lo que cambió.
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

AQUI = Path(__file__).resolve().parent
CACHE, FONDOS, FUENTES = AQUI / "cache", AQUI / "recursos" / "fondos", AQUI / "recursos" / "fuentes"
W, H, FPS, SR = 1080, 1920, 30, 24000
NARANJA, BLANCO = (235, 104, 52), (255, 255, 255)
MAX_WER = 0.25          # si Whisper entiende mal más del 25 % de las palabras, se narra de nuevo
INTENTOS = 3
MIN_SEGUNDOS, MAX_SEGUNDOS = 45, 75     # la tarea pide de 45 a 75 segundos
MUSICA_LUFS = -30.0     # la voz queda en -14 LUFS: la música, 16 dB más baja
# Zonas seguras de Reels: arriba la barra de la app, abajo el pie y a la derecha los botones
ARRIBA, ABAJO, IZQ, DER = 230, 420, 70, 170
Y_SUBTITULO = H - ABAJO - 110           # debajo del gráfico (que termina en y = 1350)
Y_CREDITOS = 1110                       # en la última escena, debajo de la captura del dashboard

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def fuente(peso, tam):
    return ImageFont.truetype(str(FUENTES / f"BarlowCondensed-{peso}.ttf"), tam)


# ---------------------------------------------------------------- texto

def numeros_a_palabras(texto):
    """'40 %' -> 'cuarenta por ciento'; '27 292' -> 'veintisiete mil doscientos noventa y dos'."""
    def cambiar(m):
        num, unidad = m.group(1), m.group(2) or ""
        entero, _, dec = re.sub(r"[ .](?=\d{3}\b)", "", num).partition(",")
        palabras = num2words(int(entero), lang="es")
        if dec:
            palabras += " coma " + num2words(int(dec), lang="es")
        return palabras + (" por ciento" if unidad.strip() == "%" else "")
    return re.sub(r"(\d{1,3}(?:[ .]\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(\s?%)?", cambiar, texto)


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

    CACHE.mkdir(parents=True, exist_ok=True)
    ref = CACHE / "referencia.wav"
    a_wav(voz, ref, segundos=25)
    ref_text = texto_voz or " ".join(s.text.strip() for s in whisper.transcribe(str(ref), language="es")[0])
    print(f"Tu grabación dice: «{ref_text}»" + ("" if texto_voz else " (transcrito por Whisper; corrígelo con --texto-voz)"))
    firma_voz = huella(Path(voz).read_bytes(), modelo_tts, ref_text)

    tts, prompt = None, None
    escenas = []
    for i, e in enumerate(guion["escenas"], 1):
        texto = numeros_a_palabras(e["frase"])
        base = CACHE / f"escena_{i:02d}_{huella(texto, firma_voz)}"
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


def limitar(audio):
    """Redondea los picos con un limitador suave, sin saturar."""
    alto = np.abs(audio) > 0.8
    audio[alto] = np.sign(audio[alto]) * (0.8 + 0.18 * np.tanh((np.abs(audio[alto]) - 0.8) / 0.18))
    return audio


def unir_audio(escenas):
    """Une las escenas con pausas, deja la voz en -14 LUFS y devuelve dónde empieza cada escena."""
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
    partes.append(pausa(1.5))       # unos segundos finales con la música y los créditos
    audio = np.concatenate(partes)
    factor = 1.0
    if len(audio) / SR > MAX_SEGUNDOS:  # si pasa del máximo, se acelera un poco sin cambiar el tono
        factor = len(audio) / SR / (MAX_SEGUNDOS - 1)
        crudo, rapido = CACHE / "sin_acelerar.wav", CACHE / "acelerado.wav"
        sf.write(crudo, audio, SR)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(crudo), "-filter:a", f"atempo={factor:.4f}",
                        "-ar", str(SR), str(rapido)], check=True)
        audio, _ = sf.read(rapido, dtype="float32")
        tramos = [(a / factor, b / factor) for a, b in tramos]
        print(f"Audio acelerado {factor:.3f} veces para no pasar de {MAX_SEGUNDOS} s")
    medidor = pyloudnorm.Meter(SR)
    for _ in range(3):
        audio = limitar(pyloudnorm.normalize.loudness(audio, medidor.integrated_loudness(audio), -14.0))
    return audio, tramos, desfases, factor


def mezclar_musica(voz, musica):
    """Pone la música debajo de la voz: 16 dB más baja, con entrada y salida suaves."""
    a_wav(musica, CACHE / "musica.wav")
    m, _ = sf.read(CACHE / "musica.wav", dtype="float32")
    m = np.tile(m, int(np.ceil(len(voz) / len(m))))[:len(voz)]          # se repite si es más corta
    medidor = pyloudnorm.Meter(SR)
    m = pyloudnorm.normalize.loudness(m, medidor.integrated_loudness(m), MUSICA_LUFS)
    entrada, salida = int(1.5 * SR), int(2.5 * SR)
    m[:entrada] *= np.linspace(0, 1, entrada)
    m[-salida:] *= np.linspace(1, 0, salida)
    return limitar(voz + m)


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


def dibujar_cifra(d, texto, x, y, fnt):
    """Escribe la cifra; la flecha «→» (que la fuente no trae) se dibuja como una figura."""
    partes = texto.split("→")
    tam = fnt.size
    for k, parte in enumerate(partes):
        d.text((x, y), parte, font=fnt, fill=NARANJA)
        x += fnt.getlength(parte)
        if k < len(partes) - 1:
            yc, largo, grosor = y + tam * 0.58, tam * 0.55, max(6, tam // 14)
            d.line((x, yc, x + largo - grosor, yc), fill=NARANJA, width=grosor)
            d.polygon([(x + largo, yc), (x + largo - tam * 0.2, yc - tam * 0.17), (x + largo - tam * 0.2, yc + tam * 0.17)],
                      fill=NARANJA)
            x += largo + fnt.getlength(" ") * 0.6


def ancho_cifra(texto, fnt):
    return sum(fnt.getlength(p) for p in texto.split("→")) + (texto.count("→")) * (fnt.size * 0.55 + fnt.getlength(" ") * 0.6)


def capa_fija(e, titulo, final, creditos, fuente_txt):
    """Lo que no cambia durante la escena: oscurecido, encabezado, aviso de IA, fuente, cifra y etiqueta."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    capa.alpha_composite(degradado(700, opacidad=150), (0, 0))
    capa.alpha_composite(degradado(560, arriba=False, opacidad=200), (0, H - 560))
    d = ImageDraw.Draw(capa)
    d.text((IZQ, ARRIBA + 34), titulo.upper(), font=fuente("SemiBold", 34), fill=(255, 255, 255, 215))
    aviso = "Voz generada con IA"
    fa = fuente("SemiBold", 30)
    ancho = fa.getlength(aviso) + 28
    d.rounded_rectangle((IZQ, ARRIBA + 86, IZQ + ancho, ARRIBA + 130), radius=22, fill=(0, 0, 0, 150), outline=(255, 255, 255, 120))
    d.text((IZQ + 14, ARRIBA + 91), aviso, font=fa, fill=BLANCO)
    d.text((IZQ + ancho + 18, ARRIBA + 93), f"Datos: {fuente_txt.split(' (')[0]}", font=fuente("Medium", 28),
           fill=(255, 255, 255, 200))
    tam = 170
    while ancho_cifra(e["cifra"], fuente("Bold", tam)) > W - IZQ - DER and tam > 80:
        tam -= 10
    dibujar_cifra(d, e["cifra"], IZQ - 4, ARRIBA + 160, fuente("Bold", tam))
    fe = fuente("SemiBold", 54)
    y = ARRIBA + 160 + tam + 22
    for linea in envolver(e["etiqueta"], fe, W - IZQ - DER):
        d.text((IZQ, y), linea, font=fe, fill=BLANCO)
        y += 60
    if final:
        fc = fuente("Medium", 30)
        lineas = [l for c in creditos for l in envolver(c, fc, W - IZQ - DER - 20)]
        y = Y_CREDITOS
        d.rounded_rectangle((IZQ - 18, y - 14, W - DER + 18, y + 36 * len(lineas) + 8), radius=14, fill=(0, 0, 0, 200))
        for linea in lineas:
            d.text((IZQ, y), linea, font=fc, fill=(255, 255, 255, 235))
            y += 36
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
    y = Y_SUBTITULO
    d.rounded_rectangle((x - 26, y - 16, x + total + 26, y + 96), radius=18, fill=(0, 0, 0, 185))
    for (palabra, ini, fin), ancho in zip(bloque, anchos):
        d.text((x, y), palabra, font=fs, fill=NARANJA if ini <= t < fin + 0.05 else BLANCO)
        x += ancho + espacio


def fondo_en(imagen, avance):
    """Acercamiento lento (efecto Ken Burns): del 100 % al 104 % a lo largo de la escena."""
    z = 1 + 0.04 * avance
    w, h = W / z, H / z
    x0, y0 = (W - w) / 2, (H - h) / 2
    return imagen.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


# ---------------------------------------------------------------- todo junto

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--guion", default=str(AQUI / "guion.json"), help="guion revisado (JSON)")
    p.add_argument("--voz", required=True, help="tu grabación de 15 a 25 segundos (.m4a, .ogg, .mp3, .wav)")
    p.add_argument("--autor", default="", help="tu nombre, para los créditos")
    p.add_argument("--texto-voz", help="lo que dices en la grabación, palabra por palabra (si Whisper se equivoca)")
    p.add_argument("--musica", default=str(AQUI / "recursos" / "musica.mp3"))
    p.add_argument("--credito-musica", default="«Lightless Dawn», Kevin MacLeod (incompetech.com), CC BY 4.0")
    p.add_argument("--url", default="noelialruiz.github.io/Python_intermedio_2026/tarea_3/web")
    p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    p.add_argument("--whisper", default="small")
    a = p.parse_args()

    from faster_whisper import WhisperModel

    guion = json.loads(Path(a.guion).read_text(encoding="utf-8"))
    t0 = time.time()
    whisper = WhisperModel(a.whisper, device="cpu", compute_type="int8")
    escenas = narrar_escenas(guion, a.voz, a.tts, whisper, a.texto_voz)
    voz, tramos, desfases, factor = unir_audio(escenas)
    duracion = len(voz) / SR
    wav = CACHE / "reel_audio.wav"
    sf.write(wav, mezclar_musica(voz, a.musica), SR)
    print(f"Audio: {duracion:.1f} s; voz en -14 LUFS y música en {MUSICA_LUFS:.0f} LUFS")
    if not MIN_SEGUNDOS <= duracion <= MAX_SEGUNDOS:
        print(f"  ¡Ojo! El reel dura {duracion:.0f} s; la tarea pide de {MIN_SEGUNDOS} a {MAX_SEGUNDOS}.")

    palabras = []
    for e, g, (ini, fin), d in zip(escenas, guion["escenas"], tramos, desfases):
        palabras.append(tiempos_de_palabras(g["frase"], [dict(q, ini=(q["ini"] - d) / factor, fin=(q["fin"] - d) / factor) for q in e["palabras"]], ini, fin))
    bloques = [bloques_de_subtitulo(pp) for pp in palabras]
    srt([b for bb in bloques for b in bb], AQUI / "subtitulos.srt")

    fondos = {g["fondo"]: Image.open(FONDOS / f"{g['fondo']}.png").convert("RGB") for g in guion["escenas"]}
    total = len(guion["escenas"])
    creditos = [f"Reel de {a.autor}" if a.autor else "", f"Dashboard: {a.url}", f"Datos: {guion['fuente']}",
                f"Música: {a.credito_musica}", "Voz: generada con IA (Qwen3-TTS) a partir de mi propia voz"]
    capas = [capa_fija(g, guion["titulo"], i == total - 1, [c for c in creditos if c], guion["fuente"])
             for i, g in enumerate(guion["escenas"])]

    escritor = imageio_ffmpeg.write_frames(
        str(AQUI / "reel.mp4"), (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        quality=None, audio_path=str(wav), audio_codec="aac", macro_block_size=8,
        output_params=["-crf", "26", "-maxrate", "1.6M", "-bufsize", "3.2M", "-preset", "veryfast",  # pesa poco para GitHub
                       "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", "-shortest"])
    escritor.send(None)
    n_cuadros = int(duracion * FPS)
    for c in range(n_cuadros):
        t = c / FPS
        i = next((k for k, (ini, fin) in enumerate(tramos) if t < fin + 0.4), total - 1)
        ini, fin = tramos[i]
        inicio_visual = tramos[i - 1][1] + 0.4 if i else 0.0
        fin_visual = duracion if i == total - 1 else fin + 0.4
        avance = min(1.0, max(0.0, (t - inicio_visual) / max(fin_visual - inicio_visual, 0.1)))
        cuadro = fondo_en(fondos[guion["escenas"][i]["fondo"]], avance).convert("RGBA")
        entrada = min(1.0, (t - inicio_visual) / 0.35)  # la cifra aparece en 0,35 s
        capa = capas[i] if entrada >= 1 else Image.fromarray(
            (np.asarray(capas[i]) * np.array([1, 1, 1, entrada])).astype("uint8"), "RGBA")
        cuadro.alpha_composite(capa)
        cuadro = cuadro.convert("RGB")
        d = ImageDraw.Draw(cuadro, "RGBA")       # sobre RGB, los colores semitransparentes se mezclan con el fondo
        dibujar_barras(d, i, total, avance)
        bloque = next((b for b in bloques[i] if b[0][1] - 0.05 <= t <= b[-1][2] + 0.25), None)
        if bloque:
            dibujar_subtitulo(d, bloque, t)
        if c == int(1.2 * FPS):
            cuadro.convert("RGB").save(AQUI / "portada.png")
        escritor.send(cuadro.convert("RGB").tobytes())
        if c % (5 * FPS) == 0:
            print(f"  video: {t:4.0f} s de {duracion:.0f}", flush=True)
    escritor.close()
    peso = (AQUI / "reel.mp4").stat().st_size / 1e6
    print(f"\nListo en {time.time() - t0:.0f} s: reel/reel.mp4 ({peso:.1f} MB, {duracion:.1f} s), "
          "reel/subtitulos.srt y reel/portada.png")


if __name__ == "__main__":
    main()