"""Paso 1 del reel: arma el prompt para el modelo y revisa el guion que devuelve.

Uso:
    python guion.py --texto ../reto-c-incendios/README.md --solo-prompt > prompt.txt
    python guion.py --texto ../reto-c-incendios/README.md --respuesta respuesta_qwen.txt --modelo qwen

El modelo devuelve el guion como JSON, escena por escena. Este script lo valida y marca con ¡¡
toda cifra que no aparece tal cual en el texto. Las afirmaciones las revisa una persona.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROMPT = """Eres guionista de reels de divulgación. Convierte el TEXTO de abajo en el guion de un reel vertical
de 45 a 55 segundos, narrado en español del Perú, en primera persona, por quien hizo el trabajo.

Reglas:
1. Usa solo hechos que estén en el TEXTO. No agregues datos, causas, comparaciones ni adjetivos que el texto
   no diga. Si el texto da una cifra con una advertencia (por ejemplo, que es una estimación), conserva la advertencia.
2. Seis escenas. Cada escena tiene una sola idea y una sola cifra.
3. "frase" es lo que se dice en voz alta: de 14 a 24 palabras, con los números escritos en palabras.
4. "cifra" es lo que se ve en pantalla: cópiala exactamente como aparece en el TEXTO (con su unidad: ha, %, km, S/).
5. "etiqueta" explica la cifra en 3 a 7 palabras.
6. La primera escena engancha con una pregunta o un dato; la última dice de dónde vienen los datos.
7. Escribe además tres posts para acompañar el reel: uno para Instagram (hasta 600 caracteres, con 3 a 5 hashtags),
   uno para X (hasta 270 caracteres) y uno para LinkedIn (hasta 900 caracteres). Ninguno exagera lo que dice el TEXTO.

Responde solo con JSON válido, sin texto antes ni después, con esta forma:
{{
  "titulo": "…",
  "escenas": [
    {{"frase": "…", "cifra": "…", "etiqueta": "…"}}
  ],
  "posts": {{"instagram": "…", "x": "…", "linkedin": "…"}}
}}

TEXTO:
<<<
{texto}
>>>
"""

NUMERO = re.compile(r"\d[\d\s.,]*\d|\d")


def leer_texto(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(ruta).pages)
    else:
        texto = ruta.read_text(encoding="utf-8")
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto)          # imágenes de markdown
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)      # enlaces: deja solo el texto
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)         # bloques de código
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def numeros(texto):
    """Números del texto sin separadores de miles ni decimales: '90 376' y '90,376' dan '90376'."""
    return {re.sub(r"[\s.,]", "", n) for n in NUMERO.findall(texto)}


def extraer_json(respuesta):
    respuesta = re.sub(r"^```(?:json)?|```$", "", respuesta.strip(), flags=re.M).strip()
    inicio, fin = respuesta.find("{"), respuesta.rfind("}")
    return json.loads(respuesta[inicio:fin + 1])


def revisar(guion, texto):
    del_texto = numeros(texto)
    avisos = []
    for i, e in enumerate(guion["escenas"], 1):
        for campo in ("frase", "cifra", "etiqueta"):
            if not str(e.get(campo, "")).strip():
                avisos.append(f"Escena {i}: falta «{campo}»")
        faltan = [n for n in NUMERO.findall(e.get("cifra", "") + " " + e.get("etiqueta", ""))
                  if re.sub(r"[\s.,]", "", n) not in del_texto]
        if faltan:
            e["cifra"] = "¡¡" + e["cifra"]
            avisos.append(f"Escena {i}: {', '.join(faltan)} no aparece tal cual en el texto")
        if re.search(r"\d", e.get("frase", "")):
            avisos.append(f"Escena {i}: la frase tiene dígitos; se leerán como palabras al narrar")
        palabras = len(e.get("frase", "").split())
        if not 10 <= palabras <= 30:
            avisos.append(f"Escena {i}: la frase tiene {palabras} palabras")
    for red, maximo in [("instagram", 600), ("x", 270), ("linkedin", 900)]:
        post = guion.get("posts", {}).get(red, "")
        if not post:
            avisos.append(f"Falta el post de {red}")
        elif len(post) > maximo:
            avisos.append(f"El post de {red} tiene {len(post)} caracteres (máximo {maximo})")
        faltan = [n for n in NUMERO.findall(post) if re.sub(r"[\s.,]", "", n) not in del_texto]
        if faltan:
            avisos.append(f"Post de {red}: {', '.join(faltan)} no aparece tal cual en el texto")
    total = sum(len(e.get("frase", "").split()) for e in guion["escenas"])
    return avisos, total


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--texto", required=True, help="texto largo (.md, .txt o .pdf)")
    p.add_argument("--solo-prompt", action="store_true", help="imprime el prompt para pegarlo en un chat")
    p.add_argument("--respuesta", help="archivo con lo que respondió el modelo")
    p.add_argument("--modelo", default="modelo", help="nombre corto para el archivo de salida (qwen, deepseek…)")
    a = p.parse_args()

    texto = leer_texto(a.texto)
    if a.solo_prompt:
        print(PROMPT.format(texto=texto))
        return
    if not a.respuesta:
        p.error("falta --respuesta (o usa --solo-prompt)")

    guion = extraer_json(Path(a.respuesta).read_text(encoding="utf-8"))
    avisos, palabras = revisar(guion, texto)
    salidas = Path("salidas")
    salidas.mkdir(exist_ok=True)
    destino = salidas / f"guion_{a.modelo}.json"
    destino.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{guion.get('titulo', '(sin título)')} · {len(guion['escenas'])} escenas · {palabras} palabras "
          f"(unos {palabras / 2.6:.0f} s de voz)\n")
    for i, e in enumerate(guion["escenas"], 1):
        print(f"{i}. [{e['cifra']} · {e['etiqueta']}]\n   {e['frase']}\n")
    print("Avisos automáticos:" if avisos else "Sin avisos automáticos.")
    for aviso in avisos:
        print("  -", aviso)
    print(f"\nGuardado en {destino}. Las cifras se revisan con código; las afirmaciones, contra el texto.")


if __name__ == "__main__":
    main()
