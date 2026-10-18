import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

CARPETA = Path(__file__).parent
RUTA_NOTICIAS = CARPETA / "datos" / "noticias.csv"
RUTA_METRICAS = CARPETA / "modelo" / "metricas.json"
RUTA_MODELO = CARPETA / "modelo"

# Modelo publicado en Hugging Face: lo usa la app en la nube, donde no está el modelo local
MODELO_HUGGING_FACE = "NoeliaF/clasificador-noticias-pe"

st.set_page_config(page_title="Clasificador de noticias", page_icon=":newspaper:", layout="wide")


@st.cache_data
def cargar_noticias():
    return pd.read_csv(RUTA_NOTICIAS)


@st.cache_data
def cargar_metricas():
    with open(RUTA_METRICAS, encoding="utf-8") as archivo:
        return json.load(archivo)


@st.cache_resource
def cargar_clasificador():
    # Se importa aquí y desde transformers.pipelines: la página carga sin esperar a torch
    # y se evita el atajo «from transformers import pipeline», que falló en Streamlit Cloud
    from transformers.pipelines import pipeline

    # Usa el modelo local si existe; si no, el publicado en Hugging Face
    if (RUTA_MODELO / "model.safetensors").exists():
        origen = str(RUTA_MODELO)
    else:
        origen = MODELO_HUGGING_FACE
    return pipeline("text-classification", model=origen, top_k=None)


noticias = cargar_noticias()
metricas = cargar_metricas()

# 1. Encabezado y contexto
st.title("¿Pueden los titulares peruanos convertirse en un clasificador de noticias?")
st.markdown(
    "Recolectamos titulares de **El Comercio** desde sus sitemaps de noticias, los "
    "etiquetamos con un LLM (supervisión débil), revisamos 20 a mano y afinamos "
    "**DistilBERT multilingüe** para clasificarlos en 4 categorías: política, economía, "
    "deportes y ciencia/tecnología. Las métricas se calcularon en un test reservado."
)

# 2. Filtros en la barra lateral
st.sidebar.header("Filtros")
todos_los_medios = sorted(noticias["medio"].unique())
todas_las_categorias = sorted(noticias["etiqueta"].unique())
medios = st.sidebar.multiselect("Medio", todos_los_medios, default=todos_los_medios)
categorias = st.sidebar.multiselect(
    "Categoría", todas_las_categorias, default=todas_las_categorias
)
filtradas = noticias[noticias["medio"].isin(medios) & noticias["etiqueta"].isin(categorias)]

# 3. Indicadores clave
columna_1, columna_2, columna_3 = st.columns(3)
columna_1.metric("Noticias recolectadas", metricas["total_noticias"])
columna_2.metric(
    "F1 macro en test",
    f"{metricas['f1_test']:.2f}",
    delta=f"{metricas['f1_test'] - metricas['f1_zero_shot']:+.2f} frente al zero-shot",
)
acuerdo = metricas["acuerdo_llm_humano"] / metricas["auditados"]
columna_3.metric(
    "Acuerdo LLM vs. auditoría humana",
    f"{acuerdo:.0%}",
    help=f"{metricas['acuerdo_llm_humano']} de {metricas['auditados']} casos revisados a mano",
)

# 4. Distribución de categorías filtradas
conteo = filtradas["etiqueta"].value_counts().reset_index()
conteo.columns = ["etiqueta", "noticias"]
figura = px.bar(
    conteo, x="etiqueta", y="noticias", text="noticias",
    title=f"{len(filtradas)} noticias con los filtros elegidos",
)
st.plotly_chart(figura, width="stretch")

# 5. Tabla interactiva y descarga
st.dataframe(filtradas, width="stretch", hide_index=True)
st.download_button(
    "Descargar CSV",
    data=filtradas.to_csv(index=False).encode("utf-8"),
    file_name="noticias_filtradas.csv",
    mime="text/csv",
)

# 6. Probador en vivo
st.header("Prueba el clasificador")
titular = st.text_input(
    "Escribe o pega un titular",
    placeholder="Ej.: Congreso aprueba nuevo retiro de fondos de AFP",
)
if st.button("Clasificar", type="primary"):
    hay_modelo = (RUTA_MODELO / "model.safetensors").exists() or MODELO_HUGGING_FACE != ""
    if titular.strip() == "":
        st.warning("Escribe un titular primero.")
    elif not hay_modelo:
        st.error("No encuentro el modelo: ejecuta antes 02_clasificacion.ipynb.")
    else:
        clasificador = cargar_clasificador()
        # Con una lista de un titular, la respuesta es una lista con sus 4 probabilidades
        probabilidades = pd.DataFrame(clasificador([titular])[0])
        mejor = probabilidades.iloc[0]
        ganadora = mejor["label"]
        probabilidad = mejor["score"]
        st.success(f"Categoría predicha: **{ganadora}** · probabilidad {probabilidad:.0%}")
        figura_probabilidades = px.bar(
            probabilidades, x="score", y="label", orientation="h", range_x=[0, 1],
            labels={"score": "Probabilidad", "label": "Categoría"},
        )
        st.plotly_chart(figura_probabilidades, width="stretch")
