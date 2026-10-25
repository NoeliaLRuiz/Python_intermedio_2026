"""Dashboard de la Tarea 2: explora los documentos y audios ya procesados en los notebooks.

    streamlit run app.py

No corre OCR, ASR ni LLM: solo lee los CSV de datos/. Las imágenes y audios se muestran solo si su licencia
permite publicarlos y no contienen datos personales.
"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Voces y documentos peruanos", page_icon="📜", layout="wide")
DATOS = Path(__file__).parent / "datos"
COLORES = {"impreso": "#2a78d6", "foto": "#eb6834", "manuscrito": "#7d55c7"}


@st.cache_data
def cargar():
    leer = lambda nombre: pd.read_csv(DATOS / nombre, keep_default_na=False)       # tablas de texto
    docs, clips = leer("documentos.csv"), leer("transcripciones.csv")
    llm, fuentes, cambios = leer("extraccion_llm.csv"), leer("fuentes.csv"), leer("seudonimizacion.csv")
    detalle = pd.read_csv(DATOS / "evaluacion_detalle.csv")                           # tablas con números
    detalle["hipotesis"] = detalle["hipotesis"].fillna("")
    comparacion = pd.read_csv(DATOS / "comparacion_modelos.csv")
    auditoria = pd.read_csv(DATOS / "auditoria_llm.csv").fillna("")
    docs["imagen_publicable"] = docs["imagen_publicable"].astype(str).eq("True")
    ejemplos = {p.stem: p for p in (DATOS / "ejemplos").glob("clip_*.ogg")}
    clips["ejemplo"] = clips["id"].map(lambda i: str(ejemplos[i]) if i in ejemplos else "")
    return docs, clips, llm, fuentes, cambios, detalle, comparacion, auditoria


docs, clips, llm, fuentes, cambios, detalle, comparacion, auditoria = cargar()
campos_llm = dict(zip(llm["id"], llm["campos_json"].map(json.loads)))
modelo_base_ocr = docs["modelo_ocr"].iloc[0]
modelo_base_asr = clips["modelo_asr"].iloc[0]

# ───────────────────────────────────────────── encabezado e indicadores
st.title("¿Se pueden convertir documentos escaneados y entrevistas en audio en texto estructurado y buscable?")
st.markdown(
    f"**{len(docs)} documentos peruanos** (impresos, fotos de placas y manuscritos de 1822 a 2001, más una foto propia) y "
    f"**{clips['duracion_seg'].sum() / 60:.0f} minutos de entrevistas** en español peruano de Wikimedia Commons, "
    "con licencia libre. OCR con PaddleOCR, transcripción con faster-whisper (VAD y diarización), seudonimización, "
    "extracción de campos con Gemini y comparación de modelos sobre 10 documentos y 10 clips transcritos a mano. "
    "Todo se calculó antes en los notebooks; esta página solo explora los resultados."
)

cer = comparacion[comparacion["metrica"] == "CER"].set_index("modelo")["error"]
wer = comparacion[comparacion["metrica"] == "WER"].set_index("modelo")["error"]
base_ocr, base_asr = "PaddleOCR PP-OCRv6 (base)", "faster-whisper small (base)"
c = st.columns(5)
c[0].metric("Documentos procesados", len(docs), f"{(fuentes['modalidad'] == 'documento').sum() - len(docs)} descartados", delta_color="off")
c[1].metric("Minutos de audio transcritos", f"{clips['duracion_seg'].sum() / 60:.1f}", f"{len(clips)} clips", delta_color="off")
c[2].metric("CER PaddleOCR (10 documentos)", f"{cer[base_ocr]:.1%}",
            f"mejor: {cer.idxmin().split(' (')[0]} {cer.min():.1%}", delta_color="off")
c[3].metric("WER faster-whisper small (10 clips)", f"{wer[base_asr]:.1%}",
            f"mejor: {wer.idxmin().split(' (')[0]} {wer.min():.1%}", delta_color="off")
c[4].metric("Concordancia LLM vs. auditoría", f"{auditoria['correcto'].astype(int).mean():.0%}",
            f"{auditoria['correcto'].astype(int).sum()}/{len(auditoria)} completamente correctas", delta_color="off")

pestanas = st.tabs(["Resumen", "Documentos", "Audios", "Evaluación de modelos", "Fuentes y método"])


def descargar_csv(tabla, nombre, clave):
    st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8"), nombre, "text/csv", key=clave)


def mostrar_campos(id_):
    campos = {k: v for k, v in campos_llm.get(id_, {}).items() if v not in (None, [], "")}
    if not campos:
        st.info("Sin campos extraídos.")
        return
    for k, v in campos.items():
        st.markdown(f"**{k.replace('_', ' ')}:** " + ("; ".join(f"«{x}»" for x in v) if isinstance(v, list) else str(v)))


# ───────────────────────────────────────────── resumen
with pestanas[0]:
    izq, der = st.columns(2)
    fig = px.histogram(docs, x="tipo", color="tipo", color_discrete_map=COLORES, text_auto=True,
                       category_orders={"tipo": ["impreso", "foto", "manuscrito"]},
                       labels={"tipo": "Tipo de documento", "count": "Documentos"},
                       title="Los tres tipos de documento están representados de forma pareja")
    izq.plotly_chart(fig.update_layout(showlegend=False, yaxis_title="Documentos"), width="stretch")
    minutos = clips.groupby("condicion")["duracion_seg"].sum().div(60).sort_values().reset_index(name="minutos")
    fig = px.bar(minutos, x="minutos", y="condicion", orientation="h", text_auto=".1f",
                 labels={"condicion": "Condición de grabación", "minutos": "Minutos de audio"},
                 title="Los testimonios grabados en interiores son la mayor parte del audio")
    der.plotly_chart(fig, width="stretch")

    st.subheader("Buscar en todos los textos")
    consulta = st.text_input("Palabra o frase (OCR y transcripciones)", placeholder="ej.: Lima, cine, fiesta, Grau",
                             key="buscar_todo")
    if consulta:
        hallados = pd.concat([
            docs.loc[docs["texto_ocr"].str.contains(consulta, case=False, regex=False), ["id", "titulo", "tipo", "texto_ocr"]]
            .rename(columns={"texto_ocr": "texto"}).assign(modalidad="documento"),
            clips.loc[clips["texto_asr"].str.contains(consulta, case=False, regex=False), ["id", "titulo", "condicion", "texto_asr"]]
            .rename(columns={"texto_asr": "texto", "condicion": "tipo"}).assign(modalidad="audio"),
        ])
        st.write(f"{len(hallados)} resultados para «{consulta}»")
        st.dataframe(hallados, hide_index=True, width="stretch")

# ───────────────────────────────────────────── documentos
with pestanas[1]:
    f1, f2, f3 = st.columns([2, 2, 3])
    tipos = f1.multiselect("Tipo de documento", ["impreso", "foto", "manuscrito"], default=["impreso", "foto", "manuscrito"])
    modelos_ocr = ["PaddleOCR PP-OCRv6 (base)"] + sorted(set(detalle.loc[detalle["metrica"] == "CER", "modelo"]) - {base_ocr})
    modelo = f2.selectbox("Modelo de OCR", modelos_ocr, help="Los modelos alternativos solo se corrieron sobre la muestra de 10 documentos.")
    palabra = f3.text_input("Buscar en el texto OCR", key="buscar_docs")

    if modelo == base_ocr:
        vista = docs[["id", "titulo", "tipo", "fuente", "texto_ocr", "n_caracteres", "conf_mediana"]].copy()
        vista = vista.merge(detalle.loc[detalle["modelo"] == modelo, ["id", "error"]].rename(columns={"error": "CER"}), on="id", how="left")
    else:
        vista = (detalle.loc[detalle["modelo"] == modelo, ["id", "hipotesis", "error"]]
                 .rename(columns={"hipotesis": "texto_ocr", "error": "CER"})
                 .merge(docs[["id", "titulo", "tipo", "fuente"]], on="id"))
        vista["n_caracteres"] = vista["texto_ocr"].str.len()
    vista = vista[vista["tipo"].isin(tipos)]
    if palabra:
        vista = vista[vista["texto_ocr"].str.contains(palabra, case=False, regex=False)]

    st.caption(f"{len(vista)} documentos · modelo: {modelo}")
    fig = px.bar(vista.sort_values("n_caracteres"), x="n_caracteres", y="titulo", color="tipo", orientation="h",
                 color_discrete_map=COLORES, height=max(300, 22 * len(vista)),
                 labels={"n_caracteres": "Caracteres leídos", "titulo": ""},
                 title="Cuánto texto rescató el OCR de cada documento")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(vista, hide_index=True, width="stretch")
    descargar_csv(vista, "documentos_filtrados.csv", "dl_docs")

    st.subheader("Explorador de documentos")
    elegido = st.selectbox("Documento", docs["id"] + " · " + docs["titulo"], key="doc")
    d = docs[docs["id"] == elegido.split(" · ")[0]].iloc[0]
    izq, der = st.columns([2, 3])
    with izq:
        if d["imagen_publicable"]:
            st.image(d["url_imagen"], caption=d["fuente"], width="stretch")
        else:
            st.warning("La imagen no se muestra: es una foto propia de una obra de arte o contiene datos personales "
                       "(seudonimizados en el texto).")
        st.markdown(f"**Tipo:** {d['tipo']} · **Confianza mediana del OCR:** {d['conf_mediana']:.2f}")
    with der:
        st.markdown("**Texto OCR (PaddleOCR)**")
        st.text_area("ocr", d["texto_ocr"], height=220, label_visibility="collapsed")
        st.markdown("**Campos extraídos por el LLM**")
        mostrar_campos(d["id"])
        if d["texto_referencia"]:
            st.markdown("**Transcripción manual (referencia)**")
            st.text_area("ref", d["texto_referencia"], height=140, label_visibility="collapsed")
            comparar = detalle[detalle["id"] == d["id"]][["modelo", "error", "segundos", "hipotesis"]]
            st.dataframe(comparar.rename(columns={"error": "CER"}).style.format({"CER": "{:.1%}", "segundos": "{:.1f}"}),
                         hide_index=True, width="stretch")

# ───────────────────────────────────────────── audios
with pestanas[2]:
    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    condiciones = sorted(clips["condicion"].unique())
    elegidas = f1.multiselect("Condición de grabación", condiciones, default=condiciones)
    modelos_asr = [base_asr] + sorted(set(detalle.loc[detalle["metrica"] == "WER", "modelo"]) - {base_asr})
    modelo = f2.selectbox("Modelo de ASR", modelos_asr, help="Los modelos alternativos solo se corrieron sobre la muestra de 10 clips.")
    rango = f3.slider("Duración (s)", 0, int(clips["duracion_seg"].max()) + 1, (0, int(clips["duracion_seg"].max()) + 1))
    palabra = f4.text_input("Buscar en la transcripción", key="buscar_audios")

    if modelo == base_asr:
        vista = clips[["id", "titulo", "condicion", "duracion_seg", "n_hablantes", "texto_asr"]].copy()
        vista = vista.merge(detalle.loc[detalle["modelo"] == modelo, ["id", "error"]].rename(columns={"error": "WER"}), on="id", how="left")
    else:
        vista = (detalle.loc[detalle["modelo"] == modelo, ["id", "hipotesis", "error"]]
                 .rename(columns={"hipotesis": "texto_asr", "error": "WER"})
                 .merge(clips[["id", "titulo", "condicion", "duracion_seg", "n_hablantes"]], on="id"))
    vista = vista[vista["condicion"].isin(elegidas) & vista["duracion_seg"].between(*rango)]
    if palabra:
        vista = vista[vista["texto_asr"].str.contains(palabra, case=False, regex=False)]

    st.caption(f"{len(vista)} clips · {vista['duracion_seg'].sum() / 60:.1f} min · modelo: {modelo}")
    fig = px.bar(vista.sort_values("duracion_seg"), x="duracion_seg", y="titulo", color="condicion", orientation="h",
                 height=max(300, 22 * len(vista)), hover_data=["id", "n_hablantes"],
                 labels={"duracion_seg": "Duración (segundos)", "titulo": "", "condicion": "Condición"},
                 title="Duración de cada clip")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(vista, hide_index=True, width="stretch")
    descargar_csv(vista, "transcripciones_filtradas.csv", "dl_audios")

    st.subheader("Explorador de audios")
    elegido = st.selectbox("Clip", clips["id"] + " · " + clips["titulo"], key="clip")
    a = clips[clips["id"] == elegido.split(" · ")[0]].iloc[0]
    izq, der = st.columns([2, 3])
    with izq:
        st.markdown(f"**Condición:** {a['condicion']} · **Duración:** {a['duracion_seg']:.0f} s · "
                    f"**Hablantes detectados:** {a['n_hablantes']}")
        if a["ejemplo"]:
            st.audio(a["ejemplo"])
            st.caption(f"Primeros 30 s. {a['fuente']}")
        else:
            st.warning("Este audio no se reproduce aquí: en él se dicen nombres de personas. Se puede consultar su "
                       "transcripción seudonimizada.")
        st.markdown("**Campos extraídos por el LLM**")
        mostrar_campos(a["id"])
    with der:
        st.markdown("**Transcripción (faster-whisper small, con marcas de hablante)**")
        st.text_area("asr", a["texto_asr"], height=260, label_visibility="collapsed")
        if a["texto_referencia"]:
            st.markdown("**Comparación de modelos en este clip**")
            comparar = detalle[detalle["id"] == a["id"]][["modelo", "error", "rtf", "hipotesis"]]
            st.dataframe(comparar.rename(columns={"error": "WER", "rtf": "factor de tiempo real"})
                         .style.format({"WER": "{:.1%}", "factor de tiempo real": "{:.2f}"}),
                         hide_index=True, width="stretch")
            with st.expander("Transcripción manual (referencia)"):
                st.write(a["texto_referencia"])

# ───────────────────────────────────────────── evaluación
with pestanas[3]:
    st.markdown("Errores sobre las **mismas** muestras: 10 documentos y 10 clips del corpus, transcritos a mano. "
                "CER = errores por carácter; WER = errores por palabra; factor de tiempo real = segundos de cómputo "
                "por segundo de audio (CPU de una laptop).")
    columnas = ["modalidad", "modelo", "metrica", "error", "segundos_por_caso", "factor_tiempo_real", "parametros", "donde_corre"]
    st.dataframe(comparacion[columnas].style.format({"error": "{:.1%}", "segundos_por_caso": "{:.1f}", "factor_tiempo_real": "{:.2f}"}, na_rep="—"),
                 hide_index=True, width="stretch")
    izq, der = st.columns(2)
    por_tipo = detalle[detalle["metrica"] == "CER"].groupby(["modelo", "grupo"])["error"].mean().reset_index()
    fig = px.bar(por_tipo, x="grupo", y="error", color="modelo", barmode="group",
                 category_orders={"grupo": ["impreso", "foto", "manuscrito"]},
                 labels={"grupo": "Tipo de documento", "error": "CER medio", "modelo": "Modelo"},
                 title="Los manuscritos concentran los errores de OCR")
    izq.plotly_chart(fig.update_yaxes(tickformat=".0%"), width="stretch")
    por_cond = detalle[detalle["metrica"] == "WER"].groupby(["modelo", "grupo"])["error"].mean().reset_index()
    fig = px.bar(por_cond, x="grupo", y="error", color="modelo", barmode="group",
                 labels={"grupo": "Condición de grabación", "error": "WER medio", "modelo": "Modelo"},
                 title="WER por condición de grabación")
    der.plotly_chart(fig.update_yaxes(tickformat=".0%"), width="stretch")

    st.subheader("Auditoría humana de la extracción con LLM")
    st.markdown(f"**{auditoria['correcto'].astype(int).sum()} de {len(auditoria)}** extracciones completamente "
                "correctas (todos sus campos sustentados por el texto).")
    st.dataframe(auditoria, hide_index=True, width="stretch")

# ───────────────────────────────────────────── fuentes
with pestanas[4]:
    st.markdown("Todos los archivos vienen de Wikimedia Commons. La licencia y el autor de cada uno están abajo. "
                "Los textos publicados están seudonimizados: los nombres de personas privadas y los datos de contacto "
                "se reemplazaron por marcas como `[PERSONA_1]` o `[CORREO]`.")
    st.dataframe(fuentes, hide_index=True, width="stretch",
                 column_config={"fuente_url": st.column_config.LinkColumn("fuente_url")})
    descargar_csv(fuentes, "fuentes.csv", "dl_fuentes")
    st.markdown(f"**Seudonimización:** {cambios['reemplazos'].sum()} entidades reemplazadas en {cambios['id'].nunique()} textos.")
    st.dataframe(cambios.groupby("entidad")["reemplazos"].sum().reset_index(), hide_index=True)
