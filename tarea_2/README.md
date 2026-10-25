# Tarea 2 · Voces y documentos peruanos: del archivo escaneado al texto buscable

**Pregunta:** ¿Pueden convertir documentos escaneados y entrevistas en audio en un archivo de texto estructurado y
buscable?

**Dashboard público:** https://voces-y-documentos-pe.streamlit.app/

## Qué hay en esta carpeta

| Archivo | Contenido |
|---|---|
| `01_extraccion.ipynb` | Descarga, limpieza, OCR (PaddleOCR), ASR (faster-whisper con VAD), diarización, seudonimización, EDA y exportación |
| `02_evaluacion.ipynb` | Muestra de 10 documentos y 10 clips con referencias manuales, CER/WER, modelos alternativos, extracción con LLM, auditoría humana y decisión |
| `app.py` | Dashboard de Streamlit (solo lee los CSV de `datos/`) |
| `voz.py` | Módulo de la Sesión 13 (MIT, d2cml-ai/Data-Science-Python), sin cambios |
| `herramientas.py` | Seudonimización y normalización comunes a los dos notebooks |
| `datos/documentos.csv` | 31 documentos con su texto OCR seudonimizado |
| `datos/transcripciones.csv` | 22 clips (52,3 min) con su transcripción y marcas de hablante |
| `datos/extraccion_llm.csv` | Campos JSON extraídos por Gemini de cada texto |
| `datos/fuentes.csv` | URL, autor, licencia, forma de acceso y estado (incluido o descartado) de cada archivo |
| `datos/comparacion_modelos.csv`, `datos/evaluacion_detalle.csv`, `datos/auditoria_llm.csv`, `datos/seudonimizacion.csv` | Resultados de la evaluación, la auditoría y la seudonimización |
| `datos/ejemplos/` | Fragmentos de 30 s de los clips sin datos personales, para escucharlos en el dashboard |
| `modelos/configuracion_modelos.json` | Configuración exacta de cada modelo y la lista de la muestra de evaluación |

## Corpus y fuentes

Fecha de extracción: **24 de octubre de 2026**. Los archivos vienen de **Wikimedia Commons**, más una foto propia, y se
bajaron directamente de `upload.wikimedia.org` (su `robots.txt` lo permite), con User-Agent descriptivo y pausas de
1,5 s.

- **Documentos:** 32 candidatos → **31** tras la limpieza (10 impresos, 11 fotos con sombras o inclinación y 10
  manuscritos), de 1822 a 2001: cartas manuscritas de Vallejo, Grau, Gamarra, Piérola y Bachmann, oficios y cartas
  impresas, portadas de libros y revistas, y placas de Lima y Arequipa. Ninguno es de los usados en la clase de la
  Sesión 10. Una de las fotos es propia: la ficha del retablo «Diversidades» en una exposición de la PUCP (su imagen
  no se publica porque muestra una obra de arte).
- **Audio:** 24 candidatos → **22 clips y 52,3 minutos** de español peruano: entrevistas en la calle en
  El Agustino, una conferencia de prensa de Fenmucarinap, testimonios del proyecto *Salas, pantallas y archivos*
  (WikiAcción Perú), testimonios de Junín y San Martín, entrevistas de estudiantes de la UNMSM y entrevistas en
  fiestas de Áncash.
- **Licencias:** dominio público, CC0, CC BY 1.0/3.0/4.0 y CC BY-SA 3.0/4.0; la foto propia, CC BY 4.0. El detalle por archivo (autor, licencia y
  URL) está en `datos/fuentes.csv`.
- **Descartes:** la carta del Banco Internacional de 1927 (ilegible a simple vista) y dos audios sin voz según el
  VAD (el himno de la Marina, cantado con banda, y un silbador). No hubo duplicados.

Los archivos originales (`datos/raw/`, unos 55 MB) no se suben a GitHub. Para recuperarlos basta con ejecutar la
sección 2 de `01_extraccion.ipynb`, que los baja de las URL de `datos/fuentes.csv`.

**Seudonimización:** un modelo NER propone los nombres de persona, se revisan a mano y se reemplazan por
`[PERSONA_n]`; correos, teléfonos, DNI y direcciones se reemplazan siempre. Los personajes públicos o históricos de
los documentos de archivo se mantienen. Se reemplazaron 49 entidades (48 nombres y 1 dirección) en 22 textos. La lista de nombres reales queda solo
en `datos/raw/`. Las imágenes y audios con datos personales no se muestran en el dashboard.

## Resultados

Muestra de evaluación: 10 documentos (3 impresos, 3 fotos y 4 manuscritos) y 10 clips (11,6 min) del corpus,
transcritos a mano. Todos los modelos se midieron sobre los mismos casos y con la misma normalización.

| Modalidad | Modelo | Error | Latencia (CPU de laptop) |
|---|---|---|---|
| Documentos | PaddleOCR PP-OCRv6 (línea base) | CER 0,42 | 10 s por documento |
| Documentos | EasyOCR 1.7 | CER 0,66 | 11 s por documento |
| Documentos | Gemini 3.5 Flash con visión (API) | CER 0,41 | 55 s por documento (con reintentos por saturación) |
| Documentos | **Híbrido: PaddleOCR en impresos y fotos + Gemini en manuscritos** | **CER 0,32** | — |
| Audio | faster-whisper small (línea base) | WER 0,26 | factor de tiempo real 0,18 |
| Audio | Parakeet TDT 0.6B v3 | WER 0,34 | factor mediano 0,26 (un clip tardó 33 min) |
| Audio | **Whisper large-v3-turbo** | **WER 0,19** | factor de tiempo real 0,50 |

Extracción con LLM (Gemini 3.5 Flash Lite, lotes de 8 textos): **16/20** extracciones completamente correctas
(80 %) en la auditoría humana. Fallaron el emisor (2 veces), el destinatario, la fecha, el lugar y una cita.

**Decisión:** para documentos, el esquema híbrido (PaddleOCR local para impresos y fotos; Gemini solo para
manuscritos, con revisión humana); para audio, Whisper large-v3-turbo.

### Hallazgos

1. **En manuscritos, el modelo de visión-lenguaje gana; en lo impreso, no hace falta.** Gemini baja el CER de los
   manuscritos de 0,45 (PaddleOCR) a 0,28, y en la carta de Vallejo de 0,49 a 0,13. Pero en impresos y fotos lee
   además la letra pequeña que la transcripción manual no incluyó (los emblemas de la placa de Grau), y eso cuenta
   como error. Por eso conviene un esquema híbrido: CER 0,32, frente a 0,41 de Gemini solo y 0,42 de PaddleOCR solo.
2. **En audio, el tamaño del modelo importa más que la familia, y la música lo arruina todo.** Whisper turbo baja el
   WER de 0,26 a 0,19 (en testimonios, de 0,10 a 0,03) a cambio de casi 3 veces más cómputo. En la fiesta con banda
   los tres modelos fallan (WER cercano a 0,9), porque el detector de voz descarta lo que se habla sobre la música:
   el problema está en el preprocesamiento, no en el modelo. Parakeet, entrenado sobre todo con idiomas europeos,
   inventa palabras en otros idiomas («Yeah», «Done», una frase en ruso).

### Limitaciones

1. **Muestra pequeña y referencias desparejas.** Con 10 casos por modalidad, un solo documento mueve el promedio: en
   el almanaque de 1873 la referencia no incluyó la letra pequeña y su CER pasa de 1. Sin ese documento, el CER del
   híbrido baja a 0,26.
2. **Todo corre en la CPU de una laptop y con servicios gratuitos.** Los tiempos varían de una corrida a otra (un clip
   de Parakeet tardó 33 min), Gemini respondió varias veces «saturado» y su capa gratuita permite unas 20 solicitudes
   al día. Además, la diarización exagera con ruido de calle (5 hablantes donde se oyen 3).

## Cómo ejecutarlo en local

Dashboard (solo necesita `requirements.txt`):

```bash
cd tarea_2
uv venv --python 3.12
uv pip install -r requirements.txt
.venv\Scripts\activate          # en Mac o Linux: source .venv/bin/activate
streamlit run app.py
```

Notebooks (OCR, ASR y LLM; descargan unos 6 GB de modelos la primera vez):

```bash
uv pip install -r requirements-notebooks.txt --constraint constraints.txt
```

Para la Parte 2 hace falta un archivo `.env` con `GEMINI_API_KEY=...` (no se sube a GitHub). La capa gratuita de
Gemini permite unas 20 solicitudes al día por modelo: el notebook usa unas 10 con Gemini 3.5 Flash (lectura de
imágenes) y unas 7 con Flash Lite (extracción).

## Uso de IA

El código se desarrolló con apoyo de Claude Code. Las capturas de la conversación completa están en
`evidencias_ia/`. Las transcripciones de referencia, la revisión de la seudonimización y la auditoría de las 20
extracciones se hicieron a mano.
