"""Servidor MCP de la Consulta Amigable del MEF: el presupuesto y el gasto de las entidades públicas del Perú.

    uv run pytest                                          # el contrato: las 9 pruebas deben pasar
    uv run server.py                                       # el servidor, por stdio
    claude mcp add --scope project mef -- uv run server.py # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: así cada cifra sale de una consulta que se puede repetir en la web.
"""
import html
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError

URL = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/130.0 Safari/537.36"}
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}
ANIO = date.today().year
PRIMER_ANIO = 2012

# El navegador guarda la consulta en la URL, con un número por dimensión: 0=&1=E&2=10&3= lista los pliegos del
# sector 10 del Gobierno Nacional. Un GET a esa URL devuelve la misma tabla que la web, sin iniciar sesión.
DIMENSIONES = {
    "nivel": ("1", "Nivel de gobierno: E nacional, R regional, M local"),
    "sector": ("2", "Sector del gobierno nacional o regional: 10 educación, 11 salud, 07 interior…"),
    "pliego": ("3", "Pliego: ministerio, gobierno regional, universidad u organismo. Su código se repite entre "
                    "sectores (el 010 es Educación y también la DINI): va con «sector»"),
    "ejecutora": ("4", "Unidad ejecutora, incluidas las municipalidades"),
    "municipalidad": ("7", "Municipalidad, con su ubigeo en el nombre"),
    "categoria_presupuestal": ("30", "Programa presupuestal, acciones centrales o APNOP"),
    "producto_proyecto": ("31", "Producto o proyecto de inversión"),
    "actividad_obra": ("32", "Actividad, acción de inversión u obra"),
    "funcion": ("8", "Función: 22 educación, 20 salud, 15 transporte…"),
    "division_funcional": ("33", "División funcional, dentro de una función"),
    "grupo_funcional": ("34", "Grupo funcional, dentro de una división"),
    "fuente": ("14", "Fuente de financiamiento: 1 recursos ordinarios, 2 directamente recaudados, 3 crédito, "
                     "4 donaciones y transferencias, 5 recursos determinados"),
    "rubro": ("15", "Rubro de financiamiento, más detallado que la fuente"),
    "generica": ("24", "Genérica de gasto: 5-2-1 personal, 5-2-3 bienes y servicios, 6-2-6 activos no "
                       "financieros…"),
    "subgenerica": ("25", "Subgenérica, dentro de una genérica"),
    "subgenerica_detalle": ("26", "Detalle de la subgenérica"),
    "departamento": ("21", "Departamento donde se gasta (la meta), no donde está la entidad"),
    "trimestre": ("22", "Trimestre: 1 a 4 (sin PIA ni PIM)"),
    "mes": ("23", "Mes: 1 a 12 (sin PIA ni PIM)"),
}
INCLUYE = {"todo": "ActProy", "actividades": "Actividad", "proyectos": "Proyecto"}
MONTOS = ["pia", "pim", "certificacion", "compromiso_anual", "atencion_compromiso_mensual", "devengado", "girado"]

mcp = FastMCP("mef", instructions=(
    "Presupuesto y gasto de las entidades públicas del Perú, de la Consulta Amigable del MEF (desde 2012, "
    "actualizada a diario; montos en soles). Primero ubica la entidad con buscar_entidad y usa tal cual los "
    "«filtros» que devuelve; luego usa resumen para "
    "totales y avance, evolucion para comparar años y consulta_amigable para cualquier otro desglose. No calcules "
    "a mano: cita el año, la entidad y la URL de cada cifra."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


def _texto(celda):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", celda))).replace("'", "").strip()


@lru_cache(maxsize=128)
def _consultar(ruta, anio, incluye):
    """Las filas de una consulta: el código para filtrar, el nombre, los montos en soles y el avance %."""
    url = f"{URL}?_uhc=yes&0=&{ruta}&y={anio}&ap={incluye}"
    for espera in (0, 2, 5):
        time.sleep(espera)
        try:
            pagina = httpx.get(url + "&cpage=1&psize=5000", headers=NAVEGADOR, timeout=120).text
        except httpx.HTTPError:
            continue
        if "DrpYear" in pagina:
            break
    else:
        raise ToolError(f"La Consulta Amigable no respondió. Esperen unos segundos y reintenten: {url}")
    if f'selected="selected" value="{anio}"' not in pagina:   # un año que no tiene, lo cambia en silencio por el actual
        raise ToolError(f"La Consulta Amigable no tiene el año {anio}.")
    filas = []
    for tr in re.findall(r'<tr[^>]*id="tr\d+".*?</tr>', pagina, re.S):
        celdas = [_texto(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        montos = [int(x.replace(",", "")) if x else None for x in celdas[2:9]]
        filas.append({"codigo": re.search(r'name="grp1" value="([^"/]*)', tr)[1].strip(), "nombre": celdas[1],
                      **dict(zip(MONTOS, montos)), "avance_pct": float(celdas[9]) if celdas[9] else None})
    return url, filas


def _filas(desglose, filtros=None, anio=ANIO, incluye="todo"):
    """Revisa los argumentos, arma la ruta de la URL y devuelve (url, filas)."""
    filtros = {k: str(v).strip() for k, v in (filtros or {}).items()}
    for d in [desglose, *filtros]:
        if d not in DIMENSIONES:
            raise ToolError(f"No existe la dimensión {d!r}. Usen una de: {', '.join(DIMENSIONES)}.")
    if desglose in filtros:
        raise ToolError(f"{desglose!r} no puede ser a la vez desglose y filtro.")
    if incluye not in INCLUYE:
        raise ToolError(f"incluye debe ser uno de: {', '.join(INCLUYE)}.")
    if not PRIMER_ANIO <= int(anio) <= ANIO:
        raise ToolError(f"La Consulta Amigable no tiene el año {anio}: hay datos de {PRIMER_ANIO} a {ANIO}.")
    pliego = filtros.get("pliego")
    if pliego and "sector" not in filtros and desglose != "sector":
        repetidos = _pliegos_repetidos(int(anio))
        if pliego in repetidos:   # sin el sector, la web suma todos los pliegos con ese código
            raise ToolError(f"El código de pliego {pliego} lo tienen {' y '.join(repetidos[pliego])}. Agreguen "
                            'el sector: usen los «filtros» que devuelve buscar_entidad(tipo="pliego").')
    ruta = "".join(f"{DIMENSIONES[k][0]}={v}&" for k, v in filtros.items()) + f"{DIMENSIONES[desglose][0]}="
    return _consultar(ruta, int(anio), INCLUYE[incluye])


def _pliegos_repetidos(anio):
    """Los códigos de pliego que tienen varios pliegos, de sectores distintos, con sus nombres."""
    _, filas = _filas("pliego", anio=anio)
    nombres = {}
    for f in filas:
        nombres.setdefault(f["codigo"], []).append(f["nombre"])
    return {c: n for c, n in nombres.items() if len(n) > 1}


def _sector_del_pliego(fila, anio):
    """El sector de un pliego de código repetido: la fila del desglose por sector con su mismo PIM y devengado."""
    _, sectores = _filas("sector", {"pliego": fila["codigo"]}, anio)
    return next((s["codigo"] for s in sectores if (s["pim"], s["devengado"]) == (fila["pim"], fila["devengado"])),
                None)


def _sumar(filas):
    """El total de un desglose. Suma montos redondeados, así que puede diferir en unos soles del de la web."""
    total = {m: sum(f[m] for f in filas) if filas and all(f[m] is not None for f in filas) else None
             for m in MONTOS}
    total["avance_pct"] = round(total["devengado"] / total["pim"] * 100, 1) if total["pim"] else None
    return total


def _sin_filas(filtros, anio):
    return ToolError(f"No hay datos para {filtros or 'el total'} en {anio}. Revisen los códigos: salen del "
                     "«codigo» de buscar_entidad o de una consulta anterior.")


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_entidad(texto: str, tipo: str = "ejecutora", anio: int = ANIO, limite: int = 10) -> list[dict]:
    """Busca una entidad pública por palabras del nombre y devuelve su código para usarlo en filtros.

    tipo: "ejecutora" (unidades ejecutoras, incluidas las municipalidades), "pliego" (ministerios, gobiernos
    regionales, universidades) o "municipalidad" (con su ubigeo). Ejemplos: "monterrico", "villa el salvador",
    "hospital loayza", "educacion", "san marcos". Los nombres del MEF abrevian: «M. DE EDUCACION», «U.N.».
    Devuelve código, nombre, PIM, devengado y avance % del año, de mayor a menor PIM, y los «filtros» que hay
    que pasar a las otras herramientas: un pliego cuyo código se repite en otro sector lleva también su sector.
    Si no hay resultados, prueben con menos palabras.
    """
    if tipo not in {"ejecutora", "pliego", "municipalidad"}:
        raise ToolError('tipo debe ser "ejecutora", "pliego" o "municipalidad".')
    _, filas = _filas(tipo, anio=anio)
    palabras = _sin_tildes(texto).split()
    sel = [f for f in filas if all(p in _sin_tildes(f["nombre"]) for p in palabras)]
    sel = sorted(sel, key=lambda f: f["pim"] or 0, reverse=True)[:limite]
    repetidos = _pliegos_repetidos(anio) if tipo == "pliego" else {}
    with ThreadPoolExecutor(4) as ex:
        sectores = list(ex.map(lambda f: _sector_del_pliego(f, anio) if f["codigo"] in repetidos else None, sel))
    return [{k: f[k] for k in ("codigo", "nombre", "pim", "devengado", "avance_pct")}
            | {"tipo": tipo, "filtros": ({"sector": s} if s else {}) | {tipo: f["codigo"]}}
            for f, s in zip(sel, sectores)]


@mcp.tool(annotations=SOLO_LECTURA)
def consulta_amigable(desglose: str, filtros: dict[str, str | int] | None = None, buscar: str | None = None,
                      anio: int = ANIO, incluye: str = "todo", ordenar_por: str | None = None,
                      limite: int = 30) -> dict:
    """Una tabla de la Consulta Amigable: PIA, PIM, certificación, compromiso, devengado y girado en soles, y
    avance % (devengado entre PIM), desglosados por una dimensión.

    Funciona como el navegador de la web: desglose es la dimensión que se lista y filtros fija otras, con el
    «codigo» de cada fila. Dimensiones: nivel, sector, pliego, ejecutora, municipalidad, categoria_presupuestal,
    producto_proyecto, actividad_obra, funcion, division_funcional, grupo_funcional, fuente, rubro, generica,
    subgenerica, subgenerica_detalle, departamento, trimestre y mes (el recurso mef://dimensiones las explica).

    Ejemplos:
      desglose="generica", filtros={"ejecutora": "77"}              → en qué gasta esa ejecutora
      desglose="mes", filtros={"municipalidad": "301291"}            → su gasto mes a mes
      desglose="sector", filtros={"nivel": "E"}, ordenar_por="pim"   → sectores del Gobierno Nacional
      desglose="pliego", filtros={"nivel": "R"}, ordenar_por="avance_pct" → gobiernos regionales
    buscar deja las filas cuyo nombre tiene todas esas palabras. ordenar_por: pia, pim, devengado o avance_pct,
    de mayor a menor. incluye: "todo", "actividades" o "proyectos". «total» suma todas las filas que cumplen
    buscar, aunque solo se muestren las primeras «limite». Por mes o trimestre no hay PIA ni PIM.
    """
    if ordenar_por and ordenar_por not in {"pia", "pim", "devengado", "avance_pct"}:
        raise ToolError("ordenar_por debe ser pia, pim, devengado o avance_pct.")
    url, filas = _filas(desglose, filtros, anio, incluye)
    if buscar:
        palabras = _sin_tildes(buscar).split()
        filas = [f for f in filas if all(p in _sin_tildes(f["nombre"]) for p in palabras)]
    if not filas:
        raise _sin_filas(filtros, anio)
    if ordenar_por:
        filas = sorted(filas, key=lambda f: f[ordenar_por] or 0, reverse=True)
    return {"anio": anio, "incluye": incluye, "desglose": desglose, "filtros": filtros or {},
            "filas_total": len(filas), "filas": filas[:limite], "total": _sumar(filas), "fuente": url}


def _total(filtros, anio, incluye):
    """El total de unos filtros, desglosando por una dimensión que no se esté filtrando."""
    desglose = next(d for d in ("nivel", "fuente", "funcion") if d not in (filtros or {}))
    url, filas = _filas(desglose, filtros, anio, incluye)
    return url, filas and _sumar(filas)


@mcp.tool(annotations=SOLO_LECTURA)
def resumen(filtros: dict[str, str | int] | None = None, anio: int = ANIO, incluye: str = "todo") -> dict:
    """Las cuentas del presupuesto de una entidad o grupo en un año, hechas en Python: PIA, PIM, certificación,
    devengado, girado y avance %, cuánto falta devengar, cuánto cambió el PIM respecto del PIA, el mes con más
    devengado y el avance de cada genérica, de la de menor avance a la de mayor. Úsenla siempre en vez de
    calcular a mano.

    filtros como en consulta_amigable, por ejemplo {"ejecutora": "77"} o {"nivel": "R"}; sin filtros es el
    total del Estado. En el año en curso el avance es solo hasta hoy.
    """
    url, total = _total(filtros, anio, incluye)
    if not total:
        raise _sin_filas(filtros, anio)
    t = total
    salida = {"anio": anio, "incluye": incluye, "filtros": filtros or {}, **t,
              "por_devengar": t["pim"] - t["devengado"], "certificado_sin_devengar": t["certificacion"] - t["devengado"],
              "pim_vs_pia_pct": round((t["pim"] / t["pia"] - 1) * 100, 1) if t["pia"] else None}
    fuentes = [url]
    if not {"mes", "trimestre"} & set(filtros or {}):
        url, meses = _filas("mes", filtros, anio, incluye)
        con_gasto = [m for m in meses if m["devengado"]]
        if con_gasto:
            mayor = max(con_gasto, key=lambda m: m["devengado"])
            salida["mes_mayor_devengado"] = {"mes": mayor["nombre"], "devengado": mayor["devengado"]}
            salida["devengado_promedio_mensual"] = round(sum(m["devengado"] for m in con_gasto) / len(con_gasto))
        fuentes.append(url)
    if "generica" not in (filtros or {}):
        url, genericas = _filas("generica", filtros, anio, incluye)
        salida["genericas"] = sorted(
            ({k: g[k] for k in ("codigo", "nombre", "pim", "devengado", "avance_pct")} for g in genericas if g["pim"]),
            key=lambda g: g["avance_pct"])
        fuentes.append(url)
    return salida | {"fuentes": fuentes}


@mcp.tool(annotations=SOLO_LECTURA)
def evolucion(filtros: dict[str, str | int] | None = None, desde: int = ANIO - 5, hasta: int = ANIO,
              incluye: str = "todo") -> dict:
    """PIA, PIM, devengado y avance % de una entidad o grupo año por año, con la variación del devengado
    respecto del año anterior. Úsenla para tendencias: «¿creció el gasto de X?», «¿en qué año ejecutó mejor?».

    filtros como en consulta_amigable, por ejemplo {"ejecutora": "77"}. desde y hasta son años, de 2012 al
    actual. El año en curso está incompleto: su devengado es solo hasta hoy. Los años sin datos se omiten.
    """
    if not PRIMER_ANIO <= desde <= hasta <= ANIO:
        raise ToolError(f"desde y hasta deben ir de {PRIMER_ANIO} a {ANIO}, con desde ≤ hasta.")
    with ThreadPoolExecutor(4) as ex:
        resultados = list(ex.map(lambda a: (a, *_total(filtros, a, incluye)), range(desde, hasta + 1)))
    anios, previo = [], None
    for anio, url, t in resultados:
        if not t:
            continue
        variacion = round((t["devengado"] / previo - 1) * 100, 1) if previo else None
        anios.append({"anio": anio, "pia": t["pia"], "pim": t["pim"], "devengado": t["devengado"],
                      "avance_pct": t["avance_pct"], "variacion_devengado_pct": variacion, "fuente": url})
        previo = t["devengado"]
    if not anios:
        raise _sin_filas(filtros, f"{desde}-{hasta}")
    return {"filtros": filtros or {}, "incluye": incluye, "anios": anios,
            "nota": f"{ANIO} va hasta hoy" if anios[-1]["anio"] == ANIO else ""}


@mcp.resource("mef://dimensiones")
def dimensiones() -> str:
    """Las dimensiones de la Consulta Amigable, para usar en desglose y filtros."""
    return "\n".join(f"- {nombre}: {descripcion}" for nombre, (_, descripcion) in DIMENSIONES.items())


@mcp.resource("mef://ejecutora/{codigo}")
def ficha_ejecutora(codigo: str) -> dict:
    """Ficha de una unidad ejecutora en el año en curso: nombre, nivel, sector, pliego y su presupuesto."""
    _, filas = _filas("ejecutora")
    fila = next((f for f in filas if f["codigo"] == codigo), None)
    if fila is None:
        raise ResourceError(f"No existe la ejecutora {codigo!r} en {ANIO}. Búsquenla con buscar_entidad.")
    ficha = {"codigo": codigo, "nombre": fila["nombre"], "anio": ANIO}
    for nivel in ("nivel", "sector", "pliego"):
        _, filas = _filas(nivel, {"ejecutora": codigo})
        nombres = [f["nombre"] for f in filas if "FICTICIO" not in f["nombre"]]
        if nombres:
            ficha[nivel] = nombres[0]
    return ficha | {k: fila[k] for k in ("pia", "pim", "devengado", "avance_pct")}


@mcp.prompt
def ejecucion_presupuestal(entidad: str, anio: str = str(ANIO)) -> str:
    """Reporte del presupuesto y el gasto de una entidad pública en un año."""
    return (f"Arma un reporte de la ejecución del gasto de «{entidad}» en {anio}. 1) Ubícala con buscar_entidad. "
            "2) Con resumen, da su PIA, PIM, certificación, devengado, avance % y cuánto falta devengar. 3) Señala "
            "las genéricas con menor avance y el mes con más devengado. 4) Con evolucion, compárala con los cuatro "
            "años anteriores. Usa los montos tal como los devuelve la herramienta, en soles, no hagas cuentas a mano "
            "y cita la URL de la Consulta Amigable de cada cifra.")


@mcp.prompt
def comparar_entidades(entidades: str, anio: str = str(ANIO)) -> str:
    """Compara el presupuesto y el avance de varias entidades públicas en un año."""
    return (f"Compara la ejecución del gasto en {anio} de: {entidades}. Ubica cada una con buscar_entidad y usa "
            "resumen para cada una. Presenta una tabla con PIA, PIM, devengado y avance %, ordenada por avance, y "
            "explica en tres viñetas quién ejecuta mejor y en qué genéricas se atrasan. Cita la URL de cada cifra.")


if __name__ == "__main__":
    mcp.run()
