# Reel: ¿Qué se quemó?

Tarea de la sesión 15 (Del texto a tu voz) del curso Ciencia de Datos con Python. El README del [Reto C](../reto-c-incendios/README.md) se convierte en un reel vertical de unos 50 segundos, narrado con mi voz clonada y solo con modelos abiertos.

**Entrega:** `salidas/reel.mp4` y `salidas/posts.md`, con lo que corregí del guion en [`revision.md`](revision.md).

## El flujo

| Paso | Qué hace | Herramienta | Archivo |
|---|---|---|---|
| 1. Texto largo | Los hallazgos, el método y las limitaciones del Reto C | — | `../reto-c-incendios/README.md` |
| 2. Guion | El mismo prompt en dos chats; el guion vuelve como JSON, escena por escena | DeepSeek y Qwen (chat web) | `prompt.txt`, `respuesta_*.txt` |
| 3. Revisión | El código marca las cifras que no están en el texto; yo leí cada frase contra la fuente | `guion.py` + lectura | `revision.md`, `salidas/guion_revisado.json` |
| 4. Mi voz | Clona mi voz con 19 segundos de grabación; Whisper vuelve a escuchar cada escena y la repite si entiende mal más del 25 % | Qwen3-TTS 0.6B, faster-whisper | `mi_voz.ogg` (no se sube al repositorio) |
| 5. Video | 1080 × 1920, 30 fps, −14 LUFS, subtítulos palabra por palabra y aviso de IA todo el tiempo | Pillow + ffmpeg | `salidas/reel.mp4` |

Los fondos son mapas y la imagen Sentinel-2 de Río Tambo hechos con los datos del Reto C (`fondos.py`).

## ¿Cuál inventó menos?

DeepSeek. Las dos respuestas tenían todas las cifras bien, pero Qwen dijo que el 56 % era «de lo que se quemó en el Perú» (era de la zona con fuego de los incendios grandes) y que «la sociedad civil» recaudó «para equipar» a ocho comandancias (fue una ONG, y el 88 % fue en equipos). Detalle completo en [`revision.md`](revision.md).

## Cómo repetirlo (Windows)

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe qwen-tts faster-whisper pillow imageio-ffmpeg soundfile jiwer num2words pypdf pyloudnorm "av<19"

# 1. Prompt: pegarlo en chat.qwen.ai o chat.deepseek.com y guardar la respuesta
.venv\Scripts\python guion.py --texto ..\reto-c-incendios\README.md --solo-prompt > prompt.txt
.venv\Scripts\python guion.py --texto ..\reto-c-incendios\README.md --respuesta respuesta_qwen.txt --modelo qwen

# 2. Fondos (con el entorno del Reto C, que tiene geopandas)
..\reto-c-incendios\.venv\Scripts\python fondos.py

# 3. Voz, subtítulos y video, después de revisar el guion
.venv\Scripts\python hacer_reel.py --guion salidas\guion_revisado.json --voz mi_voz.ogg --autor "Noelia León Ruiz" --texto-voz "lo que digo en la grabación"
```

`av<19` hace falta porque PyAV 19 rompe la lectura de audio de faster-whisper 1.2.1. En una laptop sin tarjeta gráfica, la voz tarda unas 10 veces lo que dura el audio: unos 8 minutos para 50 segundos. Las escenas ya narradas se guardan, así que cambiar el diseño y volver a armar el video toma menos de un minuto.

## Reglas que seguí

- **Solo mi voz:** la grabación es mía.
- **Declaro la IA:** «Voz generada con IA» aparece durante todo el video y al final de cada post.
- **Reviso la fuente:** nada sale sin leer el guion completo contra el README del Reto C.

La fuente Barlow Condensed (`fuentes/`) tiene licencia SIL Open Font License.
