# Tarea 1 · Del titular al clasificador

## 1. Pregunta del proyecto
¿Pueden convertir titulares peruanos en un clasificador de noticias? Recolecté 384 titulares
de El Comercio, los etiqueté con un LLM (supervisión débil), audité 20 a mano y afiné
DistilBERT multilingüe para clasificarlos en `politica`, `economia`, `deportes` y
`ciencia_tecnologia`. El modelo se prueba en vivo en un dashboard de Streamlit (`app.py`).

## 2. Medio y fechas de extracción
- **Medio:** El Comercio (opción B).
- **Fuente:** sitemaps de noticias por sección (`politica`, `economia`, `tecnologia`,
  `deporte-total`), permitidos en su robots.txt, con las 100 noticias más recientes de cada
  una. La bajada sale de la etiqueta `<meta name="description">` de cada noticia. Descarté
  La República porque su RSS trae solo 12–34 noticias por sección y su robots.txt prohíbe la
  paginación.
- **Fecha de descarga:** 18 de octubre de 2026, pasada la medianoche. Los XML guardados en
  `datos/raw/` llevan en el nombre la fecha 2026-10-17, que fijé en el código antes de descargar.
- **Fechas de publicación:** del 6 al 18 de octubre de 2026. Cada sección cubre un periodo
  distinto: deportes 5 días (14–18), economía 6 (12–17), política 8 (11–18) y ciencia y
  tecnología 12 (6–17).
- **Volumen:** 400 noticias descargadas → **384 finales**. Se descartaron 16: 1 URL repetida
  y 15 de secciones fuera de las 4 categorías (ecdata, opinión, elecciones, autos, BBC Mundo y
  El Dominical). Quedaron economía 99, deportes 98, ciencia y tecnología 95 y política 92.

## 3. Resultados
| Modelo | Evaluado en | F1 macro | Accuracy | Segundos por titular | Costo |
|---|---|---|---|---|---|
| Zero-shot (`Recognai/bert-base-spanish-wwm-cased-xnli`) | 40 titulares | 0.60 | 0.62 | 0.42 | gratis, local |
| LLM (Gemini 3.8 / 3.5 Flash) | test (58) | 0.95 | 0.95 | 1.2–3.5 | API: 20 solicitudes gratis por día y modelo |
| **DistilBERT afinado** | test (58) | **0.80** | **0.81** | 0.04 | gratis, local (CPU) |

- Acuerdo LLM–auditoría humana: **20/20 (100 %)**.
- El LLM coincide con la sección del diario en el 92 % de las 384 noticias.
- El test se compara con la sección del diario y no se usó para elegir el modelo ni sus parámetros.

## 4. Hallazgos
1. **Ciencia y tecnología es la categoría más difícil.** DistilBERT acertó solo 7 de sus 15
   titulares del test (F1 0.64, frente a 0.83–0.87 de las demás). Cinco se fueron a economía:
   son noticias de ambiente o seguridad digital con empresas o cifras de por medio (centros de
   datos de Google, El Niño, estafas digitales, minería ilegal y el Informe Planeta Vivo).
   Economía acertó sus 15 titulares, pero porque funciona como cajón de sastre: se llevó 6 ajenos.
2. **La sección del diario no siempre es el tema del titular.** Gemini discrepa de la sección
   en 30 de las 384 noticias (8 %), y casi todas cruzan temas: la Ley MAPE de minería (sección
   política, el LLM dice economía) o las alertas de El Niño (sección tecnología, el LLM dice
   política). En el test, DistilBERT falla en los mismos 3 titulares que Gemini: al aprender de
   sus etiquetas, hereda sus dudas.
3. **Cada sección publica a un ritmo distinto.** Deportes publica unas 20 noticias al día y
   ciencia y tecnología unas 8, así que las 100 más recientes de cada sitemap cubren entre 5 y
   12 días. El dataset no compara las categorías en un mismo periodo.

## 5. Limitaciones
1. **Etiquetas imperfectas.** El modelo se entrenó con las etiquetas de Gemini, no con
   etiquetas humanas, y por la cuota gratuita las pusieron dos modelos: `gemini-3.8-flash`
   (300 noticias) y `gemini-3.5-flash` (84). Además, el test se compara con la sección del
   diario, que tampoco es una verdad perfecta (ver hallazgo 2).
2. **Pocos datos y un resultado sensible al azar.** Con 268 titulares de entrenamiento, el
   punto de partida aleatorio pesa mucho: antes de fijar la semilla con `set_seed(42)`, dos
   ejecuciones iguales dieron F1 de 0.91 y 0.86 en test. Reporto 0.80 porque es el resultado
   reproducible con la semilla fija, no el más alto.
3. **Un solo medio y dos semanas de noticias.** El modelo aprendió la agenda de octubre de
   2026 en El Comercio; con otros medios o después de las elecciones, su desempeño puede bajar.
   Además, el zero-shot se evaluó en 40 titulares, no en el mismo test.

## 6. Cómo ejecutarlo en local
Requiere Python 3.12. En una terminal:

```bash
git clone https://github.com/NoeliaLRuiz/Python_intermedio_2026.git
cd Python_intermedio_2026/tarea_1
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

El modelo afinado (`modelo/model.safetensors`, 541 MB) no está en GitHub. Para crearlo:
1. Crea un archivo `.env` en `tarea_1/` con la línea `GEMINI_API_KEY=tu_clave`.
2. Ejecuta `02_clasificacion.ipynb` completo. Las etiquetas guardadas en
   `datos/etiquetas_llm.csv` no se vuelven a pedir (solo hay una llamada de prueba a Gemini) y
   el entrenamiento tarda unos 3 minutos en CPU.

No hace falta ejecutar `01_recoleccion.ipynb`: `datos/noticias.csv` ya está en el repositorio
y, si se ejecuta, usa los archivos guardados en `datos/raw/` en lugar de descargar de nuevo.

Luego abre el dashboard:

```bash
streamlit run app.py
```

Se abre en http://localhost:8501. Sin el modelo, el dashboard funciona igual, pero el probador
avisa que falta ejecutar el notebook 2.


El archivo `.streamlit/config.toml` apaga el vigilante de archivos de Streamlit: con
transformers, ese vigilante llena la terminal de avisos sobre `torchvision`, que no se usa.


