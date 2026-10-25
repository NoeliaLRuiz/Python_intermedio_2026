"""Funciones comunes de los dos notebooks: seudonimización y normalización para medir errores.

Los nombres reales que se reemplazan NO están en este archivo: se guardan en datos/raw/reemplazos.json,
que no se sube a GitHub. Aquí solo están las reglas y la lista de personajes públicos o históricos que se
mantienen a propósito (criterio explicado en 01_extraccion.ipynb, sección 6).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import voz

ARCHIVO_REEMPLAZOS = Path("datos/raw/reemplazos.json")       # generado por el NER + revisión humana
ARCHIVO_EXTRA = Path("datos/raw/reemplazos_extra.json")      # nombres que el NER no vio, agregados a mano

# Personajes públicos o históricos que aparecen en documentos de archivo: no se seudonimizan.
PUBLICOS = [
    "Ricardo Palma", "Miguel Grau", "Grau Seminario", "César Vallejo", "José María Eguren", "Felipe Santiago Salaverry",
    "Arturo Prat", "Carmela Carvajal", "Juan Velasco Alvarado", "Armando Robles Godoy", "José Olaya",
    "Simón Bolívar", "Bernardo de Tagle", "Torre Tagle", "San Martín", "Santa Cruz", "Juan de Salazar", "San Donás",
    "Manuel Prado", "Nazario Chávez Aliaga", "Segundo Ciro Gallardo", "Segundo Gallardo Gallo", "Carlos J. Bachmann", "Luis Antonio Eguiguren",
    "José Quiñones", "Quiñones", "Ernesto Burzagli", "José de la Riva Agüero", "Riva Agüero", "Ramón Freire",
    "Agustín Gamarra", "Domingo Tristán", "Miguel de San Román", "Nicolás de Piérola", "Juan de Arona",
    "Manuel Rodríguez Cuadros", "César Gaviria", "José Bernardo de Tagle", "Lapadula", "Gianluca Lapadula", "Dios", "Jesús", "Cristo",
    "Virgen", "Santísima Trinidad", "Tayta Palli", "Taitapalli", "Stallone", "Superman", "Pisco", "Capón", "Fénix", "Nazarenas", "Carmelitas",
]

# Datos de contacto e identificación: siempre se reemplazan.
PATRONES = {
    "[CORREO]": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "[TELEFONO]": r"(?<!\d)9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)",
    "[DNI]": r"(?i)\bDNI\b\W{0,3}\d{8}",
    "[DIRECCION]": r"(?:Prolongación|Prolongacion|Av\.|Avenida|Jr\.|Jirón|Calle)\s+[\w.]+(?:\s+[\w.]+){0,4}\s+\d{1,5}\b",
}


# Palabras que el NER confunde con nombres: títulos, cargos y tratamientos. Al inicio de un nombre se quitan
# ('Don Ricardo Palma' -> 'Ricardo Palma'); un candidato hecho solo de estas palabras se descarta.
TITULOS = {"don", "doña", "dona", "señor", "senor", "señora", "senora", "señorita", "senorita", "sr", "sra", "srta",
           "dr", "dra", "prof", "profesor", "profesora", "general", "ministro", "presidente", "director", "directora",
           "teniente", "alcalde", "alcaldesa", "regidor", "regidora", "capitán", "capitan", "coronel", "excmo",
           "estado", "plenipotenciario", "libertad", "s", "e", "v", "su", "de", "del", "la"}


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def limpiar_nombre(nombre: str) -> str:
    "Quita títulos y tratamientos al inicio del nombre: 'Señorita ANA PÉREZ' -> 'ANA PÉREZ'."
    palabras = nombre.replace("-", " ").replace(".", " ").split()      # 'Jean-Pierre' cuenta como dos palabras
    while palabras and palabras[0].lower() in TITULOS:
        palabras = palabras[1:]
    return " ".join(palabras)


def parece_nombre(nombre: str, en_documento: bool) -> bool:
    """Filtra falsos positivos del NER. En documentos (OCR con ruido) se exige nombre y apellido; en audios,
    donde todas las personas son privadas, también cuenta un nombre de pila suelto ('Carlos')."""
    palabras = nombre.split()
    if not palabras or all(p.lower() in TITULOS for p in palabras) or sum(len(p) for p in palabras) < 4:
        return False
    return len(palabras) >= 2 or not en_documento


def es_publico(nombre: str) -> bool:
    """True si el nombre es un personaje público o histórico de la lista: el nombre completo, una parte de dos
    o más palabras, el apellido final ('Palma'), o un texto que contiene el nombre completo. También acepta
    lecturas con errores del OCR ('Rioardo Palme', 'Simón Belivar'). Un nombre de pila suelto ('Juan') no basta:
    podría ser una persona privada."""
    from rapidfuzz import fuzz
    c = _sin_tildes(limpiar_nombre(nombre)).split()
    if not c:
        return False
    for publico in PUBLICOS:
        p = _sin_tildes(publico).split()
        if any(c[k:k + len(p)] == p for k in range(len(c) - len(p) + 1)):
            return True
        for i in range(len(p) - len(c) + 1):
            trozo = p[i:i + len(c)]
            if (len(c) >= 2 or i + len(c) == len(p)) and fuzz.ratio(" ".join(c), " ".join(trozo)) >= 80:
                return True
    return False


def cargar_reemplazos() -> dict[str, str]:
    "Diccionario nombre real -> seudónimo (archivo privado) más los agregados a mano."
    reemplazos = json.loads(ARCHIVO_REEMPLAZOS.read_text(encoding="utf-8")) if ARCHIVO_REEMPLAZOS.exists() else {}
    if ARCHIVO_EXTRA.exists():
        for nombre in json.loads(ARCHIVO_EXTRA.read_text(encoding="utf-8")):
            if nombre not in reemplazos:
                reemplazos[nombre] = f"[PERSONA_{len(set(reemplazos.values())) + 1}]"
    return reemplazos


def seudonimizar(texto: str, reemplazos: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Cambia nombres (comparación difusa de voz.seudonimizar) y datos de contacto (expresiones regulares).

    Devuelve el texto nuevo y cuántos reemplazos hizo de cada tipo ('PERSONA', 'CORREO', ...).
    Los nombres más largos van primero para que 'Isabel Vásquez' se cambie entero antes que 'Isabel'.
    """
    conteo: dict[str, int] = {}
    for nombre in sorted(reemplazos, key=len, reverse=True):
        seudonimo = reemplazos[nombre]
        nuevo = voz.seudonimizar(texto, {nombre: seudonimo})
        n = nuevo.count(seudonimo) - texto.count(seudonimo)
        if n > 0:
            conteo["PERSONA"] = conteo.get("PERSONA", 0) + n
        texto = nuevo
    for etiqueta, patron in PATRONES.items():
        texto, n = re.subn(patron, etiqueta, texto)
        if n:
            conteo[etiqueta.strip("[]")] = conteo.get(etiqueta.strip("[]"), 0) + n
    return texto, conteo


def para_medir(texto: str) -> str:
    """Normalización común para CER y WER: sin marcas de hablante ni seudónimos, minúsculas, sin puntuación
    y con un solo espacio entre palabras (voz.normalizar). Las tildes se mantienen."""
    texto = re.sub(r"\[(HABLANTE|PERSONA)_\d+\]|\[(CORREO|TELEFONO|DNI|DIRECCION)\]", " ", str(texto))
    return voz.normalizar(texto.replace("\n", " "))
