"""El contrato del servidor: si estas pruebas pasan, Claude Code y evaluar.py pueden usarlo.

    uv run pytest -q

Llaman al servidor en memoria, igual que lo haría Claude Code, y piden datos reales a la Consulta Amigable.
Usan 2025, un año cerrado, para que las cifras no cambien de un día a otro.
"""
import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


async def _con_cliente(f):
    async with Client(mcp) as c:
        return await f(c)


def llamar(herramienta, **args):
    return asyncio.run(_con_cliente(lambda c: c.call_tool(herramienta, args))).data


def test_buscar_encuentra_monterrico():
    r = llamar("buscar_entidad", texto="monterrico", anio=2025)
    assert "77" in [x["codigo"] for x in r]
    assert {"codigo", "nombre", "pim", "devengado", "avance_pct"} <= r[0].keys()


def test_cuatro_herramientas_como_minimo():
    nombres = {t.name for t in asyncio.run(_con_cliente(lambda c: c.list_tools()))}
    assert {"buscar_entidad", "consulta_amigable", "resumen"} <= nombres
    assert len(nombres) >= 4, "falta la herramienta propia"


def test_consulta_por_generica():
    r = llamar("consulta_amigable", desglose="generica", filtros={"ejecutora": "77"}, anio=2025)
    assert r["filas_total"] == 5
    assert r["filas"][0]["codigo"] == "5-2-1"
    assert r["total"]["pim"] == 16_142_660 and r["total"]["devengado"] == 14_510_157   # Monterrico, 2025
    assert r["fuente"].startswith("https://apps5.mineco.gob.pe")


def test_consulta_por_mes():
    r = llamar("consulta_amigable", desglose="mes", filtros={"ejecutora": "77"}, anio=2025)
    assert len(r["filas"]) == 12
    assert r["filas"][0]["pia"] is None
    assert r["filas"][-1] == pytest.approx({**r["filas"][-1], "nombre": "12: Diciembre", "devengado": 2_352_067})


def test_resumen_sin_cuentas_a_mano():
    r = llamar("resumen", filtros={"ejecutora": "77"}, anio=2025)
    assert r["avance_pct"] == pytest.approx(89.9)
    assert r["por_devengar"] == 1_632_503
    assert r["pim_vs_pia_pct"] == pytest.approx(34.2)
    assert r["mes_mayor_devengado"]["mes"] == "12: Diciembre"
    assert r["genericas"][0]["codigo"] == "5-2-5"   # otros gastos: PIM de S/ 1,400 y nada devengado


def test_pliego_de_codigo_repetido():
    r = llamar("buscar_entidad", texto="m. de educacion", tipo="pliego", anio=2025)
    assert r[0]["filtros"] == {"sector": "10", "pliego": "010"}
    with pytest.raises(ToolError, match="INTELIGENCIA"):   # el 010 también es la DINI: sin sector, se suman
        llamar("resumen", filtros={"pliego": "010"}, anio=2025)
    assert llamar("resumen", filtros=r[0]["filtros"], anio=2025)["pim"] == 10_137_988_396


def test_errores_claros():
    with pytest.raises(ToolError, match="ministerio"):
        llamar("consulta_amigable", desglose="ministerio")
    with pytest.raises(ToolError, match="2030"):
        llamar("resumen", filtros={"ejecutora": "77"}, anio=2030)


def test_un_recurso():
    async def contar(c):
        return len(await c.list_resources()) + len(await c.list_resource_templates())
    assert asyncio.run(_con_cliente(contar)) >= 1


def test_un_prompt():
    assert len(asyncio.run(_con_cliente(lambda c: c.list_prompts()))) >= 1
